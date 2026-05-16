# Launch runbook

Sequential checklist to take this repo from "committed" to "live on Fiverr".
Each step has exact copy-paste commands and an explicit success signal.

**State at commit `45519e2`:** initial commit on `main`, 87 files, no remote.

---

## Step 1 — Push to GitHub (5 min)

Create a private repo on GitHub (UI or CLI), then:

```powershell
# from C:\Users\mxz\OneDrive\Desktop\fiverr-ai-agency
git remote add origin https://github.com/<YOUR-USERNAME>/fiverr-ai-agency.git
git push -u origin main
```

**Success signal:** the Actions tab on GitHub shows two CI jobs (orchestrator + dashboard) running. Wait for both to pass green before continuing.

If a job fails, the deploy will likely fail too — fix locally and re-push.

---

## Step 2 — Supabase project (10 min)

1. Go to <https://supabase.com/dashboard> → **New project**.
2. Region: closest to you. Postgres version: 15 (default).
3. Wait ~2 min for provisioning.
4. **Settings → API:**
   - Copy `URL` → save as `SUPABASE_URL`
   - Copy `anon` key → save as `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - Copy `service_role` key → save as `SUPABASE_SERVICE_ROLE_KEY` (treat as a password)

### Apply migrations

```powershell
cd "C:\Users\mxz\OneDrive\Desktop\fiverr-ai-agency"
npx supabase login                          # browser opens once
npx supabase link --project-ref <YOUR-REF>  # ref is in your project URL
npx supabase db push
```

**Success signal:** Supabase dashboard → Table Editor → `agents` table shows **19 rows**. `agent_status` also shows 19 rows, all `current_status = idle`.

### Create storage buckets

Supabase dashboard → **Storage** → **New bucket**, all PRIVATE (uncheck "Public bucket"):

- `client-references`
- `deliverables`
- `delivery-packages`

### Create operator account

Supabase dashboard → **Auth → Users → Add user → Create new user**:

- Email: your email
- Password: a strong password (you'll log into the dashboard with this)
- Auto Confirm User: ✓ ON

---

## Step 3 — Gmail OAuth (15 min)

Follow `docs/intake-setup.md` sections 1–3, then run:

```powershell
cd orchestrator
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# .env in repo root with SUPABASE_*, ANTHROPIC_API_KEY, FAL_KEY, GMAIL_* paths
agency auth-gmail
```

**Success signal:** browser opens, you grant Gmail access, the CLI prints `auth_gmail.success token_file=token.json`. The file `orchestrator/token.json` now exists.

Open Gmail → Settings → Filters → Create new filter:
- From: `no-reply@fiverr.com`
- Apply label: `Fiverr/Orders`

---

## Step 4 — Railway (15 min)

In one tab: <https://railway.app/new> → **Deploy from GitHub** → select your repo.

Railway will guess one service. **You need three** (per `docs/deployment.md`):

### Service A — `intake`
- Root Directory: `orchestrator`
- Start Command: leave blank (uses `railway.json` → `agency intake-loop`)
- Variables: paste these (substitute your values):
  ```
  SUPABASE_URL=https://YOUR-REF.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=eyJ...
  ANTHROPIC_API_KEY=sk-ant-...
  FAL_KEY=...
  GMAIL_CREDENTIALS_FILE=/app/credentials.json
  GMAIL_TOKEN_FILE=/app/token.json
  GMAIL_LABEL_PENDING=Fiverr/Orders
  GMAIL_LABEL_PROCESSED=FiverrAgency/Processed
  GMAIL_LABEL_FAILED=FiverrAgency/Failed
  ```
- **Settings → File Mounts:**
  - Path `/app/credentials.json`, paste the contents of your local `credentials.json`
  - Path `/app/token.json`, paste the contents of your local `token.json`
- Deploy

### Service B — `worker`
- **+ New service** → same GitHub repo
- Root Directory: `orchestrator`
- Start Command override: `agency run-loop`
- Variables: copy from `intake` (same keys, same values)
- File Mounts: same as `intake`
- Deploy

### Service C — `dashboard`
- **+ New service** → same GitHub repo
- Root Directory: `dashboard`
- Start Command: leave blank
- Variables:
  ```
  SUPABASE_URL=https://YOUR-REF.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=eyJ...
  NEXT_PUBLIC_SUPABASE_URL=https://YOUR-REF.supabase.co
  NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
  NEXT_PUBLIC_POLL_INTERVAL_MS=2000
  ```
- **Settings → Networking → Generate Domain**
- Deploy

**Success signals (each service's Logs tab):**
- `intake`: `intake.runner.loop_start interval_seconds=60.0`
- `worker`: `run_loop.start interval_seconds=30.0`
- `dashboard`: visit the generated URL — agent grid renders with 19 nodes

---

## Step 5 — Test order (5 min)

Send yourself an email to the Gmail you wired up:

- **From:** any address you control
- **To:** the Gmail address watched by `intake`
- **Subject:** `New order: YouTube thumbnail for gaming channel`
- **Body:**
  ```
  Service: YouTube thumbnail

  Order details: I need a MrBeast-style YouTube thumbnail for my Minecraft
  speedrun video. Big shocked face on the left, neon pixel explosion behind,
  title "WORLD RECORD" in bold yellow. 1280x720, high contrast.

  Deadline: 2 days
  ```

In Gmail, apply the `Fiverr/Orders` label manually (the filter only fires on `no-reply@fiverr.com`).

**Watch the cascade (about 60–90 seconds total):**

| Service | Log line | Time |
|---------|----------|------|
| `intake` | `intake.runner.message_succeeded` | ~60s after labelling |
| `worker` | `run_loop.processing order_id=...` | ~30s after intake |
| `worker` | `agent.completed agent_key=thumbnail_gen` | ~10s later |
| `worker` | `run_loop.complete order_id=...` | ~30s after that |
| `dashboard` | Sidebar shows new package card | live |

Click the card in the dashboard sidebar — the package detail page should render the 3 generated thumbnail previews.

**If it works:** congratulations, the pipeline is live. Approve / reject the test package to clean up state.

**If something fails:** check the failing service's logs, fix locally, push to `main`. Railway auto-redeploys on every push.

---

## Step 6 — Publish Fiverr gigs (30 min, ongoing)

Open `docs/fiverr-gigs.md`. Copy **Gig 1 (Thumbnails)** verbatim into Fiverr.

**Don't launch all 6 gigs at once.** Fiverr's algorithm penalizes new sellers who spam-list. Publish thumbnails first; once you have 5 reviews, publish the next.

### First-week tactics

- Set up phone notifications for Fiverr — respond within 30 min during week 1
- Run first 5 orders at break-even ($10 thumbnails, deliver in <12h)
- After 5 five-star reviews, raise to $15 base and publish Social Graphics
- After 10 reviews, publish AI Headshots
- After 20 reviews, publish Logo / Brand / Background Removal

---

## Operating loop (steady-state)

Per real order:

1. Fiverr emails the order → `intake` parses + inserts → `worker` runs through graph
2. Dashboard sidebar shows new package card (~2 min after order received)
3. You click the card, review 3 variants, edit the message if needed, click **Approve**
4. Open the Fiverr order in another tab, paste the message + attach the ZIP from the dashboard link, click Fiverr's deliver button
5. Return to dashboard, click **Mark as delivered**
6. Order moves to `delivered`. Total operator time per order: **~2 minutes**.

---

## Common operational issues

| Symptom | Fix |
|---------|-----|
| `intake` logs `not an order` for every email | Brief is too short, or the email isn't a real Fiverr order. Check `clarification_requests` table |
| Visual QC fails every variant | Lower `VISUAL_QC_THRESHOLD` env var from 0.70 → 0.60 temporarily, investigate |
| Dashboard images don't load | Signed URL expired → fixed by `/api/deliverables/[id]/file` proxy (already wired) |
| `rembg` first order takes 60s | Normal — downloading 150 MB ONNX model. Subsequent orders are fast |
| `worker` retries a stuck order | Mark it `cancelled` in Supabase manually: `UPDATE orders SET status='cancelled' WHERE id='...';` |

---

## Future enhancements (not blocking launch)

- **Auto-deliver to Fiverr:** Fiverr ToS prohibits bots from clicking deliver. Stay manual.
- **Revision handling:** when a client requests revisions, manually re-run the order via dashboard.
- **Brand Consistency agent:** CLIP similarity vs client references — listed in agent registry but not yet implemented.
- **Cron-based re-generation** for failed visual QC.
- **Multi-operator support:** RLS policies scoped by `auth.uid()`.
