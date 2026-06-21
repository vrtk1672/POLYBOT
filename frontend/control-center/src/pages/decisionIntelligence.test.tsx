import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { TruthEnvelope } from "../lib/truth-contract";

function envelope(overrides: Partial<TruthEnvelope> = {}): TruthEnvelope {
  return {
    status: "PARTIAL",
    source: "stage10_test_source",
    last_updated: "2026-06-08T00:00:00+00:00",
    stale_after_seconds: 300,
    truth_state: "REFRESH_REQUIRED",
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
    status: "OK",
    generated_at: "2026-06-08T00:00:00+00:00",
    security_governance_status: "YELLOW_ACCEPTED_BY_OPERATOR",
    total_evaluations: 3,
    RISK_SUPPORT: 1,
    RISK_WATCH: 0,
    RISK_REVIEW: 1,
    RISK_BLOCK: 1,
    avg_evidence_quality_score: 0.77,
    blocker_subtypes: { RISK_BLOCKED_NO_EDGE: 1, STALE_RISK_DECISION: 1 },
    critical_missing_counts: { ACTIVE_FRESH_TRUSTED_ORDERBOOK: 1 },
    optional_missing_counts: { SOCIAL_CONTEXT_MISSING: 1 },
    edge_source_type_counts: { PRICE_PAYOUT_ASYMMETRY: 1 },
    stale_legacy_risk_block_ignored_count: 1,
    legacy_risk_ignored_count: 1,
    risk_source_selection_summary: [
      { selected_risk_source: "RISK_EVIDENCE_MESH", selected_risk_source_freshness: "ACTIVE_FRESH", count: 2 }
    ],
    latest_risk_review_traces: [
      {
        decision_id: "governance-1",
        subject_id: "subject-review",
        actionability_class: "HARD_BLOCK",
        market_id: "market-1",
        side: "YES"
      }
    ],
    closest_to_actionable_risk_subjects: [
      {
        subject_id: "candidate-a",
        market_id: "market-a",
        risk_decision: "RISK_REVIEW",
        risk_blocker_subtype: "STALE_ORDERBOOK",
        truth_state: "ACTIVE_FRESH"
      },
      {
        subject_id: "candidate-without-truth",
        market_id: "market-b",
        risk_decision: "RISK_SUPPORT"
      }
    ],
    latest_evaluations: [
      {
        evaluation_id: "risk-eval-1",
        subject_id: "subject-review",
        risk_decision: "RISK_REVIEW",
        risk_blocker_subtype: "STALE_ORDERBOOK",
        edge_source_type: "PRICE_PAYOUT_ASYMMETRY",
        evidence_quality_score: 0.82,
        created_at: "2026-06-08T00:01:00+00:00"
      }
    ]
  };
}

function lifecycleSummary() {
  return {
    status: "OK",
    generated_at: "2026-06-08T00:00:00+00:00",
    security_governance_status: "YELLOW_ACCEPTED_BY_OPERATOR",
    total_decisions: 4,
    decisions_by_actionability: { HARD_BLOCK: 3, WATCH_FOR_CONFIRMATION: 1 },
    allow_paper_intent_count: 0,
    allow_paper_execution_count: 0,
    hard_block_count: 3,
    risk_evidence_used_count: 2,
    legacy_risk_ignored_count: 1,
    stale_legacy_risk_block_ignored_count: 1,
    risk_review_promoted_to_watch_count: 1,
    risk_review_kept_blocked_count: 1,
    risk_review_actionable_count: 0,
    critical_blockers_top: [{ value: "STALE_ORDERBOOK", count: 2 }],
    risk_source_selection_summary: [
      { selected_risk_source: "RISK_EVIDENCE_MESH", selected_risk_source_freshness: "ACTIVE_FRESH", count: 2 }
    ],
    latest_decisions: [
      {
        decision_id: "decision-1",
        subject_id: "subject-review",
        actionability_class: "HARD_BLOCK",
        allow_paper_intent: false,
        allow_paper_execution: false,
        reason: "STALE_ORDERBOOK",
        created_at: "2026-06-08T00:02:00+00:00"
      }
    ],
    latest_risk_review_traces: [
      {
        decision_id: "decision-1",
        subject_id: "subject-review",
        actionability_class: "HARD_BLOCK",
        market_id: "market-1",
        side: "YES"
      }
    ]
  };
}

function responseForUrl(url: string) {
  if (url.includes("/decision-xray")) {
    return envelope({
      status: "PARTIAL",
      source: "risk_evidence_mesh_source",
      truth_state: "REFRESH_REQUIRED",
      data: { risk_evidence: riskEvidenceSummary(), decision_visibility: "read_only", approval_claimed: false },
      warnings: ["decision warning"],
      errors: ["decision error detail"]
    });
  }

  if (url.includes("/blockers")) {
    return envelope({
      status: "PARTIAL",
      source: "no_trade_log_risk_evidence_mesh",
      truth_state: "REFRESH_REQUIRED",
      data: {
        blockers: {
          no_trade: {
            status: "OK",
            total_no_trade_records: 2,
            top_no_trade_reasons: [{ reason: "MISSING_EXIT_PLAN", count: 1 }],
            missing_requirements_summary: [{ requirement: "ACTIVE_FRESH_TRUSTED_ORDERBOOK", count: 1 }],
            latest_no_trade: [{ subject_id: "no-trade-1", category: "MISSING_DATA", reason: "MISSING_EXIT_PLAN" }]
          },
          risk_evidence: riskEvidenceSummary()
        },
        read_only: true
      },
      warnings: ["blocker partial warning"]
    });
  }

  if (url.includes("/closest-actionable")) {
    return envelope({
      status: "PARTIAL",
      source: "risk_evidence_mesh_candidates",
      truth_state: "REFRESH_REQUIRED",
      data: {
        candidates: riskEvidenceSummary().closest_to_actionable_risk_subjects,
        count: 2,
        read_only: true
      },
      warnings: ["candidate truth required"]
    });
  }

  if (url.includes("/truth-state")) {
    return envelope({
      status: "REAL",
      source: "truth_state_registry",
      truth_state: "ACTIVE_FRESH",
      data: {
        status: "OK",
        truth_state_counts: {
          ACTIVE_FRESH: 7,
          LAST_KNOWN: 3,
          HISTORICAL_ONLY: 2,
          REFRESH_REQUIRED: 5,
          UNKNOWN: 1
        },
        source_state_counts: [{ source_type: "ORDERBOOK_SNAPSHOT", truth_state: "REFRESH_REQUIRED", count: 2 }],
        latest_truth: [{ truth_id: "truth-1", source_type: "RISK_DECISION", truth_state: "ACTIVE_FRESH", decision_permission: "CAN_AUTHORIZE" }]
      }
    });
  }

  if (url.includes("/risk-evidence")) {
    return envelope({
      status: "REAL",
      source: "risk_evidence_mesh_evaluations",
      truth_state: "ACTIVE_FRESH",
      data: { risk_evidence: riskEvidenceSummary(), risk_gate_bypassed: false, approval_claimed: false },
      warnings: ["risk evidence is display only"]
    });
  }

  if (url.includes("/lifecycle-governance")) {
    return envelope({
      status: "REAL",
      source: "lifecycle_governance",
      truth_state: "ACTIVE_FRESH",
      data: { lifecycle_governance: lifecycleSummary(), read_only: true, actions_triggered: [] },
      warnings: ["non-risk stale gates still block"]
    });
  }

  if (url.includes("/mesh-dialogues")) {
    return envelope({
      status: "MISSING",
      source: "brain_dialogue_events",
      truth_state: "UNKNOWN",
      data: {
        mesh_dialogues: { events: [], count: 0, latest_event_at: null, read_only: true },
        dialogue_invented: false
      },
      warnings: ["True brain/mesh dialogue events are absent; no dialogue is invented."]
    });
  }

  return envelope({
    status: "PARTIAL",
    source: "stage10_fallback_source",
    truth_state: "REFRESH_REQUIRED",
    data: {},
    warnings: ["fallback read-only envelope"]
  });
}

const dangerousControlLabels = [
  /^SYSTEM ON$/i,
  /^SYSTEM OFF$/i,
  /^START RUN$/i,
  /^STOP RUN$/i,
  /^KILL$/i,
  /^KILL SWITCH$/i,
  /^RESET BALANCE$/i,
  /^RESET PAPER BALANCE$/i
];

const fakeClaims = [/fake green/i, /fake approval/i, /fake pnl/i, /fake runtime status/i, /^SYSTEM ONLINE$/i, /^SYSTEM HEALTHY$/i];

describe("Stage 10 decision intelligence pages", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => Promise.resolve(jsonResponse(responseForUrl(String(input))))));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("Decision X-Ray renders backend truth status, source, warnings, and errors", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Decision" }));
    const page = await screen.findByTestId("page-decision-xray");

    await waitFor(() => expect(within(page).getByText("Decision Evidence Summary")).toBeInTheDocument());
    expect(within(page).getAllByText("PARTIAL").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("risk_evidence_mesh_source").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("decision warning").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("decision error detail").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("subject-review").length).toBeGreaterThan(0);
  });

  it("Blocker Center renders blockers and preserves partial state", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Blocker Center" }));
    const page = await screen.findByTestId("page-blocker-center");

    await waitFor(() => expect(within(page).getAllByText("MISSING_EXIT_PLAN").length).toBeGreaterThan(0));
    expect(within(page).getAllByText("PARTIAL").length).toBeGreaterThan(0);
    expect(within(page).getByText("ACTIVE_FRESH_TRUSTED_ORDERBOOK")).toBeInTheDocument();
    expect(within(page).getByText("RISK_EVIDENCE_MESH")).toBeInTheDocument();
    expect(within(page).getByText("STALE_RISK_DECISION")).toBeInTheDocument();
  });

  it("Closest to Actionable renders candidates only when truth_state is present", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Closest to Actionable" }));
    const page = await screen.findByTestId("page-closest-actionable");

    await waitFor(() => expect(within(page).getByText("candidate-a")).toBeInTheDocument());
    expect(within(page).getByText("ACTIVE_FRESH")).toBeInTheDocument();
    expect(within(page).queryByText("candidate-without-truth")).not.toBeInTheDocument();
    expect(within(page).getByText("1 candidate row(s) were omitted because truth_state was missing.")).toBeInTheDocument();
  });

  it("Truth State renders the expected truth vocabulary when present", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Truth State" }));
    const page = await screen.findByTestId("page-truth-state");

    await waitFor(() => expect(within(page).getAllByText("ACTIVE_FRESH").length).toBeGreaterThan(0));
    for (const state of ["ACTIVE_FRESH", "LAST_KNOWN", "HISTORICAL_ONLY", "REFRESH_REQUIRED", "UNKNOWN"]) {
      expect(within(page).getAllByText(state).length).toBeGreaterThan(0);
    }
    expect(within(page).getByText("ORDERBOOK_SNAPSHOT")).toBeInTheDocument();
  });

  it("Risk Evidence Mesh renders risk evidence and does not claim approval", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Risk Evidence Mesh" }));
    const page = await screen.findByTestId("page-risk-evidence-mesh");

    await waitFor(() => expect(within(page).getByText("Risk Evidence Truth")).toBeInTheDocument());
    expect(within(page).getAllByText("RISK_SUPPORT").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("RISK_REVIEW").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("RISK_BLOCK").length).toBeGreaterThan(0);
    expect(within(page).getByText("PRICE_PAYOUT_ASYMMETRY")).toBeInTheDocument();
    expect(within(page).getAllByText("false").length).toBeGreaterThan(0);
    expect(within(page).queryByText(/^APPROVED$/i)).not.toBeInTheDocument();
  });

  it("Lifecycle Governance renders actionability state and blockers", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Lifecycle Governance" }));
    const page = await screen.findByTestId("page-lifecycle-governance");

    await waitFor(() => expect(within(page).getByText("Governance Outcome")).toBeInTheDocument());
    expect(within(page).getAllByText("HARD_BLOCK").length).toBeGreaterThan(0);
    expect(within(page).getByText("WATCH_FOR_CONFIRMATION")).toBeInTheDocument();
    expect(within(page).getAllByText("STALE_ORDERBOOK").length).toBeGreaterThan(0);
    expect(within(page).getByText("non-risk stale gates still block")).toBeInTheDocument();
  });

  it("Mesh Dialogues renders no invented dialogue when source is missing", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Mesh Dialogues" }));
    const page = await screen.findByTestId("page-mesh-dialogues");

    await waitFor(() => expect(within(page).getByText("Brain / Mesh Dialogue Events")).toBeInTheDocument());
    expect(within(page).getAllByText("MISSING").length).toBeGreaterThan(0);
    expect(within(page).getByText("No brain dialogue events were returned. The UI will not invent dialogue.")).toBeInTheDocument();
    expect(within(page).getAllByText("false").length).toBeGreaterThan(0);
    expect(within(page).queryByText("coordinator invented summary")).not.toBeInTheDocument();
  });

  it("manual refresh remains read-only and no dangerous/fake controls appear", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Decision" }));
    const refresh = await screen.findByRole("button", { name: "Refresh read-only data" });
    await user.click(refresh);

    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(1));
    for (const [, init] of vi.mocked(fetch).mock.calls) {
      expect(init?.method).toBe("GET");
    }
    for (const label of dangerousControlLabels) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
    for (const claim of fakeClaims) {
      expect(screen.queryByText(claim)).not.toBeInTheDocument();
    }
  });
});
