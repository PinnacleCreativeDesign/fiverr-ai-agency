# Fiverr AI Agency

A semi-autonomous creative service business powered by a multi-agent AI pipeline.

Clients place orders on Fiverr. A pipeline of 19 specialized AI agents parses the brief, generates assets, runs quality control, and prepares a delivery package. The operator reviews and clicks deliver. The agents do everything in between.

## Service scope — Phase 1 (Easy Tier)

| Service | Primary generator |
|---------|------------------|
| YouTube thumbnails | Flux 1.1 Pro + SDXL |
| Social media graphics | Flux 1.1 Pro + SDXL |
| Background removal | rembg + transparent-background |
| AI headshots | Flux 1.1 Pro (photorealistic) |
| Business logos | SDXL + DALL-E 3 → vectorized to SVG |
| Business design concepts | SDXL + Claude (mood boards, palettes, typography) |

## Architecture — 19 agents across 6 layers

```
┌─ Coordination ─┐   ┌─ Creative ────┐   ┌─ Generation ──────┐
│ Orchestrator   │──▶│ Prompt Eng.   │──▶│ Thumbnail Gen     │
│ Intake Parser  │   │ Style Ref.    │   │ Social Graphics   │
│ Brief Clarif.  │   │               │   │ Background Removal│
└────────────────┘   └───────────────┘   │ Headshot Gen      │
                                          │ Logo Gen          │
                                          │ Business Design   │
                                          └───────────────────┘
                                                    │
                     ┌─ Delivery ─┐  ┌─ Quality ────┐  ┌─ Editing ─────┐
                     │ Packager   │◀─│ Technical QC │◀─│ Image Editor  │
                     │ Upsell     │  │ Visual QC    │  │ Upscaler      │
                     └────────────┘  │ Brand Consist│  │ Text Renderer │
                                     └──────────────┘  └───────────────┘
```

## Tech stack

| Layer | Tool |
|-------|------|
| Orchestration | Claude Sonnet 4.6 + LangGraph 1.1 |
| Workflow automation | n8n (self-hosted on Railway) |
| Image generation | fal.ai (Flux 1.1 Pro), DALL-E 3, SDXL via ComfyUI |
| Image editing | Pillow, OpenCV, rembg, Real-ESRGAN (ncnn) |
| Vision QC | Claude Sonnet 4.6 Vision, CLIP embeddings |
| Database + Realtime | Supabase (Postgres) |
| Dashboard | Next.js 15 + `@xyflow/react` 12 |
| Hosting | Railway (logic) + RunPod (on-demand GPU for SDXL) |

## Repository layout

```
fiverr-ai-agency/
├── README.md
├── .env.example                  # all required env vars
├── .gitignore
├── supabase/
│   └── migrations/
│       ├── 20260514120000_initial_schema.sql
│       └── 20260514120001_seed_agents.sql
├── orchestrator/                 # (next milestone) Python + LangGraph
├── n8n/                          # (next milestone) workflow exports
├── dashboard/                    # (next milestone) Next.js + React Flow
└── docs/
    └── architecture.md
```

## Setup — current milestone

1. **Create a Supabase project**: <https://supabase.com/dashboard>
2. **Run migrations** in order from `supabase/migrations/`:
   ```bash
   supabase link --project-ref <your-ref>
   supabase db push
   # or paste each .sql file into the SQL editor in order
   ```
3. **Create Storage buckets** (private, not in migrations because Storage policies are clearer via the dashboard):
   - `client-references` — reference images uploaded by clients
   - `deliverables` — generated assets
   - `delivery-packages` — final ZIPs for operator approval
4. **Create the operator auth account**: signup is disabled in `config.toml`. Use the Supabase dashboard → Auth → Users → "Add user" to create your single operator login (this becomes the dashboard credential).
5. **Copy `.env.example` to `.env`** and fill in keys. None of the agent code is wired yet — the env is staged for the next milestone.
6. **Verify seed**: in Supabase, table `agents` should contain 19 rows; `agent_status` should mirror them with `idle` status.

## Next milestones

- [ ] Orchestrator skeleton (LangGraph state machine, agent registry, run logging)
- [ ] First agent: Intake Parser (n8n Gmail → Supabase orders)
- [ ] First generation agent: Thumbnail Generator (fal.ai Flux Pro 1.1)
- [ ] Dashboard MVP: live agent grid via Supabase Realtime
- [ ] First Fiverr gig launch

## Operating model

The operator's per-order work:
1. Receive notification (n8n)
2. Approve clarification draft if Brief Clarification flagged the brief (~10% of orders)
3. Review the prepared delivery in the dashboard
4. Click deliver on Fiverr (Fiverr ToS requires human-initiated delivery)

Everything else runs without human input.
