import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { TruthEnvelope } from "../lib/truth-contract";
import { DecisionGraph } from "./DecisionGraph";
import { buildDecisionGraph } from "./decisionGraphAdapter";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function envelope(overrides: Partial<TruthEnvelope> = {}): TruthEnvelope {
  return {
    status: "REAL",
    source: "risk_evidence_mesh_evaluations",
    last_updated: "2026-06-08T00:00:00+00:00",
    stale_after_seconds: 300,
    truth_state: "ACTIVE_FRESH",
    data: {},
    warnings: [],
    errors: [],
    ...overrides
  };
}

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

function riskEvidenceSummary() {
  return {
    total_evaluations: 2,
    RISK_SUPPORT: 1,
    RISK_REVIEW: 1,
    RISK_BLOCK: 1,
    blocker_subtypes: { RISK_BLOCKED_NO_EDGE: 1 },
    critical_missing_counts: { ACTIVE_FRESH_TRUSTED_ORDERBOOK: 1 },
    optional_missing_counts: { SOCIAL_CONTEXT_MISSING: 1 },
    risk_source_selection_summary: [{ selected_risk_source: "RISK_EVIDENCE_MESH", selected_risk_source_freshness: "ACTIVE_FRESH", count: 1 }],
    latest_evaluations: [
      {
        evaluation_id: "risk-eval-1",
        subject_id: "candidate-graph-1",
        market_id: "market-1",
        risk_decision: "RISK_REVIEW",
        risk_blocker_subtype: "STALE_ORDERBOOK",
        edge_source_type: "PRICE_PAYOUT_ASYMMETRY",
        evidence_quality_score: 0.82,
        truth_state: "ACTIVE_FRESH"
      }
    ],
    latest_risk_review_traces: [
      {
        decision_id: "trace-1",
        subject_id: "candidate-graph-1",
        actionability_class: "HARD_BLOCK",
        market_id: "market-1",
        side: "YES"
      }
    ]
  };
}

function lifecycleSummary(includeBlockers = true) {
  return {
    total_decisions: 1,
    latest_decisions: [
      {
        decision_id: "decision-1",
        subject_id: "candidate-graph-1",
        actionability_class: "HARD_BLOCK",
        reason: "STALE_ORDERBOOK",
        allow_paper_intent: false,
        allow_paper_execution: false
      }
    ],
    latest_risk_review_traces: [
      {
        decision_id: "trace-1",
        subject_id: "candidate-graph-1",
        actionability_class: "HARD_BLOCK",
        market_id: "market-1",
        side: "YES"
      }
    ],
    critical_blockers_top: includeBlockers ? [{ value: "STALE_ORDERBOOK", count: 1 }] : [],
    risk_source_selection_summary: [{ selected_risk_source: "RISK_EVIDENCE_MESH", selected_risk_source_freshness: "ACTIVE_FRESH", count: 1 }],
    stale_legacy_risk_block_ignored_count: 1
  };
}

function meshDialogueSummary() {
  return {
    events: [
      {
        brain_name: "coordinator",
        event_type: "brain_dialogue.risk_review",
        message: "Risk review stayed blocked by evidence.",
        status: "BLOCKED",
        confidence: 0.71
      }
    ],
    count: 1,
    latest_event_at: "2026-06-08T00:01:00+00:00"
  };
}

function responseForUrl(url: string) {
  if (url.includes("/decision-xray")) {
    return envelope({
      status: "PARTIAL",
      source: "risk_evidence_mesh_source",
      truth_state: "REFRESH_REQUIRED",
      data: { risk_evidence: riskEvidenceSummary(), approval_claimed: false, risk_gate_bypassed: false }
    });
  }

  if (url.includes("/risk-evidence")) {
    return envelope({
      data: { risk_evidence: riskEvidenceSummary(), approval_claimed: false, risk_gate_bypassed: false }
    });
  }

  if (url.includes("/lifecycle-governance")) {
    return envelope({
      source: "lifecycle_governance",
      data: { lifecycle_governance: lifecycleSummary(), actions_triggered: [] }
    });
  }

  if (url.includes("/mesh-dialogues")) {
    return envelope({
      source: "brain_dialogue_events",
      data: { mesh_dialogues: meshDialogueSummary(), dialogue_invented: false }
    });
  }

  return envelope({ status: "PARTIAL", source: "stage12_fallback", truth_state: "REFRESH_REQUIRED" });
}

describe("Stage 12 decision graph adapter and component", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", ResizeObserverStub);
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => Promise.resolve(jsonResponse(responseForUrl(String(input))))));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates graph nodes only from provided backend-like evidence data", () => {
    const graph = buildDecisionGraph(
      "decision-xray",
      envelope({ data: { risk_evidence: { latest_evaluations: [riskEvidenceSummary().latest_evaluations[0]] } } })
    );

    expect(graph.nodes.map((node) => node.data.label)).toEqual(expect.arrayContaining(["risk_evidence_mesh_evaluations", "candidate-graph-1", "RISK_REVIEW", "STALE_ORDERBOOK"]));
    expect(graph.nodes.map((node) => node.data.label)).not.toContain("APPROVED");
  });

  it("creates blocker nodes only when blockers are provided", () => {
    const withoutBlocker = buildDecisionGraph(
      "decision-xray",
      envelope({ data: { risk_evidence: { latest_evaluations: [{ evaluation_id: "risk-eval-no-blocker", subject_id: "candidate-no-blocker", risk_decision: "RISK_SUPPORT" }] } } })
    );

    expect(withoutBlocker.nodes.map((node) => node.data.category)).not.toContain("Blocker");
    expect(withoutBlocker.nodes.map((node) => node.data.label)).not.toContain("MISSING_EXIT_PLAN");
  });

  it("returns an honest missing graph when source data is missing", () => {
    const graph = buildDecisionGraph("decision-xray", envelope({ status: "MISSING", source: null, truth_state: "UNKNOWN", data: {} }));

    expect(graph.nodes).toHaveLength(0);
    expect(graph.messages).toContain("Graph source is missing; graph nodes are withheld.");
    expect(graph.messages).toContain("Graph source returned MISSING; no graph facts are invented.");
  });

  it("shows stale legacy ignored and non-risk blockers only when provided", () => {
    const withBlockers = buildDecisionGraph("candidate-lifecycle", envelope({ source: "lifecycle_governance", data: { lifecycle_governance: lifecycleSummary(true) } }));
    const withoutBlockers = buildDecisionGraph("candidate-lifecycle", envelope({ source: "lifecycle_governance", data: { lifecycle_governance: lifecycleSummary(false) } }));

    expect(withBlockers.nodes.map((node) => node.data.label)).toContain("STALE_ORDERBOOK");
    expect(withBlockers.nodes.map((node) => node.data.label)).toContain("RISK_EVIDENCE_MESH");
    expect(withoutBlockers.nodes.filter((node) => node.data.category === "Non-Risk Blocker")).toHaveLength(0);
  });

  it("DecisionGraph renders missing state honestly", () => {
    render(<DecisionGraph kind="decision-xray" envelope={envelope({ status: "MISSING", source: null, truth_state: "UNKNOWN", data: {} })} />);

    expect(screen.getByText("Graph source is missing; graph nodes are withheld.")).toBeInTheDocument();
    expect(screen.getByTestId("decision-graph-decision-xray-empty")).toBeInTheDocument();
    expect(screen.queryByText(/^APPROVED$/i)).not.toBeInTheDocument();
  });

  it("DecisionGraph renders nodes for provided evidence and blockers", async () => {
    render(<DecisionGraph kind="decision-xray" envelope={envelope({ data: { risk_evidence: riskEvidenceSummary() } })} />);

    expect(await screen.findByTestId("decision-graph-decision-xray")).toBeInTheDocument();
    expect(screen.getAllByText("candidate-graph-1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("STALE_ORDERBOOK").length).toBeGreaterThan(0);
    expect(screen.getAllByText("RISK_BLOCKED_NO_EDGE").length).toBeGreaterThan(0);
  });

  it("renders graph panels in Decision Intelligence pages without dangerous controls or fake claims", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Decision" }));
    const page = await screen.findByTestId("page-decision-xray");

    await waitFor(() => expect(within(page).getByText("Decision X-Ray Graph")).toBeInTheDocument());
    expect(within(page).getByTestId("decision-graph-decision-xray")).toBeInTheDocument();
    expect(within(page).getAllByText("candidate-graph-1").length).toBeGreaterThan(0);
    expect(within(page).queryByRole("button", { name: /system on|system off|start run|stop run|kill switch|reset balance|execute|order/i })).not.toBeInTheDocument();
    expect(within(page).queryByText(/fake approval|fake green|fake pnl|fake runtime status/i)).not.toBeInTheDocument();
    expect(within(page).queryByText(/^APPROVED$/i)).not.toBeInTheDocument();
  });

  it("renders the Brain Flow graph from real dialogue events only", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Mesh Dialogues" }));
    const page = await screen.findByTestId("page-mesh-dialogues");

    await waitFor(() => expect(within(page).getByText("Brain Flow Graph")).toBeInTheDocument());
    expect(within(page).getAllByText("coordinator").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("brain_dialogue.risk_review").length).toBeGreaterThan(0);
    expect(within(page).queryByText("coordinator invented summary")).not.toBeInTheDocument();
  });
});
