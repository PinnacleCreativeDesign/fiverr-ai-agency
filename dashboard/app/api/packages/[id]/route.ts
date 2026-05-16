/**
 * GET /api/packages/[id] — full package detail for the review page.
 * Returns the package row, its order, and all deliverables for that order.
 */

import { NextResponse } from "next/server";

import {
  type DeliveryPackage,
  type Order,
  getServerClient,
} from "@/lib/supabase";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export interface Deliverable {
  id: string;
  order_id: string;
  parent_deliverable_id: string | null;
  file_url: string;
  file_name: string;
  file_type: string;
  dimensions: { width: number; height: number; dpi: number } | null;
  variant_index: number;
  quality_score: number | null;
  technical_qc_passed: boolean | null;
  is_approved: boolean;
  created_at: string;
}

export interface PackageDetail {
  package: DeliveryPackage;
  order: Order;
  deliverables: Deliverable[];
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const supabase = getServerClient();

  const pkgRes = await supabase
    .from("delivery_packages")
    .select("*")
    .eq("id", id)
    .maybeSingle();

  if (pkgRes.error) {
    return NextResponse.json({ error: pkgRes.error.message }, { status: 500 });
  }
  const pkg = pkgRes.data as DeliveryPackage | null;
  if (!pkg) {
    return NextResponse.json({ error: "package not found" }, { status: 404 });
  }

  const [orderRes, delsRes] = await Promise.all([
    supabase.from("orders").select("*").eq("id", pkg.order_id).single(),
    supabase
      .from("deliverables")
      .select("*")
      .eq("order_id", pkg.order_id)
      .order("variant_index"),
  ]);

  if (orderRes.error || delsRes.error) {
    return NextResponse.json(
      { error: orderRes.error?.message ?? delsRes.error?.message },
      { status: 500 },
    );
  }

  const detail: PackageDetail = {
    package: pkg,
    order: orderRes.data as Order,
    deliverables: (delsRes.data ?? []) as Deliverable[],
  };

  return NextResponse.json(detail, { headers: { "Cache-Control": "no-store" } });
}
