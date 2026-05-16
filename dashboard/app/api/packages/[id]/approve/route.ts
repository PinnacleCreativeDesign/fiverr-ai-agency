/**
 * POST /api/packages/[id]/approve
 *
 * Body: { delivery_message: string }   // operator may have edited it
 * Action: flips status to `approved`, persists any edits to the message,
 *         stamps `approved_at` + `approved_by`.
 *
 * IMPORTANT: this does NOT deliver on Fiverr. Fiverr ToS requires a human to
 * click their deliver button. The operator runs `mark-delivered` after that.
 */

import { NextResponse } from "next/server";

import { getServerClient } from "@/lib/supabase";

interface ApproveBody {
  delivery_message?: string;
  approved_by?: string;
}

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const body = (await req.json().catch(() => ({}))) as ApproveBody;

  const update: Record<string, unknown> = {
    status: "approved",
    approved_at: new Date().toISOString(),
  };
  if (typeof body.delivery_message === "string" && body.delivery_message.trim()) {
    update.delivery_message = body.delivery_message.trim();
  }
  if (typeof body.approved_by === "string" && body.approved_by.trim()) {
    update.approved_by = body.approved_by.trim();
  }

  const res = await getServerClient()
    .from("delivery_packages")
    .update(update)
    .eq("id", id)
    .eq("status", "pending_approval") // refuse to re-approve / re-flip
    .select()
    .single();

  if (res.error) {
    return NextResponse.json({ error: res.error.message }, { status: 400 });
  }
  return NextResponse.json({ package: res.data }, { status: 200 });
}
