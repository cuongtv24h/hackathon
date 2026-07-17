-- === TASK:WP-006:START ===
-- Database connectivity, RLS and retention controls.
-- This migration is applied on top of the WP-005 schema baseline. It does NOT
-- modify table shapes, columns or domain constraints. It only declares roles,
-- row-level security policies, a full-access demo role for local development,
-- service-to-service boundaries, and retention helpers that the WP-006 Python
-- adapter orchestrates.

-- ----------------------------------------------------------------------------
-- 1. Roles
-- ----------------------------------------------------------------------------
-- Three production roles are introduced:
--   - hospital_chat_anon  : the anonymous end user of the chat widget/page.
--                          May insert their own conversation session/message
--                          rows and read back only what they just wrote.
--   - hospital_content    : the content_admin / domain_owner / emergency_approver
--                          role that manages knowledge, content lifecycle and
--                          emergency configuration.
--   - hospital_audit_ro   : the security_auditor / operations_analyst role that
--                          reads audit, analytics, emergency and feedback data
--                          but cannot mutate state.
-- A fourth role, hospital_full_demo, is a local-dev convenience that mirrors
-- the full access surface; it MUST remain inactive in production deployments.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'hospital_chat_anon') then
    create role hospital_chat_anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'hospital_content') then
    create role hospital_content nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'hospital_audit_ro') then
    create role hospital_audit_ro nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'hospital_full_demo') then
    create role hospital_full_demo nologin;
  end if;
end
$$;

-- ----------------------------------------------------------------------------
-- 2. Enable RLS on every MVP table (schema owned by WP-005)
-- ----------------------------------------------------------------------------
alter table knowledge_domains            enable row level security;
alter table knowledge_chunks             enable row level security;
alter table content_drafts               enable row level security;
alter table content_versions             enable row level security;
alter table content_conflicts            enable row level security;
alter table emergency_keyword_sets       enable row level security;
alter table emergency_protocols          enable row level security;
alter table emergency_events             enable row level security;
alter table conversation_sessions        enable row level security;
alter table conversation_messages        enable row level security;
alter table departments                  enable row level security;
alter table doctors                      enable row level security;
alter table schedules                    enable row level security;
alter table appointments                 enable row level security;
alter table feedback                     enable row level security;
alter table analytics_events             enable row level security;
alter table audit_events                 enable row level security;

-- ----------------------------------------------------------------------------
-- 3. Helper: the application tags every row write with the actor supplied by
--    the API layer. The chat role can only see rows that match its tag.
-- ----------------------------------------------------------------------------
create or replace function hospital_actor_tag()
returns text
language sql
stable
as $$
  select coalesce(
    current_setting('hospital.actor', true),
    'service'
  );
$$;

-- ----------------------------------------------------------------------------
-- 4. Knowledge domain / chunk / draft / version / conflict policies
-- ----------------------------------------------------------------------------
drop policy if exists kd_read_active  on knowledge_domains;
create policy kd_read_active on knowledge_domains
  for select to hospital_chat_anon
  using (true);

drop policy if exists kd_manage on knowledge_domains;
create policy kd_manage on knowledge_domains
  for all to hospital_content
  using (true) with check (true);

drop policy if exists kc_read_active on knowledge_chunks;
create policy kc_read_active on knowledge_chunks
  for select to hospital_chat_anon
  using (is_active = true and approval_status in ('approved_for_pilot', 'approved'));

drop policy if exists kc_manage on knowledge_chunks;
create policy kc_manage on knowledge_chunks
  for all to hospital_content
  using (true) with check (true);

drop policy if exists cd_manage on content_drafts;
create policy cd_manage on content_drafts
  for all to hospital_content
  using (true) with check (true);

drop policy if exists cv_manage on content_versions;
create policy cv_manage on content_versions
  for all to hospital_content
  using (true) with check (true);

drop policy if exists cc_manage on content_conflicts;
create policy cc_manage on content_conflicts
  for all to hospital_content
  using (true) with check (true);

-- ----------------------------------------------------------------------------
-- 5. Emergency configuration
-- ----------------------------------------------------------------------------
drop policy if exists eks_manage on emergency_keyword_sets;
create policy eks_manage on emergency_keyword_sets
  for all to hospital_content
  using (true) with check (true);

drop policy if exists ep_manage on emergency_protocols;
create policy ep_manage on emergency_protocols
  for all to hospital_content
  using (true) with check (true);

drop policy if exists ee_audit_read on emergency_events;
create policy ee_audit_read on emergency_events
  for select to hospital_audit_ro
  using (true);

drop policy if exists ee_service_write on emergency_events;
create policy ee_service_write on emergency_events
  for insert to hospital_chat_anon
  with check (detection_path in ('keyword', 'llm_tool'));

-- ----------------------------------------------------------------------------
-- 6. Conversation sessions / messages — chat user is bound to a session_id
-- ----------------------------------------------------------------------------
drop policy if exists cs_self_rw on conversation_sessions;
create policy cs_self_rw on conversation_sessions
  for all to hospital_chat_anon
  using (metadata ->> 'actor_tag' = hospital_actor_tag())
  with check (metadata ->> 'actor_tag' = hospital_actor_tag());

drop policy if exists cm_self_rw on conversation_messages;
create policy cm_self_rw on conversation_messages
  for all to hospital_chat_anon
  using (
    session_id in (
      select session_id from conversation_sessions
      where metadata ->> 'actor_tag' = hospital_actor_tag()
    )
  )
  with check (
    session_id in (
      select session_id from conversation_sessions
      where metadata ->> 'actor_tag' = hospital_actor_tag()
    )
  );

drop policy if exists cs_audit_read on conversation_sessions;
create policy cs_audit_read on conversation_sessions
  for select to hospital_audit_ro
  using (true);

drop policy if exists cm_audit_read on conversation_messages;
create policy cm_audit_read on conversation_messages
  for select to hospital_audit_ro
  using (true);

-- ----------------------------------------------------------------------------
-- 7. Reference data: departments, doctors, schedules
-- ----------------------------------------------------------------------------
drop policy if exists dep_read on departments;
create policy dep_read on departments
  for select to hospital_chat_anon
  using (is_active = true);

drop policy if exists dep_manage on departments;
create policy dep_manage on departments
  for all to hospital_content
  using (true) with check (true);

drop policy if exists doc_read on doctors;
create policy doc_read on doctors
  for select to hospital_chat_anon
  using (is_active = true);

drop policy if exists doc_manage on doctors;
create policy doc_manage on doctors
  for all to hospital_content
  using (true) with check (true);

drop policy if exists sch_read on schedules;
create policy sch_read on schedules
  for select to hospital_chat_anon
  using (status = 'available');

drop policy if exists sch_manage on schedules;
create policy sch_manage on schedules
  for all to hospital_content
  using (true) with check (true);

-- ----------------------------------------------------------------------------
-- 8. Appointments — the chat role can only read/write appointments whose
--    patient_phone matches the actor tag (used as opaque patient scope).
-- ----------------------------------------------------------------------------
drop policy if exists ap_self_rw on appointments;
create policy ap_self_rw on appointments
  for all to hospital_chat_anon
  using (patient_phone = hospital_actor_tag())
  with check (patient_phone = hospital_actor_tag());

drop policy if exists ap_audit_read on appointments;
create policy ap_audit_read on appointments
  for select to hospital_audit_ro
  using (true);

-- ----------------------------------------------------------------------------
-- 9. Feedback, analytics, audit — audit role reads, chat role writes its own
-- ----------------------------------------------------------------------------
drop policy if exists fb_self_write on feedback;
create policy fb_self_write on feedback
  for insert to hospital_chat_anon
  with check (true);

drop policy if exists fb_audit_read on feedback;
create policy fb_audit_read on feedback
  for select to hospital_audit_ro
  using (true);

drop policy if exists ae_audit_read on analytics_events;
create policy ae_audit_read on analytics_events
  for select to hospital_audit_ro
  using (true);

drop policy if exists ae_self_write on analytics_events;
create policy ae_self_write on analytics_events
  for insert to hospital_chat_anon
  with check (true);

drop policy if exists auv_audit_read on audit_events;
create policy auv_audit_read on audit_events
  for select to hospital_audit_ro
  using (true);

drop policy if exists auv_service_write on audit_events;
create policy auv_service_write on audit_events
  for insert to hospital_content
  with check (true);

-- ----------------------------------------------------------------------------
-- 10. Full-access demo role (local development only)
-- ----------------------------------------------------------------------------
-- Grants on tables to the demo role. The Python adapter reads the
-- HOSPITAL_FULL_DEMO_ROLE_ENABLED flag and refuses to grant/activate the role
-- unless the value is exactly 'true' AND APP_ENV is 'development'.
grant usage on schema public to hospital_full_demo;
grant select, insert, update, delete on all tables    in schema public to hospital_full_demo;
grant usage, select                  on all sequences in schema public to hospital_full_demo;
grant execute                         on all functions in schema public to hospital_full_demo;

-- ----------------------------------------------------------------------------
-- 11. Retention helpers
-- ----------------------------------------------------------------------------
-- These views expose the row counts that the WP-006 retention sweeper reads.
-- The sweeper itself lives in apps/api/foundation/database/retention.py and is
-- driven by the canonical retention periods declared in
-- docs/artifacts/interface/interface-guidelines.md (INT-09):
--   - context 30 min idle / 24h max
--   - anonymized conversation 90 days
--   - feedback 180 days
--   - mock appointment 90 days
--   - emergency/security/content audit and aggregate analytics 365 days
create or replace view v_retention_overdue_sessions as
  select session_id, last_activity_at, expires_at
    from conversation_sessions
   where expires_at < now();

create or replace view v_retention_overdue_messages as
  select message_id, session_id, created_at, expires_at
    from conversation_messages
   where expires_at < now();

create or replace view v_retention_overdue_appointments as
  select appointment_id, created_at, expires_at
    from appointments
   where expires_at < now();

create or replace view v_retention_overdue_feedback as
  select feedback_id, created_at, expires_at
    from feedback
   where expires_at < now();

create or replace view v_retention_overdue_analytics as
  select analytics_event_id, occurred_at, expires_at
    from analytics_events
   where expires_at < now();

create or replace view v_retention_overdue_audit as
  select audit_event_id, occurred_at, expires_at
    from audit_events
   where expires_at < now();

-- The sweeper calls these functions; they are intentionally narrow.
create or replace function fn_delete_overdue_sessions()
returns integer
language plpgsql
as $$
declare
  deleted_count integer;
begin
  delete from conversation_sessions where expires_at < now();
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

create or replace function fn_delete_overdue_messages()
returns integer
language plpgsql
as $$
declare
  deleted_count integer;
begin
  delete from conversation_messages where expires_at < now();
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

create or replace function fn_delete_overdue_appointments()
returns integer
language plpgsql
as $$
declare
  deleted_count integer;
begin
  delete from appointments where expires_at < now();
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

create or replace function fn_delete_overdue_feedback()
returns integer
language plpgsql
as $$
declare
  deleted_count integer;
begin
  delete from feedback where expires_at < now();
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

create or replace function fn_delete_overdue_analytics()
returns integer
language plpgsql
as $$
declare
  deleted_count integer;
begin
  delete from analytics_events where expires_at < now();
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

create or replace function fn_delete_overdue_audit()
returns integer
language plpgsql
as $$
declare
  deleted_count integer;
begin
  delete from audit_events where expires_at < now();
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

grant execute on function fn_delete_overdue_sessions()     to hospital_content;
grant execute on function fn_delete_overdue_messages()    to hospital_content;
grant execute on function fn_delete_overdue_appointments() to hospital_content;
grant execute on function fn_delete_overdue_feedback()    to hospital_content;
grant execute on function fn_delete_overdue_analytics()    to hospital_content;
grant execute on function fn_delete_overdue_audit()       to hospital_content;
grant execute on function fn_delete_overdue_sessions()     to hospital_full_demo;
grant execute on function fn_delete_overdue_messages()    to hospital_full_demo;
grant execute on function fn_delete_overdue_appointments() to hospital_full_demo;
grant execute on function fn_delete_overdue_feedback()    to hospital_full_demo;
grant execute on function fn_delete_overdue_analytics()    to hospital_full_demo;
grant execute on function fn_delete_overdue_audit()       to hospital_full_demo;
-- === TASK:WP-006:END ===
