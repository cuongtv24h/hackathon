# PromptOps Repository

This directory stores delivery prompts, not product source code.

- `_shared/`: stable shared instructions, reference format and review checklists.
- `sprint-{n}/registry.yaml`: packet index for a sprint.
- `sprint-{n}/task-packets/`: created only in Phase 6.5, one packet per work package.
- `sprint-{n}/review/`, `fix/`, `audit/`: derived prompts; never overwrite the original task packet.

Naming: `WP-xxx.{build|review|fix|audit}.md`. Every packet must name mandatory files, optional files, allowed zones and verification commands.

