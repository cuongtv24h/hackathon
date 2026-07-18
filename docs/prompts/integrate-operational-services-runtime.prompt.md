# Builder Prompt — Runtime Operational Persistence Integration

## Mission

Wire the already-completed Supabase-backed operational services into the real
FastAPI capability request flow. A normal MVP request must persist its session
context and anonymized history; feedback, analytics and audit must use the
same `OperationalRepository`. Do not leave these services available only as
unused library code.

## Mandatory Read

1. `apps/api/main.py`
   - Application lifespan and current capability pipeline composition.
2. `apps/api/foundation/operational_repository.py`
   - Canonical Supabase repository surface. Extend this file only when a
     required persistence operation is missing.
3. `apps/api/foundation/session/service.py`
4. `apps/api/logging/conversation/service.py`
5. `apps/api/foundation/feedback/service.py`
6. `apps/api/logging/audit/service.py`
7. `apps/api/foundation/analytics/service.py`
   - These services already select `OperationalRepository` when injected or
     when `DATABASE_URL` is configured. Preserve their public DTOs.
8. `apps/api/gateway/capabilities/information_assistance/router.py`
9. `apps/api/gateway/capabilities/emergency_safety/router.py`
10. `apps/api/gateway/capabilities/appointment_booking/router.py`
11. `apps/api/gateway/capabilities/appointment_status/router.py`
12. `docs/artifacts/architecture/integration-data-flow.md`
13. `docs/artifacts/interface/data-contracts.md`
14. `docs/artifacts/interface/interface-guidelines.md`
15. `tests/unit/test_operational_service_repositories.py`

## Scope

Implement only runtime integration and the tests required to prove it.

Allowed production areas:

- `apps/api/main.py`
- `apps/api/core/` (a named leaf module is preferred for runtime wiring)
- `apps/api/gateway/capabilities/`
- `apps/api/foundation/operational_repository.py` only if a missing method is
  necessary
- `tests/integration/` and `tests/unit/`

Do not modify public capability endpoint paths, API DTO schemas, RAG retrieval
contracts, LLM fallback behavior, Mock HIS contract, migration files, frontend
files, or source seed data. Do not commit secrets or log `DATABASE_URL`.

## Required Runtime Behavior

### 1. Shared composition

- In FastAPI lifespan, instantiate exactly one shared `OperationalRepository`
  from `DATABASE_URL` and construct shared Session, ConversationLog, Feedback,
  Audit, History and Analytics services with that repository.
- Store this composition on application state or an explicit runtime container;
  do not create a new database repository per capability request.
- If `DATABASE_URL` is missing, API startup must report the operational
  persistence dependency as unavailable. It must not silently substitute an
  in-memory repository in MVP runtime.
- Test injection must remain possible without a real database.

### 2. Session lifecycle

- For every capability request, ensure the supplied `session_id` has a
  persistent session before writing logs. If it does not exist, create it
  using only safe client context (`web_page`/`web_widget`, locale/timezone)
  and a non-identifying actor tag such as `anonymous`.
- Do not store browser fingerprints, phone numbers, patient names or raw user
  message content in session metadata.
- Preserve the existing 30-minute idle / 24-hour maximum policy.

### 3. Conversation history and analytics

- Before capability execution, append one redacted `user` turn.
- After a successful capability response, append one redacted `assistant`
  turn including intent/capability, tool names, citation metadata and emergency
  flag where applicable.
- The write path must use `ConversationLogService`, not direct SQL from a
  router.
- Analytics must be derived from persisted messages/events, not an in-memory
  mirror.
- Non-emergency conversation-log failure may be reported internally and must
  not replace a valid user response; never expose DB details to the client.

### 4. Audit and emergency requirements

- Persist an audit entry for emergency trigger, appointment create attempt,
  appointment create success/failure, and content-conflict resolution.
- Emergency audit is security-critical: preserve the architecture’s synchronous
  audit expectation and return the existing safe emergency response if the
  audit write is unavailable; do not log raw emergency text or patient PII.
- Map event category to the allowed schema values: `emergency`, `security`,
  or `content`.

### 5. Feedback/history/admin consistency

- Ensure FeedbackService, ConversationHistoryService and AnalyticsService used
  by runtime/admin are constructed with the same repository instance.
- Existing admin routes must continue to return aggregate/redacted data only.

## Error and Privacy Rules

- Use the existing unified error behavior. No raw psycopg exception, SQL,
  database URL, provider key, patient name, phone or full unredacted content
  may appear in API responses or logs.
- Do not create an in-memory fallback when `DATABASE_URL` is set and a
  repository write fails.
- The PII redaction service must run before every persisted conversation
  message and feedback comment.

## Required Tests

Add/update automated pytest coverage. Use fakes for `OperationalRepository`;
do not write test data to the Pilot Supabase database.

At minimum prove:

1. Lifespan creates one shared runtime composition from injected test settings.
2. PC-01 creates/ensures a session and writes redacted user + assistant rows
   with citation metadata.
3. PC-02 writes an emergency audit event without raw input text.
4. PC-03 writes audit evidence for confirmed appointment creation and retains
   idempotency behavior.
5. PC-04 persists redacted history without additional PII fields.
6. Repository failure does not silently write to memory; ordinary logging is
   non-blocking, and emergency behavior follows the safe/audited policy.
7. Existing capability contract tests remain green.

Run and report exact results:

```powershell
py -m pytest tests/unit/test_operational_service_repositories.py tests/integration/test_mvp_runtime_composition.py tests/contract/test_wp_401_information_assistance.py tests/contract/test_wp_402_emergency_safety.py tests/contract/test_wp_403_appointment_booking.py tests/contract/test_wp_404_appointment_status.py -q
```

Run any newly added runtime integration test explicitly as well.

## Acceptance Criteria

- [ ] Runtime creates one shared Supabase operational composition.
- [ ] All four capability paths ensure session persistence and use the shared
      services.
- [ ] Persisted conversation and feedback content is redacted before write.
- [ ] PC-01 citation metadata, PC-02 emergency audit, PC-03 booking audit and
      PC-04 history evidence are test-proven.
- [ ] No runtime fallback to in-memory storage occurs when `DATABASE_URL` is
      configured.
- [ ] Existing contracts remain unchanged and all required pytest commands
      pass.
- [ ] No secrets, SQL details or raw PII are exposed.

## Response Format

Do not paste code. Return only:

1. Summary
2. Changed paths
3. Runtime persistence mapping by capability
4. Automated test evidence
5. Known limitations/blockers
