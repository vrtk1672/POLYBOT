import { Background, Handle, Position, ReactFlow, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Panel } from "../layout/Panel";
import type { TruthEnvelope, TruthStatus } from "../lib/truth-contract";
import { buildDecisionGraph, type DecisionGraphKind, type DecisionGraphNodeData } from "./decisionGraphAdapter";

const statusClass: Record<TruthStatus, string> = {
  REAL: "border-poly-cyan/70 bg-poly-cyan/10 text-poly-text",
  PARTIAL: "border-poly-partial/70 bg-poly-partial/10 text-poly-text",
  STALE: "border-poly-stale/70 bg-poly-stale/10 text-poly-text",
  MISSING: "border-poly-missing/70 bg-poly-missing/10 text-poly-muted",
  ERROR: "border-poly-error/70 bg-poly-error/10 text-poly-text",
  LOCKED: "border-poly-locked/70 bg-poly-locked/10 text-poly-text",
  NOT_IMPLEMENTED: "border-poly-missing/70 bg-poly-missing/10 text-poly-muted"
};

function DecisionGraphNode({ data }: NodeProps) {
  const nodeData = data as DecisionGraphNodeData;
  return (
    <div className={`min-w-52 max-w-64 rounded-md border p-3 shadow-truth ${statusClass[nodeData.status]}`}>
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-poly-line !bg-poly-cyan" />
      <p className="text-[10px] font-semibold uppercase tracking-normal text-poly-muted">{nodeData.category}</p>
      <p className="mt-1 break-words text-sm font-semibold">{nodeData.label}</p>
      <p className="mt-2 break-words text-xs text-poly-muted">{nodeData.detail || "source-backed graph node"}</p>
      <p className="mt-2 text-[10px] uppercase text-poly-subtle">
        {nodeData.status} / {nodeData.truthState}
      </p>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-poly-line !bg-poly-cyan" />
    </div>
  );
}

const nodeTypes = {
  decisionGraphNode: DecisionGraphNode
};

export function DecisionGraph({ kind, envelope, title }: { kind: DecisionGraphKind; envelope: TruthEnvelope; title?: string }) {
  const graph = buildDecisionGraph(kind, envelope);
  const hasGraph = graph.nodes.length > 0;

  return (
    <Panel title={title ?? graph.title} eyebrow="React Flow read-only">
      <div className="space-y-3">
        <div className="flex flex-wrap gap-2 text-xs">
          <span className={`rounded-md border px-2 py-1 ${statusClass[graph.status]}`}>status: {graph.status}</span>
          <span className="rounded-md border border-poly-line px-2 py-1 text-poly-muted">truth_state: {graph.truthState}</span>
          <span className="rounded-md border border-poly-line px-2 py-1 text-poly-muted">source: {graph.source ?? "SOURCE_MISSING"}</span>
          <span className="rounded-md border border-poly-line px-2 py-1 text-poly-muted">nodes: {graph.nodes.length}</span>
          <span className="rounded-md border border-poly-line px-2 py-1 text-poly-muted">edges: {graph.edges.length}</span>
        </div>
        {graph.messages.length ? (
          <ul className="space-y-1 text-sm text-poly-muted">
            {graph.messages.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        ) : null}
        {hasGraph ? (
          <div className="h-[420px] overflow-hidden rounded-md border border-poly-line bg-poly-bg/70" data-testid={`decision-graph-${kind}`}>
            <ReactFlow
              nodes={graph.nodes}
              edges={graph.edges}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.25 }}
              nodesDraggable={false}
              nodesConnectable={false}
              edgesFocusable={false}
              nodesFocusable={false}
              elementsSelectable={false}
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#2d3f5f" gap={22} />
            </ReactFlow>
          </div>
        ) : (
          <div className="rounded-md border border-poly-missing/50 bg-poly-missing/10 p-4 text-sm text-poly-muted" data-testid={`decision-graph-${kind}-empty`}>
            No source-backed graph nodes were returned. The graph remains empty instead of inventing decisions, blockers, dialogue, or actionability.
          </div>
        )}
      </div>
    </Panel>
  );
}
