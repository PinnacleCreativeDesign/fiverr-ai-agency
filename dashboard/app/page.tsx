"use client";

/**
 * Control-room dashboard.
 *
 * Polls `/api/dashboard` every NEXT_PUBLIC_POLL_INTERVAL_MS (default 2000 ms)
 * and re-renders the grid + sidebar. Service-role lives on the server; this
 * client only sees the materialized snapshot.
 *
 * Future: swap polling for `supabase.channel(...).subscribe()` once auth is
 * wired so Realtime can honor RLS for the operator session.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AgentGrid } from "@/components/agent-grid";
import type { AgentStatus, Order, OrderStatus } from "@/lib/supabase";
import type { DashboardSnapshot } from "@/app/api/dashboard/route";

const POLL_INTERVAL_MS = Number(
  process.env.NEXT_PUBLIC_POLL_INTERVAL_MS ?? "2000",
);

export default function DashboardPage() {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    let cancelled = false;

    async function fetchOnce() {
      try {
        const res = await fetch("/api/dashboard", { signal: ac.signal });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as DashboardSnapshot;
        if (!cancelled) {
          setSnapshot(data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled && (e as Error).name !== "AbortError") {
          setError((e as Error).message);
        }
      }
    }

    fetchOnce();
    const t = setInterval(fetchOnce, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      ac.abort();
      clearInterval(t);
    };
  }, []);

  const statusByAgentId = useMemo(() => {
    const m = new Map<string, AgentStatus>();
    for (const s of snapshot?.agentStatus ?? []) m.set(s.agent_id, s);
    return m;
  }, [snapshot?.agentStatus]);

  return (
    <main className="grid h-screen grid-cols-[1fr_320px] grid-rows-[48px_1fr]">
      {/* Top bar */}
      <header className="col-span-2 flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-panel)] px-4">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold">Fiverr AI Agency — Control Room</span>
          {error && (
            <span className="rounded bg-[var(--color-error)]/20 px-2 py-0.5 text-xs text-[var(--color-error)]">
              {error}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs text-[var(--color-text-dim)]">
          {snapshot && (
            <>
              <Stat
                label="Active"
                value={snapshot.counts.activeAgents}
                tone={snapshot.counts.activeAgents > 0 ? "ok" : "dim"}
              />
              <Stat
                label="Errors"
                value={snapshot.counts.erroredAgents}
                tone={snapshot.counts.erroredAgents > 0 ? "bad" : "dim"}
              />
              <Stat label="Pending" value={snapshot.counts.pendingOrders} tone="dim" />
              <Stat
                label="Approval"
                value={snapshot.counts.packagesAwaitingApproval}
                tone={
                  snapshot.counts.packagesAwaitingApproval > 0 ? "warn" : "dim"
                }
              />
              <span className="text-[10px] opacity-60">
                {new Date(snapshot.fetchedAt).toLocaleTimeString()}
              </span>
            </>
          )}
        </div>
      </header>

      {/* Grid */}
      <section className="overflow-hidden border-r border-[var(--color-border)]">
        {snapshot ? (
          <AgentGrid agents={snapshot.agents} statusByAgentId={statusByAgentId} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-dim)]">
            Loading agents…
          </div>
        )}
      </section>

      {/* Sidebar */}
      <aside className="overflow-y-auto bg-[var(--color-panel)] p-3 text-xs">
        <SidebarSection title="Recent orders">
          {snapshot?.recentOrders.length ? (
            <ul className="space-y-1.5">
              {snapshot.recentOrders.slice(0, 10).map((o) => (
                <li
                  key={o.id}
                  className="rounded border border-[var(--color-border)] p-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] opacity-70">
                      {o.id.slice(0, 8)}
                    </span>
                    <OrderStatusPill status={o.status} />
                  </div>
                  <div className="mt-0.5 truncate">
                    <span className="text-[var(--color-text-dim)]">
                      {o.service_type}
                    </span>
                    {o.client_username && (
                      <span className="ml-1 opacity-60">@{o.client_username}</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No orders yet.</Empty>
          )}
        </SidebarSection>

        <SidebarSection title="Awaiting approval">
          {snapshot?.pendingPackages.length ? (
            <ul className="space-y-1.5">
              {snapshot.pendingPackages.map((p) => (
                <li key={p.id}>
                  <Link
                    href={`/packages/${p.id}`}
                    className="block rounded border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/5 p-2 transition hover:bg-[var(--color-warn)]/10"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[10px] opacity-70">
                        order {p.order_id.slice(0, 8)}
                      </span>
                      <span className="text-[10px] text-[var(--color-warn)]">Review →</span>
                    </div>
                    <div className="mt-0.5 line-clamp-2 opacity-90">
                      {p.delivery_message}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Nothing waiting.</Empty>
          )}
        </SidebarSection>
      </aside>
    </main>
  );
}

// ── tiny presentational helpers ──────────────────────────────────────────────

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "dim" | "ok" | "warn" | "bad";
}) {
  const colorClass = {
    dim: "text-[var(--color-text-dim)]",
    ok: "text-[var(--color-completed)]",
    warn: "text-[var(--color-warn)]",
    bad: "text-[var(--color-error)]",
  }[tone];
  return (
    <span className={`tabular-nums ${colorClass}`}>
      {label} <span className="font-semibold">{value}</span>
    </span>
  );
}

function SidebarSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-4">
      <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded border border-dashed border-[var(--color-border)] p-2 text-center text-[var(--color-text-dim)]">
      {children}
    </div>
  );
}

const ORDER_STATUS_COLOR: Record<OrderStatus, string> = {
  pending: "bg-[var(--color-idle)]",
  clarification_needed: "bg-[var(--color-warn)]",
  awaiting_response: "bg-[var(--color-warn)]",
  processing: "bg-[var(--color-processing)]",
  qc: "bg-[var(--color-processing)]",
  ready_for_delivery: "bg-[var(--color-warn)]",
  delivered: "bg-[var(--color-completed)]",
  error: "bg-[var(--color-error)]",
  cancelled: "bg-[var(--color-idle)]",
};

function OrderStatusPill({ status }: { status: Order["status"] }) {
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-white ${ORDER_STATUS_COLOR[status]}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}
