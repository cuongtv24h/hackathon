# Phase 5/6 Runtime Correction

## Decision

Tài liệu này thay thế mọi hướng dẫn trái ngược trong Phase 5, Phase 6 và packet được sinh trước ngày correction. Architecture binding vẫn là: Python/FastAPI cho backend và Vite/React/TypeScript cho frontend.

## Runtime Boundary

| Zone | Runtime | Source files | Test command | Forbidden |
|---|---|---|---|---|
| `apps/api/`, `apps/mock_his/`, `packages/contracts/` | Python/FastAPI | `.py`, package `snake_case` | `py -m pytest ... -q` | `.ts`, `.tsx`, hyphenated Python package names |
| `apps/chat-web/`, `apps/admin-web/` | Vite/React/TypeScript | `.ts`, `.tsx`, `.css`, JSON config | `npm run test` | `.py`, `__init__.py`, pytest-only acceptance |
| `tests/unit/`, `tests/integration/`, `tests/contract/` | Python backend/data | `test_*.py` | `py -m pytest ... -q` | UI rendering claims |
| frontend colocated test | Vitest/RTL | `*.test.ts`, `*.test.tsx` | `npm run test` | provider/network calls |
| browser E2E | Playwright | `*.spec.ts` | `npm run test:e2e` | replacing component tests |

`__init__.py` may only declare a Python package or re-export a small public surface. Business logic belongs in a leaf module such as `service.py`, `repository.py`, `router.py`, `provider.py` or `handler.py`.

## New Prerequisite Work Packages

### WP-010 — Backend Runtime Scaffold & Package Normalization

- Owner: API; size: M; dependency: WP-009.
- Creates FastAPI application scaffold, Python package conventions and import validation.
- Establishes snake_case code paths. Capability names remain kebab-case only in API URLs and documentation.
- All backend WPs from WP-101 through WP-404 require WP-010 acceptance evidence before dispatch.
- Existing generated `__init__.py` logic is preserved on a recovery branch and ported to leaf modules by the owning WP; it must not be merged as final package structure.

### WP-500 — Frontend Runtime Scaffold & Test Harness

- Owner: FE; size: M; dependency: WP-009.
- Creates independent Vite/React/TypeScript scaffolds for chat and admin applications, plus Vitest/React Testing Library.
- All frontend WPs WP-501 through WP-506 require WP-500 acceptance evidence before dispatch.
- Existing Python files inside frontend zones are behavior references only; they are not frontend deliverables and must not be merged into the final frontend applications.

## Exact Frontend Output Contract

| WP | Required leaf files |
|---|---|
| WP-500 | `apps/chat-web/package.json`, `apps/chat-web/tsconfig.json`, `apps/chat-web/vite.config.ts`, `apps/chat-web/src/main.tsx`, `apps/chat-web/src/App.tsx`, `apps/chat-web/src/test/setup.ts`, `apps/admin-web/package.json`, `apps/admin-web/tsconfig.json`, `apps/admin-web/vite.config.ts`, `apps/admin-web/src/main.tsx`, `apps/admin-web/src/App.tsx`, `apps/admin-web/src/test/setup.ts` |
| WP-501 | `apps/chat-web/src/shared/ChatClient.ts`, `apps/chat-web/src/shared/SSEClient.ts`, `apps/chat-web/src/widget/WidgetShell.tsx`, `apps/chat-web/src/standalone/StandaloneShell.tsx`, matching `*.test.tsx` files |
| WP-502 | `apps/chat-web/src/features/information-assistance/InformationResponse.tsx`, `InformationResponse.test.tsx` |
| WP-503 | `apps/chat-web/src/features/appointments/AppointmentFlow.tsx`, `AppointmentFlow.test.tsx` |
| WP-504 | `apps/chat-web/src/features/emergency-safety/EmergencyBanner.tsx`, `EmergencyBanner.test.tsx` |
| WP-505 | `apps/admin-web/src/features/content-management/ContentManagementPage.tsx`, `ContentManagementPage.test.tsx` |
| WP-506 | `apps/admin-web/src/features/analytics-audit/AnalyticsAuditPage.tsx`, `AnalyticsAuditPage.test.tsx` |

## Backend Leaf-Module Contract

Each backend WP must create at least one named leaf module in its owned `snake_case` zone and a pytest companion. `__init__.py` is optional and may only export that leaf module's public API. Hyphenated directories created by previous agents must be replaced by the equivalent `snake_case` directory before standard imports are accepted.

## Packet Regeneration Rule

1. Packets WP-010 and WP-500 are new and must be issued first.
2. Packets WP-101–WP-404 must be regenerated with `WP-010` dependency, Python leaf-file outputs and pytest only.
3. Packets WP-501–WP-506 must be regenerated with `WP-500` dependency, exact TypeScript/TSX outputs and `npm run test`; remove pytest as their completion test.
4. QA packets WP-602–WP-606 must be regenerated to require Vitest/Playwright evidence for frontend behavior in addition to relevant pytest evidence.
5. Packets already implemented under the old policy are not rerun blindly. Create a normalization/port fix on the owning branch, preserve behavior, then retire the obsolete Python frontend file after its TypeScript test passes.

## Merge Gates

- Reject a `.py` file under `apps/chat-web/` or `apps/admin-web/`.
- Reject a TypeScript frontend packet without `package.json`, Vite/TypeScript config and passing `npm run test`.
- Reject a backend package whose only substantive implementation is in `__init__.py`.
- Reject imports relying on a hyphenated Python package directory.
- Require `py -m pytest` for backend changes and `npm run test` for frontend changes; neither replaces the other where a capability spans both runtimes.
