/**
 * POST /api/packages/[id]/reject
 *
 * Body: { reason: string }
 * Action: flips status to `rejected` with reason. The order goes back to
 *         `processing` so the operator can re-run generation or fix manually.
 */

import { NextResponse } from "next/server";

import { getServerClient } from "@/lib/supabase";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const body = (await req.json().catch(() => ({}))) as { reason?: string };
  const reason = (body.reason ?? "").trim();
  if (!reason) {
    return NextResponse.json(
      { error: "reason is required" },
      { status: 400 },
    );
  }

  const supabase = getServerClient();

  // Reject the package
  const pkgRes = await supabase
    .from("delivery_packages")
    .update({ status: "rejected", rejection_reason: reason })
    .eq("id", id)
    .eq("status", "pending_approval")
    .select("order_id")
    .single();

  if (pkgRes.error) {
    return NextResponse.json({ error: pkgRes.error.message }, { status: 400 });
  }

  // Send the order back to processing so it can be retried
  await supabase
    .from("orders")
    .update({ status: "processing" })
    .eq("id", pkgRes.data.order_id);

  return NextResponse.json({ ok: true }, { status: 200 });
}
