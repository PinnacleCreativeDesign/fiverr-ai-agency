/**
 * POST /api/packages/[id]/mark-delivered
 *
 * Called AFTER the operator has manually clicked Fiverr's deliver button.
 * Flips the package to `sent_to_fiverr` and the parent order to `delivered`.
 * Refuses to advance unless the package is currently `approved`.
 */

import { NextResponse } from "next/server";

import { getServerClient } from "@/lib/supabase";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const supabase = getServerClient();

  const pkgRes = await supabase
    .from("delivery_packages")
    .update({ status: "sent_to_fiverr" })
    .eq("id", id)
    .eq("status", "approved")
    .select("order_id")
    .single();

  if (pkgRes.error) {
    return NextResponse.json({ error: pkgRes.error.message }, { status: 400 });
  }

  await supabase
    .from("orders")
    .update({ status: "delivered" })
    .eq("id", pkgRes.data.order_id);

  return NextResponse.json({ ok: true }, { status: 200 });
}
