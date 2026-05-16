/**
 * GET /api/deliverables/[id]/file
 *
 * Server-side proxy that regenerates a fresh 1-hour signed URL and 307-redirects
 * to it. Lets the dashboard use a stable URL pattern in <img src> tags without
 * worrying about the 7-day TTL on the signed URLs stored in `deliverables.file_url`.
 *
 * Why redirect instead of streaming bytes through Next.js:
 *   * Cheap — no edge bandwidth on the deliverable payload itself.
 *   * Lets the browser cache the underlying signed URL response for the hour.
 *
 * The `deliverables` bucket is currently the only target — package ZIPs use a
 * separate path. If that changes, look up bucket from the row.
 */

import { NextResponse } from "next/server";

import { getServerClient } from "@/lib/supabase";

const SIGNED_URL_TTL_SECONDS = 3600;

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const supabase = getServerClient();

  const { data, error } = await supabase
    .from("deliverables")
    .select("metadata, file_url")
    .eq("id", id)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ error: "deliverable not found" }, { status: 404 });
  }

  const storagePath = (data.metadata as { storage_path?: string } | null)?.storage_path;
  if (!storagePath) {
    // Fall back to the stored URL — older rows may not have storage_path.
    if (typeof data.file_url === "string" && data.file_url.startsWith("http")) {
      return NextResponse.redirect(data.file_url, 307);
    }
    return NextResponse.json({ error: "no storage path on deliverable" }, { status: 422 });
  }

  const { data: signed, error: signErr } = await supabase.storage
    .from("deliverables")
    .createSignedUrl(storagePath, SIGNED_URL_TTL_SECONDS);

  if (signErr || !signed) {
    return NextResponse.json(
      { error: signErr?.message ?? "failed to sign" },
      { status: 500 },
    );
  }

  return NextResponse.redirect(signed.signedUrl, 307);
}
