import type { ReactNode } from "react";

import type { DecisionStepData, PnLData, PositionData, TruthEnvelope, TruthState, TruthStatus } from "../../lib/truth-contract";

export const STORYBOOK_MARKER = "STORYBOOK_ONLY";
export const RUNTIME_MARKER = "NOT_CONNECTED_TO_RUNTIME";
export const DATA_MARKER = "NOT_REAL_DATA";
export const STORYBOOK_SOURCE = "storybook:fixture";
export const STORYBOOK_NOTICE = `${STORYBOOK_MARKER} / ${RUNTIME_MARKER} / ${DATA_MARKER}`;

const timestamp = "2026-06-08T08:00:00.000Z";

export function StorybookFrame({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="min-h-screen bg-poly-bg p-6 text-poly-text">
      <div className="mx-auto max-w-7xl space-y-4">
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4 shadow-truth">
          <p className="text-xs font-semibold uppercase text-poly-stale">{STORYBOOK_NOTICE}</p>
          <h1 className="mt-2 text-xl font-semibold">{title}</h1>
          <p className="mt-2 text-sm text-poly-muted">
            Static Storybook fixtures only. This canvas does not read APIs, start runtime, mutate state, or certify live health.
          </p>
        </div>
        {children}
      </div>
    </main>
  );
}

export function makeEnvelope<TData extends Record<string, unknown> = Record<string, unknown>>({
  status,
  truthState,
  source = STORYBOOK_SOURCE,
  data = {} as TData,
  warnings = [],
  errors = []
}: {
  status: TruthStatus;
  truthState: TruthState;
  source?: string | null;
  data?: TData;
  warnings?: string[];
  errors?: string[];
}): TruthEnvelope<TData> {
  return {
    status,
    source,
    last_updated: status === "MISSING" ? null : timestamp,
    stale_after_seconds: status === "STALE" ? 60 : 300,
    truth_state: truthState,
    data,
    warnings: [STORYBOOK_NOTICE, ...warnings],
    errors
  };
}

export const realEnvelopeFixture = makeEnvelope({
  status: "REAL",
  truthState: "ACTIVE_FRESH",
  data: { sample: STORYBOOK_NOTICE, source_truth: "fixture-only fresh source" }
});

export const staleEnvelopeFixture = makeEnvelope({
  status: "STALE",
  truthState: "LAST_KNOWN",
  data: { sample: STORYBOOK_NOTICE },
  warnings: ["Last known fixture state requires refresh before trust."]
});

export const missingEnvelopeFixture = makeEnvelope({
  status: "MISSING",
  truthState: "UNKNOWN",
  source: null,
  data: { sample: STORYBOOK_NOTICE },
  warnings: ["Required source is absent in this fixture."]
});

export const errorEnvelopeFixture = makeEnvelope({
  status: "ERROR",
  truthState: "REFRESH_REQUIRED",
  data: { sample: STORYBOOK_NOTICE },
  errors: ["Fixture error state; no backend error was read."]
});

export const partialEnvelopeFixture = makeEnvelope({
  status: "PARTIAL",
  truthState: "LAST_KNOWN",
  data: { sample: STORYBOOK_NOTICE },
  warnings: ["Fixture has partial source coverage."]
});

export const lockedEnvelopeFixture = makeEnvelope({
  status: "LOCKED",
  truthState: "HISTORICAL_ONLY",
  data: { sample: STORYBOOK_NOTICE },
  warnings: ["Fixture surface is locked; no permission is implied."]
});

export const notImplementedEnvelopeFixture = makeEnvelope({
  status: "NOT_IMPLEMENTED",
  truthState: "UNKNOWN",
  data: { sample: STORYBOOK_NOTICE },
  warnings: ["Fixture surface is intentionally not implemented."]
});

export const allStatusEnvelopes = [
  realEnvelopeFixture,
  staleEnvelopeFixture,
  missingEnvelopeFixture,
  errorEnvelopeFixture,
  lockedEnvelopeFixture,
  notImplementedEnvelopeFixture,
  partialEnvelopeFixture
];

export const truthStateEnvelopeFixtures = [
  makeEnvelope({ status: "REAL", truthState: "ACTIVE_FRESH", data: { state: "ACTIVE_FRESH" } }),
  makeEnvelope({ status: "STALE", truthState: "LAST_KNOWN", data: { state: "LAST_KNOWN" } }),
  makeEnvelope({ status: "LOCKED", truthState: "HISTORICAL_ONLY", data: { state: "HISTORICAL_ONLY" } }),
  makeEnvelope({ status: "ERROR", truthState: "REFRESH_REQUIRED", data: { state: "REFRESH_REQUIRED" } }),
  makeEnvelope({ status: "MISSING", truthState: "UNKNOWN", source: null, data: { state: "UNKNOWN" } })
];

export const decisionStepFixtures: Array<{ label: string; envelope: TruthEnvelope<DecisionStepData> }> = [
  {
    label: "Edge Evidence",
    envelope: makeEnvelope<DecisionStepData>({
      status: "REAL",
      truthState: "ACTIVE_FRESH",
      data: { evidence_source: STORYBOOK_SOURCE, approved: false, reason: STORYBOOK_NOTICE }
    })
  },
  {
    label: "Risk Evidence",
    envelope: makeEnvelope<DecisionStepData>({
      status: "PARTIAL",
      truthState: "LAST_KNOWN",
      data: { evidence_source: STORYBOOK_SOURCE, approved: false, reason: "Partial fixture evidence only." }
    })
  },
  {
    label: "Exit Evidence",
    envelope: makeEnvelope<DecisionStepData>({
      status: "MISSING",
      truthState: "UNKNOWN",
      source: null,
      data: { evidence_source: null, approved: false, reason: "Missing fixture source." }
    })
  }
];

export const pnlFixture: TruthEnvelope<PnLData> = makeEnvelope<PnLData>({
  status: "REAL",
  truthState: "ACTIVE_FRESH",
  data: {
    fake_pnl: true,
    realized_pnl: null,
    unrealized_pnl: null,
    net_pnl: null
  },
  warnings: ["Money values are intentionally hidden because this is a Storybook fixture."]
});

export const positionFixture: TruthEnvelope<PositionData> = makeEnvelope<PositionData>({
  status: "REAL",
  truthState: "ACTIVE_FRESH",
  data: {
    fake_positions: true,
    position_id: "STORYBOOK_FIXTURE_POSITION",
    market: "STORYBOOK_FIXTURE_MARKET",
    side: "UNKNOWN"
  },
  warnings: ["Position facts are intentionally hidden because this is a Storybook fixture."]
});

export const overviewFixture = makeEnvelope({
  status: "PARTIAL",
  truthState: "LAST_KNOWN",
  data: {
    source_counts: {
      service_health: 2,
      event_log: 3,
      runtime_incidents: 1
    },
    latest_rows: {
      service_health: { service_name: "STORYBOOK_SERVICE", last_heartbeat_at: timestamp },
      event_log: { event_type: "STORYBOOK_EVENT", stored_at: timestamp }
    },
    control_endpoints: ["/dashboard/api/v2/control/overview", "/dashboard/api/v2/control/live-flow"]
  },
  warnings: ["Overview page story uses partial fixture coverage."]
});

export const organHealthFixture = makeEnvelope({
  status: "STALE",
  truthState: "LAST_KNOWN",
  data: {
    count: 2,
    latest_heartbeat_at: timestamp,
    services: [
      { service_name: "STORYBOOK_MARKET_SERVICE", status: "LAST_KNOWN", last_heartbeat_at: timestamp },
      { service_name: "STORYBOOK_EVENT_SERVICE", status: "UNKNOWN", last_heartbeat_at: null }
    ]
  },
  warnings: ["Heartbeat rows are static fixture rows."]
});

export const liveFlowFixture = makeEnvelope({
  status: "REAL",
  truthState: "ACTIVE_FRESH",
  data: {
    count: 2,
    events: [
      { id: "storybook-event-1", event_type: "STORYBOOK_DATA_OBSERVED", stored_at: timestamp },
      { id: "storybook-event-2", event_type: "STORYBOOK_NO_TRADE_RECORDED", stored_at: timestamp }
    ]
  },
  warnings: ["Event rows are static fixture rows."]
});

export const logsErrorsFixture = makeEnvelope({
  status: "ERROR",
  truthState: "REFRESH_REQUIRED",
  data: {
    runtime_incidents: [{ id: "storybook-incident-1", incident_type: "STORYBOOK_INCIDENT", last_seen_at: timestamp }],
    event_delivery_attempts: [{ attempt_id: "storybook-attempt-1", status: "FAILED", finished_at: timestamp }],
    events: [{ event_id: "storybook-event-3", event_type: "STORYBOOK_EVENT", stored_at: timestamp }]
  },
  errors: ["Static fixture incident; no backend incident was fetched."]
});

export const decisionXrayFixture = makeEnvelope({
  status: "PARTIAL",
  truthState: "LAST_KNOWN",
  data: {
    approval_claimed: false,
    decision_visibility: STORYBOOK_NOTICE,
    risk_gate_bypassed: false,
    risk_evidence: {
      total_evaluations: 2,
      avg_evidence_quality_score: "UNKNOWN",
      security_governance_status: "STORYBOOK_ONLY",
      blocker_subtypes: { MISSING_EXIT_PLAN: 1 },
      critical_missing_counts: { EXIT_PLAN: 1 },
      latest_evaluations: [
        {
          subject_id: "STORYBOOK_SUBJECT",
          evaluation_id: "storybook-eval-1",
          risk_decision: "RISK_REVIEW",
          risk_blocker_subtype: "MISSING_EXIT_PLAN",
          edge_source_type: STORYBOOK_SOURCE,
          truth_state: "LAST_KNOWN"
        }
      ]
    }
  },
  warnings: ["Decision story makes no approval or actionability claim."]
});

export const blockerCenterFixture = makeEnvelope({
  status: "REAL",
  truthState: "ACTIVE_FRESH",
  data: {
    blockers: {
      no_trade: {
        total_no_trade_records: 1,
        latest_no_trade: [{ subject_id: "STORYBOOK_SUBJECT", reason: "MISSING_EVIDENCE", truth_state: "ACTIVE_FRESH" }],
        top_no_trade_reasons: [{ reason: "MISSING_EVIDENCE", count: 1 }],
        missing_requirements_summary: [{ requirement: "EXIT_PLAN", count: 1 }]
      },
      risk_evidence: {
        RISK_BLOCK: 1,
        blocker_subtypes: { MISSING_EVIDENCE: 1 },
        risk_source_selection_summary: [{ selected_risk_source: STORYBOOK_SOURCE, selected_risk_source_freshness: "ACTIVE_FRESH", count: 1 }],
        latest_risk_review_traces: [{ subject_id: "STORYBOOK_SUBJECT", actionability_class: "BLOCKED", market_id: "STORYBOOK_MARKET" }]
      }
    }
  }
});

export const truthStateFixture = makeEnvelope({
  status: "PARTIAL",
  truthState: "LAST_KNOWN",
  data: {
    truth_state_counts: {
      ACTIVE_FRESH: 1,
      LAST_KNOWN: 2,
      HISTORICAL_ONLY: 1,
      REFRESH_REQUIRED: 1,
      UNKNOWN: 1
    },
    source_state_counts: [{ source_type: STORYBOOK_SOURCE, truth_state: "LAST_KNOWN", count: 2 }],
    latest_truth: [{ truth_id: "storybook-truth-1", source_type: STORYBOOK_SOURCE, truth_state: "LAST_KNOWN", decision_permission: "NO" }]
  }
});

export const riskEvidenceFixture = makeEnvelope({
  status: "PARTIAL",
  truthState: "LAST_KNOWN",
  data: {
    risk_gate_bypassed: false,
    approval_claimed: false,
    risk_evidence: {
      total_evaluations: 1,
      RISK_SUPPORT: 0,
      RISK_WATCH: 0,
      RISK_REVIEW: 1,
      RISK_BLOCK: 0,
      edge_source_type_counts: { [STORYBOOK_SOURCE]: 1 },
      critical_missing_counts: { EXIT_PLAN: 1 },
      optional_missing_counts: { LIQUIDITY_CONTEXT: 1 },
      latest_evaluations: [{ subject_id: "STORYBOOK_SUBJECT", evaluation_id: "storybook-risk-1", risk_decision: "RISK_REVIEW", evidence_quality_score: "UNKNOWN" }],
      latest_risk_review_traces: [{ subject_id: "STORYBOOK_SUBJECT", actionability_class: "REVIEW", market_id: "STORYBOOK_MARKET" }]
    }
  }
});

export const lifecycleFixture = makeEnvelope({
  status: "LOCKED",
  truthState: "HISTORICAL_ONLY",
  data: {
    lifecycle_governance: {
      hard_block_count: 1,
      risk_review_promoted_to_watch_count: 0,
      risk_review_actionable_count: 0,
      allow_paper_intent_count: 0,
      allow_paper_execution_count: 0,
      legacy_risk_ignored_count: 0,
      decisions_by_actionability: { BLOCKED: 1 },
      critical_blockers_top: [{ value: "MISSING_EXIT_PLAN", count: 1 }],
      risk_source_selection_summary: [{ selected_risk_source: STORYBOOK_SOURCE, selected_risk_source_freshness: "HISTORICAL_ONLY", count: 1 }],
      latest_decisions: [{ subject_id: "STORYBOOK_SUBJECT", actionability_class: "BLOCKED", allow_paper_intent: false, allow_paper_execution: false }],
      latest_risk_review_traces: [{ subject_id: "STORYBOOK_SUBJECT", actionability_class: "BLOCKED", market_id: "STORYBOOK_MARKET" }]
    }
  },
  warnings: ["Locked fixture page exposes no action controls."]
});

export const meshDialogueFixture = makeEnvelope({
  status: "MISSING",
  truthState: "UNKNOWN",
  source: null,
  data: {
    dialogue_invented: false,
    mesh_dialogues: {
      count: 0,
      events: []
    }
  },
  warnings: ["No dialogue events are invented in Storybook."]
});

export const pnlLedgerFixture = makeEnvelope({
  status: "MISSING",
  truthState: "UNKNOWN",
  source: null,
  data: {
    pnl_ledger: {}
  },
  warnings: ["Ledger source missing in fixture; money values are withheld."]
});

export const capitalFixture = makeEnvelope({
  status: "NOT_IMPLEMENTED",
  truthState: "UNKNOWN",
  data: {},
  warnings: ["Dedicated capital source is not represented by this fixture."]
});

export const positionsFixture = makeEnvelope({
  status: "MISSING",
  truthState: "UNKNOWN",
  source: null,
  data: {
    positions: {}
  },
  warnings: ["Position source missing in fixture; rows are withheld."]
});

export const noTradeFixture = makeEnvelope({
  status: "REAL",
  truthState: "ACTIVE_FRESH",
  source: `${STORYBOOK_SOURCE}:no_trade_log`,
  data: {
    first_class_decision: "YES",
    no_trade: {
      total_no_trade_records: 1,
      latest_no_trade: [{ no_trade_id: "storybook-no-trade-1", primary_reason: "MISSING_EVIDENCE", truth_state: "ACTIVE_FRESH" }],
      top_no_trade_reasons: [{ reason: "MISSING_EVIDENCE", count: 1 }]
    }
  }
});
