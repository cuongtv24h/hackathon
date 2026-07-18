"""Generate R1 GitHub Project packets after the Python/React runtime correction."""

from pathlib import Path
import yaml


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "prompts" / "reissues" / "r1" / "task-packets"

FILES = {
    "WP-101": ["apps/api/foundation/session/service.py", "apps/api/foundation/configuration/service.py", "apps/api/foundation/feedback/service.py", "tests/unit/test_wp_101_foundation_session.py"],
    "WP-102": ["apps/api/foundation/knowledge/repository/service.py", "apps/api/foundation/knowledge/content/service.py", "tests/integration/test_wp_102_knowledge_content.py"],
    "WP-103": ["apps/api/foundation/emergency/service.py", "apps/api/capabilities/emergency/protocols/service.py", "tests/unit/test_wp_103_emergency_foundation.py"],
    "WP-104": ["apps/api/foundation/appointments/service.py", "apps/mock_his/app.py", "tests/integration/test_wp_104_appointments.py"],
    "WP-105": ["apps/api/logging/conversation/service.py", "apps/api/logging/audit/service.py", "apps/api/foundation/analytics/service.py", "tests/integration/test_wp_105_analytics_logging.py"],
    "WP-201": ["apps/api/ai/rag/search_tool.py", "tests/unit/test_wp_201_knowledge_search.py"],
    "WP-202": ["apps/api/capabilities/emergency/prefilter/tool.py", "tests/unit/test_wp_202_emergency_prefilter.py"],
    "WP-203": ["apps/api/foundation/appointments/tools/service.py", "tests/integration/test_wp_203_appointment_tools.py"],
    "WP-204": ["apps/api/ai/guardrails/privacy/service.py", "apps/api/logging/conversation/tool_adapter.py", "tests/unit/test_wp_204_privacy_logging.py"],
    "WP-301": ["apps/api/ai/providers/llm_provider.py", "apps/api/ai/providers/embedding_provider.py", "tests/unit/test_wp_301_ai_provider.py"],
    "WP-302": ["apps/api/ai/orchestrator/core/service.py", "apps/api/ai/guardrails/service.py", "tests/unit/test_wp_302_ai_orchestration.py"],
    "WP-303": ["apps/api/ai/orchestrator/information_assistance/pipeline.py", "tests/integration/test_wp_303_information_assistance.py"],
    "WP-304": ["apps/api/ai/orchestrator/emergency_safety/pipeline.py", "tests/integration/test_wp_304_emergency_safety.py"],
    "WP-305": ["apps/api/ai/orchestrator/appointment_booking/pipeline.py", "tests/integration/test_wp_305_appointment_booking.py"],
    "WP-306": ["apps/api/ai/orchestrator/appointment_status/pipeline.py", "tests/integration/test_wp_306_appointment_status.py"],
    "WP-401": ["apps/api/gateway/capabilities/information_assistance/router.py", "tests/contract/test_wp_401_information_assistance.py"],
    "WP-402": ["apps/api/gateway/capabilities/emergency_safety/router.py", "tests/contract/test_wp_402_emergency_safety.py"],
    "WP-403": ["apps/api/gateway/capabilities/appointment_booking/router.py", "tests/contract/test_wp_403_appointment_booking.py"],
    "WP-404": ["apps/api/gateway/capabilities/appointment_status/router.py", "tests/contract/test_wp_404_appointment_status.py"],
    "WP-501": ["apps/chat-web/src/shared/ChatClient.ts", "apps/chat-web/src/shared/SSEClient.ts", "apps/chat-web/src/widget/WidgetShell.tsx", "apps/chat-web/src/widget/WidgetShell.test.tsx", "apps/chat-web/src/standalone/StandaloneShell.tsx", "apps/chat-web/src/standalone/StandaloneShell.test.tsx"],
    "WP-502": ["apps/chat-web/src/features/information-assistance/InformationResponse.tsx", "apps/chat-web/src/features/information-assistance/InformationResponse.test.tsx"],
    "WP-503": ["apps/chat-web/src/features/appointments/AppointmentFlow.tsx", "apps/chat-web/src/features/appointments/AppointmentFlow.test.tsx"],
    "WP-504": ["apps/chat-web/src/features/emergency-safety/EmergencyBanner.tsx", "apps/chat-web/src/features/emergency-safety/EmergencyBanner.test.tsx"],
    "WP-505": ["apps/admin-web/src/features/content-management/ContentManagementPage.tsx", "apps/admin-web/src/features/content-management/ContentManagementPage.test.tsx"],
    "WP-506": ["apps/admin-web/src/features/analytics-audit/AnalyticsAuditPage.tsx", "apps/admin-web/src/features/analytics-audit/AnalyticsAuditPage.test.tsx"],
    "WP-601": ["tests/contract/test_wp_601_data_contracts.py", "tests/data_validation/test_wp_601_seed_contracts.py"],
    "WP-602": ["apps/chat-web/src/e2e/information-assistance.spec.ts", "tests/integration/test_wp_602_information_assistance.py"],
    "WP-603": ["apps/chat-web/src/e2e/emergency-safety.spec.ts", "tests/integration/test_wp_603_emergency_safety.py"],
    "WP-604": ["apps/chat-web/src/e2e/appointments.spec.ts", "tests/integration/test_wp_604_appointments.py"],
    "WP-605": ["apps/admin-web/src/e2e/admin-dashboard.spec.ts", "tests/integration/test_wp_605_admin_dashboard.py"],
    "WP-606": ["tests/nfr/test_wp_606_release_gate.py", "tests/release/test_wp_606_vps_release.py", "config/deployment/release_gate.yaml"],
}


def sprint_wave(wp_id):
    group = int(wp_id.split("-")[1]) // 100
    return {1: (1, 2), 2: (2, 3), 3: (2, 4), 4: (2, 5), 5: (2, 6), 6: (3, 7)}[group]


def frontend(wp_id):
    return wp_id.startswith("WP-5")


def qa_frontend(wp_id):
    return wp_id in {"WP-602", "WP-603", "WP-604", "WP-605", "WP-606"}


def build_packet(wp):
    wp_id = wp["id"]
    sprint, wave = sprint_wave(wp_id)
    revision_id = wp_id + "-R1"
    paths = FILES[wp_id]
    test_paths = [path for path in paths if path.startswith("tests/") or path.endswith(".test.tsx") or path.endswith(".spec.ts")]
    is_frontend = frontend(wp_id)
    backend_needed = not is_frontend or qa_frontend(wp_id)
    frontend_needed = is_frontend or qa_frontend(wp_id)
    commands = []
    if backend_needed:
        commands.append("py -m pytest " + " ".join(path for path in test_paths if path.endswith(".py")) + " -q")
    if frontend_needed:
        app = "apps/admin-web" if wp_id in {"WP-505", "WP-506", "WP-605"} else "apps/chat-web"
        commands.append("npm.cmd --prefix " + app + " run test -- --run")
    if qa_frontend(wp_id):
        commands.append("npm.cmd --prefix apps/chat-web run test:e2e")
    files = "\n".join("- `" + path + "`" for path in paths)
    deps = wp.get("dependencies", []) + (["WP-010"] if 101 <= int(wp_id.split("-")[1]) <= 404 else []) + (["WP-500"] if is_frontend else [])
    deps = list(dict.fromkeys(deps))
    dep_lines = "\n".join("- `" + dep + "` must be Stable/Done or have approved integration evidence." for dep in deps)
    runtime = "Vite/React/TypeScript only; do not create Python files under frontend apps." if is_frontend else "Python/FastAPI only; substantive behavior must be in named snake_case leaf modules, never only in __init__.py."
    test_contract = "\n".join("- `" + command + "`" for command in commands)
    return f'''---
task_id: {revision_id}
work_package: {wp_id}
title: "{wp['title']} — Runtime-corrected reissue"
sprint: {sprint}
wave: {wave}
pool: {wp['owner_pool']}
priority: P1
layer: {wp['layer']}
branch: task/{revision_id}
column: Prompt Backlog
labels: [wp:{wp_id}, revision:r1, supersedes:legacy, pool:{wp['owner_pool'].lower()}, wave:{wave}, sprint:{sprint}]
input_documents:
  - docs/reference-packs/work-packages/{wp_id.lower()}.pack.md
  - docs/5-6-runtime-correction.md
  - docs/spec-registry/runtime-test-policy.yaml
  - docs/spec-registry/reissue-r1-task-to-file-contract-map.yaml
---

# [{revision_id}] {wp['title']}

## Purpose

Runtime-corrected reissue of canonical work package `{wp_id}`. The legacy packet is superseded and must not be dispatched.

## Dependencies

{dep_lines}

## Output File Contract

{files}

## Required Test Contract

{test_contract}

## Builder Prompt

```prompt
You are the Builder Agent for {revision_id}, the R1 reissue of {wp_id}.

MANDATORY READ
1. docs/reference-packs/work-packages/{wp_id.lower()}.pack.md
2. docs/5-6-runtime-correction.md
3. docs/spec-registry/runtime-test-policy.yaml
4. docs/spec-registry/reissue-r1-task-to-file-contract-map.yaml
5. docs/reference-packs/document-reference-policy.md

Read only material relevant to {wp_id}. {runtime}
Create or update only the listed output files. Add exact TASK:{wp_id}:START and END markers using the language-appropriate comment syntax; strict JSON uses x-task-region-markers. Do not redesign architecture or public contracts, create secrets, or edit unrelated work-package zones.

Testing is mandatory. Run every command in Required Test Contract and report exact commands/results. Use mocks/fakes for provider and network calls. Do not claim completion based only on a manual smoke check.

Return only summary, changed paths, automated test evidence, and blockers.
```

## Acceptance Criteria

- [ ] Every listed file is created or updated with the correct task marker.
- [ ] Implementation follows the corrected runtime boundary and has no legacy Python frontend artifact.
- [ ] Tests cover a successful path, contract shape and at least one error or edge case.
- [ ] Every required automated command passes, or a blocker is explicitly documented.
- [ ] Legacy `{wp_id}` packet is not used for implementation.
'''


def main():
    with open(ROOT / "docs/spec-registry/work-package-map.yaml", encoding="utf-8") as handle:
        work_packages = yaml.safe_load(handle)["work_packages"]
    OUT.mkdir(parents=True, exist_ok=True)
    index = {"version": "r1", "packets": []}
    for wp in work_packages:
        if wp["id"] not in FILES:
            continue
        packet_id = wp["id"] + "-R1"
        path = OUT / (packet_id + ".packet.md")
        path.write_text(build_packet(wp), encoding="utf-8")
        index["packets"].append({"id": packet_id, "work_package": wp["id"], "file": str(path.relative_to(ROOT)).replace("\\", "/"), "supersedes": "legacy " + wp["id"]})
    registry = OUT.parent / "registry.yaml"
    registry.write_text(yaml.safe_dump(index, allow_unicode=True, sort_keys=False), encoding="utf-8")
    contracts = {
        "version": "r1",
        "supersedes": "legacy task-to-file contract entries for WP-101 through WP-606",
        "work_packages": [],
    }
    for wp in work_packages:
        if wp["id"] not in FILES:
            continue
        contracts["work_packages"].append({
            "id": wp["id"] + "-R1",
            "canonical_work_package": wp["id"],
            "owner_pool": wp["owner_pool"],
            "files": [
                {"path": path, "operation": "CREATE", "region": "{TASK:" + wp["id"] + "}"}
                for path in FILES[wp["id"]]
            ],
        })
    contract_path = ROOT / "docs/spec-registry/reissue-r1-task-to-file-contract-map.yaml"
    contract_path.write_text(yaml.safe_dump(contracts, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print("generated=%d" % len(index["packets"]))


if __name__ == "__main__":
    main()
