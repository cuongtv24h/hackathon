-- === TASK:WP-005:START ===
-- MVP Pilot schema foundation. RLS policies are owned by WP-006.

create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists knowledge_domains (
  domain_id uuid primary key default gen_random_uuid(),
  domain_code text not null unique check (domain_code in ('dat_lich', 'quy_trinh', 'bhyt', 'gia_dich_vu', 'gio_lam_viec', 'bac_si_khoa', 'thong_tin_benh_vien')),
  domain_name text not null,
  owner_name text not null,
  last_reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists knowledge_chunks (
  chunk_id uuid primary key default gen_random_uuid(),
  domain_id uuid not null references knowledge_domains(domain_id),
  content text not null,
  sub_topic text,
  source_id text not null,
  source_path text not null,
  source_version text not null,
  approval_status text not null check (approval_status in ('draft', 'approved_for_pilot', 'approved', 'rejected', 'retired')),
  effective_date date,
  page_numbers jsonb not null default '[]'::jsonb,
  tags jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector(768),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  retired_at timestamptz,
  check (jsonb_typeof(page_numbers) = 'array'),
  check (jsonb_typeof(tags) = 'array')
);

create index if not exists knowledge_chunks_domain_active_idx on knowledge_chunks (domain_id, is_active, approval_status);
create index if not exists knowledge_chunks_source_idx on knowledge_chunks (source_id, source_version);
create index if not exists knowledge_chunks_embedding_idx on knowledge_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create table if not exists content_drafts (
  draft_id uuid primary key default gen_random_uuid(),
  domain_id uuid not null references knowledge_domains(domain_id),
  source_chunk_id uuid references knowledge_chunks(chunk_id),
  content_after text not null,
  expected_version text,
  state text not null default 'draft' check (state in ('draft', 'submitted', 'approved', 'rejected', 'published')),
  changed_by text not null,
  approved_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  published_at timestamptz
);

create table if not exists content_versions (
  version_id uuid primary key default gen_random_uuid(),
  chunk_id uuid not null references knowledge_chunks(chunk_id),
  content_before text,
  content_after text not null,
  changed_by text not null,
  approved_by text,
  changed_at timestamptz not null default now(),
  source_version text not null
);

create table if not exists content_conflicts (
  conflict_id uuid primary key default gen_random_uuid(),
  source_chunk_ids jsonb not null,
  conflicting_fields jsonb not null,
  state text not null default 'open' check (state in ('open', 'investigating', 'resolved', 'dismissed')),
  due_at timestamptz not null default (now() + interval '24 hours'),
  resolution_note text,
  resolved_by text,
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  check (jsonb_typeof(source_chunk_ids) = 'array'),
  check (jsonb_typeof(conflicting_fields) = 'array')
);

create table if not exists emergency_keyword_sets (
  keyword_set_id uuid primary key default gen_random_uuid(),
  version text not null unique,
  critical_keywords jsonb not null,
  caution_keywords jsonb not null,
  approved_by text not null,
  effective_date date not null,
  is_active boolean not null default false,
  created_at timestamptz not null default now(),
  check (jsonb_typeof(critical_keywords) = 'array'),
  check (jsonb_typeof(caution_keywords) = 'array')
);

create table if not exists emergency_protocols (
  protocol_id uuid primary key default gen_random_uuid(),
  level smallint not null check (level in (1, 2)),
  version text not null,
  response_template text not null,
  hotline_numbers jsonb not null,
  emergency_address text,
  approved_by text not null,
  effective_date date not null,
  is_active boolean not null default false,
  created_at timestamptz not null default now(),
  unique (level, version),
  check (jsonb_typeof(hotline_numbers) = 'array')
);

create table if not exists conversation_sessions (
  session_id uuid primary key default gen_random_uuid(),
  channel text not null check (channel in ('web_widget', 'web_page')),
  metadata jsonb not null default '{}'::jsonb,
  started_at timestamptz not null default now(),
  last_activity_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '24 hours')
);

create index if not exists conversation_sessions_expiry_idx on conversation_sessions (expires_at);

create table if not exists conversation_messages (
  message_id uuid primary key default gen_random_uuid(),
  session_id uuid not null references conversation_sessions(session_id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system', 'tool')),
  content_redacted text not null,
  intent text,
  tools_called jsonb not null default '[]'::jsonb,
  citations jsonb not null default '[]'::jsonb,
  emergency_triggered boolean not null default false,
  detection_path text check (detection_path in ('keyword', 'llm_tool')),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '90 days'),
  check (jsonb_typeof(tools_called) = 'array'),
  check (jsonb_typeof(citations) = 'array')
);

create index if not exists conversation_messages_session_created_idx on conversation_messages (session_id, created_at);
create index if not exists conversation_messages_expiry_idx on conversation_messages (expires_at);

create table if not exists emergency_events (
  event_id uuid primary key default gen_random_uuid(),
  session_id uuid not null references conversation_sessions(session_id),
  message_id uuid references conversation_messages(message_id),
  keyword_set_id uuid references emergency_keyword_sets(keyword_set_id),
  protocol_id uuid references emergency_protocols(protocol_id),
  detection_path text not null check (detection_path in ('keyword', 'llm_tool')),
  matched_evidence jsonb not null default '[]'::jsonb,
  level smallint not null check (level in (1, 2)),
  response_time_ms integer check (response_time_ms >= 0),
  triggered_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '365 days'),
  check (jsonb_typeof(matched_evidence) = 'array')
);

create table if not exists departments (
  department_id uuid primary key default gen_random_uuid(),
  department_name text not null unique,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists doctors (
  doctor_id uuid primary key default gen_random_uuid(),
  department_id uuid references departments(department_id),
  full_name text not null,
  title text,
  specialty text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists schedules (
  schedule_id uuid primary key default gen_random_uuid(),
  doctor_id uuid not null references doctors(doctor_id),
  schedule_date date not null,
  time_slot text not null,
  status text not null default 'available' check (status in ('available', 'booked')),
  created_at timestamptz not null default now(),
  unique (doctor_id, schedule_date, time_slot)
);

create table if not exists appointments (
  appointment_id uuid primary key default gen_random_uuid(),
  doctor_id uuid not null references doctors(doctor_id),
  schedule_id uuid not null unique references schedules(schedule_id),
  patient_name text not null,
  patient_phone text not null,
  patient_dob date,
  has_insurance boolean not null default false,
  visit_reason text not null,
  visit_type text not null check (visit_type in ('first_visit', 'follow_up')),
  status text not null default 'pending' check (status in ('pending', 'confirmed', 'cancelled', 'completed', 'rejected')),
  rejection_reason text,
  idempotency_key text unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '90 days')
);

create index if not exists appointments_expiry_idx on appointments (expires_at);

create table if not exists feedback (
  feedback_id uuid primary key default gen_random_uuid(),
  session_id uuid references conversation_sessions(session_id),
  rating smallint check (rating between 1 and 5),
  comment_redacted text,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '180 days')
);

create table if not exists analytics_events (
  analytics_event_id uuid primary key default gen_random_uuid(),
  session_id uuid references conversation_sessions(session_id),
  event_type text not null,
  properties jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '365 days')
);

create index if not exists analytics_events_occurred_idx on analytics_events (occurred_at);

create table if not exists audit_events (
  audit_event_id uuid primary key default gen_random_uuid(),
  event_category text not null check (event_category in ('emergency', 'security', 'content')),
  actor_reference text,
  entity_type text not null,
  entity_id uuid,
  action text not null,
  payload_redacted jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '365 days')
);

create index if not exists audit_events_category_occurred_idx on audit_events (event_category, occurred_at);
-- === TASK:WP-005:END ===
