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
- The baseline migration starts with `vector(768)` for migration-history compatibility; after the complete supported migration sequence, the canonical MVP dimension is `vector(1024)`.
- Apply on an empty database before seed import/indexing work in WP-008.

## Hybrid Search and Jina Profile Additions

- **Vector Profile Upgrade:** Migration `004` establishes hybrid-search readiness; migration `005` sets the final column to `vector(1024)` for Jina `jina-embeddings-v5-text-small`. The cosine index uses IVFFlat with cosine operations.
- **Full-Text Search (FTS):** The generated column `search_document` concatenated from `content`, `sub_topic`, `source_id`, and `source_path` is indexed via a `GIN` index (`knowledge_chunks_search_document_idx`) using the PostgreSQL `simple` text-search configuration.
- **Clean-Install Ordering:**
  1. `202607180001_wp005_initial_schema.sql` (baseline schema)
  2. `202607180004_wp005_hybrid_search.sql` (additive migration)
  3. `202607180005_wp005_jina_1024_profile.sql` (canonical Jina profile)
- **Forward-Rollback Guidance:** Dimension migrations fail closed when embeddings exist. Switching profile requires re-embedding and a new forward migration; never edit applied migration history.
<!-- === TASK:WP-005:END === -->
