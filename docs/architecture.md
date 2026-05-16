# Architecture

## System overview

```
                       ┌─────────────────────────┐
   Fiverr order email ─┤      n8n (intake)       │
                       │   Gmail watcher + LLM   │
                       └────────────┬────────────┘
                                    │ INSERT into orders
                                    ▼
                       ┌─────────────────────────┐
                       │     Supabase (Postgres) │◀─── Dashboard (Next.js + xyflow)
                       │   orders, agent_runs,   │     subscribes via Realtime
                       │  agent_status, etc.     │
                       └────────────┬────────────┘
                                    │ trigger / poll
                                    ▼
                       ┌─────────────────────────┐
                       │  Orchestrator (Python)  │
                       │   LangGraph 1.1 state   │
                       │  machine, Claude 4.6    │
                       └────────────┬────────────┘
                                    │ invokes
                       ┌────────────┴────────────┐
                       │                         │
                       ▼                         ▼
              ┌──────────────────┐      ┌────────────────────┐
              │ Generation agents│      │  Editing / QC      │
              │  (fal.ai, SDXL)  │      │  (Python pipelines)│
              └────────┬─────────┘      └──────────┬─────────┘
                       │                           │
                       └────────────┬──────────────┘
                                    ▼
                       ┌─────────────────────────┐
                       │   Delivery Packager     │
                       │  builds ZIP + message   │
                       └────────────┬────────────┘
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │  Operator dashboard     │
                       │  → click deliver        │
                       └─────────────────────────┘
```

## Data flow per order

1. **Intake.** Client places order on Fiverr. Fiverr sends an order notification email. n8n watches the Gmail label `Fiverr/Orders`, extracts subject/body/attachments, and calls Claude to produce a structured JSON `{ service_type, brief, deadline, reference_image_urls }`. n8n inserts a row into `orders` with `status = 'pending'` and stores the raw email in `raw_payload` for debugging.

2. **Routing.** The Orchestrator polls (or is webhook-triggered) for new `pending` orders. It invokes the **Brief Clarification agent** to score the brief. If `confidence_score < BRIEF_CONFIDENCE_THRESHOLD` (default 0.65), it writes a `clarification_requests` row and sets the order to `clarification_needed`. The operator approves/sends the message manually. Otherwise it advances to `processing`.

3. **Creative direction.** The Orchestrator invokes the **Prompt Engineering agent**, which selects a template from `prompt_templates` (matched by `service_type`) and fills variables from the brief. If reference images exist, the **Style Reference Analyzer** extracts attributes first and feeds them into the prompt.

4. **Generation.** The Orchestrator routes to the right generation agent based on `service_type`:
   - `thumbnail` → Thumbnail Generator (Flux Pro 1.1)
   - `social_graphic` → Social Graphics Generator (Flux Pro 1.1)
   - `headshot` → AI Headshot Generator (Flux Pro 1.1 Ultra)
   - `background_removal` → Background Removal (rembg, no generation)
   - `logo` → Logo Generator (SDXL + DALL-E 3, vectorized)
   - `business_design` → Business Design Concept (SDXL + Claude)

   Each generation agent writes one or more rows to `deliverables` (typically 3 variants).

5. **Editing.** Generated assets pass through:
   - **Image Editor** — color grading, contrast, layout adjustments
   - **Upscaler** — Real-ESRGAN ncnn to 4K
   - **Text Renderer** — title/caption overlays when the brief requires copy

   Editing agents update the `deliverables` row in place (new `file_url` for the edited version is fine — old can be kept for revision requests).

6. **Quality control.** All deliverables run through:
   - **Technical QC** — dimension, DPI, file format → sets `technical_qc_passed`
   - **Visual QC** — Claude Vision checks for distorted faces, hands, spelling on overlays → sets `quality_score`
   - **Brand Consistency** — CLIP embedding similarity vs client reference → sets `brand_consistency_score`

   If any score falls below threshold, the Orchestrator retries generation up to `MAX_GENERATION_RETRIES` (default 2). If still failing, marks the order `error` for operator triage.

7. **Delivery preparation.** Best-scoring variants are marked `is_approved = true`. The **Delivery Packager** builds a ZIP, uploads to the `delivery-packages` storage bucket, and drafts a delivery message. The **Upsell agent** appends a suggested next service. A `delivery_packages` row is created with `status = 'pending_approval'`.

8. **Operator approval.** The dashboard shows pending packages. The operator reviews, clicks approve, then manually delivers on Fiverr (ToS requires human-initiated delivery). The dashboard sets `status = 'sent_to_fiverr'` and the order to `delivered`.

## Database schema (summary)

| Table | Purpose | Realtime? |
|-------|---------|-----------|
| `agents` | Static registry of 19 agents | No |
| `agent_status` | Live state per agent (one row each) | **Yes** |
| `agent_runs` | Append-only execution audit log | **Yes** |
| `orders` | One row per client request | **Yes** |
| `deliverables` | Generated assets, multiple per order | **Yes** |
| `delivery_packages` | Final ZIP + message awaiting operator approval | **Yes** |
| `clarification_requests` | Drafts for ambiguous briefs | No |
| `prompt_templates` | Reusable prompt templates per service type | No |

See [supabase/migrations/](../supabase/migrations/) for the canonical definitions.

## Agent contract

Every agent — whether implemented in Python, an n8n node, or a workflow — must follow this contract when writing status:

```text
ON START
  insert into agent_runs (order_id, agent_id, status, started_at, input_data)
    values (..., 'processing', now(), <input>)
    returning id;  -- capture run_id
  update agent_status
    set current_status = 'processing',
        current_order_id = <order_id>,
        current_run_id = <run_id>,
        last_log = <one-line summary of what we are about to do>
    where agent_id = <agent_id>;

ON COMPLETE
  update agent_runs
    set status = 'completed',
        completed_at = now(),
        output_data = <output>,
        log_summary = <one-line summary of what we produced>,
        cost_usd = <api cost or null>
    where id = <run_id>;
  update agent_status
    set current_status = 'idle',         -- or 'completed' briefly for UI flash
        last_log = <one-line summary>,
        last_completed_at = now(),
        total_runs = total_runs + 1
    where agent_id = <agent_id>;

ON ERROR
  update agent_runs
    set status = 'error',
        completed_at = now(),
        error_message = <error>
    where id = <run_id>;
  update agent_status
    set current_status = 'error',
        last_log = <error one-liner>,
        last_error_at = now(),
        total_errors = total_errors + 1
    where agent_id = <agent_id>;
```

A helper module in the orchestrator (`orchestrator/src/agents/lifecycle.py`, next milestone) will wrap this so individual agents only implement business logic.

## Thresholds and tuning

| Setting | Default | Where read | Meaning |
|---------|---------|-----------|---------|
| `BRIEF_CONFIDENCE_THRESHOLD` | 0.65 | Orchestrator | Below this, send clarification |
| `BRAND_CONSISTENCY_THRESHOLD` | 0.75 | Brand Consistency agent | CLIP cosine cutoff |
| `MAX_GENERATION_RETRIES` | 2 | Orchestrator | Retries before erroring out |

## Security

**Baseline (in migration 20260514120000).**
- RLS is enabled on all tables.
- Authenticated users get read-only access via `for select to authenticated using (true)` policies on every table.
- Service-role bypasses RLS automatically — the orchestrator (Python) and n8n both use the service-role key for writes.
- Realtime respects these SELECT policies for the dashboard's `authenticated` subscription. (Without a SELECT policy, Realtime silently drops events.)
- Signup is disabled in `supabase/config.toml` (`auth.enable_signup = false`). Provision the operator account by inserting a row via the Supabase dashboard or `auth.admin.createUser`.

**Write paths.**
- Backend writes: orchestrator + n8n → service role key (server only, never exposed to a browser).
- Operator approval click: Next.js server action that holds the service-role key in an environment variable. The browser only ever holds the anon key.

**To revisit before Phase 2.**
- Tighten policies if multi-operator: scope reads to `auth.uid()`-owned rows.
- Add a `revisions` audit policy if clients are ever given direct DB-backed access (not planned).

## Cost model (per order, rough)

| Component | Cost |
|-----------|------|
| Claude Sonnet 4.6 for prompt engineering + QC vision (~5 calls × ~2k tokens) | ~$0.05 |
| Flux Pro 1.1 (3 variants × 1MP) | ~$0.12 |
| SDXL on RunPod (optional, ~30s of 4090) | ~$0.01 |
| Storage + DB | ~$0.001 |
| **Total per order** | **~$0.18** |

At a $15 thumbnail price, gross margin ≈ 98% before Fiverr's 20% take. Net ≈ $11.80 per order.

## Build sequence

Phase 1 (this repo, in order):
1. ✅ Schema + agent registry
2. Orchestrator skeleton (LangGraph state graph + agent lifecycle wrapper)
3. n8n intake workflow (Gmail → Claude parser → orders insert)
4. First generation agent: Thumbnail Generator (fal.ai)
5. Editing + QC for thumbnails
6. Delivery Packager
7. Dashboard MVP (Next.js + xyflow)
8. Launch first Fiverr gig

Phase 2: Add Social Graphics, Background Removal, Headshots.
Phase 3: Add Logo (with vectorization) and Business Design.
Phase 4: Optional direct intake (form on landing page, Discord bot).
