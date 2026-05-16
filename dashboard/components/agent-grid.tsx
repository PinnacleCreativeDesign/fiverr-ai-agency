"use client";

/**
 * Live agent grid powered by @xyflow/react.
 *
 * Receives an array of agents (static config) and a map of agent_id →
 * agent_status (live state). Renders one custom node per agent, positioned
 * via `position_x` / `position_y` from the DB. Status color + last log are
 * derived from the live status map.
 *
 * Edges are intentionally omitted in this MVP — the column layout conveys
 * pipeline flow without the visual noise of N×M cross-layer connections.
 * Add explicit edges later when individual orders need traced paths.
 */

import {
  Background,
  BackgroundVariant,
  Controls,
  type Node,
  type NodeProps,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import { useMemo } from "react";

import type { Agent, AgentStatus } from "@/lib/supabase";

interface AgentNodeData extends Record<string, unknown> {
  agent: Agent;
  status: AgentStatus | undefined;
}

type AgentFlowNode = Node<AgentNodeData, "agent">;

const STATUS_STYLES: Record<
  "idle" | "processing" | "error",
  { ring: string; pill: string; pillText: string }
> = {
  idle: {
    ring: "ring-1 ring-[var(--color-border)]",
    pill: "bg-[var(--color-idle)]",
    pillText: "idle",
  },
  processing: {
    ring: "ring-2 ring-[var(--color-processing)] agent-processing",
    pill: "bg-[var(--color-processing)]",
    pillText: "processing",
  },
  error: {
    ring: "ring-2 ring-[var(--color-error)]",
    pill: "bg-[var(--color-error)]",
    pillText: "error",
  },
};

function AgentNode({ data }: NodeProps<AgentFlowNode>) {
  const { agent, status } = data;
  const state = status?.current_status ?? "idle";
  const styles = STATUS_STYLES[state];

  return (
    <div
      className={`w-[240px] rounded-lg bg-[var(--color-panel)] p-3 text-left ${styles.ring}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium leading-tight text-[var(--color-text)]">
          {agent.display_name}
        </span>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white ${styles.pill}`}
        >
          {styles.pillText}
        </span>
      </div>
      <div
        className="mt-1 line-clamp-2 text-[11px] text-[var(--color-text-dim)]"
        title={status?.last_log ?? agent.description}
      >
        {status?.last_log ?? agent.description}
      </div>
      <div className="mt-2 flex items-center gap-3 text-[10px] text-[var(--color-text-dim)]">
        <span>runs {status?.total_runs ?? 0}</span>
        {(status?.total_errors ?? 0) > 0 && (
          <span className="text-[var(--color-error)]">
            errors {status?.total_errors}
          </span>
        )}
      </div>
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

const LAYER_LABELS: { key: Agent["layer"]; label: string; x: number }[] = [
  { key: "coordination", label: "Coordination", x: 0 },
  { key: "creative", label: "Creative", x: 280 },
  { key: "generation", label: "Generation", x: 560 },
  { key: "editing", label: "Editing", x: 840 },
  { key: "quality", label: "Quality", x: 1120 },
  { key: "delivery", label: "Delivery", x: 1400 },
];

export interface AgentGridProps {
  agents: Agent[];
  statusByAgentId: Map<string, AgentStatus>;
}

export function AgentGrid({ agents, statusByAgentId }: AgentGridProps) {
  const nodes: AgentFlowNode[] = useMemo(
    () =>
      agents.map((agent) => ({
        id: agent.id,
        type: "agent" as const,
        position: { x: agent.position_x, y: agent.position_y + 60 }, // +60 to clear layer banner
        data: { agent, status: statusByAgentId.get(agent.id) },
        draggable: false,
        selectable: false,
      })),
    [agents, statusByAgentId],
  );

  return (
    <div className="relative h-full w-full">
      {/* Layer banner pinned at top of canvas */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex h-12 items-center px-4">
        {LAYER_LABELS.map((l) => (
          <div
            key={l.key}
            className="absolute text-xs font-semibold uppercase tracking-wider text-[var(--color-text-dim)]"
            style={{ left: l.x + 16 }}
          >
            {l.label}
          </div>
        ))}
      </div>

      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={[]}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag
          zoomOnScroll
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#1e1f24" />
          <Controls showInteractive={false} className="!bg-[var(--color-panel)]" />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
