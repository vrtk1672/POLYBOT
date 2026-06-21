import type { Edge, Node } from "@xyflow/react";

import type { TruthEnvelope, TruthStatus, TruthState } from "../lib/truth-contract";
import { asArray, asRecord, fieldText, type UnknownRecord } from "./visibilityUtils";

export type DecisionGraphKind = "decision-xray" | "brain-flow" | "candidate-lifecycle" | "conflict-map";

export type DecisionGraphNodeData = {
  label: string;
  category: string;
  detail: string;
  status: TruthStatus;
  truthState: TruthState;
};

export type DecisionGraphModel = {
  kind: DecisionGraphKind;
  title: string;
  status: TruthStatus;
  truthState: TruthState;
  source: string | null;
  nodes: Node<DecisionGraphNodeData>[];
  edges: Edge[];
  messages: string[];
};

type NodeDraft = {
  id: string;
  label: string;
  category: string;
  detail?: string;
  status?: TruthStatus;
  truthState?: TruthState;
  x: number;
  y: number;
};

const TITLE_BY_KIND: Record<DecisionGraphKind, string> = {
  "decision-xray": "Decision X-Ray Graph",
  "brain-flow": "Brain Flow Graph",
  "candidate-lifecycle": "Candidate Lifecycle Graph",
  "conflict-map": "Conflict Map Graph"
};

const BLOCKING_WORDS = ["BLOCK", "BLOCKED", "MISSING", "STALE", "HARD_BLOCK", "NO_TRADE", "ERROR"];

function makeId(prefix: string, raw: unknown, index: number) {
  const text = String(raw ?? `${prefix}-${index}`).trim() || `${prefix}-${index}`;
  return `${prefix}-${text.replace(/[^a-zA-Z0-9_-]+/g, "-").slice(0, 80)}-${index}`;
}

function addNode(nodes: NodeDraft[], draft: NodeDraft) {
  if (nodes.some((node) => node.id === draft.id)) return;
  nodes.push(draft);
}

function addEdge(edges: Edge[], source: string, target: string, label?: string) {
  if (!source || !target || source === target) return;
  const id = `${source}->${target}:${label ?? ""}`;
  if (edges.some((edge) => edge.id === id)) return;
  edges.push({
    id,
    source,
    target,
    label,
    type: "smoothstep",
    animated: false
  });
}

function toGraphNodes(envelope: TruthEnvelope, drafts: NodeDraft[]): Node<DecisionGraphNodeData>[] {
  return drafts.map((draft) => ({
    id: draft.id,
    type: "decisionGraphNode",
    position: { x: draft.x, y: draft.y },
    data: {
      label: draft.label,
      category: draft.category,
      detail: draft.detail ?? "",
      status: draft.status ?? envelope.status,
      truthState: draft.truthState ?? envelope.truth_state
    },
    draggable: false,
    selectable: false
  }));
}

function sourceNode(envelope: TruthEnvelope, nodes: NodeDraft[]) {
  if (!envelope.source) return null;
  const id = "source-envelope";
  addNode(nodes, {
    id,
    label: envelope.source,
    category: "Source",
    detail: `truth_state=${envelope.truth_state}`,
    x: 0,
    y: 120
  });
  return id;
}

function riskEvidencePayload(envelope: TruthEnvelope) {
  const data = asRecord(envelope.data);
  return asRecord(data.risk_evidence);
}

function lifecyclePayload(envelope: TruthEnvelope) {
  return asRecord(asRecord(envelope.data).lifecycle_governance);
}

function meshPayload(envelope: TruthEnvelope) {
  return asRecord(asRecord(envelope.data).mesh_dialogues);
}

function blockerStatus(text: string): TruthStatus {
  return BLOCKING_WORDS.some((word) => text.toUpperCase().includes(word)) ? "ERROR" : "PARTIAL";
}

function buildDecisionXray(envelope: TruthEnvelope, nodes: NodeDraft[], edges: Edge[]) {
  const source = sourceNode(envelope, nodes);
  const riskEvidence = riskEvidencePayload(envelope);
  const evaluations = asArray(riskEvidence.latest_evaluations);
  const criticalMissing = asRecord(riskEvidence.critical_missing_counts);
  const blockerSubtypes = asRecord(riskEvidence.blocker_subtypes);

  evaluations.slice(0, 10).forEach((row, index) => {
    const subject = fieldText(row, ["subject_id", "candidate_id", "market_id"], "");
    const evaluation = fieldText(row, ["evaluation_id", "risk_decision"], "");
    if (!subject && !evaluation) return;

    const candidateId = makeId("candidate", subject || evaluation, index);
    const evidenceId = makeId("risk-evidence", evaluation || subject, index);
    addNode(nodes, {
      id: candidateId,
      label: subject || "UNKNOWN_SUBJECT",
      category: "Candidate",
      detail: fieldText(row, ["market_id", "side", "truth_state"], "source-backed row"),
      x: 260,
      y: index * 130
    });
    addNode(nodes, {
      id: evidenceId,
      label: fieldText(row, ["risk_decision", "evaluation_id"], "RISK_EVIDENCE"),
      category: "Risk Evidence",
      detail: fieldText(row, ["edge_source_type", "risk_blocker_subtype", "evidence_quality_score"], "evidence row"),
      status: blockerStatus(fieldText(row, ["risk_decision", "risk_blocker_subtype"], "")),
      x: 560,
      y: index * 130
    });
    if (source) addEdge(edges, source, candidateId, "reads");
    addEdge(edges, candidateId, evidenceId, "evaluated by");

    const blocker = fieldText(row, ["risk_blocker_subtype"], "");
    if (blocker) {
      const blockerId = makeId("blocker", blocker, index);
      addNode(nodes, {
        id: blockerId,
        label: blocker,
        category: "Blocker",
        detail: "backend risk_blocker_subtype",
        status: blockerStatus(blocker),
        x: 870,
        y: index * 130
      });
      addEdge(edges, evidenceId, blockerId, "reports");
    }
  });

  Object.entries(criticalMissing).forEach(([name, count], index) => {
    const nodeId = makeId("critical-missing", name, index);
    addNode(nodes, {
      id: nodeId,
      label: name,
      category: "Evidence",
      detail: `missing_count=${String(count)}`,
      status: "MISSING",
      x: 870,
      y: 380 + index * 110
    });
    if (source) addEdge(edges, source, nodeId, "missing");
  });

  Object.entries(blockerSubtypes).forEach(([name, count], index) => {
    const nodeId = makeId("blocker-subtype", name, index);
    addNode(nodes, {
      id: nodeId,
      label: name,
      category: "Blocker",
      detail: `count=${String(count)}`,
      status: blockerStatus(name),
      x: 1180,
      y: index * 110
    });
    if (source) addEdge(edges, source, nodeId, "blocked by");
  });
}

function buildConflictMap(envelope: TruthEnvelope, nodes: NodeDraft[], edges: Edge[]) {
  const source = sourceNode(envelope, nodes);
  const riskEvidence = riskEvidencePayload(envelope);
  const blockerSubtypes = asRecord(riskEvidence.blocker_subtypes);
  const criticalMissing = asRecord(riskEvidence.critical_missing_counts);
  const optionalMissing = asRecord(riskEvidence.optional_missing_counts);
  const riskSourceSelection = asArray(riskEvidence.risk_source_selection_summary);

  Object.entries(blockerSubtypes).forEach(([name, count], index) => {
    const nodeId = makeId("risk-blocker", name, index);
    addNode(nodes, {
      id: nodeId,
      label: name,
      category: "Risk Evidence",
      detail: `count=${String(count)}`,
      status: blockerStatus(name),
      x: 300,
      y: index * 120
    });
    if (source) addEdge(edges, source, nodeId, "risk blocker");
  });

  Object.entries(criticalMissing).forEach(([name, count], index) => {
    const nodeId = makeId("critical", name, index);
    addNode(nodes, {
      id: nodeId,
      label: name,
      category: "Non-Risk Blocker",
      detail: `critical_missing=${String(count)}`,
      status: "MISSING",
      x: 620,
      y: index * 120
    });
    if (source) addEdge(edges, source, nodeId, "critical");
  });

  Object.entries(optionalMissing).forEach(([name, count], index) => {
    const nodeId = makeId("optional", name, index);
    addNode(nodes, {
      id: nodeId,
      label: name,
      category: "Evidence",
      detail: `optional_missing=${String(count)}`,
      status: "PARTIAL",
      x: 940,
      y: index * 120
    });
    if (source) addEdge(edges, source, nodeId, "optional");
  });

  riskSourceSelection.slice(0, 8).forEach((row, index) => {
    const selected = fieldText(row, ["selected_risk_source", "source"], "");
    if (!selected) return;
    const nodeId = makeId("risk-source", selected, index);
    addNode(nodes, {
      id: nodeId,
      label: selected,
      category: "Legacy Risk",
      detail: fieldText(row, ["selected_risk_source_freshness", "truth_state", "count"], "source selection"),
      status: fieldText(row, ["selected_risk_source_freshness", "truth_state"], "").includes("STALE") ? "STALE" : "PARTIAL",
      x: 300,
      y: 420 + index * 110
    });
    if (source) addEdge(edges, source, nodeId, "selected");
  });
}

function buildCandidateLifecycle(envelope: TruthEnvelope, nodes: NodeDraft[], edges: Edge[]) {
  const source = sourceNode(envelope, nodes);
  const lifecycle = lifecyclePayload(envelope);
  const decisions = asArray(lifecycle.latest_decisions);
  const traces = asArray(lifecycle.latest_risk_review_traces);
  const criticalGates = asArray(lifecycle.critical_blockers_top);
  const riskSourceSelection = asArray(lifecycle.risk_source_selection_summary);

  decisions.slice(0, 8).forEach((row, index) => {
    const subject = fieldText(row, ["subject_id", "candidate_id", "market_id"], "");
    const decision = fieldText(row, ["decision_id", "actionability_class"], "");
    if (!subject && !decision) return;
    const candidateId = makeId("candidate", subject || decision, index);
    const gateId = makeId("lifecycle-gate", decision || subject, index);
    addNode(nodes, {
      id: candidateId,
      label: subject || "UNKNOWN_SUBJECT",
      category: "Candidate",
      detail: fieldText(row, ["market_id", "side"], "lifecycle decision row"),
      x: 260,
      y: index * 140
    });
    addNode(nodes, {
      id: gateId,
      label: fieldText(row, ["actionability_class", "decision_id"], "LIFECYCLE_GATE"),
      category: "Lifecycle Gate",
      detail: fieldText(row, ["reason", "allow_paper_intent", "allow_paper_execution"], "governance decision"),
      status: blockerStatus(fieldText(row, ["actionability_class", "reason"], "")),
      x: 590,
      y: index * 140
    });
    if (source) addEdge(edges, source, candidateId, "reads");
    addEdge(edges, candidateId, gateId, "governed by");
  });

  traces.slice(0, 8).forEach((row, index) => {
    const subject = fieldText(row, ["subject_id", "decision_id"], "");
    if (!subject) return;
    const traceId = makeId("risk-review-trace", subject, index);
    addNode(nodes, {
      id: traceId,
      label: fieldText(row, ["actionability_class", "subject_id"], "RISK_REVIEW_TRACE"),
      category: "Risk Evidence",
      detail: fieldText(row, ["market_id", "side", "selected_risk_source"], "risk review trace"),
      status: blockerStatus(fieldText(row, ["actionability_class"], "")),
      x: 920,
      y: index * 140
    });
    if (source) addEdge(edges, source, traceId, "trace");
  });

  criticalGates.slice(0, 8).forEach((row, index) => {
    const blocker = fieldText(row, ["value", "blocker", "name"], "");
    if (!blocker) return;
    const blockerId = makeId("critical-gate", blocker, index);
    addNode(nodes, {
      id: blockerId,
      label: blocker,
      category: "Non-Risk Blocker",
      detail: `count=${fieldText(row, ["count"], "UNKNOWN")}`,
      status: blockerStatus(blocker),
      x: 1220,
      y: index * 120
    });
    if (source) addEdge(edges, source, blockerId, "still blocks");
  });

  riskSourceSelection.slice(0, 8).forEach((row, index) => {
    const selected = fieldText(row, ["selected_risk_source", "source"], "");
    if (!selected) return;
    const nodeId = makeId("selected-risk-source", selected, index);
    addNode(nodes, {
      id: nodeId,
      label: selected,
      category: "Legacy Risk",
      detail: fieldText(row, ["selected_risk_source_freshness", "count"], "risk source selection"),
      status: fieldText(row, ["selected_risk_source_freshness"], "").includes("STALE") ? "STALE" : "PARTIAL",
      x: 1220,
      y: 420 + index * 110
    });
    if (source) addEdge(edges, source, nodeId, "source priority");
  });
}

function buildBrainFlow(envelope: TruthEnvelope, nodes: NodeDraft[], edges: Edge[]) {
  const source = sourceNode(envelope, nodes);
  const mesh = meshPayload(envelope);
  const events = asArray(mesh.events);

  events.slice(0, 14).forEach((row, index) => {
    const speaker = fieldText(row, ["brain_name", "source", "speaker", "role"], "");
    const eventType = fieldText(row, ["event_type", "status", "conflict"], "");
    if (!speaker && !eventType) return;
    const brainId = makeId("brain", speaker || eventType, index);
    const eventId = makeId("dialogue-event", eventType || speaker, index);
    addNode(nodes, {
      id: brainId,
      label: speaker || "MESH_SOURCE",
      category: speaker.toUpperCase().includes("COORDINATOR") ? "Coordinator" : "Mesh Dialogue",
      detail: fieldText(row, ["opinion", "confidence", "status"], "dialogue source"),
      x: 280,
      y: index * 120
    });
    addNode(nodes, {
      id: eventId,
      label: eventType || "DIALOGUE_EVENT",
      category: "Mesh Dialogue",
      detail: fieldText(row, ["message", "coordinator_summary", "final_summary", "conflict"], "dialogue event"),
      status: blockerStatus(fieldText(row, ["conflict", "status"], "")),
      x: 650,
      y: index * 120
    });
    if (source) addEdge(edges, source, brainId, "dialogue");
    addEdge(edges, brainId, eventId, "emits");
  });
}

export function buildDecisionGraph(kind: DecisionGraphKind, envelope: TruthEnvelope): DecisionGraphModel {
  const nodeDrafts: NodeDraft[] = [];
  const edges: Edge[] = [];
  const messages: string[] = [];

  if (!envelope.source) {
    messages.push("Graph source is missing; graph nodes are withheld.");
  }

  if (envelope.status === "ERROR") {
    messages.push("Graph source returned ERROR; no decision graph is inferred.");
  }

  if (envelope.status === "MISSING") {
    messages.push("Graph source returned MISSING; no graph facts are invented.");
  }

  if (envelope.status === "NOT_IMPLEMENTED") {
    messages.push("Graph source is NOT_IMPLEMENTED.");
  }

  if (envelope.status !== "ERROR" && envelope.source) {
    if (kind === "decision-xray") buildDecisionXray(envelope, nodeDrafts, edges);
    if (kind === "conflict-map") buildConflictMap(envelope, nodeDrafts, edges);
    if (kind === "candidate-lifecycle") buildCandidateLifecycle(envelope, nodeDrafts, edges);
    if (kind === "brain-flow") buildBrainFlow(envelope, nodeDrafts, edges);
  }

  if (!nodeDrafts.length) {
    messages.push("No source-backed graph rows were present in this envelope.");
  }

  return {
    kind,
    title: TITLE_BY_KIND[kind],
    status: envelope.status,
    truthState: envelope.truth_state,
    source: envelope.source,
    nodes: toGraphNodes(envelope, nodeDrafts),
    edges,
    messages
  };
}
