/**
 * GET /api/dashboard — single endpoint returning everything the dashboard
 * needs to render one frame. Server-only; uses the service-role client.
 *
 * The frontend polls this every ~2s. One round-trip per refresh keeps the
 * dashboard's network panel readable and avoids N+1 fan-out on the DB.
 */

import { NextResponse } from "next/server";

import {
  type Agent,
  type AgentStatus,
  type DeliveryPackage,
  type Order,
  getServerClient,
} from "@/lib/supabase";

export const dynamic = "force-dynamic"; // no caching
export const revalidate = 0;

export interface DashboardSnapshot {
  agents: Agent[];
  agentStatus: AgentStatus[];
  recentOrders: Order[];
  pendingPackages: DeliveryPackage[];
  counts: {
    pendingOrders: number;
    processingOrders: number;
    packagesAwaitingApproval: number;
    activeAgents: number;
    erroredAgents: number;
  };
  fetchedAt: string;
}

export async function GET(): Promise<NextResponse> {
  const supabase = getServerClient();

  // Fire all reads concurrently — service-role bypasses RLS, no auth latency.
  const [agentsRes, statusRes, ordersRes, packagesRes] = await Promise.all([
    supabase.from("agents").select("*").order("layer").order("layer_order"),
    supabase.from("agent_status").select("*"),
    supabase
      .from("orders")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(25),
    supabase
      .from("delivery_packages")
      .select("*")
      .eq("status", "pending_approval")
      .order("created_at", { ascending: false }),
  ]);

  for (const r of [agentsRes, statusRes, ordersRes, packagesRes]) {
    if (r.error) {
      return NextResponse.json(
        { error: r.error.message },
        { status: 500 },
      );
    }
  }

  const agents = (agentsRes.data ?? []) as Agent[];
  const agentStatus = (statusRes.data ?? []) as AgentStatus[];
  const orders = (ordersRes.data ?? []) as Order[];
  const packages = (packagesRes.data ?? []) as DeliveryPackage[];

  const snapshot: DashboardSnapshot = {
    agents,
    agentStatus,
    recentOrders: orders,
    pendingPackages: packages,
    counts: {
      pendingOrders: orders.filter((o) => o.status === "pending").length,
      processingOrders: orders.filter(
        (o) => o.status === "processing" || o.status === "qc",
      ).length,
      packagesAwaitingApproval: packages.length,
      activeAgents: agentStatus.filter((s) => s.current_status === "processing")
        .length,
      erroredAgents: agentStatus.filter((s) => s.current_status === "error")
        .length,
    },
    fetchedAt: new Date().toISOString(),
  };

  return NextResponse.json(snapshot, {
    headers: { "Cache-Control": "no-store" },
  });
}
