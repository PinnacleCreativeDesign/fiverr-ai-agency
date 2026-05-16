-- ============================================================================
-- Fiverr AI Agency — Initial schema
-- ============================================================================
-- Foundation tables for the 19-agent pipeline. Every agent writes status here
-- and the dashboard (Next.js + @xyflow/react) subscribes via Supabase Realtime.
--
-- Design notes:
-- * RLS is ENABLED on every table from day 1. Permissive read policies for
--   authenticated users are added below. Writes are service-role only. Realtime
--   silently drops events for rows without a SELECT policy — getting this right
--   on day 1 saves a painful debugging session later (see Supabase Realtime
--   docs §Postgres Changes).
-- * `agent_runs` is the immutable audit log (one row per execution).
-- * `agent_status` is a denormalized "latest state per agent" table optimized
--   for Realtime — the dashboard subscribes here, not on `agent_runs`.
-- * All timestamps are `timestamptz` to keep multi-timezone semantics clean.
-- * Trigger functions set explicit `search_path` to prevent search-path
--   injection attacks (Postgres hardening best practice).
-- ============================================================================

create extension if not exists "pgcrypto";

-- ============================================================================
-- ENUMS
-- ============================================================================

create type service_type as enum (
  'thumbnail',
  'social_graphic',
  'headshot',
  'background_removal',
  'logo',
  'business_design'
);

create type order_source as enum (
  'fiverr',
  'direct',
  'discord',
  'manual'
);

create type order_status as enum (
  'pending',               -- just ingested, not yet routed
  'clarification_needed',  -- brief confidence below threshold
  'awaiting_response',     -- clarification sent, waiting on client
  'processing',            -- agents working
  'qc',                    -- quality control running
  'ready_for_delivery',    -- package built, awaiting operator approval
  'delivered',             -- operator clicked deliver on Fiverr
  'error',                 -- terminal error, needs operator triage
  'cancelled'
);

create type agent_layer as enum (
  'coordination',
  'creative',
  'generation',
  'editing',
  'quality',
  'delivery'
);

-- Narrow enum for the live snapshot column. `agent_runs.status` uses the
-- broader `run_status` because runs have queued/skipped states that an
-- *agent* never has.
create type agent_state as enum (
  'idle',
  'processing',
  'error'
);

create type run_status as enum (
  'queued',
  'processing',
  'completed',
  'error',
  'skipped'
);

create type package_status as enum (
  'pending_approval',
  'approved',
  'sent_to_fiverr',
  'rejected'
);

create type clarification_status as enum (
  'drafted',
  'sent',
  'answered',
  'cancelled'
);

-- ============================================================================
-- TRIGGER HELPERS
-- ============================================================================

create or replace function set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- Atomically maintain the run/error counters on agent_status from agent_runs
-- terminal-state transitions. Avoids racy read-modify-write in application code.
create or replace function update_agent_status_counters()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
  if new.status = 'completed'
     and (tg_op = 'INSERT' or old.status is distinct from 'completed') then
    update public.agent_status
    set total_runs        = total_runs + 1,
        last_completed_at = coalesce(new.completed_at, now())
    where agent_id = new.agent_id;
  elsif new.status = 'error'
        and (tg_op = 'INSERT' or old.status is distinct from 'error') then
    update public.agent_status
    set total_errors  = total_errors + 1,
        last_error_at = coalesce(new.completed_at, now())
    where agent_id = new.agent_id;
  end if;
  return new;
end;
$$;

-- ============================================================================
-- AGENTS — registry of all agents in the pipeline (static config)
-- ============================================================================

create table agents (
  id                     uuid           primary key default gen_random_uuid(),
  agent_key              text           not null unique,
  display_name           text           not null,
  layer                  agent_layer    not null,
  description            text           not null,
  layer_order            int            not null,
  position_x             int            not null default 0,
  position_y             int            not null default 0,
  -- Data-driven routing. Generation agents declare which service types they
  -- handle; the orchestrator picks by `service_type = any(handles_service_types)`.
  -- Non-routable agents (editing, QC, delivery) leave this empty.
  handles_service_types  service_type[] not null default '{}',
  is_active              boolean        not null default true,
  created_at             timestamptz    not null default now()
);

comment on table agents is
  'Registry of all agents. Seeded by 20260514120001_seed_agents.sql.';

create index agents_layer_idx           on agents (layer, layer_order);
create index agents_handles_service_idx on agents using gin (handles_service_types);

-- ============================================================================
-- ORDERS — every incoming service request
-- ============================================================================

create table orders (
  id                uuid         primary key default gen_random_uuid(),
  fiverr_order_id   text         unique,                 -- null for non-Fiverr sources
  -- Idempotency for non-Fiverr sources (or for n8n retries before fiverr_order_id is known).
  -- Insert with on conflict do nothing on this column.
  idempotency_key   text         unique,
  source            order_source not null default 'fiverr',
  client_username   text,
  client_email      text,
  service_type      service_type not null,
  brief             text         not null,
  reference_images  jsonb        not null default '[]'::jsonb,
  deadline          timestamptz,
  confidence_score  numeric(3,2)
                     check (confidence_score is null
                            or (confidence_score >= 0 and confidence_score <= 1)),
  status            order_status not null default 'pending',
  raw_payload       jsonb        not null default '{}'::jsonb,
  metadata          jsonb        not null default '{}'::jsonb,
  created_at        timestamptz  not null default now(),
  updated_at        timestamptz  not null default now()
);

comment on table orders is
  'One row per client request. Intake Parser writes here. Orchestrator reads here.';

create index orders_status_idx        on orders (status, created_at desc);
create index orders_service_type_idx  on orders (service_type);
create index orders_created_idx       on orders (created_at desc);

create trigger orders_set_updated_at
  before update on orders
  for each row execute function set_updated_at();

-- ============================================================================
-- AGENT_RUNS — immutable execution history
-- ============================================================================

create table agent_runs (
  id             uuid       primary key default gen_random_uuid(),
  -- Nullable for "system" agents that run before an order exists (Intake Parser).
  -- The lifecycle wrapper attaches the order_id once the order has been inserted.
  order_id       uuid       references orders(id) on delete cascade,
  agent_id       uuid       not null references agents(id),
  status         run_status not null default 'queued',
  started_at     timestamptz,
  completed_at   timestamptz,
  duration_ms    int        generated always as (
                              case
                                when started_at is not null and completed_at is not null
                                then (extract(epoch from (completed_at - started_at)) * 1000)::int
                                else null
                              end
                            ) stored,
  input_data     jsonb,
  output_data    jsonb,
  error_message  text,
  log_summary    text,
  cost_usd       numeric(10,4),
  created_at     timestamptz not null default now()
);

comment on table agent_runs is
  'Append-only audit log. One row per agent invocation. Updated until terminal status.';

create index agent_runs_order_idx   on agent_runs (order_id, created_at);
create index agent_runs_agent_idx   on agent_runs (agent_id, created_at desc);
create index agent_runs_active_idx  on agent_runs (status) where status in ('queued', 'processing');
create index agent_runs_errors_idx  on agent_runs (created_at desc) where status = 'error';

create trigger agent_runs_update_counters
  after insert or update of status on agent_runs
  for each row execute function update_agent_status_counters();

-- ============================================================================
-- AGENT_STATUS — live snapshot per agent (one row per agent, updated in place)
-- ============================================================================

create table agent_status (
  agent_id          uuid        primary key references agents(id) on delete cascade,
  current_status    agent_state not null default 'idle',
  current_order_id  uuid        references orders(id) on delete set null,
  current_run_id    uuid        references agent_runs(id) on delete set null,
  last_log          text,
  last_completed_at timestamptz,
  last_error_at     timestamptz,
  total_runs        bigint      not null default 0,
  total_errors      bigint      not null default 0,
  updated_at        timestamptz not null default now()
);

comment on table agent_status is
  'Denormalized live state. Updated by agents at start/complete/error. Dashboard subscribes via Realtime.';

create index agent_status_status_idx       on agent_status (current_status);
create index agent_status_current_order_idx on agent_status (current_order_id)
  where current_order_id is not null;

create trigger agent_status_set_updated_at
  before update on agent_status
  for each row execute function set_updated_at();

-- ============================================================================
-- DELIVERABLES — every generated asset
-- ============================================================================

create table deliverables (
  id                       uuid        primary key default gen_random_uuid(),
  order_id                 uuid        not null references orders(id) on delete cascade,
  -- If this is a revision of an earlier deliverable, link back.
  parent_deliverable_id    uuid        references deliverables(id) on delete set null,
  produced_by_agent_id     uuid        references agents(id),
  produced_by_run_id       uuid        references agent_runs(id) on delete set null,
  file_url                 text        not null,
  file_name                text        not null,
  file_type                text        not null,
  file_size_bytes          bigint,
  dimensions               jsonb,
  variant_index            int         not null default 0,
  quality_score            numeric(3,2)
                            check (quality_score is null
                                   or (quality_score >= 0 and quality_score <= 1)),
  brand_consistency_score  numeric(3,2)
                            check (brand_consistency_score is null
                                   or (brand_consistency_score >= 0 and brand_consistency_score <= 1)),
  technical_qc_passed      boolean,
  is_approved              boolean     not null default false,
  metadata                 jsonb       not null default '{}'::jsonb,
  created_at               timestamptz not null default now()
);

comment on table deliverables is
  'Generated assets. Multiple variants per order; revisions link via parent_deliverable_id.';

create index deliverables_order_idx     on deliverables (order_id, variant_index);
create index deliverables_approved_idx  on deliverables (order_id) where is_approved = true;
create index deliverables_parent_idx    on deliverables (parent_deliverable_id)
  where parent_deliverable_id is not null;

-- ============================================================================
-- DELIVERY_PACKAGES — final package the operator approves and delivers
-- ============================================================================

create table delivery_packages (
  id                 uuid           primary key default gen_random_uuid(),
  order_id           uuid           not null references orders(id) on delete cascade,
  zip_url            text,
  delivery_message   text           not null,
  upsell_suggestion  text,
  status             package_status not null default 'pending_approval',
  approved_at        timestamptz,
  approved_by        text,
  rejection_reason   text,
  created_at         timestamptz    not null default now(),
  updated_at         timestamptz    not null default now()
);

-- At most one active (pending or approved) package per order. Rejected and
-- sent packages can coexist (revisions after delivery create new packages).
create unique index delivery_packages_active_per_order_idx
  on delivery_packages (order_id)
  where status in ('pending_approval', 'approved');

comment on index delivery_packages_active_per_order_idx is
  'Enforces a single live package per order. Released when status moves to sent_to_fiverr or rejected.';

create index delivery_packages_status_idx on delivery_packages (status, created_at desc);

create trigger delivery_packages_set_updated_at
  before update on delivery_packages
  for each row execute function set_updated_at();

-- ============================================================================
-- CLARIFICATION_REQUESTS — drafts for ambiguous briefs
-- ============================================================================

create table clarification_requests (
  id                    uuid                 primary key default gen_random_uuid(),
  order_id              uuid                 not null references orders(id) on delete cascade,
  questions             jsonb                not null,
  draft_message         text                 not null,
  status                clarification_status not null default 'drafted',
  sent_at               timestamptz,
  response_received_at  timestamptz,
  response_text         text,
  created_at            timestamptz          not null default now()
);

create index clarification_requests_order_idx  on clarification_requests (order_id);
create index clarification_requests_status_idx on clarification_requests (status)
  where status in ('drafted', 'sent');

-- ============================================================================
-- PROMPT_TEMPLATES — reusable prompts for Creative Direction agent
-- ============================================================================

create table prompt_templates (
  id             uuid         primary key default gen_random_uuid(),
  service_type   service_type not null,
  template_name  text         not null,
  template_body  text         not null,
  variables      jsonb        not null default '[]'::jsonb,
  description    text,
  usage_count    bigint       not null default 0,
  is_active      boolean      not null default true,
  created_at     timestamptz  not null default now(),
  unique (service_type, template_name)
);

create index prompt_templates_service_idx on prompt_templates (service_type, is_active);

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================
-- Service-role (used by the orchestrator and n8n) bypasses RLS automatically.
-- Authenticated users (the operator in the dashboard) get read-only access via
-- the policies below. Write paths from the dashboard go through Next.js server
-- actions that hold the service-role key — never expose service_role to a
-- browser.

alter table agents                 enable row level security;
alter table agent_status           enable row level security;
alter table agent_runs             enable row level security;
alter table orders                 enable row level security;
alter table deliverables           enable row level security;
alter table delivery_packages      enable row level security;
alter table clarification_requests enable row level security;
alter table prompt_templates       enable row level security;

create policy "authenticated read agents"
  on agents for select to authenticated using (true);
create policy "authenticated read agent_status"
  on agent_status for select to authenticated using (true);
create policy "authenticated read agent_runs"
  on agent_runs for select to authenticated using (true);
create policy "authenticated read orders"
  on orders for select to authenticated using (true);
create policy "authenticated read deliverables"
  on deliverables for select to authenticated using (true);
create policy "authenticated read delivery_packages"
  on delivery_packages for select to authenticated using (true);
create policy "authenticated read clarification_requests"
  on clarification_requests for select to authenticated using (true);
create policy "authenticated read prompt_templates"
  on prompt_templates for select to authenticated using (true);

-- ============================================================================
-- REALTIME PUBLICATION
-- ============================================================================
-- Supabase creates the `supabase_realtime` publication by default. With RLS
-- enabled above, Realtime will respect the SELECT policies for the subscribed
-- user role (authenticated for the dashboard).

alter publication supabase_realtime add table agent_status;
alter publication supabase_realtime add table agent_runs;
alter publication supabase_realtime add table orders;
alter publication supabase_realtime add table delivery_packages;
alter publication supabase_realtime add table deliverables;
