# Gmail intake setup

The orchestrator polls a Gmail inbox for Fiverr order notification emails,
extracts structured order data with Claude, and inserts rows into Supabase.
This document walks through the one-time setup.

You only do steps 1–3 once. Step 4 (the OAuth bootstrap) happens once per
deploy environment.

## 1. Gmail label setup

In the Gmail web UI, create one label (the others are auto-created by the
orchestrator on first run):

- **`Fiverr/Orders`** — apply this label to incoming Fiverr order notification emails

The fastest way to populate this label automatically:

1. Gmail → **Settings** → **Filters and Blocked Addresses** → **Create a new filter**
2. **From**: `no-reply@fiverr.com`
3. Click **Create filter**
4. Check **Apply the label** → choose `Fiverr/Orders`
5. Optionally also check **Skip the Inbox** (Archive it) so your inbox stays clean
6. Click **Create filter**

The orchestrator auto-creates these labels on its first run:

- **`FiverrAgency/Processed`** — orchestrator moves successfully-parsed emails here
- **`FiverrAgency/Failed`** — orchestrator moves emails it couldn't parse here (operator review)

## 2. Google Cloud project + OAuth credentials

1. Go to <https://console.cloud.google.com/>.
2. Create a new project (e.g., `fiverr-ai-agency`).
3. Enable the **Gmail API** for that project:
   - **APIs & Services** → **Library** → search "Gmail API" → **Enable**.
4. Configure the OAuth consent screen:
   - **APIs & Services** → **OAuth consent screen**.
   - User type: **External** (the only option for free Google accounts).
   - Fill in app name, support email, developer email. Other fields can be blank.
   - Scopes: skip the "Add or Remove Scopes" page — the scope is requested at runtime.
   - Test users: add your own Gmail address. While the app is in "Testing" mode, only test users can authorize it.
5. Create OAuth client credentials:
   - **APIs & Services** → **Credentials** → **Create credentials** → **OAuth client ID**.
   - Application type: **Desktop app**.
   - Name: anything (e.g., `fiverr-agency-cli`).
   - Click **Create**, then **Download JSON**.
6. Save the downloaded JSON as `credentials.json` in the directory where you'll run the orchestrator (typically `orchestrator/` or the repository root).

> **Why Desktop, not Web?** The CLI uses `InstalledAppFlow.run_local_server(...)` which spins up a local HTTP server on a random port to receive the OAuth redirect. That flow expects Desktop credentials. Web credentials would require hosting a callback URL.

## 3. Configure environment

In `.env`:

```dotenv
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token.json
GMAIL_LABEL_PENDING=Fiverr/Orders
GMAIL_LABEL_PROCESSED=FiverrAgency/Processed
GMAIL_LABEL_FAILED=FiverrAgency/Failed
INTAKE_POLL_INTERVAL_SECONDS=60
INTAKE_MAX_PER_CYCLE=10
```

The paths are resolved relative to the orchestrator's working directory.
Either set them as absolute paths or run the orchestrator from the directory
containing `credentials.json`.

## 4. Bootstrap the OAuth token

This is the one-time interactive step that produces `token.json`. Must be run
on a machine with a local browser (not over headless SSH).

```powershell
# from orchestrator/, with the venv activated and `pip install -e ".[dev]"` done
agency auth-gmail
```

What happens:

1. The CLI reads `credentials.json`.
2. Opens your default browser to Google's OAuth consent page.
3. You sign in and click **Allow**.
4. The browser redirects to `http://localhost:RANDOM_PORT/` where the CLI's local server captures the auth code.
5. The CLI exchanges it for a refresh token and writes `token.json`.

If you see "Google hasn't verified this app," that's because the consent
screen is still in Testing mode — click **Advanced** → **Go to <app> (unsafe)**.
This is fine because you authored the app yourself.

## 5. First run

With `token.json` in place:

```powershell
# Process the current backlog of Fiverr emails and exit
agency intake-once

# Or run the polling loop
agency intake-loop
```

`intake-once` exits 0 on full success, 1 if any email landed in
`FiverrAgency/Failed`.

## 6. Deploying to production

You have two options for the token file in production:

**Option A — Commit `token.json` to a secret manager**
Generate `token.json` locally via `agency auth-gmail`, then upload it as a
secret in Railway / your hosting platform. Mount it at the path referenced by
`GMAIL_TOKEN_FILE`.

**Option B — Inline JSON env var (future)**
Not yet supported by this CLI; would require a small change to
`GmailClient.connect` to read JSON from `GMAIL_TOKEN_JSON` instead of a file.
Track as a TODO when deploying.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `RuntimeError: Gmail token at ... is invalid` | Refresh token revoked or expired | Re-run `agency auth-gmail` |
| `HttpError 403: insufficient authentication scopes` | Token issued with a narrower scope | Delete `token.json` and re-run `auth-gmail` |
| Emails arrive at `Fiverr/Orders` but `intake-once` returns 0 processed | Polling label is wrong, or label name has a typo | Verify `GMAIL_LABEL_PENDING` matches the label as it appears in Gmail (case- and slash-sensitive) |
| Emails land in `FiverrAgency/Failed` repeatedly | Claude can't parse the email shape | Inspect the raw email; the parser logs `intake.runner.terminal_failure` with the error. Likely the email isn't a real order (marketing, account notification). Mark `intake_parser` agent's prompts for tuning. |
| Orchestrator processes the same email twice | Idempotency key didn't match a previous run, or the Processed label wasn't applied | Check `orders.idempotency_key` for the message id; verify the previous run completed and applied the label |
