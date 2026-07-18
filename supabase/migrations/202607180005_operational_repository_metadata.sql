-- Operational persistence fields required by canonical MVP DTOs.
-- Existing rows remain valid and no raw PII is introduced.

alter table feedback
  add column if not exists category text,
  add column if not exists metadata jsonb not null default '{}'::jsonb;

alter table content_drafts
  add column if not exists metadata jsonb not null default '{}'::jsonb;

create index if not exists content_conflicts_open_idx
  on content_conflicts (state, due_at)
  where state in ('open', 'investigating');
