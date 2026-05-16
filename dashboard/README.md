# Dashboard

Live operator view of the 19-agent pipeline. Next.js 15 (App Router) +
`@xyflow/react` v12 + Tailwind v4 + Supabase JS.

## Architecture

```
┌──────────────────────┐   GET (every 2s)   ┌─────────────────────────────┐
│  app/page.tsx        │ ─────────────────► │  app/api/dashboard/route.ts │
│  (client component)  │                    │  (service-role read)        │
│  • AgentGrid         │ ◄───────────────── │  • agents                   │
│  • Sidebar           │   DashboardSnapshot│  • agent_status             │
└──────────────────────┘                    │  • orders (recent 25)       │
                                            │  • delivery_packages        │
                                            │    (pending_approval)       │
                                            └─────────────────────────────┘
```

The service-role key lives **only** in `SUPABASE_SERVICE_ROLE_KEY` (no
`NEXT_PUBLIC_` prefix), so Next.js refuses to bundle it into client code.
The browser fetches a sanitized snapshot from the API route.

## Layout

```
dashboard/
├── package.json
├── tsconfig.json
├── next.config.ts
├── postcss.config.mjs
├── .env.example
├── app/
│   ├── layout.tsx
│   ├── page.tsx                 # main dashboard
│   ├── globals.css              # Tailwind v4 + xyflow styles + theme tokens
│   └── api/
│       └── dashboard/
│           └── route.ts         # single GET endpoint
├── components/
│   └── agent-grid.tsx           # @xyflow/react grid + custom AgentNode
└── lib/
    └── supabase.ts              # service-role client + DB types
```

## Install + run

```powershell
cd dashboard
npm install
cp .env.example .env.local
# fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, NEXT_PUBLIC_SUPABASE_URL,
# NEXT_PUBLIC_SUPABASE_ANON_KEY
npm run dev
# open http://localhost:3000
```

## What you see

- **Top bar**: live counters (active agents, errors, pending orders, packages awaiting approval) and last-refresh timestamp.
- **Center**: agent grid laid out left-to-right by pipeline layer. Each node shows display name, status pill (`idle` / `processing` / `error`), the latest `last_log` string, and run/error counts. Processing agents pulse blue. Errored agents border in red.
- **Right sidebar**: recent 10 orders with status pills, and any delivery packages waiting on operator approval.

## Polling vs Realtime

This MVP polls `/api/dashboard` every `NEXT_PUBLIC_POLL_INTERVAL_MS` (default
2000 ms). The trade-off is intentional:

| | Polling (current) | Realtime (future) |
|---|---|---|
| Auth required | No — service-role on server | Yes — RLS demands authenticated user |
| Latency | 0–2 s | <100 ms |
| Bandwidth | One JSON per 2 s | Per-change deltas |
| Setup | Zero | Login page + middleware + `@supabase/ssr` |

Swap path: once auth lands, replace the `useEffect` poller in `app/page.tsx`
with a `supabase.channel("agent-status").on("postgres_changes", …).subscribe()`
that updates `snapshot.agentStatus`. The component shape doesn't change.

## Codex-review notes

- `DashboardSnapshot` type is exported from the API route and imported into
  the client page. One source of truth for the frame contract.
- `getServerClient()` is a lazy singleton so multiple API routes in the same
  process share one connection.
- React Flow nodes are non-draggable, non-selectable — this is a status view,
  not an editor. Prevents accidental layout drift.
- No edges between nodes in the MVP. Columns convey flow; explicit per-order
  paths can be drawn later when needed.
- Tailwind v4 in CSS-first mode: theme tokens live in `globals.css` under
  `@theme {}`, no `tailwind.config.ts`.

## Next milestones (not in this iteration)

- Order detail page: full brief, deliverable previews, approve / reject buttons.
- Server action `POST /api/packages/[id]/approve` that flips `status` to
  `approved` (operator still clicks deliver on Fiverr manually).
- Supabase Auth + Realtime upgrade path.
