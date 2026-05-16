"use client";

/**
 * Package review page — the operator's approval surface.
 *
 * Two-stage flow (Fiverr ToS requires a human to click their deliver button):
 *   1. Approve → flips package status to `approved`. Operator then goes to
 *      Fiverr in another tab and clicks deliver.
 *   2. Mark Delivered → flips package to `sent_to_fiverr` and order to `delivered`.
 *
 * Rejection sends the order back to `processing` so it can be retried or
 * fixed manually.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";

import type { PackageDetail } from "@/app/api/packages/[id]/route";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; detail: PackageDetail };

export default function PackagePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const [state, setState] = useState<State>({ kind: "loading" });
  const [message, setMessage] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [pending, setPending] = useState<null | "approve" | "reject" | "deliver">(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Load detail
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/packages/${id}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as PackageDetail;
        if (!cancelled) {
          setState({ kind: "ready", detail: data });
          setMessage(data.package.delivery_message);
        }
      } catch (e) {
        if (!cancelled) setState({ kind: "error", message: (e as Error).message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function doAction(
    action: "approve" | "reject" | "deliver",
    body: Record<string, unknown> = {},
  ) {
    setPending(action);
    setActionError(null);
    try {
      const path =
        action === "approve"
          ? "approve"
          : action === "reject"
            ? "reject"
            : "mark-delivered";
      const res = await fetch(`/api/packages/${id}/${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(err.error ?? `HTTP ${res.status}`);
      }
      // Reload the page state so status / buttons refresh
      router.refresh();
      const re = await fetch(`/api/packages/${id}`);
      if (re.ok) setState({ kind: "ready", detail: (await re.json()) as PackageDetail });
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setPending(null);
    }
  }

  if (state.kind === "loading") return <Centered>Loading…</Centered>;
  if (state.kind === "error") return <Centered tone="error">{state.message}</Centered>;

  const { package: pkg, order, deliverables } = state.detail;
  // Show overlay variants if present, else originals (matches packager logic)
  const overlays = deliverables.filter((d) => d.parent_deliverable_id);
  const displayDeliverables = overlays.length ? overlays : deliverables.filter((d) => !d.parent_deliverable_id);

  const isPending = pkg.status === "pending_approval";
  const isApproved = pkg.status === "approved";
  const isTerminal = pkg.status === "sent_to_fiverr" || pkg.status === "rejected";

  return (
    <main className="mx-auto max-w-5xl p-6 text-sm">
      <header className="mb-6 flex items-center justify-between">
        <Link
          href="/"
          className="text-xs text-[var(--color-text-dim)] hover:text-[var(--color-text)]"
        >
          ← Control Room
        </Link>
        <StatusBadge status={pkg.status} />
      </header>

      <h1 className="mb-1 text-lg font-semibold">Order {order.id.slice(0, 8)}</h1>
      <p className="mb-4 text-[var(--color-text-dim)]">
        <span className="capitalize">{order.service_type.replace(/_/g, " ")}</span>
        {order.client_username && <> · @{order.client_username}</>}
      </p>

      <section className="mb-6 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
        <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
          Original brief
        </h2>
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{order.brief}</p>
      </section>

      <section className="mb-6">
        <h2 className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
          Deliverables ({displayDeliverables.length})
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {displayDeliverables.map((d) => (
            <figure
              key={d.id}
              className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)]"
            >
              {/* Use the proxy so stale 7-day signed URLs auto-refresh.
                  eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/api/deliverables/${d.id}/file`}
                alt={d.file_name}
                className="block aspect-video w-full object-cover"
              />
              <figcaption className="flex items-center justify-between px-3 py-1.5 text-[11px] text-[var(--color-text-dim)]">
                <span>{d.file_name}</span>
                {d.technical_qc_passed === false && (
                  <span className="text-[var(--color-error)]">QC failed</span>
                )}
                {d.technical_qc_passed === true && (
                  <span className="text-[var(--color-completed)]">QC ✓</span>
                )}
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="mb-6">
        <label className="mb-2 block text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-dim)]">
          Delivery message
        </label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          disabled={!isPending}
          rows={8}
          className="w-full resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-panel)] p-3 font-mono text-xs leading-relaxed disabled:opacity-60"
        />
      </section>

      {actionError && (
        <div className="mb-4 rounded-md bg-[var(--color-error)]/15 px-3 py-2 text-xs text-[var(--color-error)]">
          {actionError}
        </div>
      )}

      {isPending && (
        <section className="flex flex-wrap gap-2">
          <ActionButton
            tone="primary"
            disabled={pending !== null}
            onClick={() => doAction("approve", { delivery_message: message })}
          >
            {pending === "approve" ? "Approving…" : "Approve"}
          </ActionButton>
          <details className="flex-1 min-w-[260px]">
            <summary className="cursor-pointer rounded-md border border-[var(--color-border)] px-3 py-2 text-center">
              Reject
            </summary>
            <div className="mt-2 flex gap-2">
              <input
                type="text"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Reason (required)"
                className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1.5 text-xs"
              />
              <ActionButton
                tone="danger"
                disabled={pending !== null || !rejectReason.trim()}
                onClick={() => doAction("reject", { reason: rejectReason })}
              >
                Confirm reject
              </ActionButton>
            </div>
          </details>
        </section>
      )}

      {isApproved && (
        <section className="rounded-lg border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/5 p-4">
          <h3 className="mb-1 text-sm font-semibold text-[var(--color-warn)]">
            Approved — now deliver on Fiverr
          </h3>
          <p className="mb-3 text-xs text-[var(--color-text-dim)]">
            Open the Fiverr order, paste the message above if you want, attach the ZIP from{" "}
            {pkg.zip_url ? (
              <a href={pkg.zip_url} className="underline" target="_blank" rel="noreferrer">
                this link
              </a>
            ) : (
              "the package"
            )}
            , and click Fiverr&apos;s deliver button. Then come back and mark as delivered.
          </p>
          <ActionButton
            tone="primary"
            disabled={pending !== null}
            onClick={() => doAction("deliver")}
          >
            {pending === "deliver" ? "Marking…" : "Mark as delivered"}
          </ActionButton>
        </section>
      )}

      {isTerminal && (
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-4 text-xs text-[var(--color-text-dim)]">
          {pkg.status === "sent_to_fiverr" ? "Delivered on Fiverr." : `Rejected: ${pkg.rejection_reason ?? ""}`}
        </section>
      )}
    </main>
  );
}

// ── tiny presentational helpers ──────────────────────────────────────────────

function Centered({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone?: "error";
}) {
  return (
    <main className="flex h-screen items-center justify-center text-sm">
      <p className={tone === "error" ? "text-[var(--color-error)]" : "text-[var(--color-text-dim)]"}>
        {children}
      </p>
    </main>
  );
}

function ActionButton({
  children,
  onClick,
  disabled,
  tone,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  tone: "primary" | "danger";
}) {
  const toneClass =
    tone === "primary"
      ? "bg-[var(--color-processing)] hover:opacity-90"
      : "bg-[var(--color-error)] hover:opacity-90";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-4 py-2 text-xs font-semibold text-white disabled:opacity-50 ${toneClass}`}
    >
      {children}
    </button>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color = {
    pending_approval: "bg-[var(--color-warn)]",
    approved: "bg-[var(--color-processing)]",
    sent_to_fiverr: "bg-[var(--color-completed)]",
    rejected: "bg-[var(--color-error)]",
  }[status] ?? "bg-[var(--color-idle)]";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white ${color}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}
