# Document Reference Policy

## 1. Document Hierarchy

- Tầng 1 — Source Docs: human-facing, long-form. Hiện gồm `docs/3.architecture-design.md` và `docs/4.interface-design.md`.
- Tầng 2 — Normalized Artifacts: machine-friendly, single-concern under `docs/artifacts/`.
- Tầng 3 — Spec Registries: YAML indexes under `docs/spec-registry/`.
- Tầng 4 — Reference Packs: execution-ready capability summaries under `docs/reference-packs/`.

## 2. Who Reads What

- Builder Agent: Reference Packs primary; Artifact Files secondary.
- Reviewer Agent: Artifact Files + Reference Packs.
- Audit Agent: Artifact Files; Source Docs only when trace verification is needed.
- Human Lead: Source Docs + Registries.

## 3. Reference Rules for Builder Prompts

### Rule 1 — No direct source doc references by default

Builder prompts reference Packs or Artifacts. Source docs are read only when explicitly required by lead or an artifact is marked INCOMPLETE.

### Rule 2 — Always use file paths

Always use an addressable path such as `docs/artifacts/interface/data-contracts.md`. Never use an abstract reference such as “Phase 4 / Artifact 4”.

### Rule 3 — Separate mandatory and optional

Every builder prompt distinguishes:

- MANDATORY READ: must read before starting.
- OPTIONAL REFERENCE: read only for listed ambiguity.

### Rule 4 — Scope reading instruction

Include: “Read only the sections listed. Do not expand to unrelated sections.”

### Rule 5 — Pack first, artifact second, source last

Priority:

1. Reference Pack.
2. Artifact File for detailed contract.
3. Source Doc only when lead requires or trace ambiguity remains.

## 4. Reference Format in Prompts

```text
INPUT DOCUMENTS — MANDATORY READ

1. `docs/reference-packs/capabilities/information-assistance.pack.md`
   - Purpose: Example execution summary for the target capability.

2. `docs/artifacts/interface/data-contracts.md`
   - Purpose: Canonical field details for this example.

REFERENCE DOCUMENTS — OPTIONAL

1. `docs/artifacts/architecture/component-architecture.md`
   - Purpose: Read only if the task crosses a component boundary.

SCOPE
Read only the sections listed. Do not expand to unrelated sections.
```

## 5. Traceability Chain

`Source Doc → Artifact → Registry → Pack → Task Prompt`

- Artifact front matter identifies source file and exact headings.
- `docs/spec-registry/artifact-index.yaml` indexes artifact traceability.
- Capability/contract/tool/component registries refer only to real artifact paths.
- Pack front matter lists artifact dependencies; body lists source artifact paths.

## 6. When to Update

- Update artifacts when source docs change.
- Regenerate registries when artifacts are added, removed, renamed or re-versioned.
- Regenerate packs when relevant artifacts/contracts change.
- Task prompts reference stable pack/artifact versions and must not copy stale contracts.

## 7. Conflict and Incomplete Handling

- Source docs outrank normalized artifacts if verified conflict exists.
- Do not silently repair an artifact. Update source or record an explicit approved clarification, then regenerate downstream documents.
- `INCOMPLETE` means the source has not decided the item. Builder must not invent it.
- If a task requires an INCOMPLETE item, stop planning that subtask and request a lead decision.
