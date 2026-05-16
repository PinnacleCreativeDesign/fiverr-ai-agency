# Deployment guide

## Architecture

Railway hosts **three services**, all from the same GitHub repo:

| Service | Root dir | Start command | Purpose |
|---------|----------|---------------|---------|
| `intake` | `orchestrator/` | `agency intake-loop` | Polls Gmail → inserts `orders` rows |
| `worker` | `orchestrator/` | `agency run-loop` | Polls `orders` → runs the LangGraph state machine |
| `dashboard` | `dashboard/` | `npm start` | Operator UI (Next.js) |

Splitting `intake` and `worker` means a stuck graph run can't block new orders from arriving.

---

## Step 1 — Supabase

```bash
npx supabase link --project-ref <your-ref>
npx supabase db push           # runs both migrations
```

Verify: table `agents` has **19 rows**; `agent_status` has 19 rows all `idle`.

**Storage buckets** (Supabase → Storage → New bucket, all PRIVATE):
- `client-references`
- `deliverables`
- `delivery-packages`

**Operator account**: Supabase → Auth → Users → Add user (signup is disabled in `config.toml`).

---

## Step 2 — Gmail OAuth (local, one-time)

```bash
cd orchestrator
pip install -e ".[dev]"
agency auth-gmail
```

Writes `orchestrator/token.json`. Keep this file — you'll upload it as a Railway secret in Step 4.

---

## Step 3 — Push to GitHub

```bash
git init && git add . && git commit -m "initial"
gh repo create fiverr-ai-agency --private --source=. --push
```

Railway will deploy from this repo.

---

## Step 4 — Railway: create three services

In Railway dashboard:

### Service A — `intake`
1. **New service** → **GitHub Repo** → select your repo
2. **Settings** → **Root Directory** = `orchestrator`
3. **Settings** → **Start Command** leave blank (uses `railway.json`)
4. **Variables** tab — add:
   ```
   SUPABASE_URL=https://...supabase.co
   SUPABASE_SERVICE_ROLE_KEY=...
   ANTHROPIC_API_KEY=...
   FAL_KEY=...
   GMAIL_CREDENTIALS_FILE=/app/credentials.json
   GMAIL_TOKEN_FILE=/app/token.json
   GMAIL_LABEL_PENDING=Fiverr/Orders
   GMAIL_LABEL_PROCESSED=FiverrAgency/Processed
   GMAIL_LABEL_FAILED=FiverrAgency/Failed
   STORAGE_BUCKET_DELIVERABLES=deliverables
   STORAGE_BUCKET_PACKAGES=delivery-packages
   STORAGE_BUCKET_REFERENCES=client-references
   ```
5. **Settings** → **File Mounts**: add two file mounts pointing at `/app/credentials.json` and `/app/token.json` (paste the JSON contents from your local OAuth setup)
6. Deploy

### Service B — `worker`
1. **New service** → same GitHub repo
2. **Root Directory** = `orchestrator`
3. **Start Command** override: `agency run-loop`
4. **Variables** — copy from `intake` service (Railway has a "share variables" feature, or duplicate)
5. Deploy

### Service C — `dashboard`
1. **New service** → same GitHub repo
2. **Root Directory** = `dashboard`
3. Start Command leave blank (uses `railway.json`)
4. **Variables** tab:
   ```
   SUPABASE_URL=https://...supabase.co
   SUPABASE_SERVICE_ROLE_KEY=...
   NEXT_PUBLIC_SUPABASE_URL=https://...supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=...
   NEXT_PUBLIC_POLL_INTERVAL_MS=2000
   ```
5. **Settings** → **Networking** → **Generate Domain**
6. Deploy

---

## Step 5 — Verify deployment

Check Railway logs for each service:

**intake** should log within 60s:
```
intake.runner.loop_start interval_seconds=60.0
```

**worker** should log:
```
run_loop.start interval_seconds=30.0
```

**dashboard** should respond at the generated URL. Hitting `/api/dashboard` returns JSON with `agents.length === 19`.

---

## Step 6 — Send yourself a test order

Send an email to your Gmail (the one wired to OAuth) from any address you control, with subject like:

> New order: YouTube thumbnail for gaming channel

Body:

> Service: YouTube thumbnail
>
> Order details: I need a thumbnail for my Minecraft speedrun video. Shocked face on left, pixel explosion behind, title "WORLD RECORD" in bold yellow. 1280x720.
>
> Deadline: 2 days

Add the `Fiverr/Orders` label (or set up the filter to do this automatically for `noreply@fiverr.com`).

Within ~60s the `intake` service should log:
```
intake.runner.message_succeeded message_id=... order_id=...
```

Within ~30s of that, `worker` picks it up:
```
run_loop.processing order_id=...
run_loop.complete order_id=...
```

Open the dashboard URL — the agent grid should light up briefly (each agent flashes blue → idle) and a package card appears in the right sidebar.

---

## Step 7 — Fiverr gigs

Once a test order completes successfully end-to-end, you're ready to take real orders.

Launch order (highest demand first):

1. **YouTube Thumbnails** — `"I will design high-CTR YouTube thumbnails for gaming, finance, and lifestyle channels"` · $10–15 basic · $40–80 premium · 24h delivery
2. **Social Media Graphics** — after first 5 reviews
3. **AI Headshots / Logos / Brand Concepts** — after 10 reviews

In Gmail, ensure the filter is set:
- **From:** `no-reply@fiverr.com`
- **Apply label:** `Fiverr/Orders`

---

## Cost (low volume, 20 orders/month)

| Item | Cost |
|------|------|
| Supabase Free tier | $0 |
| Railway Hobby (3 services × $5 each = $15, but Hobby plan covers $5 of usage) | ~$10 |
| Anthropic (intake + clarification + prompt eng + visual QC) | ~$3 |
| fal.ai (3 variants × $0.04 × 20 orders) | ~$2.40 |
| **Fixed monthly cost** | **~$15** |

At $15 average order × 20 orders × 80% (after Fiverr's cut) = $240 revenue → **net ~$222/month at 20 orders**.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `intake` exits immediately | Check Gmail token mount path matches `GMAIL_TOKEN_FILE` env var |
| `worker` errors on first Visual QC | Anthropic key missing or wrong model id — verify `ANTHROPIC_MODEL=claude-sonnet-4-6` |
| `worker` errors on Thumbnail Generator | `FAL_KEY` missing or rate-limited |
| Dashboard shows 0 agents | Service-role key wrong, or migrations didn't run |
| Deliverable images don't display in dashboard | Signed URLs expired (7-day TTL) — regenerate by re-running the order, or add a refresh endpoint (TODO) |
| `rembg` first-order is slow | First run downloads the ONNX model (~150 MB). Subsequent runs are fast. Persists across container restarts on Railway. |
