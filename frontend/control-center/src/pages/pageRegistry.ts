import type { TruthStatus } from "../lib/truth-contract";
import type { ControlCenterEndpointKey } from "../api/controlCenterEndpoints";
import { controlCenterEndpoints } from "../api/controlCenterEndpoints";

export type PageId =
  | "overview"
  | "decision-xray"
  | "blocker-center"
  | "closest-actionable"
  | "truth-state"
  | "risk-evidence-mesh"
  | "lifecycle-governance"
  | "live-flow"
  | "pnl-ledger"
  | "positions"
  | "capital"
  | "organ-health"
  | "ai-brain"
  | "logs-errors"
  | "settings"
  | "mesh-dialogues"
  | "no-trade";

export type PageShellStatus = Extract<TruthStatus, "NOT_IMPLEMENTED" | "PARTIAL" | "LOCKED" | "MISSING">;

export type PageShellConfig = {
  id: PageId;
  label: string;
  title: string;
  purpose: string;
  endpointKey: ControlCenterEndpointKey | null;
  endpoint: string | null;
  status: PageShellStatus;
  stateLabel: "DEMO_ONLY" | "NOT_IMPLEMENTED" | "PARTIAL" | "LOCKED";
  summary: string;
  notes: string[];
};

export const PAGE_SHELLS: PageShellConfig[] = [
  {
    id: "overview",
    label: "Command Cockpit",
    title: "Command Cockpit",
    purpose: "Operator-first cockpit for system state, safe controls, live flow, run state, decision truth, and money truth.",
    endpointKey: "overview",
    endpoint: controlCenterEndpoints.overview,
    status: "PARTIAL",
    stateLabel: "DEMO_ONLY",
    summary: "Command Cockpit translates source-backed body status into operator-readable truth without inventing health.",
    notes: ["READ_ONLY visibility page.", "No runtime status is inferred beyond the Truth Contract envelope."]
  },
  {
    id: "decision-xray",
    label: "Decision",
    title: "Decision X-Ray",
    purpose: "Explains the decision chain, evidence gates, and no-trade reasons once connected.",
    endpointKey: "decisionXray",
    endpoint: controlCenterEndpoints.decisionXray,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Decision X-Ray shows read-only Risk Evidence decision traces without claiming approval.",
    notes: ["READ_ONLY decision intelligence page.", "No approval or trade readiness is displayed unless backend explicitly provides evidence."]
  },
  {
    id: "blocker-center",
    label: "Blocker Center",
    title: "Blocker Center",
    purpose: "Lists missing, stale, locked, or risk-blocking evidence when real blockers are available.",
    endpointKey: "blockers",
    endpoint: controlCenterEndpoints.blockers,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Blocker Center shows no-trade and risk-evidence blockers from read-only summaries.",
    notes: ["READ_ONLY decision intelligence page.", "No blocker count is invented."]
  },
  {
    id: "closest-actionable",
    label: "Closest to Actionable",
    title: "Closest to Actionable",
    purpose: "Shows candidates nearest to actionability only when every candidate has truth_state.",
    endpointKey: "closestActionable",
    endpoint: controlCenterEndpoints.closestActionable,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Closest to Actionable shows candidates only when backend supplies truth_state.",
    notes: ["READ_ONLY decision intelligence page.", "No candidate is promoted without truth_state."]
  },
  {
    id: "truth-state",
    label: "Truth State",
    title: "Truth State",
    purpose: "Surfaces Control Center truth vocabulary, freshness, and source coverage.",
    endpointKey: "truthState",
    endpoint: controlCenterEndpoints.truthState,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Truth State shows freshness, stale, historical, refresh-required, and unknown source truth.",
    notes: ["READ_ONLY decision intelligence page.", "No source is marked fresh by the frontend."]
  },
  {
    id: "risk-evidence-mesh",
    label: "Risk Evidence Mesh",
    title: "Risk Evidence Mesh",
    purpose: "Displays risk evidence and missing proof required before any decision can be trusted.",
    endpointKey: "riskEvidence",
    endpoint: controlCenterEndpoints.riskEvidence,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Risk Evidence Mesh shows risk evidence, edge source, blocker, and stale legacy risk handling summaries.",
    notes: ["READ_ONLY decision intelligence page.", "No risk approval is claimed."]
  },
  {
    id: "lifecycle-governance",
    label: "Lifecycle Governance",
    title: "Lifecycle Governance",
    purpose: "Shows lifecycle gates and governance evidence once read-only sources are connected.",
    endpointKey: "lifecycleGovernance",
    endpoint: controlCenterEndpoints.lifecycleGovernance,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Lifecycle Governance shows actionability, selected risk source, freshness, and blocking gates.",
    notes: ["READ_ONLY decision intelligence page.", "No lifecycle action is exposed."]
  },
  {
    id: "live-flow",
    label: "Live",
    title: "Live Flow",
    purpose: "Visualizes recent event flow from the read-only live-flow source.",
    endpointKey: "liveFlow",
    endpoint: controlCenterEndpoints.liveFlow,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Live flow shows recent event rows from the read-only live-flow envelope.",
    notes: ["READ_ONLY visibility page.", "No subscription or mutating flow control is exposed."]
  },
  {
    id: "pnl-ledger",
    label: "Money",
    title: "PnL & Ledger",
    purpose: "Shows ledger-backed paper PnL truth from the read-only paper ledger endpoint.",
    endpointKey: "pnlLedger",
    endpoint: controlCenterEndpoints.pnlLedger,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "PnL & Ledger displays money values only when the envelope source is ledger-backed.",
    notes: ["READ_ONLY money visibility page.", "No ledger value is displayed from a missing or non-ledger source."]
  },
  {
    id: "positions",
    label: "Positions",
    title: "Positions",
    purpose: "Shows canonical paper position truth from the read-only positions endpoint.",
    endpointKey: "positions",
    endpoint: controlCenterEndpoints.positions,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Positions displays canonical position rows only from paper_positions-backed data.",
    notes: ["READ_ONLY money visibility page.", "Orders and fills are not displayed as positions."]
  },
  {
    id: "capital",
    label: "Capital",
    title: "Capital",
    purpose: "Displays overview-backed capital availability only when overview contains a capital section.",
    endpointKey: "overview",
    endpoint: controlCenterEndpoints.overview,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Capital uses overview because no dedicated capital endpoint exists in the Stage 5 map.",
    notes: ["READ_ONLY money visibility page.", "If overview lacks capital reconciliation, balances are withheld."]
  },
  {
    id: "organ-health",
    label: "Organ Health",
    title: "Organ Health",
    purpose: "Shows organ/service health only when backed by heartbeat truth.",
    endpointKey: "organs",
    endpoint: controlCenterEndpoints.organs,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Organ Health shows service heartbeat evidence from the read-only organs envelope.",
    notes: ["READ_ONLY visibility page.", "No healthy claim is made by the frontend."]
  },
  {
    id: "ai-brain",
    label: "AI Brain",
    title: "AI Brain",
    purpose: "Displays AI interpretation status and evidence without execution authority.",
    endpointKey: "ai",
    endpoint: controlCenterEndpoints.ai,
    status: "NOT_IMPLEMENTED",
    stateLabel: "NOT_IMPLEMENTED",
    summary: "AI context is not fetched or inferred in this shell.",
    notes: ["NOT_IMPLEMENTED shell.", "No AI execution capability is exposed."]
  },
  {
    id: "logs-errors",
    label: "Logs & Errors",
    title: "Logs & Errors",
    purpose: "Shows incident, delivery, and event-like records from read-only log sources.",
    endpointKey: "logs",
    endpoint: controlCenterEndpoints.logs,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Logs & Errors shows incident, delivery-attempt, and recent event rows from the read-only logs envelope.",
    notes: ["READ_ONLY visibility page.", "No incident stream subscription or backend mutation is exposed."]
  },
  {
    id: "settings",
    label: "Controls",
    title: "Controls",
    purpose: "Hosts Stage 15 safety-gated Control Center actions.",
    endpointKey: null,
    endpoint: null,
    status: "LOCKED",
    stateLabel: "LOCKED",
    summary: "Settings hosts frontend-only Refresh/Export and audited Control Center action wrappers.",
    notes: [
      "CONTROL_ACTIONS_GATED shell.",
      "Backend actions use only /dashboard/api/v2/control/actions/{action_name}.",
      "No raw runtime, execution, blocker bypass, order entry, or live endpoint is exposed."
    ]
  },
  {
    id: "mesh-dialogues",
    label: "Mesh Dialogues",
    title: "Mesh Dialogues",
    purpose: "Shows source-backed brain and mesh explanation events when real dialogue events exist.",
    endpointKey: "meshDialogues",
    endpoint: controlCenterEndpoints.meshDialogues,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "Mesh Dialogues shows real brain_dialogue_events only; it does not invent dialogue.",
    notes: ["READ_ONLY decision intelligence page.", "No invented dialogue is displayed."]
  },
  {
    id: "no-trade",
    label: "No-Trade",
    title: "No-Trade",
    purpose: "Shows first-class no-trade records and reasons from the read-only no-trade endpoint.",
    endpointKey: "noTrade",
    endpoint: controlCenterEndpoints.noTrade,
    status: "PARTIAL",
    stateLabel: "PARTIAL",
    summary: "No-Trade displays backend-supplied no-trade explanations without inventing reasons.",
    notes: ["READ_ONLY money visibility page.", "No no-trade reason is invented by the frontend."]
  }
];

export const DEFAULT_PAGE_ID: PageId = "overview";
