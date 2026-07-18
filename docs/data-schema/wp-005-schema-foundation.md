<!-- === TASK:WP-005:START === -->
# WP-005 Supabase Schema Foundation

## Scope

Migration `202607180001_wp005_initial_schema.sql` establishes the MVP Pilot persistence foundation. RLS policies, connectivity and retention-job execution are intentionally deferred to WP-006.

## Canonical table groups

| Domain | Tables | Contract alignment |
|---|---|---|
| Knowledge and content | `knowledge_domains`, `knowledge_chunks`, `content_drafts`, `content_versions`, `content_conflicts` | `KnowledgeChunkDTO`, content workflow and conflict DTOs |
| Emergency | `emergency_keyword_sets`, `emergency_protocols`, `emergency_events` | `EmergencyEventReceiptDTO`, approved protocol/keyword data |
| Conversation | `conversation_sessions`, `conversation_messages` | `SessionDTO`, `MessageDTO`, `EmergencyContextDTO` |
| Appointment | `departments`, `doctors`, `schedules`, `appointments` | `AppointmentDTO`, booking/status flows |
| Feedback and operations | `feedback`, `analytics_events`, `audit_events` | feedback, analytics and immutable emergency/security/content audit requirements |

## Data boundaries

- `appointments` is the only MVP table group storing patient identity fields.
- Conversation, feedback, analytics and audit tables use `*_redacted` or structured metadata; raw PII must not be written there.
- Knowledge retrieval filters `knowledge_chunks` by `is_active` and approved status. Embeddings are internal and never public DTO fields.
- New appointments default to `pending`; a schedule can have at most one appointment.

## Retention fields

`expires_at` is stored on session, conversation, appointment, feedback, emergency, analytics and audit records to support the approved Pilot retention windows. Enforcement job and RLS are not part of this migration.

## Migration requirements

- Supabase PostgreSQL must have `pgcrypto` and `vector` extensions available.
- The original WP-005 migration used `vector(768)`. It is superseded for the Pilot by WP-008 migration `202607180004_wp008_jina_embedding_dimension.sql`, which upgrades an empty knowledge index to `vector(1024)` for Jina `jina-embeddings-v5-text-small`. Existing non-null vectors must be explicitly re-embedded; the compatibility migration must stop rather than silently discard them.
- Apply on an empty database before seed import/indexing work in WP-008.
<!-- === TASK:WP-005:END === -->
