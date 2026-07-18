"""Supabase persistence for operational MVP data.

This is the production repository used by runtime composition.  It keeps raw
PII out of analytics by accepting only already-redacted conversation content.
"""

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


class OperationalRepository:
    def __init__(self, database_url):
        if not database_url:
            raise ValueError("DATABASE_URL is required for operational persistence")
        self._database_url = database_url

    @contextmanager
    def _cursor(self):
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(self._database_url, row_factory=dict_row, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()

    def create_session(self, external_session_id, channel, metadata=None):
        metadata = dict(metadata or {})
        metadata["external_session_id"] = external_session_id
        with self._cursor() as cursor:
            cursor.execute(
                """insert into conversation_sessions (channel, metadata)
                   values (%s, %s::jsonb) returning session_id::text, started_at::text, expires_at::text""",
                [channel, json.dumps(metadata)],
            )
            return cursor.fetchone()

    def get_session_context(self, external_session_id):
        """Return the persisted, redacted session context or ``None``.

        Session-only state is deliberately kept in the session metadata rather
        than copied into analytics tables.  The public service owns its DTO
        shape; this repository only stores the opaque, already-safe payload.
        """
        with self._cursor() as cursor:
            cursor.execute(
                """select session_id::text, channel, metadata, started_at::text, expires_at::text
                     from conversation_sessions
                    where metadata->>'external_session_id' = %s and expires_at > now()""",
                [external_session_id],
            )
            return cursor.fetchone()

    def update_session_context(self, external_session_id, metadata):
        with self._cursor() as cursor:
            cursor.execute(
                """update conversation_sessions set metadata=%s::jsonb, last_activity_at=now()
                     where metadata->>'external_session_id' = %s and expires_at > now()
                     returning session_id::text, channel, metadata, started_at::text, expires_at::text""",
                [json.dumps(metadata), external_session_id],
            )
            return cursor.fetchone()

    def append_message(self, external_session_id, role, content_redacted, *, intent=None,
                       tools_called=None, citations=None, emergency_triggered=False,
                       detection_path=None):
        with self._cursor() as cursor:
            cursor.execute(
                """insert into conversation_messages
                     (session_id, role, content_redacted, intent, tools_called, citations, emergency_triggered, detection_path)
                   select session_id, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s
                     from conversation_sessions
                    where metadata->>'external_session_id' = %s
                   returning message_id::text, created_at::text""",
                [role, content_redacted, intent, json.dumps(tools_called or []), json.dumps(citations or []),
                 emergency_triggered, detection_path, external_session_id],
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("session not found")
            return row

    def create_feedback(self, external_session_id, rating, comment_redacted, category=None, metadata=None):
        with self._cursor() as cursor:
            cursor.execute(
                """insert into feedback (session_id, rating, comment_redacted, category, metadata)
                   select session_id, %s, %s, %s, %s::jsonb from conversation_sessions
                    where metadata->>'external_session_id' = %s
                   returning feedback_id::text, created_at::text""",
                [rating, comment_redacted, category, json.dumps(metadata or {}), external_session_id],
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("session not found")
            return row

    def feedback_by_id(self, feedback_id):
        with self._cursor() as cursor:
            cursor.execute("""select feedback_id::text, coalesce(session.metadata->>'external_session_id', '') session_id,
                              rating, comment_redacted, category, metadata, created_at::text from feedback
                              left join conversation_sessions session using (session_id) where feedback_id=%s::uuid""", [feedback_id])
            return cursor.fetchone()

    def feedback_by_session(self, external_session_id):
        with self._cursor() as cursor:
            cursor.execute("""select feedback_id::text, %s session_id, rating, comment_redacted, category, metadata, created_at::text
                              from feedback join conversation_sessions session using (session_id)
                              where session.metadata->>'external_session_id'=%s order by created_at desc""",
                           [external_session_id, external_session_id])
            return list(cursor.fetchall())

    def write_audit(self, category, actor, entity_type, action, payload=None):
        with self._cursor() as cursor:
            cursor.execute(
                """insert into audit_events (event_category, actor_reference, entity_type, action, payload_redacted)
                   values (%s, %s, %s, %s, %s::jsonb) returning audit_event_id::text, occurred_at::text""",
                [category, actor, entity_type, action, json.dumps(payload or {})],
            )
            return cursor.fetchone()

    def history(self, limit=50, offset=0):
        with self._cursor() as cursor:
            cursor.execute(
                """select message_id::text, coalesce(session.metadata->>'external_session_id', session.session_id::text) session_id,
                          session.channel, message.role, message.content_redacted, coalesce(message.intent, '') intent,
                          message.tools_called, message.emergency_triggered, message.created_at::text
                     from conversation_messages message join conversation_sessions session using (session_id)
                    order by message.created_at desc limit %s offset %s""", [limit, offset])
            items = list(cursor.fetchall())
            cursor.execute("select count(*) count from conversation_messages")
            return {"items": items, "total": cursor.fetchone()["count"]}

    def conversation_history(self, external_session_id, limit=50, offset=0, from_time=None, to_time=None):
        clauses = ["session.metadata->>'external_session_id' = %s"]
        values = [external_session_id]
        if from_time:
            clauses.append("message.created_at >= %s::timestamptz")
            values.append(from_time)
        if to_time:
            clauses.append("message.created_at <= %s::timestamptz")
            values.append(to_time)
        where_clause = " and ".join(clauses)
        with self._cursor() as cursor:
            cursor.execute(
                f"""select message_id::text turn_id, coalesce(session.metadata->>'external_session_id', session.session_id::text) session_id,
                           message.role, message.content_redacted content, message.intent, message.tools_called tool_calls,
                           message.citations, message.emergency_triggered, message.created_at::text
                      from conversation_messages message join conversation_sessions session using (session_id)
                     where {where_clause} order by message.created_at desc limit %s offset %s""",
                values + [limit, offset],
            )
            items = list(cursor.fetchall())
            cursor.execute(
                f"""select count(*) count from conversation_messages message
                      join conversation_sessions session using (session_id) where {where_clause}""", values)
            return {"items": items, "total": cursor.fetchone()["count"]}

    def audit_log(self, event_type=None, actor=None, limit=50, offset=0, from_time=None, to_time=None):
        clauses, values = ["true"], []
        if event_type:
            clauses.append("action = %s")
            values.append(event_type)
        if actor:
            clauses.append("actor_reference = %s")
            values.append(actor)
        if from_time:
            clauses.append("occurred_at >= %s::timestamptz")
            values.append(from_time)
        if to_time:
            clauses.append("occurred_at <= %s::timestamptz")
            values.append(to_time)
        where_clause = " and ".join(clauses)
        with self._cursor() as cursor:
            cursor.execute(
                f"""select audit_event_id::text audit_id, action event_type, coalesce(actor_reference, '') actor,
                           entity_type resource, payload_redacted details, occurred_at::text
                      from audit_events where {where_clause} order by occurred_at desc limit %s offset %s""",
                values + [limit, offset],
            )
            items = list(cursor.fetchall())
            cursor.execute(f"select count(*) count from audit_events where {where_clause}", values)
            return {"items": items, "total": cursor.fetchone()["count"]}

    def analytics_summary(self, from_time, to_time):
        with self._cursor() as cursor:
            cursor.execute("""select count(distinct session_id) conversations, count(*) turns,
                              coalesce(avg(case when intent = 'fallback' then 1.0 else 0.0 end), 0) fallback_rate,
                              coalesce(avg(case when emergency_triggered then 1.0 else 0.0 end), 0) emergency_rate
                              from conversation_messages where created_at between %s::timestamptz and %s::timestamptz""",
                           [from_time, to_time])
            summary = cursor.fetchone()
            cursor.execute("""select coalesce(avg(rating), 0) score from feedback
                              where created_at between %s::timestamptz and %s::timestamptz""", [from_time, to_time])
            summary["feedback_score"] = float(cursor.fetchone()["score"])
            cursor.execute("""select intent, count(*) count from conversation_messages
                              where role='user' and intent is not null and created_at between %s::timestamptz and %s::timestamptz
                              group by intent order by count desc limit 10""", [from_time, to_time])
            summary["top_questions"] = list(cursor.fetchall())
            return summary

    def dashboard(self):
        with self._cursor() as cursor:
            cursor.execute("select count(*) total_conversations from conversation_sessions")
            conversations = cursor.fetchone()["total_conversations"]
            cursor.execute("select count(*) emergency_events from emergency_events")
            emergency = cursor.fetchone()["emergency_events"]
            cursor.execute("select count(*) unresolved_conflicts from content_conflicts where state in ('open','investigating')")
            conflicts = cursor.fetchone()["unresolved_conflicts"]
            cursor.execute("select coalesce(avg(rating), 0) feedback_score from feedback")
            feedback = float(cursor.fetchone()["feedback_score"])
            cursor.execute("""select coalesce(intent, 'unknown') intent, count(*) count
                              from conversation_messages where intent is not null group by intent order by count desc limit 10""")
            top_intents = list(cursor.fetchall())
            return {"total_conversations": conversations, "emergency_events": emergency,
                    "unresolved_conflicts": conflicts, "feedback_score": feedback,
                    "top_intents": top_intents, "generated_at": datetime.now(timezone.utc).isoformat()}

    def conflicts(self):
        with self._cursor() as cursor:
            cursor.execute("""select conflict_id::text, source_chunk_ids, conflicting_fields, due_at::text, state,
                              coalesce(resolution_note, '') resolution_note, coalesce(resolved_by, '') resolved_by,
                              resolved_at::text from content_conflicts order by due_at asc""")
            return list(cursor.fetchall())

    def resolve_conflict(self, conflict_id, state, note, actor):
        with self._cursor() as cursor:
            cursor.execute("""update content_conflicts set state=%s, resolution_note=%s, resolved_by=%s,
                              resolved_at=now() where conflict_id=%s::uuid and state in ('open','investigating')
                              returning conflict_id::text, state, resolved_at::text""", [state, note, actor, conflict_id])
            row = cursor.fetchone()
            if not row:
                raise ValueError("open conflict not found")
            return row

    def content_draft(self, operation, *args):
        """Repository callable consumed by ``ContentManagementService``."""
        if operation == "create":
            data = args[0]
            metadata = {key: data.get(key, "") for key in ("sub_topic", "source_id", "source_section", "source_page", "tags", "author", "reviewer", "rejection_reason")}
            with self._cursor() as cursor:
                cursor.execute("""insert into content_drafts (domain_id, content_after, expected_version, state, changed_by, metadata)
                    select domain_id, %s, %s, 'draft', %s, %s::jsonb from knowledge_domains where domain_code=%s
                    returning draft_id::text""", [data["content"], "draft", data.get("author") or "demo-admin", json.dumps(metadata), data["domain"]])
                row = cursor.fetchone()
                if not row: raise ValueError("unknown content domain")
                return self.content_draft("get", row["draft_id"])
        if operation == "get":
            with self._cursor() as cursor:
                cursor.execute("""select draft.draft_id::text, draft.content_after content, domain.domain_code domain,
                    coalesce(draft.metadata->>'sub_topic','') sub_topic, coalesce(draft.metadata->>'source_id','') source_id,
                    coalesce(draft.metadata->>'source_section','') source_section, coalesce(draft.metadata->>'source_page','') source_page,
                    coalesce(draft.expected_version,'draft') version, draft.state status, draft.changed_by author,
                    coalesce(draft.approved_by,'') reviewer, coalesce(draft.metadata->>'rejection_reason','') rejection_reason,
                    draft.created_at::text, draft.updated_at::text, coalesce(draft.metadata->'tags','[]'::jsonb) tags
                    from content_drafts draft join knowledge_domains domain using(domain_id) where draft_id=%s::uuid""", [args[0]])
                return cursor.fetchone()
        if operation == "patch":
            draft_id, updates = args
            existing = self.content_draft("get", draft_id)
            if not existing: return None
            metadata = {"sub_topic": updates.get("sub_topic", existing["sub_topic"]), "source_id": existing["source_id"], "source_section": updates.get("source_section", existing["source_section"]), "source_page": updates.get("source_page", existing["source_page"]), "tags": updates.get("tags", existing["tags"]), "author": existing["author"]}
            with self._cursor() as cursor:
                cursor.execute("update content_drafts set content_after=%s, metadata=%s::jsonb, updated_at=now() where draft_id=%s::uuid", [updates.get("content", existing["content"]), json.dumps(metadata), draft_id])
            return self.content_draft("get", draft_id)
        if operation == "submit":
            draft_id, author = args
            with self._cursor() as cursor: cursor.execute("update content_drafts set state='submitted', changed_by=%s, updated_at=now() where draft_id=%s::uuid", [author or "demo-admin", draft_id])
            return self.content_draft("get", draft_id)
        if operation == "review":
            draft_id, reviewer, approved, reason = args
            with self._cursor() as cursor:
                cursor.execute("update content_drafts set state=%s, approved_by=%s, metadata=metadata || %s::jsonb, updated_at=now() where draft_id=%s::uuid", ["approved" if approved else "rejected", reviewer, json.dumps({"rejection_reason": reason}), draft_id])
            return self.content_draft("get", draft_id)
        if operation == "publish":
            draft_id, publisher = args
            with self._cursor() as cursor:
                cursor.execute("update content_drafts set state='published', published_at=now(), approved_by=%s, updated_at=now() where draft_id=%s::uuid returning source_chunk_id::text, content_after, published_at::text", [publisher or "demo-admin", draft_id])
                row = cursor.fetchone()
                if not row or not row["source_chunk_id"]: raise ValueError("draft must be linked to an existing knowledge chunk before publishing")
                cursor.execute("insert into content_versions (chunk_id, content_before, content_after, changed_by, approved_by, source_version) select chunk_id, content, %s, %s, %s, source_version from knowledge_chunks where chunk_id=%s::uuid", [row["content_after"], publisher or "demo-admin", publisher or "demo-admin", row["source_chunk_id"]])
                return {"chunk_id": row["source_chunk_id"], "version": "published", "published_at": row["published_at"], "publisher": publisher}
        raise ValueError("unknown content draft operation")
