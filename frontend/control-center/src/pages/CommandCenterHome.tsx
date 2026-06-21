import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CircleStop,
  Database,
  Download,
  Lock,
  MessageSquareText,
  Power,
  PowerOff,
  Radar,
  RefreshCw,
  Siren,
  Target,
  WalletCards
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import type { ControlCenterActionEnvelope, ControlCenterActionName } from "../api/controlCenterActions";
import { useControlCenterActionMutation } from "../api/useControlCenterActions";
import {
  useAiQuery,
  useBlockersQuery,
  useCandidateExplanationsQuery,
  useCandidateEventCorrelationQuery,
  useCandidatePricePathQuery,
  useCandidateProducerFreshnessQuery,
  useCandidateScopedEventsQuery,
  useEligibleIntentBridgeQuery,
  useEventMeshProofQuery,
  useMeshEvidenceBundlesQuery,
  usePaperActionabilityQuery,
  usePaperCertificationPlanQuery,
  useClosestActionableQuery,
  useFullMonitorRunQuery,
  useLiveFlowQuery,
  useLogsQuery,
  useMeshDialoguesQuery,
  useNoTradeQuery,
  useOrgansQuery,
  useOrderbookPriceReadinessQuery,
  usePaperReadinessQuery,
  useOverviewQuery,
  usePrePaperSafetyQuery,
  usePaperSimulationQuery,
  usePnlLedgerQuery,
  usePositionsQuery,
  useRiskEvidenceQuery,
  useRuntimeReadinessQuery,
  useRuntimeSupervisorQuery,
  useSupervisorLifePathQuery
} from "../api/useControlCenterQueries";
import type { TruthEnvelope } from "../lib/truth-contract";
import { asArray, asRecord, fieldText, latestTimestamp, type UnknownRecord } from "./visibilityUtils";

type CockpitAction = {
  action: ControlCenterActionName;
  label: string;
  icon: typeof Power;
  tone: "primary" | "muted" | "danger";
  confirmation?: string;
  duration?: boolean;
};

const cockpitActions: CockpitAction[] = [
  { action: "system-on", label: "SYSTEM ON", icon: Power, tone: "primary" },
  { action: "enable-paper-simulation", label: "PAPER SIMULATION ON", icon: WalletCards, tone: "primary" },
  { action: "disable-paper-simulation", label: "PAPER SIMULATION OFF", icon: Lock, tone: "muted" },
  { action: "system-off", label: "SYSTEM OFF", icon: PowerOff, tone: "muted" },
  { action: "start-full-monitor-run", label: "START MONITORING RUN", icon: Radar, tone: "primary", duration: true },
  { action: "stop-current-run", label: "STOP CURRENT RUN", icon: CircleStop, tone: "muted" },
  { action: "kill-switch", label: "KILL SWITCH", icon: Siren, tone: "danger", confirmation: "KILL" }
];

const statusLabels: Record<string, string> = {
  REAL: "Live data available",
  PARTIAL: "Partially connected",
  MISSING: "No data yet",
  ERROR: "Error",
  STALE: "Stale data",
  LOCKED: "Locked",
  UNKNOWN: "Unknown",
  REFRESH_REQUIRED: "Refresh needed",
  ACTIVE_FRESH: "Fresh",
  COMPLETED: "Completed",
  RUNNING: "Running",
  STOPPED: "Stopped",
  ACCEPTED: "Accepted",
  REJECTED: "Rejected",
  STARTING: "Monitoring run starting",
  STOPPING: "Stopping",
  FAILED: "Run failed",
  DEGRADED: "Degraded",
  KILLED: "Killed",
  ALIVE: "Alive",
  BLOCKED: "Blocked",
  REGISTERED_NOT_RUNNING: "Registered, not running",
  RUNNING_ALLOWED: "Running allowed",
  RUNNING_BLOCKED: "Running blocked",
  RUNNING_FRESH: "Running fresh",
  RUNNING_STALE: "Running stale",
  FRESH: "Fresh",
  DIAGNOSTIC_IDLE: "Diagnostic idle",
  DIAGNOSTIC_RUNNING: "Diagnostic running",
  DIAGNOSTIC_STOPPED: "Diagnostic stopped",
  DIAGNOSTIC_STALE: "Diagnostic stale",
  CYCLE_CREATED: "Cycle created",
  CYCLE_RUNNING: "Cycle running",
  CYCLE_COMPLETED: "Cycle completed",
  CYCLE_FAILED: "Cycle failed",
  CYCLE_BLOCKED: "Cycle blocked",
  CYCLE_STALE: "Cycle stale",
  READY: "Ready",
  CANDIDATES_UPDATED: "Candidates updated",
  NO_CANDIDATES_FOUND: "No candidates found",
  CANDIDATES_BLOCKED_BY_MODE: "Candidates blocked by mode",
  CANDIDATES_BLOCKED_BY_SOURCE: "Candidates blocked by source",
  CANDIDATES_BLOCKED_BY_RUNTIME: "Candidates blocked by runtime",
  CANDIDATES_NOT_UPDATED_WITH_REASON: "Candidates not updated",
  PASSED: "Passed"
};

function operatorStatus(value?: string | null) {
  const raw = value || "UNKNOWN";
  return { raw, label: statusLabels[raw] ?? raw.replace(/_/g, " ").toLowerCase() };
}

function statusTone(status?: string | null) {
  if (status === "REAL" || status === "ACTIVE_FRESH" || status === "COMPLETED" || status === "RUNNING" || status === "ACCEPTED" || status === "ALIVE" || status === "RUNNING_ALLOWED" || status === "RUNNING_FRESH" || status === "FRESH") {
    return "border-poly-cyan/70 bg-poly-cyan/10 text-poly-cyan";
  }
  if (status === "PARTIAL" || status === "REFRESH_REQUIRED" || status === "STOPPED" || status === "DEGRADED" || status === "REGISTERED_NOT_RUNNING" || status === "DIAGNOSTIC_IDLE" || status === "DIAGNOSTIC_STOPPED") return "border-poly-partial/70 bg-poly-partial/10 text-poly-partial";
  if (status === "ERROR" || status === "KILL" || status === "KILLED" || status === "REJECTED") return "border-poly-error/70 bg-poly-error/10 text-poly-error";
  if (status === "LOCKED" || status === "BLOCKED" || status === "RUNNING_BLOCKED") return "border-poly-locked/70 bg-poly-locked/10 text-poly-locked";
  if (status === "STALE" || status === "RUNNING_STALE" || status === "DIAGNOSTIC_STALE") return "border-poly-missing/70 bg-poly-missing/10 text-poly-muted";
  return "border-poly-missing/70 bg-poly-missing/10 text-poly-muted";
}

function actionTone(tone: CockpitAction["tone"]) {
  if (tone === "danger") return "border-poly-error/80 bg-poly-error/10 text-poly-error hover:bg-poly-error/15";
  if (tone === "primary") return "border-poly-cyan/80 bg-poly-cyan/10 text-poly-text hover:bg-poly-cyan/15";
  return "border-poly-line bg-poly-panelStrong text-poly-text hover:border-poly-cyan/60";
}

function dataOrEmpty(envelope?: TruthEnvelope) {
  return asRecord(envelope?.data);
}

function StatusPill({ value, detail }: { value?: string | null; detail?: string }) {
  const status = operatorStatus(value);
  return (
    <span title={`Raw status: ${status.raw}${detail ? ` / ${detail}` : ""}`} className={`inline-flex rounded-md border px-2 py-1 text-xs font-semibold ${statusTone(status.raw)}`}>
      {status.label}
      <span className="sr-only">Raw status: {status.raw}</span>
      <span className="sr-only">{status.raw}</span>
    </span>
  );
}

function Section({ title, eyebrow, icon, children, emphasis = false }: { title: string; eyebrow: string; icon: ReactNode; children: ReactNode; emphasis?: boolean }) {
  return (
    <section className={`rounded-md border p-4 shadow-truth ${emphasis ? "border-poly-cyan/50 bg-poly-panelStrong" : "border-poly-line bg-poly-panel"}`}>
      <div className="mb-4 flex items-start gap-3">
        <div className="rounded-md border border-poly-line bg-poly-bg/60 p-2 text-poly-cyan">{icon}</div>
        <div>
          <p className="text-[11px] font-bold uppercase text-poly-cyan">{eyebrow}</p>
          <h2 className="mt-1 text-lg font-semibold text-poly-text">{title}</h2>
        </div>
      </div>
      {children}
    </section>
  );
}

function MiniFact({ label, value, detail, tone }: { label: string; value: ReactNode; detail?: string; tone?: string }) {
  return (
    <div className={`rounded-md border border-poly-line bg-poly-bg/50 p-3 ${tone ?? ""}`}>
      <p className="text-[11px] font-semibold uppercase text-poly-muted">{label}</p>
      <div className="mt-2 break-words text-lg font-semibold text-poly-text">{value}</div>
      {detail ? <p className="mt-2 text-xs leading-5 text-poly-muted">{detail}</p> : null}
    </div>
  );
}

function runFromEnvelope(envelope?: TruthEnvelope) {
  const data = dataOrEmpty(envelope);
  const current = asRecord(data.current);
  const latest = asRecord(data.latest);
  return { current, latest, visible: Object.keys(current).length ? current : latest };
}

function supervisorFromEnvelope(envelope?: TruthEnvelope) {
  const data = dataOrEmpty(envelope);
  const status = fieldText(data, ["supervisor_status"], "IDLE");
  return {
    visible: data,
    status,
    running: ["STARTING", "RUNNING", "DEGRADED"].includes(status)
  };
}

function exportSnapshot(snapshot: unknown) {
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `polybot-control-center-cockpit-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function firstReason(noTradeData: UnknownRecord, blockerData: UnknownRecord) {
  const direct = asArray(noTradeData.top_no_trade_reasons);
  const nested = asArray(asRecord(blockerData.no_trade).top_no_trade_reasons);
  const reasons = direct.length ? direct : nested;
  return reasons[0] ? fieldText(reasons[0], ["reason", "category", "blocker"], "NO_TRADE_RECORDED") : "No no-trade reason returned";
}

function actionMessage(action: ControlCenterActionEnvelope | null) {
  if (!action) return null;
  return action.errors[0] ?? action.warnings[0] ?? action.safety_checks.find((check) => check.status !== "PASS")?.detail ?? action.safety_checks[0]?.detail ?? "";
}

function runGuidance(lastAction: ControlCenterActionEnvelope | null, runState: ReturnType<typeof runFromEnvelope>, runtimeMode: string) {
  const latestStatus = fieldText(runState.visible, ["status"], "");
  if (lastAction?.action === "system-on" && lastAction.status === "ACCEPTED") {
    const stateAfter = asRecord(lastAction.state_after);
    const state = asRecord(stateAfter.state);
    const result = asRecord(lastAction.result);
    const safeMode = asRecord(result.safe_monitoring_mode);
    const modeAfter = fieldText(state, ["current_mode"], fieldText(safeMode, ["to_mode"], runtimeMode));
    const powerAfter = fieldText(result, ["system_power", "power"], "ON");
    return {
      state: "READY",
      title: "Safe monitoring mode is on.",
      detail: `SYSTEM ON completed. Current mode after SYSTEM ON: ${modeAfter}. System power: ${powerAfter}.`,
      nextStep: "Step 2: START MONITORING RUN.",
      rawStatus: lastAction.status
    };
  }
  if (lastAction?.action === "start-full-monitor-run" && lastAction.status === "LOCKED") {
    return {
      state: "LOCKED",
      title: "Full Monitor Run is locked by system mode.",
      detail: actionMessage(lastAction) || "The backend locked this action. Backend truth is preserved.",
      nextStep:
        runtimeMode !== "UNKNOWN"
          ? `Current mode is ${runtimeMode}. Step 1: SYSTEM ON. Step 2: START MONITORING RUN.`
          : "Required mode is not clear from backend response. Step 1: check Controls and press SYSTEM ON if appropriate. Step 2: START MONITORING RUN.",
      rawStatus: lastAction.status
    };
  }
  if (latestStatus) {
    const readable = operatorStatus(latestStatus);
    return {
      state: latestStatus,
      title: `Full Monitor Run ${readable.label}.`,
      detail: fieldText(runState.visible, ["run_id"], "Latest run is loaded from backend truth."),
      nextStep: latestStatus === "COMPLETED" ? "Review run summary and live feed changes." : "Follow the loaded run state; no running state is invented.",
      rawStatus: latestStatus
    };
  }
  return {
    state: "READY",
    title: "No Full Monitor Run has been started in this process.",
    detail: "The backend has no current or latest process-local run.",
    nextStep: "Step 1: SYSTEM ON if power is OFF. Step 2: START MONITORING RUN.",
    rawStatus: fullRunMissingStatus(runState)
  };
}

function supervisorGuidance(supervisorState: ReturnType<typeof supervisorFromEnvelope>, systemPower: string) {
  if (systemPower === "ON" && supervisorState.running) {
    return {
      title: "POLYBOT is monitoring in DATA_ONLY mode.",
      detail: "Live execution is disabled. Paper simulation only runs after explicit PAPER SIMULATION ON.",
      status: supervisorState.status
    };
  }
  if (systemPower === "ON") {
    return {
      title: "System is ON but supervisor is not running.",
      detail: "This is degraded. Use SYSTEM ON to request the supervisor again, or inspect backend errors.",
      status: supervisorState.status || "DEGRADED"
    };
  }
  return {
    title: "System is OFF. Press SYSTEM ON to start monitoring.",
    detail: "Full Monitor Run remains a diagnostic/report action; normal life comes from SYSTEM ON.",
    status: supervisorState.status || "STOPPED"
  };
}

function paperSimulationMessage(paper: UnknownRecord, supervisor: UnknownRecord, flow: UnknownRecord) {
  const status = fieldText(paper, ["status"], "DISABLED");
  if (status !== "ENABLED") return "Paper simulation is off. Enable it to allow simulated paper orders.";
  const orders = Number(fieldText(supervisor, ["paper_orders_created"], "0"));
  const blocked = Number(fieldText(supervisor, ["paper_intents_blocked"], "0"));
  const blockers = asArray(supervisor.paper_blockers);
  if (orders > 0) return "Paper simulation is enabled and canonical paper orders have been created.";
  if (blocked > 0 || blockers.length > 0) return "Paper simulation is enabled; candidates are being blocked or logged as NO_TRADE by the paper gate.";
  if (Object.keys(flow).length > 0) return "Paper simulation is enabled, but no candidate passed the paper gate yet.";
  return "Paper simulation is enabled; waiting for the next supervisor cycle.";
}

function fullRunMissingStatus(runState: ReturnType<typeof runFromEnvelope>) {
  return Object.keys(runState.current).length || Object.keys(runState.latest).length ? "REAL" : "MISSING";
}

function isRunActive(status: string) {
  return ["STARTING", "RUNNING", "STOPPING"].includes(status);
}

function secondsLabel(value: unknown) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return "UNKNOWN";
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

function eventLabel(row: UnknownRecord) {
  const raw = fieldText(row, ["event_type", "type", "category", "source", "id"], "event");
  const known: Record<string, string> = {
    "runtime.cycle.started": "Runtime cycle started",
    "runtime.cycle.finished": "Runtime cycle finished",
    "market.snapshot.created": "Market snapshot captured",
    "opportunity.scored": "Opportunity scored",
    "risk.rejected": "Risk blocked a candidate",
    "risk.approved": "Risk approved a candidate",
    "execution.order.submitted_paper": "Paper order created",
    "execution.fill.created": "Paper fill simulated",
    "position.opened": "Paper position opened",
    "no_trade.logged": "Paper candidate blocked"
  };
  return known[raw] ?? `Technical event: ${raw.replace(/[._-]/g, " ")}`;
}

function eventSource(row: UnknownRecord) {
  return fieldText(row, ["source_service", "source", "aggregate_type", "category"], "event_log");
}

function eventSummary(row: UnknownRecord) {
  const direct = fieldText(row, ["summary", "message", "detail", "description"], "");
  if (direct) return direct;
  const payload = asRecord(row.payload_json);
  const status = fieldText(payload, ["status"], "");
  if (status) return `System reported ${status.replace(/_/g, " ").toLowerCase()}.`;
  return "Technical event is visible; no readable summary was supplied.";
}

function eventTime(row: UnknownRecord) {
  return latestTimestamp(row, ["stored_at", "occurred_at", "created_at", "updated_at", "last_seen_at", "finished_at"]);
}

function dialogueRows(envelope?: TruthEnvelope) {
  const data = dataOrEmpty(envelope);
  const mesh = asRecord(data.mesh_dialogues);
  const nested = asArray(mesh.events);
  const direct = asArray(data.events);
  return nested.length ? nested : direct;
}

function dialogueTitle(row: UnknownRecord) {
  return fieldText(row, ["brain_name", "role", "speaker", "source", "event_type"], "Brain dialogue");
}

function dialogueMessage(row: UnknownRecord) {
  const text = fieldText(row, ["message", "opinion", "summary", "content", "coordinator_summary", "final_summary"], "");
  if (text && text !== "UNKNOWN") return text;
  return fieldText(row, ["status", "conflict"], "Dialogue event recorded; message field is not populated.");
}

function moneyVerdict(pnl: TruthEnvelope | undefined, positions: TruthEnvelope | undefined, ledgerRows: UnknownRecord[], positionRows: UnknownRecord[]) {
  if (!pnl?.source) return "Ledger source missing";
  if (pnl.status === "STALE") return "Data stale";
  if (pnl.status === "MISSING" || pnl.status === "ERROR") return "PnL unavailable";
  if (positions?.source && positionRows.length > 0) return "Ledger data and positions available";
  if (positions?.source) return "Ledger data available; no active positions returned";
  if (ledgerRows.length > 0) return "Ledger data available";
  return "Ledger data available; detailed rows withheld or empty";
}

export function CommandCenterHome() {
  const queryClient = useQueryClient();
  const actionMutation = useControlCenterActionMutation();

  const overview = useOverviewQuery();
  const organs = useOrgansQuery();
  const liveFlow = useLiveFlowQuery();
  const logs = useLogsQuery();
  const meshDialogues = useMeshDialoguesQuery();
  const fullMonitorRun = useFullMonitorRunQuery();
  const runtimeReadiness = useRuntimeReadinessQuery();
  const runtimeSupervisor = useRuntimeSupervisorQuery();
  const supervisorLifePath = useSupervisorLifePathQuery();
  const candidateProducerFreshness = useCandidateProducerFreshnessQuery();
  const paperReadiness = usePaperReadinessQuery();
  const candidateExplanations = useCandidateExplanationsQuery();
  const eligibleIntentBridge = useEligibleIntentBridgeQuery();
  const orderbookPriceReadiness = useOrderbookPriceReadinessQuery();
  const candidatePricePath = useCandidatePricePathQuery();
  const eventMeshProof = useEventMeshProofQuery();
  const meshEvidenceBundles = useMeshEvidenceBundlesQuery();
  const candidateEventCorrelation = useCandidateEventCorrelationQuery();
  const candidateScopedEvents = useCandidateScopedEventsQuery();
  const paperActionability = usePaperActionabilityQuery();
  const prePaperSafety = usePrePaperSafetyQuery();
  const paperCertificationPlan = usePaperCertificationPlanQuery();
  const paperSimulation = usePaperSimulationQuery();
  const blockers = useBlockersQuery();
  const closest = useClosestActionableQuery();
  const riskEvidence = useRiskEvidenceQuery();
  const noTrade = useNoTradeQuery();
  const pnl = usePnlLedgerQuery();
  const positions = usePositionsQuery();
  const ai = useAiQuery();

  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(10);
  const [intervalSeconds, setIntervalSeconds] = useState(10);
  const [killConfirm, setKillConfirm] = useState("");
  const [lastAction, setLastAction] = useState<ControlCenterActionEnvelope | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);

  const allQueries = [overview, organs, liveFlow, logs, meshDialogues, fullMonitorRun, runtimeReadiness, runtimeSupervisor, supervisorLifePath, candidateProducerFreshness, paperReadiness, candidateExplanations, eligibleIntentBridge, orderbookPriceReadiness, candidatePricePath, eventMeshProof, meshEvidenceBundles, candidateEventCorrelation, candidateScopedEvents, paperActionability, prePaperSafety, paperCertificationPlan, paperSimulation, blockers, closest, riskEvidence, noTrade, pnl, positions, ai];
  const refreshing = allQueries.some((query) => query.isFetching);
  const envelopes = allQueries.map((query) => query.data).filter(Boolean) as TruthEnvelope[];
  const overviewData = dataOrEmpty(overview.data);
  const sourceCounts = asRecord(overviewData.source_counts);
  const latestRows = asRecord(overviewData.latest_rows);
  const systemStateRow = asRecord(latestRows.system_state);
  const backendConnected = envelopes.some((envelope) => !String(envelope.source ?? "").startsWith("frontend:"));
  const dbConnected = Object.keys(sourceCounts).length > 0 && !overview.data?.warnings.some((warning) => warning.includes("database is not configured"));
  const systemPower = fieldText(overviewData, ["system_power", "power_state"], fieldText(systemStateRow, ["system_power"], "UNKNOWN"));
  const runtimeMode = fieldText(overviewData, ["current_mode", "runtime_mode", "mode"], fieldText(systemStateRow, ["current_mode"], "UNKNOWN"));
  const runtimeReadinessData = dataOrEmpty(runtimeReadiness.data);
  const supervisorLifePathData = dataOrEmpty(supervisorLifePath.data);
  const supervisorLifePathCounts = asRecord(supervisorLifePathData.counts);
  const candidateProducerFreshnessData = dataOrEmpty(candidateProducerFreshness.data);
  const candidateProducerCounts = asRecord(candidateProducerFreshnessData.counts);
  const runtimeLifeState = fieldText(runtimeReadinessData, ["runtime_life_state"], "UNKNOWN");
  const runState = runFromEnvelope(fullMonitorRun.data);
  const supervisorState = supervisorFromEnvelope(runtimeSupervisor.data);
  const paperSimulationData = dataOrEmpty(paperSimulation.data);
  const paperReadinessData = dataOrEmpty(paperReadiness.data);
  const paperReadinessCounts = asRecord(paperReadinessData.counts);
  const candidateExplanationData = dataOrEmpty(candidateExplanations.data);
  const candidateExplanationCounts = asRecord(candidateExplanationData.counts);
  const candidateExplanationGap = asRecord(candidateExplanationData.eligible_intent_gap);
  const candidateExplanationItems = asArray(candidateExplanationData.items).map((item) => asRecord(item));
  const topCandidateBlockers = asArray(candidateExplanationData.top_blockers).map((item) => asRecord(item));
  const bridgeData = dataOrEmpty(eligibleIntentBridge.data);
  const bridgeCounts = asRecord(bridgeData.counts);
  const bridgeGap = asRecord(bridgeData.eligible_intent_gap);
  const bridgeItems = asArray(bridgeData.items).map((item) => asRecord(item));
  const topBridgeOutcomes = asArray(bridgeData.top_outcomes).map((item) => asRecord(item));
  const topBridgeBlockers = asArray(bridgeData.top_blockers).map((item) => asRecord(item));
  const orderbookPriceData = dataOrEmpty(orderbookPriceReadiness.data);
  const orderbookPriceCounts = asRecord(orderbookPriceData.counts);
  const orderbookPriceItems = asArray(orderbookPriceData.items).map((item) => asRecord(item));
  const orderbookPriceSample = orderbookPriceItems[0] ?? {};
  const topOrderbookBlockers = asArray(orderbookPriceData.top_blockers).map((item) => asRecord(item));
  const candidatePricePathData = dataOrEmpty(candidatePricePath.data);
  const candidatePricePathCounts = asRecord(candidatePricePathData.counts);
  const candidatePricePathItems = asArray(candidatePricePathData.items).map((item) => asRecord(item));
  const candidatePricePathSample = candidatePricePathItems[0] ?? {};
  const eventMeshProofData = dataOrEmpty(eventMeshProof.data);
  const eventMeshProofCounts = asRecord(eventMeshProofData.counts);
  const eventMeshProofItems = asArray(eventMeshProofData.items).map((item) => asRecord(item));
  const eventMeshProofSample = eventMeshProofItems[0] ?? {};
  const eventMeshCoordinator = asRecord(eventMeshProofSample.coordinator);
  const meshEvidenceData = dataOrEmpty(meshEvidenceBundles.data);
  const meshEvidenceCounts = asRecord(meshEvidenceData.counts);
  const meshEvidenceItems = asArray(meshEvidenceData.items).map((item) => asRecord(item));
  const meshEvidenceSample = meshEvidenceItems[0] ?? {};
  const meshEvidenceOpinionStates = asRecord(meshEvidenceSample.opinion_states);
  const meshEvidenceOpinions = asRecord(meshEvidenceSample.opinions);
  const meshEvidenceCapitalOpinion = asRecord(meshEvidenceOpinions.capital);
  const meshEvidenceLifecycleOpinion = asRecord(meshEvidenceOpinions.lifecycle);
  const meshEvidenceCoordinator = asRecord(meshEvidenceSample.coordinator);
  const candidateEventCorrelationData = dataOrEmpty(candidateEventCorrelation.data);
  const candidateEventCorrelationCounts = asRecord(candidateEventCorrelationData.counts);
  const candidateEventCorrelationItems = asArray(candidateEventCorrelationData.items).map((item) => asRecord(item));
  const candidateEventCorrelationSample = candidateEventCorrelationItems[0] ?? {};
  const candidateScopedEventsData = dataOrEmpty(candidateScopedEvents.data);
  const candidateScopedEventsCounts = asRecord(candidateScopedEventsData.counts);
  const candidateScopedEventsItems = asArray(candidateScopedEventsData.items).map((item) => asRecord(item));
  const candidateScopedEventsSample = candidateScopedEventsItems[0] ?? {};
  const paperActionabilityData = dataOrEmpty(paperActionability.data);
  const paperActionabilityCounts = asRecord(paperActionabilityData.counts);
  const paperActionabilityItems = asArray(paperActionabilityData.items).map((item) => asRecord(item));
  const paperActionabilitySample = paperActionabilityItems[0] ?? {};
  const prePaperSafetyData = dataOrEmpty(prePaperSafety.data);
  const prePaperSafetyCounts = asRecord(prePaperSafetyData.counts);
  const prePaperSafetyBlockers = asArray(prePaperSafetyData.unified_blockers).map((item) => asRecord(item));
  const paperCertificationPlanData = dataOrEmpty(paperCertificationPlan.data);
  const paperFlow = asRecord(supervisorState.visible.latest_paper_flow);
  const supervisorGuide = supervisorGuidance(supervisorState, systemPower);
  const runStatus = fieldText(runState.visible, ["status"], "");
  const runActive = isRunActive(runStatus);
  const runGuide = runGuidance(lastAction, runState, runtimeMode);
  const liveEvents = asArray(dataOrEmpty(liveFlow.data).events);
  const logData = dataOrEmpty(logs.data);
  const logEvents = [...asArray(logData.runtime_incidents), ...asArray(logData.events), ...asArray(logData.event_delivery_attempts)];
  const feedEvents = [...liveEvents, ...logEvents].slice(0, 5);
  const dialogues = dialogueRows(meshDialogues.data);
  const blockerPayload = asRecord(dataOrEmpty(blockers.data).blockers);
  const noTradePayload = asRecord(dataOrEmpty(noTrade.data).no_trade);
  const closestCandidates = asArray(dataOrEmpty(closest.data).candidates);
  const riskPayload = asRecord(dataOrEmpty(riskEvidence.data).risk_evidence);
  const pnlPayload = asRecord(dataOrEmpty(pnl.data).pnl_ledger);
  const positionPayload = asRecord(dataOrEmpty(positions.data).positions);
  const positionRows = asArray(positionPayload.positions).length ? asArray(positionPayload.positions) : asArray(positionPayload.items);
  const ledgerRows = asArray(pnlPayload.ledger_rows);
  const moneyState = moneyVerdict(pnl.data, positions.data, ledgerRows, positionRows);
  const warningsCount = envelopes.reduce((total, envelope) => total + envelope.warnings.length, 0);
  const errorsCount = envelopes.reduce((total, envelope) => total + envelope.errors.length, 0);
  const diagnosticWarnings = [
    ...new Set(envelopes.flatMap((envelope) => envelope.warnings.map((warning) => warning.replace(/fake pnl/gi, "invented PnL"))))
  ];

  const loadedSnapshot = useMemo(() => {
    const entries = queryClient.getQueriesData({ queryKey: ["control-center"] });
    return Object.fromEntries(entries.map(([key, value]) => [Array.isArray(key) ? String(key[1] ?? "unknown") : String(key), value ?? null]));
  }, [queryClient, envelopes.length]);

  function refreshReadOnlyData() {
    void queryClient.invalidateQueries({ queryKey: ["control-center"] });
    setExportMessage("Refresh requested.");
  }

  function exportReport() {
    exportSnapshot({
      report_type: "POLYBOT_CONTROL_CENTER_OPERATOR_COCKPIT",
      generated_at: new Date().toISOString(),
      source: "frontend:tanstack_query_cache",
      envelopes: loadedSnapshot
    });
    setExportMessage("Export prepared from loaded truth envelopes.");
  }

  function canSubmit(action: CockpitAction) {
    if (!actor.trim() || !reason.trim()) return false;
    if (action.duration && (!Number.isFinite(durationMinutes) || durationMinutes < 1 || durationMinutes > 60)) return false;
    if (action.duration && (!Number.isFinite(intervalSeconds) || intervalSeconds < 10 || intervalSeconds > 300)) return false;
    if (action.confirmation && killConfirm.trim() !== action.confirmation) return false;
    return !actionMutation.isPending;
  }

  async function submitAction(action: CockpitAction) {
    if (!canSubmit(action)) return;
    const result = await actionMutation.mutateAsync({
      action: action.action,
      payload: {
        actor,
        reason,
        confirmation: action.confirmation ? killConfirm : undefined,
        duration_minutes: action.duration ? durationMinutes : undefined,
        interval_seconds: action.action === "system-on" || action.duration ? intervalSeconds : undefined,
        metadata: { source: "control-center-v1.5-stage-25-monitoring-runtime" }
      }
    });
    setLastAction(result);
    if (action.action === "system-on") {
      await Promise.all([overview.refetch(), runtimeReadiness.refetch(), runtimeSupervisor.refetch(), supervisorLifePath.refetch(), candidateProducerFreshness.refetch(), orderbookPriceReadiness.refetch(), candidatePricePath.refetch(), eventMeshProof.refetch(), meshEvidenceBundles.refetch(), candidateEventCorrelation.refetch(), candidateScopedEvents.refetch(), paperActionability.refetch(), prePaperSafety.refetch(), paperCertificationPlan.refetch(), paperSimulation.refetch(), fullMonitorRun.refetch(), organs.refetch(), liveFlow.refetch()]);
    } else if (action.action === "system-off" || action.action === "kill-switch") {
      await Promise.all([overview.refetch(), runtimeReadiness.refetch(), runtimeSupervisor.refetch(), supervisorLifePath.refetch(), candidateProducerFreshness.refetch(), orderbookPriceReadiness.refetch(), candidatePricePath.refetch(), eventMeshProof.refetch(), meshEvidenceBundles.refetch(), candidateEventCorrelation.refetch(), candidateScopedEvents.refetch(), paperActionability.refetch(), prePaperSafety.refetch(), paperCertificationPlan.refetch(), paperSimulation.refetch(), fullMonitorRun.refetch()]);
    } else if (action.action === "enable-paper-simulation" || action.action === "disable-paper-simulation") {
      await Promise.all([paperSimulation.refetch(), runtimeReadiness.refetch(), runtimeSupervisor.refetch(), liveFlow.refetch(), noTrade.refetch(), pnl.refetch(), positions.refetch()]);
    } else {
      await Promise.all([fullMonitorRun.refetch(), runtimeReadiness.refetch()]);
    }
  }

  return (
    <div className="space-y-5" data-testid="page-overview">
      <section className="rounded-md border border-poly-cyan/50 bg-poly-panelStrong p-5 shadow-truth">
        <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
          <div>
            <p className="text-xs font-bold uppercase text-poly-cyan">POLYBOT Operator Cockpit</p>
            <h1 className="mt-2 text-4xl font-semibold text-poly-text md:text-5xl">Command Cockpit</h1>
            <p className="mt-3 max-w-3xl text-base leading-7 text-poly-muted">
              One operator view for body state, safe actions, live motion, decision truth, and money truth.
            </p>
            <div className="mt-5 grid gap-3 md:grid-cols-4">
              <MiniFact label="Runtime Life" value={<StatusPill value={runtimeLifeState} />} detail={`Power: ${fieldText(runtimeReadinessData, ["system_power_state"], systemPower)}`} />
              <MiniFact label="Supervisor" value={<StatusPill value={supervisorState.status} />} detail="SYSTEM ON starts this DATA_ONLY heartbeat." />
              <MiniFact label="Backend" value={<StatusPill value={backendConnected ? "REAL" : "MISSING"} />} detail="Docker API is the served data owner." />
              <MiniFact label="Database" value={<StatusPill value={dbConnected ? "REAL" : "MISSING"} />} detail={`${Object.keys(sourceCounts).length} source groups connected.`} />
              <MiniFact label="System Mode" value={runtimeMode} detail={`Raw mode: ${runtimeMode}`} />
              <MiniFact label="Paper Simulation" value={<StatusPill value={fieldText(paperSimulationData, ["status"], "DISABLED")} />} detail={fieldText(paperSimulationData, ["reason"], "Explicit operator switch required.")} />
            </div>
          </div>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
            <p className="text-[11px] font-bold uppercase text-poly-cyan">Health verdict</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusPill value={overview.data?.status} detail={overview.data?.truth_state} />
              <StatusPill value={overview.data?.truth_state} />
            </div>
            <p className="mt-3 text-sm leading-6 text-poly-muted">
              {dbConnected && backendConnected
                ? "Core Control Center data is reachable. Degraded or partial states remain visible instead of being painted green."
                : "Control Center cannot prove the body is fully connected yet."}
            </p>
            <p className="mt-3 text-xs text-poly-muted">Last refresh: {latestTimestamp(overviewData)}</p>
            <p className="sr-only">/dashboard/api/v2/control/overview</p>
            <p className="sr-only">/dashboard/api/v2/control/supervisor-life-path</p>
            <p className="sr-only">/dashboard/api/v2/control/candidate-producer-freshness</p>
            <p className="sr-only">/dashboard/api/v2/control/full-monitor-run</p>
            <p className="sr-only">/dashboard/api/v2/control/runtime-supervisor</p>
            <p className="sr-only">{overview.data?.source ?? "source pending"}</p>
            <div className="sr-only" aria-label="Overview diagnostic continuity">
              <p>Latest Source Rows</p>
              {Object.keys(sourceCounts).map((source) => (
                <p key={`diagnostic-source-${source}`}>{source}</p>
              ))}
              {diagnosticWarnings.map((warning) => (
                <p key={`diagnostic-warning-${warning}`}>{warning}</p>
              ))}
            </div>
            {refreshing ? <p className="mt-2 text-xs font-semibold text-poly-cyan">Refreshing read-only envelopes...</p> : null}
          </div>
        </div>
      </section>

      <section className="rounded-md border border-poly-line bg-poly-panel p-4 shadow-truth" aria-label="Primary action strip">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-bold uppercase text-poly-cyan">What can I safely press now?</p>
            <h2 className="mt-1 text-2xl font-semibold text-poly-text">Primary Action Strip</h2>
          </div>
          <div className="text-sm text-poly-muted">Actor and reason unlock audited runtime actions. KILL remains isolated and confirmation-gated.</div>
        </div>
        <div className="grid gap-4 xl:grid-cols-[300px_1fr_190px]">
          <div className="grid gap-3">
            <label className="grid gap-1 text-sm text-poly-muted">
              Actor
              <input value={actor} onChange={(event) => setActor(event.target.value)} className="rounded-md border border-poly-line bg-poly-bg px-3 py-2 text-poly-text outline-none focus:border-poly-cyan" placeholder="operator id" />
            </label>
            <label className="grid gap-1 text-sm text-poly-muted">
              Reason
              <input value={reason} onChange={(event) => setReason(event.target.value)} className="rounded-md border border-poly-line bg-poly-bg px-3 py-2 text-poly-text outline-none focus:border-poly-cyan" placeholder="required audit reason" />
            </label>
            <label className="grid gap-1 text-sm text-poly-muted">
              Duration minutes
              <input type="number" min={1} max={60} value={durationMinutes} onChange={(event) => setDurationMinutes(Number(event.target.value))} className="rounded-md border border-poly-line bg-poly-bg px-3 py-2 text-poly-text outline-none focus:border-poly-cyan" />
            </label>
            <label className="grid gap-1 text-sm text-poly-muted">
              Interval seconds
              <input type="number" min={10} max={300} value={intervalSeconds} onChange={(event) => setIntervalSeconds(Number(event.target.value))} className="rounded-md border border-poly-line bg-poly-bg px-3 py-2 text-poly-text outline-none focus:border-poly-cyan" />
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {cockpitActions.filter((action) => action.action !== "kill-switch" && (action.action !== "stop-current-run" || runActive)).map((action) => {
              const Icon = action.icon;
              return (
                <button key={action.action} type="button" aria-label={action.label} disabled={!canSubmit(action)} onClick={() => void submitAction(action)} className={`min-h-24 rounded-md border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-45 ${actionTone(action.tone)}`}>
                  <Icon aria-hidden="true" size={20} />
                  <span className="mt-3 block text-sm font-bold">{action.label}</span>
                  <span aria-hidden="true" className="mt-2 block text-xs text-poly-muted">{action.duration ? "Diagnostic/report run. Normal monitoring starts with SYSTEM ON." : action.action === "system-on" ? "Starts DATA_ONLY monitoring supervisor." : "Uses audited action wrapper."}</span>
                </button>
              );
            })}
            <button type="button" aria-label="Refresh read-only data" onClick={refreshReadOnlyData} className="min-h-24 rounded-md border border-poly-line bg-poly-panelStrong p-4 text-left text-poly-text hover:border-poly-cyan/60">
              <RefreshCw aria-hidden="true" size={20} />
              <span className="mt-3 block text-sm font-bold">REFRESH</span>
              <span className="mt-2 block text-xs text-poly-muted">Reload read-only truth.</span>
            </button>
            <button type="button" onClick={exportReport} className="min-h-24 rounded-md border border-poly-line bg-poly-panelStrong p-4 text-left text-poly-text hover:border-poly-cyan/60">
              <Download aria-hidden="true" size={20} />
              <span className="mt-3 block text-sm font-bold">EXPORT REPORT</span>
              <span className="mt-2 block text-xs text-poly-muted">Export loaded truth.</span>
            </button>
          </div>
          <div className="rounded-md border border-poly-error/70 bg-poly-error/10 p-3">
            <label className="grid gap-1 text-sm text-poly-muted">
              KILL confirmation
              <input value={killConfirm} onChange={(event) => setKillConfirm(event.target.value)} className="rounded-md border border-poly-line bg-poly-bg px-3 py-2 text-poly-text outline-none focus:border-poly-error" placeholder="KILL" />
            </label>
            <button type="button" disabled={!canSubmit(cockpitActions[4])} onClick={() => void submitAction(cockpitActions[4])} className={`mt-3 min-h-20 w-full rounded-md border p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-45 ${actionTone("danger")}`}>
              <Siren aria-hidden="true" size={20} />
              <span className="mt-2 block text-sm font-bold">KILL SWITCH</span>
              <span className="mt-1 block text-xs text-poly-muted">Requires actor, reason, and exact confirmation.</span>
            </button>
          </div>
        </div>
        {lastAction ? (
          <div className="mt-4 rounded-md border border-poly-line bg-poly-bg/50 p-3 text-sm text-poly-muted">
            Last action: <span className="font-semibold text-poly-text">{lastAction.action}</span> <StatusPill value={lastAction.status} />
            {actionMessage(lastAction) ? <span className="ml-2">{actionMessage(lastAction)}</span> : null}
          </div>
        ) : exportMessage ? (
          <p className="mt-4 text-sm text-poly-muted">{exportMessage}</p>
        ) : null}
      </section>

      <Section title="Current Runtime Readiness" eyebrow="Single runtime truth" icon={<Database size={18} />} emphasis>
        <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
          <div className="grid gap-3 md:grid-cols-4">
            <MiniFact label="Runtime Life" value={<StatusPill value={runtimeLifeState} />} detail={runtimeReadiness.data?.source ?? "runtime readiness source pending"} />
            <MiniFact label="System Power" value={<StatusPill value={fieldText(runtimeReadinessData, ["system_power_state"], "UNKNOWN")} />} detail={`Mode: ${fieldText(asRecord(runtimeReadinessData.state), ["current_mode"], runtimeMode)}`} />
            <MiniFact label="Scheduler" value={<StatusPill value={fieldText(runtimeReadinessData, ["scheduler_state"], "UNKNOWN")} />} detail={fieldText(runtimeReadinessData, ["scheduler_blocked_reason"], "No scheduler blocker returned")} />
            <MiniFact label="Supervisor" value={<StatusPill value={fieldText(runtimeReadinessData, ["supervisor_state"], "UNKNOWN")} />} detail={fieldText(runtimeReadinessData, ["runtime_supervisor_truth_scope"], "PROCESS_LOCAL")} />
            <MiniFact label="Active Cycle" value={<StatusPill value={fieldText(runtimeReadinessData, ["active_cycle_state"], "MISSING")} />} detail={fieldText(asRecord(runtimeReadinessData.active_cycle), ["cycle_id"], "No active cycle")} />
            <MiniFact label="Last Successful Cycle" value={<StatusPill value={fieldText(runtimeReadinessData, ["last_successful_cycle_state"], "MISSING")} />} detail={fieldText(asRecord(runtimeReadinessData.last_successful_cycle), ["last_updated"], "No success timestamp")} />
            <MiniFact label="Full Monitor Run" value={<StatusPill value={fieldText(runtimeReadinessData, ["full_monitor_run_state"], "DIAGNOSTIC_IDLE")} />} detail={fieldText(runtimeReadinessData, ["full_monitor_run_label"], "DIAGNOSTIC_ONLY")} />
            <MiniFact label="Collect Data" value={fieldText(runtimeReadinessData, ["governor_allows_collect_data"], "false")} detail="Governor-derived permission" />
          </div>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-3">
            <p className="text-sm font-semibold text-poly-text">Readiness blockers</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {asArray(runtimeReadinessData.blockers).length ? (
                asArray(runtimeReadinessData.blockers).slice(0, 10).map((blocker, index) => (
                  <span key={`${String(blocker)}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                    {String(blocker)}
                  </span>
                ))
              ) : (
                <span className="rounded-md border border-poly-cyan/50 bg-poly-cyan/10 px-2 py-1 text-xs font-semibold text-poly-cyan">NO_BLOCKERS_RETURNED</span>
              )}
            </div>
            <p className="mt-3 text-xs leading-5 text-poly-muted">Last readiness refresh: {fieldText(runtimeReadinessData, ["generated_at"], "pending")}</p>
          </div>
        </div>
      </Section>

      <Section title="Supervisor Life Path" eyebrow="SYSTEM ON is life, Full Monitor Run is diagnosis" icon={<Activity size={18} />} emphasis>
        <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
          <div className="grid gap-3 md:grid-cols-4">
            <MiniFact label="Supervisor Life" value={<StatusPill value={fieldText(supervisorLifePathData, ["supervisor_life_state"], "UNKNOWN")} />} detail={supervisorLifePath.data?.source ?? "life path source pending"} />
            <MiniFact label="System Power" value={<StatusPill value={fieldText(supervisorLifePathData, ["system_power_state"], "UNKNOWN")} />} detail={`Runtime: ${fieldText(supervisorLifePathData, ["runtime_life_state"], "UNKNOWN")}`} />
            <MiniFact label="Supervisor" value={<StatusPill value={fieldText(supervisorLifePathData, ["supervisor_state"], "UNKNOWN")} />} detail={`Heartbeat age: ${secondsLabel(supervisorLifePathData.supervisor_age_seconds)}`} />
            <MiniFact label="Cycle State" value={<StatusPill value={fieldText(supervisorLifePathData, ["cycle_state"], "UNKNOWN")} />} detail={`Last cycle age: ${secondsLabel(supervisorLifePathData.last_cycle_age_seconds)}`} />
            <MiniFact label="Supervisor Cycles" value={fieldText(supervisorLifePathData, ["cycles_completed_since_system_on"], "0")} detail={`Scheduler cycles: ${fieldText(supervisorLifePathData, ["scheduler_cycles_completed_since_system_on"], "0")}`} />
            <MiniFact label="Events Updated" value={fieldText(supervisorLifePathData, ["events_updated"], "false")} detail={`${fieldText(supervisorLifePathCounts, ["events_since_system_on"], "0")} since SYSTEM ON`} />
            <MiniFact label="Candidates Updated" value={fieldText(supervisorLifePathData, ["candidates_updated"], "false")} detail={`${fieldText(supervisorLifePathCounts, ["candidates_updated_since_system_on"], "0")} since SYSTEM ON`} />
            <MiniFact label="Readiness Updated" value={`${fieldText(supervisorLifePathData, ["runtime_readiness_updated"], "false")} / ${fieldText(supervisorLifePathData, ["paper_readiness_updated"], "false")}`} detail="runtime / paper" />
            <MiniFact label="Paper Readiness" value={<StatusPill value={fieldText(asRecord(supervisorLifePathData.paper_readiness), ["paper_readiness_state"], "UNKNOWN")} />} detail={`Simulation: ${fieldText(asRecord(supervisorLifePathData.paper_readiness), ["paper_simulation_state"], "UNKNOWN")}`} />
            <MiniFact label="Full Monitor Run" value={fieldText(supervisorLifePathData, ["full_monitor_run_label"], "DIAGNOSTIC_ONLY")} detail={fieldText(supervisorLifePathData, ["full_monitor_run_state"], "DIAGNOSTIC_IDLE")} />
          </div>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-3">
            <p className="text-sm font-semibold text-poly-text">Life path blockers</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {asArray(supervisorLifePathData.blockers).length ? (
                asArray(supervisorLifePathData.blockers).slice(0, 10).map((blocker, index) => (
                  <span key={`${String(blocker)}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                    {String(blocker)}
                  </span>
                ))
              ) : (
                <span className="rounded-md border border-poly-cyan/50 bg-poly-cyan/10 px-2 py-1 text-xs font-semibold text-poly-cyan">NO_LIFE_PATH_BLOCKERS_RETURNED</span>
              )}
            </div>
            <p className="mt-3 text-xs leading-5 text-poly-muted">Last life-path refresh: {fieldText(supervisorLifePathData, ["last_updated"], "pending")}</p>
          </div>
        </div>
      </Section>

      <Section title="Candidate Producer Freshness" eyebrow="SYSTEM ON feeds candidate truth" icon={<Target size={18} />} emphasis>
        <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
          <div className="grid gap-3 md:grid-cols-4">
            <MiniFact label="Producer" value={<StatusPill value={fieldText(candidateProducerFreshnessData, ["candidate_producer_state"], "UNKNOWN")} />} detail={candidateProducerFreshness.data?.source ?? "candidate producer source pending"} />
            <MiniFact label="Candidate Freshness" value={<StatusPill value={fieldText(candidateProducerFreshnessData, ["candidate_freshness_state"], "UNKNOWN")} />} detail={fieldText(candidateProducerFreshnessData, ["last_candidate_updated_at"], "No candidate timestamp")} />
            <MiniFact label="Update Result" value={<StatusPill value={fieldText(candidateProducerFreshnessData, ["candidate_update_result"], "UNKNOWN")} />} detail={fieldText(candidateProducerFreshnessData, ["supervisor_candidate_path_result"], "UNKNOWN")} />
            <MiniFact label="After SYSTEM ON" value={fieldText(asRecord(candidateProducerFreshnessData.updated_after_system_on), ["candidates"], "false")} detail={`${fieldText(candidateProducerCounts, ["candidates_updated_since_system_on"], "0")} candidate rows`} />
            <MiniFact label="Market Refresh" value={fieldText(asRecord(candidateProducerFreshnessData.updated_after_system_on), ["market_refresh"], "false")} detail={fieldText(candidateProducerFreshnessData, ["last_market_refresh_at"], "No market refresh")} />
            <MiniFact label="Market Snapshots" value={fieldText(asRecord(candidateProducerFreshnessData.updated_after_system_on), ["market_snapshots"], "false")} detail={fieldText(candidateProducerFreshnessData, ["last_market_snapshot_at"], "No market snapshot")} />
            <MiniFact label="Candidate Explanations" value={fieldText(asRecord(candidateProducerFreshnessData.updated_after_system_on), ["candidate_explanations"], "false")} detail={fieldText(candidateProducerFreshnessData, ["last_candidate_explanation_updated_at"], "No explanation timestamp")} />
            <MiniFact label="Eligible Bridge" value={fieldText(asRecord(candidateProducerFreshnessData.updated_after_system_on), ["eligible_bridge"], "false")} detail={fieldText(candidateProducerFreshnessData, ["last_eligible_bridge_updated_at"], "No bridge timestamp")} />
            <MiniFact label="No-Trade" value={fieldText(candidateProducerFreshnessData, ["last_no_trade_updated_at"], "No no-trade update")} detail={`${fieldText(candidateProducerCounts, ["no_trade_updated_since_system_on"], "0")} since SYSTEM ON`} />
            <MiniFact label="Paper Readiness" value={fieldText(asRecord(candidateProducerFreshnessData.updated_after_system_on), ["paper_readiness"], "false")} detail={fieldText(candidateProducerFreshnessData, ["last_paper_readiness_updated_at"], "No paper readiness update")} />
          </div>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-3">
            <p className="text-sm font-semibold text-poly-text">Candidate producer blockers</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {asArray(candidateProducerFreshnessData.blockers).length ? (
                asArray(candidateProducerFreshnessData.blockers).slice(0, 10).map((blocker, index) => (
                  <span key={`${String(blocker)}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                    {String(blocker)}
                  </span>
                ))
              ) : (
                <span className="rounded-md border border-poly-cyan/50 bg-poly-cyan/10 px-2 py-1 text-xs font-semibold text-poly-cyan">NO_CANDIDATE_PRODUCER_BLOCKERS_RETURNED</span>
              )}
            </div>
            <p className="mt-3 text-xs leading-5 text-poly-muted">Last candidate-producer refresh: {fieldText(candidateProducerFreshnessData, ["last_updated"], "pending")}</p>
          </div>
        </div>
      </Section>

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Section title="Runtime Supervisor Heartbeat" eyebrow="SYSTEM ON continuous monitoring" icon={<Activity size={18} />} emphasis>
          <div className={`rounded-md border p-4 ${systemPower === "ON" && !supervisorState.running ? "border-poly-partial/60 bg-poly-partial/10" : "border-poly-line bg-poly-bg/50"}`}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-xl font-semibold text-poly-text">{supervisorGuide.title}</h3>
              <StatusPill value={supervisorGuide.status} />
            </div>
            <p className="mt-3 text-sm leading-6 text-poly-muted">{supervisorGuide.detail}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="rounded-md border border-poly-cyan/50 bg-poly-cyan/10 px-2 py-1 text-xs font-semibold text-poly-cyan">DATA_ONLY monitoring</span>
              <span className="rounded-md border border-poly-line bg-poly-bg px-2 py-1 text-xs font-semibold text-poly-muted">Live execution disabled</span>
              <span className="rounded-md border border-poly-line bg-poly-bg px-2 py-1 text-xs font-semibold text-poly-muted">
                Paper simulation {fieldText(supervisorState.visible, ["paper_simulation_status"], "DISABLED")}
              </span>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <MiniFact label="Session" value={fieldText(supervisorState.visible, ["session_id"], "No session")} />
              <MiniFact label="Last cycle" value={fieldText(supervisorState.visible, ["last_cycle_at"], "Not yet")} />
              <MiniFact label="Next cycle" value={fieldText(supervisorState.visible, ["next_cycle_at"], "Not scheduled")} />
              <MiniFact label="Current cycle" value={fieldText(supervisorState.visible, ["current_cycle_status"], "IDLE")} />
              <MiniFact label="Interval" value={`${fieldText(supervisorState.visible, ["interval_seconds"], "60")}s`} />
              <MiniFact label="Elapsed" value={secondsLabel(supervisorState.visible.elapsed_seconds)} />
              <MiniFact label="Cycles completed" value={fieldText(supervisorState.visible, ["cycles_completed"], "0")} />
              <MiniFact label="Cycles failed" value={fieldText(supervisorState.visible, ["cycles_failed"], "0")} />
              <MiniFact label="Markets" value={fieldText(supervisorState.visible, ["markets_checked"], "0")} />
              <MiniFact label="Events" value={fieldText(supervisorState.visible, ["events_seen"], "0")} />
              <MiniFact label="Opportunities" value={fieldText(supervisorState.visible, ["opportunities_found"], "0")} />
              <MiniFact label="AI calls / failures" value={`${fieldText(supervisorState.visible, ["ai_calls"], "0")} / ${fieldText(supervisorState.visible, ["ai_failures"], "0")}`} />
              <MiniFact label="Paper orders / fills" value={`${fieldText(supervisorState.visible, ["paper_orders_created"], "0")} / ${fieldText(supervisorState.visible, ["paper_fills_created"], "0")}`} />
              <MiniFact label="Paper positions" value={fieldText(supervisorState.visible, ["paper_positions_opened"], "0")} />
            </div>
            {fieldText(supervisorState.visible, ["report_path"], "") ? (
              <p className="mt-4 break-words rounded-md border border-poly-line bg-poly-panel/70 p-3 text-sm text-poly-muted">
                Supervisor session report: <span className="font-semibold text-poly-text">{fieldText(supervisorState.visible, ["report_path"])}</span>
              </p>
            ) : null}
          </div>
        </Section>

        <Section title="Orderbook Price Readiness" eyebrow="Trusted fresh price path" icon={<Activity size={18} />} emphasis>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-poly-text">Fresh trusted orderbook before Paper execution</p>
                <p className="mt-1 text-xs text-poly-muted">Price readiness does not activate Paper Simulation or create execution artifacts.</p>
              </div>
              <StatusPill value={fieldText(orderbookPriceData, ["readiness_state"], "UNKNOWN")} detail={fieldText(orderbookPriceData, ["freshness_state"], "UNKNOWN")} />
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-4">
              <MiniFact label="Price Ready" value={fieldText(orderbookPriceCounts, ["price_ready"], "0")} detail={`${fieldText(orderbookPriceCounts, ["candidates_checked"], "0")} candidates checked`} />
              <MiniFact label="Trusted Fresh" value={fieldText(orderbookPriceCounts, ["trusted_fresh_orderbooks"], "0")} detail={`${fieldText(orderbookPriceCounts, ["trusted_stale_orderbooks"], "0")} stale trusted`} />
              <MiniFact label="Waiting Refresh" value={fieldText(orderbookPriceCounts, ["waiting_for_refresh"], "0")} detail={`${fieldText(orderbookPriceCounts, ["missing_orderbooks"], "0")} missing orderbooks`} />
              <MiniFact label="TTL" value={fieldText(asRecord(orderbookPriceData.ttl), ["execution_orderbook_ttl_seconds"], "180")} detail="execution seconds" />
              <MiniFact label="Sample Candidate" value={fieldText(orderbookPriceSample, ["candidate_id"], "No candidate")} detail={fieldText(orderbookPriceSample, ["market_id"], "No market")} />
              <MiniFact label="Token / Side" value={`${fieldText(orderbookPriceSample, ["token_id"], "MISSING")} / ${fieldText(orderbookPriceSample, ["side"], "UNKNOWN")}`} />
              <MiniFact label="Entry Source" value={fieldText(orderbookPriceSample, ["entry_price_source"], "UNKNOWN")} detail={fieldText(orderbookPriceSample, ["entry_price"], "No price")} />
              <MiniFact label="Exit Liquidity" value={fieldText(orderbookPriceSample, ["exit_liquidity_state"], "UNKNOWN")} detail={fieldText(orderbookPriceSample, ["exit_price_source"], "UNKNOWN")} />
              <MiniFact label="Best Bid / Ask" value={`${fieldText(orderbookPriceSample, ["best_bid"], "-")} / ${fieldText(orderbookPriceSample, ["best_ask"], "-")}`} detail={`Spread: ${fieldText(orderbookPriceSample, ["spread"], "-")}`} />
              <MiniFact label="Depth 1c / 2c / 5c" value={`${fieldText(orderbookPriceSample, ["depth_1c"], "0")} / ${fieldText(orderbookPriceSample, ["depth_2c"], "0")} / ${fieldText(orderbookPriceSample, ["depth_5c"], "0")}`} />
              <MiniFact label="Orderbook Age" value={fieldText(orderbookPriceSample, ["orderbook_age_seconds"], "UNKNOWN")} detail={fieldText(orderbookPriceSample, ["last_orderbook_at"], "No orderbook")} />
              <MiniFact label="Refresh Before Exec" value={fieldText(orderbookPriceSample, ["refresh_before_execution_state"], fieldText(asRecord(orderbookPriceData.refresh_path), ["refresh_before_execution_state"], "UNKNOWN"))} />
              <MiniFact label="Candidate Ready" value={fieldText(candidatePricePathCounts, ["candidate_price_ready"], "0")} detail={`${fieldText(candidatePricePathCounts, ["candidates_checked"], "0")} candidate-specific`} />
              <MiniFact label="Candidate Refresh" value={fieldText(candidatePricePathCounts, ["refresh_available"], "0")} detail={`${fieldText(candidatePricePathCounts, ["stale_orderbook"], "0")} stale exact books`} />
              <MiniFact label="Candidate Trust" value={fieldText(candidatePricePathCounts, ["trusted_fresh_for_candidate"], "0")} detail={`${fieldText(candidatePricePathCounts, ["trusted_stale_for_candidate"], "0")} stale trusted`} />
              <MiniFact label="Candidate State" value={fieldText(candidatePricePathSample, ["candidate_price_path_state"], "UNKNOWN")} detail={fieldText(candidatePricePathSample, ["candidate_trusted_orderbook_state"], "UNKNOWN")} />
              <MiniFact label="Candidate Token" value={fieldText(candidatePricePathSample, ["token_id"], "MISSING")} detail={fieldText(candidatePricePathSample, ["candidate_id"], "No candidate")} />
              <MiniFact label="Candidate Refresh Plan" value={fieldText(asRecord(candidatePricePathSample.refresh_plan), ["can_refresh"], "UNKNOWN")} detail={fieldText(asRecord(candidatePricePathSample.refresh_plan), ["blocked_reason"], fieldText(candidatePricePathSample, ["refresh_before_execution_state"], "UNKNOWN"))} />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {topOrderbookBlockers.length ? (
                topOrderbookBlockers.slice(0, 10).map((entry, index) => (
                  <span key={`${fieldText(entry, ["blocker"], "UNKNOWN")}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                    {fieldText(entry, ["blocker"], "UNKNOWN")} ({fieldText(entry, ["count"], "0")})
                  </span>
                ))
              ) : (
                <span className="rounded-md border border-poly-cyan/50 bg-poly-cyan/10 px-2 py-1 text-xs font-semibold text-poly-cyan">NO_PRICE_BLOCKERS_RETURNED</span>
              )}
            </div>
          </div>
        </Section>

        <Section title="Minimal Event Mesh Proof" eyebrow="One orderbook event wakes brains" icon={<MessageSquareText size={18} />} emphasis>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-poly-text">orderbook.snapshot.created trace</p>
                <p className="mt-1 text-xs text-poly-muted">Proof only; brain reactions and coordinator trace do not create execution artifacts.</p>
              </div>
              <StatusPill value={fieldText(eventMeshProofData, ["mesh_proof_state"], "UNKNOWN")} detail={fieldText(eventMeshProofSample, ["event_delivery_state"], "UNKNOWN")} />
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-4">
              <MiniFact label="Events Seen" value={fieldText(eventMeshProofCounts, ["events_seen"], "0")} detail={`${fieldText(eventMeshProofCounts, ["fully_proven_events"], "0")} fully proven`} />
              <MiniFact label="Liquidity Brain" value={fieldText(eventMeshProofCounts, ["events_with_liquidity_reaction"], "0")} detail="events with reaction" />
              <MiniFact label="Risk Brain" value={fieldText(eventMeshProofCounts, ["events_with_risk_reaction"], "0")} detail="events with reaction" />
              <MiniFact label="Exit Brain" value={fieldText(eventMeshProofCounts, ["events_with_exit_reaction"], "0")} detail="events with reaction" />
              <MiniFact label="Capital Brain" value={fieldText(eventMeshProofCounts, ["events_with_capital_reaction"], "0")} detail={`${fieldText(eventMeshProofCounts, ["events_with_event_native_capital"], "0")} event-native`} />
              <MiniFact label="Lifecycle Brain" value={fieldText(eventMeshProofCounts, ["events_with_lifecycle_reaction"], "0")} detail={`${fieldText(eventMeshProofCounts, ["events_with_event_native_lifecycle"], "0")} event-native`} />
              <MiniFact label="All Five Brains" value={fieldText(eventMeshProofCounts, ["events_with_all_five_reactions"], "0")} detail="same event correlation" />
              <MiniFact label="Coordinator" value={fieldText(eventMeshProofCounts, ["events_with_coordinator_trace"], "0")} detail={fieldText(eventMeshCoordinator, ["decision"], "NO_DECISION")} />
              <MiniFact label="Correlation" value={fieldText(eventMeshProofSample, ["correlation_id"], "No event")} detail={fieldText(eventMeshProofSample, ["event_id"], "No event id")} />
              <MiniFact label="Market / Side" value={`${fieldText(eventMeshProofSample, ["market_id"], "MISSING")} / ${fieldText(eventMeshProofSample, ["side"], "UNKNOWN")}`} detail={fieldText(eventMeshProofSample, ["token_id"], "No token")} />
              <MiniFact label="Decision" value={fieldText(eventMeshCoordinator, ["decision"], "UNKNOWN")} detail={fieldText(eventMeshCoordinator, ["state"], "UNKNOWN")} />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {asArray(eventMeshProofData.top_blockers).length ? (
                asArray(eventMeshProofData.top_blockers).slice(0, 10).map((entry, index) => {
                  const row = asRecord(entry);
                  return (
                    <span key={`${fieldText(row, ["blocker"], "UNKNOWN")}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                      {fieldText(row, ["blocker"], "UNKNOWN")} ({fieldText(row, ["count"], "0")})
                    </span>
                  );
                })
              ) : (
                <span className="rounded-md border border-poly-cyan/50 bg-poly-cyan/10 px-2 py-1 text-xs font-semibold text-poly-cyan">NO_MESH_PROOF_BLOCKERS_RETURNED</span>
              )}
            </div>
          </div>
        </Section>

        <Section title="Candidate Event Correlation" eyebrow="Candidate actionability requires candidate-scoped event evidence" icon={<Target size={18} />} emphasis>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-poly-text">orderbook.snapshot.created to candidate link</p>
                <p className="mt-1 text-xs text-poly-muted">Market-level events remain visible but cannot authorize candidate actionability.</p>
              </div>
              <StatusPill value={fieldText(candidateEventCorrelationData, ["readiness_state"], "UNKNOWN")} detail={fieldText(candidateEventCorrelationSample, ["candidate_event_link_state"], "UNKNOWN")} />
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-4">
              <MiniFact label="Events Checked" value={fieldText(candidateEventCorrelationCounts, ["events_checked"], "0")} detail={`${fieldText(candidateEventCorrelationCounts, ["candidate_scoped"], "0")} candidate-scoped`} />
              <MiniFact label="Linked" value={fieldText(candidateEventCorrelationCounts, ["linked_to_candidate"], "0")} detail="high-confidence candidate links" />
              <MiniFact label="Market Only" value={fieldText(candidateEventCorrelationCounts, ["market_level_only"], "0")} detail={`${fieldText(candidateEventCorrelationCounts, ["market_scoped_only"], "0")} market-scoped`} />
              <MiniFact label="Unlinked / Ambiguous" value={`${fieldText(candidateEventCorrelationCounts, ["unlinked"], "0")} / ${fieldText(candidateEventCorrelationCounts, ["ambiguous_multiple_candidates"], "0")}`} />
              <MiniFact label="Sample Link" value={fieldText(candidateEventCorrelationSample, ["candidate_event_link_state"], "UNKNOWN")} detail={fieldText(candidateEventCorrelationSample, ["candidate_event_actionability_scope"], "UNKNOWN")} />
              <MiniFact label="Confidence" value={fieldText(candidateEventCorrelationSample, ["correlation_confidence"], "UNKNOWN")} detail={fieldText(candidateEventCorrelationSample, ["candidate_id"], "No candidate")} />
              <MiniFact label="Event" value={fieldText(candidateEventCorrelationSample, ["correlation_id"], "No correlation")} detail={fieldText(candidateEventCorrelationSample, ["event_id"], "No event")} />
              <MiniFact label="Coordinator" value={fieldText(candidateEventCorrelationSample, ["coordinator_decision"], "NO_DECISION")} detail={fieldText(candidateEventCorrelationSample, ["mesh_bundle_state"], "No bundle")} />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {asArray(candidateEventCorrelationData.top_unlinked_reasons).length ? (
                asArray(candidateEventCorrelationData.top_unlinked_reasons).slice(0, 10).map((entry, index) => {
                  const row = asRecord(entry);
                  return (
                    <span key={`${fieldText(row, ["reason"], "UNKNOWN")}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                      {fieldText(row, ["reason"], "UNKNOWN")} ({fieldText(row, ["count"], "0")})
                    </span>
                  );
                })
              ) : (
                <span className="rounded-md border border-poly-cyan/50 bg-poly-cyan/10 px-2 py-1 text-xs font-semibold text-poly-cyan">NO_UNLINKED_REASONS_RETURNED</span>
              )}
            </div>
          </div>
        </Section>

        <Section title="Candidate-Scoped Events" eyebrow="Candidate-targeted refresh must carry candidate_id" icon={<Target size={18} />} emphasis>
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <StatusPill value={fieldText(candidateScopedEventsData, ["readiness_state"], "UNKNOWN")} detail={fieldText(candidateScopedEventsSample, ["candidate_scoped_event_state"], "UNKNOWN")} />
              <span className="text-xs text-poly-muted">Source: candidate-event correlation</span>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <MiniFact label="Checked" value={fieldText(candidateScopedEventsCounts, ["events_checked"], "0")} />
              <MiniFact label="Candidate-Scoped" value={fieldText(candidateScopedEventsCounts, ["candidate_event_scoped"], "0")} />
              <MiniFact label="Market Only" value={fieldText(candidateScopedEventsCounts, ["market_event_only"], "0")} />
              <MiniFact label="Ambiguous" value={fieldText(candidateScopedEventsCounts, ["ambiguous_candidate_event"], "0")} />
              <MiniFact label="Token/Side Mismatch" value={fieldText(candidateScopedEventsCounts, ["token_side_mismatch"], "0")} />
              <MiniFact label="Sample Confidence" value={fieldText(candidateScopedEventsSample, ["correlation_confidence"], "UNKNOWN")} detail={fieldText(candidateScopedEventsSample, ["candidate_event_actionability_scope"], "UNKNOWN")} />
            </div>
          </div>
        </Section>

        <Section title="Paper Actionability" eyebrow="Coordinator decision mapped to paper readiness contract" icon={<Target size={18} />} emphasis>
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <StatusPill value={fieldText(paperActionabilityData, ["readiness_state"], "UNKNOWN")} detail={fieldText(paperActionabilitySample, ["paper_actionability_state"], "UNKNOWN")} />
              <span className="text-xs text-poly-muted">Execution remains disabled in this phase.</span>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <MiniFact label="Checked" value={fieldText(paperActionabilityCounts, ["items_checked"], "0")} />
              <MiniFact label="Actionable Small Paper" value={fieldText(paperActionabilityCounts, ["actionable_small_paper"], "0")} />
              <MiniFact label="Waiting Price" value={fieldText(paperActionabilityCounts, ["waiting_for_price_refresh"], "0")} />
              <MiniFact label="Blocked Lifecycle" value={fieldText(paperActionabilityCounts, ["blocked_by_lifecycle"], "0")} />
              <MiniFact label="Blocked Data" value={fieldText(paperActionabilityCounts, ["blocked_by_data"], "0")} />
              <MiniFact label="Sample Coordinator" value={fieldText(paperActionabilitySample, ["coordinator_decision"], "NO_DECISION")} detail={fieldText(paperActionabilitySample, ["candidate_id"], "No candidate")} />
            </div>
          </div>
        </Section>

        <Section title="Pre-Paper Safety" eyebrow="Certification readiness checklist, not Paper ON" icon={<Lock size={18} />} emphasis>
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <StatusPill value={fieldText(prePaperSafetyData, ["readiness_state"], "UNKNOWN")} detail={fieldText(prePaperSafetyData, ["status"], "UNKNOWN")} />
              <span className="text-xs text-poly-muted">Paper Simulation should remain OFF before Phase 10.</span>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <MiniFact label="Paper Intents" value={fieldText(prePaperSafetyCounts, ["paper_intents"], "0")} />
              <MiniFact label="Paper Orders" value={fieldText(prePaperSafetyCounts, ["paper_orders"], "0")} />
              <MiniFact label="Paper Fills" value={fieldText(prePaperSafetyCounts, ["paper_fills"], "0")} />
              <MiniFact label="Paper Positions" value={fieldText(prePaperSafetyCounts, ["paper_positions"], "0")} />
              <MiniFact label="Live Orders" value={fieldText(prePaperSafetyCounts, ["live_orders"], "0")} />
              <MiniFact label="Duplicate Intent Risk" value={fieldText(prePaperSafetyCounts, ["duplicate_active_intent_risk"], "0")} />
            </div>
          </div>
        </Section>

        <Section title="Unified Blockers" eyebrow="New blocker shape for pre-paper surfaces" icon={<AlertTriangle size={18} />} emphasis>
          <div className="space-y-2">
            {prePaperSafetyBlockers.length ? (
              prePaperSafetyBlockers.slice(0, 8).map((blocker, index) => (
                <div key={`${fieldText(blocker, ["blocker_code"], "BLOCKER")}-${index}`} className="rounded-md border border-poly-line bg-poly-panel p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-poly-text">{fieldText(blocker, ["blocker_code"], "UNKNOWN_BLOCKER")}</span>
                    <StatusPill value={fieldText(blocker, ["severity"], "UNKNOWN")} />
                  </div>
                  <p className="mt-1 text-xs text-poly-muted">{asArray(blocker.required_to_pass).join(" ") || "No required-to-pass text available."}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-poly-muted">No unified blockers reported.</p>
            )}
          </div>
        </Section>

        <Section title="Paper Certification Plan" eyebrow="Dry Phase 10 contract" icon={<Database size={18} />} emphasis>
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <StatusPill value={fieldText(paperCertificationPlanData, ["plan_state"], "UNKNOWN")} detail={fieldText(paperCertificationPlanData, ["readiness_state"], "UNKNOWN")} />
              <span className="text-xs text-poly-muted">This plan does not activate Paper Simulation.</span>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              <MiniFact label="Duration" value={fieldText(asRecord(paperCertificationPlanData.duration), ["recommended_minutes"], "0")} detail="minutes" />
              <MiniFact label="Minimum Cycles" value={fieldText(asRecord(paperCertificationPlanData.duration), ["minimum_cycles"], "0")} />
              <MiniFact label="Maximum Cycles" value={fieldText(asRecord(paperCertificationPlanData.duration), ["maximum_cycles"], "0")} />
            </div>
            <div className="rounded-md border border-poly-line bg-poly-panel p-3 text-sm text-poly-muted">
              Forbidden artifacts: {asArray(paperCertificationPlanData.forbidden_artifact_types).join(", ") || "None listed"}
            </div>
          </div>
        </Section>

        <Section title="Mesh Evidence Bundles" eyebrow="Shared decision room" icon={<Database size={18} />} emphasis>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-poly-text">Shared event evidence</p>
                <p className="mt-1 text-xs text-poly-muted">Bundle assembled from event, orderbook, brain outputs, coordinator, capital, and lifecycle sources.</p>
              </div>
              <StatusPill value={fieldText(meshEvidenceSample, ["bundle_state"], fieldText(meshEvidenceData, ["bundle_state"], "UNKNOWN"))} detail={fieldText(meshEvidenceSample, ["mesh_session_state"], "UNKNOWN")} />
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-4">
              <MiniFact label="Bundles" value={fieldText(meshEvidenceCounts, ["bundles"], "0")} detail={`${fieldText(meshEvidenceCounts, ["complete"], "0")} complete / ${fieldText(meshEvidenceCounts, ["conflicted"], "0")} conflicted`} />
              <MiniFact label="Liquidity / Risk / Exit" value={`${fieldText(meshEvidenceOpinionStates, ["liquidity"], "MISSING")} / ${fieldText(meshEvidenceOpinionStates, ["risk"], "MISSING")} / ${fieldText(meshEvidenceOpinionStates, ["exit"], "MISSING")}`} />
              <MiniFact label="Capital / Lifecycle" value={`${fieldText(meshEvidenceOpinionStates, ["capital"], "MISSING")} / ${fieldText(meshEvidenceOpinionStates, ["lifecycle"], "MISSING")}`} />
              <MiniFact label="Capital Native" value={fieldText(meshEvidenceCapitalOpinion, ["event_native_state"], "UNKNOWN")} detail={fieldText(meshEvidenceCapitalOpinion, ["capital_opinion_state"], "UNKNOWN")} />
              <MiniFact label="Lifecycle Native" value={fieldText(meshEvidenceLifecycleOpinion, ["event_native_state"], "UNKNOWN")} detail={fieldText(meshEvidenceLifecycleOpinion, ["lifecycle_opinion_state"], "UNKNOWN")} />
              <MiniFact label="Consensus" value={fieldText(meshEvidenceSample, ["mesh_consensus_state"], fieldText(meshEvidenceCoordinator, ["mesh_consensus_state"], "UNKNOWN"))} detail={`${fieldText(meshEvidenceCounts, ["with_all_five_opinions"], "0")} all-five bundles`} />
              <MiniFact label="Coordinator" value={fieldText(meshEvidenceCoordinator, ["decision"], "NO_DECISION")} detail={fieldText(meshEvidenceCoordinator, ["state"], "UNKNOWN")} />
              <MiniFact label="Correlation" value={fieldText(meshEvidenceSample, ["correlation_id"], "No bundle")} detail={fieldText(meshEvidenceSample, ["event_id"], "No event")} />
              <MiniFact label="Market / Side" value={`${fieldText(meshEvidenceSample, ["market_id"], "MISSING")} / ${fieldText(meshEvidenceSample, ["side"], "UNKNOWN")}`} detail={fieldText(meshEvidenceSample, ["token_id"], "No token")} />
              <MiniFact label="Orderbook" value={fieldText(asRecord(meshEvidenceSample.orderbook), ["freshness_state"], "UNKNOWN")} detail={fieldText(asRecord(meshEvidenceSample.orderbook), ["snapshot_id"], "No snapshot")} />
              <MiniFact label="Conflicts" value={String(asArray(meshEvidenceSample.conflicts).length)} detail={fieldText(meshEvidenceSample, ["bundle_state"], "UNKNOWN")} />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {asArray(meshEvidenceData.top_conflicts).length ? (
                asArray(meshEvidenceData.top_conflicts).slice(0, 10).map((entry, index) => {
                  const row = asRecord(entry);
                  return (
                    <span key={`${fieldText(row, ["conflict"], "UNKNOWN")}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                      {fieldText(row, ["conflict"], "UNKNOWN")} ({fieldText(row, ["count"], "0")})
                    </span>
                  );
                })
              ) : asArray(meshEvidenceData.top_missing_opinions).length ? (
                asArray(meshEvidenceData.top_missing_opinions).slice(0, 10).map((entry, index) => {
                  const row = asRecord(entry);
                  return (
                    <span key={`${fieldText(row, ["opinion"], "UNKNOWN")}-${index}`} className="rounded-md border border-poly-partial/60 bg-poly-partial/10 px-2 py-1 text-xs font-semibold text-poly-partial">
                      MISSING_{fieldText(row, ["opinion"], "UNKNOWN").toUpperCase()} ({fieldText(row, ["count"], "0")})
                    </span>
                  );
                })
              ) : (
                <span className="rounded-md border border-poly-cyan/50 bg-poly-cyan/10 px-2 py-1 text-xs font-semibold text-poly-cyan">NO_BUNDLE_CONFLICTS_RETURNED</span>
              )}
            </div>
          </div>
        </Section>

        <Section title="Paper Simulation Flow" eyebrow="Explicit simulated execution" icon={<WalletCards size={18} />} emphasis>
          <div className={`rounded-md border p-4 ${fieldText(paperSimulationData, ["status"], "DISABLED") === "ENABLED" ? "border-poly-cyan/50 bg-poly-cyan/10" : "border-poly-line bg-poly-bg/50"}`}>
            <div className="mb-4 rounded-md border border-poly-line bg-poly-bg/50 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-poly-text">Paper Ready</p>
                  <p className="mt-1 text-xs text-poly-muted">Current readiness only; historical ledger health does not count.</p>
                </div>
                <StatusPill value={fieldText(paperReadinessData, ["paper_readiness_state"], "UNKNOWN")} detail={fieldText(paperReadinessData, ["paper_execution_readiness_state"], "UNKNOWN")} />
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-4">
                <MiniFact label="Answer" value={fieldText(paperReadinessData, ["paper_readiness_state"], "UNKNOWN") === "READY" ? "YES" : fieldText(paperReadinessData, ["paper_readiness_state"], "UNKNOWN") === "PARTIAL" ? "PARTIAL" : fieldText(paperReadinessData, ["paper_readiness_state"], "UNKNOWN") === "UNKNOWN" ? "UNKNOWN" : "NO"} detail={fieldText(paperReadinessData, ["last_updated"], "No readiness timestamp")} />
                <MiniFact label="Execution" value={<StatusPill value={fieldText(paperReadinessData, ["paper_execution_readiness_state"], "UNKNOWN")} />} />
                <MiniFact label="Simulation" value={<StatusPill value={fieldText(paperReadinessData, ["paper_simulation_state"], "UNKNOWN")} />} />
                <MiniFact label="Governor Paper" value={fieldText(paperReadinessData, ["governor_allows_paper"], "false")} />
                <MiniFact label="Market / Orderbook" value={`${fieldText(paperReadinessData, ["market_data_state"], "UNKNOWN")} / ${fieldText(paperReadinessData, ["orderbook_state"], "UNKNOWN")}`} detail={`Trusted: ${fieldText(paperReadinessData, ["trusted_orderbook_state"], "UNKNOWN")}`} />
                <MiniFact label="Price Path" value={fieldText(paperReadinessData, ["price_path_state"], "UNKNOWN")} detail={`Refresh: ${fieldText(paperReadinessData, ["refresh_before_execution_state"], "UNKNOWN")}`} />
                <MiniFact label="Candidates" value={fieldText(paperReadinessData, ["candidate_state"], "UNKNOWN")} detail={`${fieldText(paperReadinessCounts, ["eligible_candidates"], "0")} eligible / ${fieldText(paperReadinessCounts, ["blocked_candidates"], "0")} blocked`} />
                <MiniFact label="Intents" value={fieldText(paperReadinessData, ["intent_state"], "UNKNOWN")} detail={`${fieldText(paperReadinessCounts, ["fresh_intents"], "0")} fresh / ${fieldText(paperReadinessCounts, ["stale_intents"], "0")} stale`} />
                <MiniFact label="Risk / Exit / Capital" value={`${fieldText(paperReadinessData, ["risk_state"], "UNKNOWN")} / ${fieldText(paperReadinessData, ["exit_state"], "UNKNOWN")} / ${fieldText(paperReadinessData, ["capital_state"], "UNKNOWN")}`} detail={`Lifecycle: ${fieldText(paperReadinessData, ["lifecycle_state"], "UNKNOWN")}`} />
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {asArray(paperReadinessData.blockers).length ? (
                  asArray(paperReadinessData.blockers).slice(0, 12).map((blocker, index) => (
                    <span key={`${String(blocker)}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                      {String(blocker)}
                    </span>
                  ))
                ) : (
                  <span className="rounded-md border border-poly-cyan/50 bg-poly-cyan/10 px-2 py-1 text-xs font-semibold text-poly-cyan">NO_BLOCKERS_RETURNED</span>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-xl font-semibold text-poly-text">Paper-only path</h3>
              <StatusPill value={fieldText(paperSimulationData, ["status"], "DISABLED")} />
            </div>
            <p className="mt-3 text-sm leading-6 text-poly-muted">{paperSimulationMessage(paperSimulationData, supervisorState.visible, paperFlow)}</p>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <MiniFact label="Switch" value={fieldText(paperSimulationData, ["enabled"], "false")} detail="SYSTEM ON alone does not enable paper orders." />
              <MiniFact label="Paper intents" value={fieldText(supervisorState.visible, ["paper_intents_created"], "0")} />
              <MiniFact label="Blocked / no-trade" value={fieldText(supervisorState.visible, ["paper_intents_blocked"], "0")} />
              <MiniFact label="Orders / fills" value={`${fieldText(supervisorState.visible, ["paper_orders_created"], "0")} / ${fieldText(supervisorState.visible, ["paper_fills_created"], "0")}`} />
              <MiniFact label="Positions opened" value={fieldText(supervisorState.visible, ["paper_positions_opened"], "0")} />
              <MiniFact label="Positions marked" value={fieldText(supervisorState.visible, ["paper_positions_marked"], "0")} />
              <MiniFact label="Realized PnL" value={fieldText(asRecord(paperSimulationData.paper_pnl), ["realized_pnl", "paper_realized_pnl"], fieldText(pnlPayload, ["realized_pnl", "paper_realized_pnl"], "WITHHELD"))} />
              <MiniFact label="Latest flow" value={fieldText(paperFlow, ["status"], fieldText(paperFlow, ["reason"], "No cycle yet"))} />
            </div>
            {asArray(supervisorState.visible.paper_blockers).length ? (
              <div className="mt-4 rounded-md border border-poly-line bg-poly-panel/70 p-3">
                <p className="text-sm font-semibold text-poly-text">Latest paper blockers</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {asArray(supervisorState.visible.paper_blockers).slice(0, 8).map((blocker, index) => (
                    <span key={`${String(blocker)}-${index}`} className="rounded-md border border-poly-line bg-poly-bg px-2 py-1 text-xs text-poly-muted">
                      {String(blocker)}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Section>

        <Section title="Candidate Explanation Ledger" eyebrow="Why candidates stop" icon={<MessageSquareText size={18} />} emphasis>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-xl font-semibold text-poly-text">Candidate truth</h3>
              <StatusPill value={candidateExplanations.data?.status} detail={candidateExplanations.data?.truth_state} />
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <MiniFact label="Total" value={fieldText(candidateExplanationCounts, ["total_candidates"], "0")} />
              <MiniFact label="Blocked" value={fieldText(candidateExplanationCounts, ["blocked"], "0")} />
              <MiniFact label="Eligible" value={fieldText(candidateExplanationCounts, ["eligible"], "0")} />
              <MiniFact label="Ready for intent" value={fieldText(candidateExplanationCounts, ["ready_for_intent"], "0")} />
              <MiniFact label="Eligible without intent" value={fieldText(candidateExplanationGap, ["eligible_without_intent"], "0")} detail={`${fieldText(candidateExplanationGap, ["eligible_candidates"], "0")} eligible / ${fieldText(candidateExplanationGap, ["paper_intents"], "0")} intents`} />
              <MiniFact label="Intent created" value={fieldText(candidateExplanationCounts, ["intent_created"], "0")} />
              <MiniFact label="Stale" value={fieldText(candidateExplanationCounts, ["stale"], "0")} />
              <MiniFact label="Freshness" value={<StatusPill value={fieldText(candidateExplanationData, ["freshness_state"], "UNKNOWN")} />} />
            </div>
            <div className="mt-4 rounded-md border border-poly-line bg-poly-panel/70 p-3">
              <p className="text-sm font-semibold text-poly-text">Top blockers</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {topCandidateBlockers.length ? (
                  topCandidateBlockers.slice(0, 10).map((item, index) => (
                    <span key={`${fieldText(item, ["blocker"], "BLOCKER")}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                      {fieldText(item, ["blocker"], "UNKNOWN_BLOCKER")} ({fieldText(item, ["count"], "0")})
                    </span>
                  ))
                ) : (
                  <span className="rounded-md border border-poly-missing/60 bg-poly-missing/10 px-2 py-1 text-xs font-semibold text-poly-muted">NO_BLOCKERS_RETURNED</span>
                )}
              </div>
            </div>
            {candidateExplanationItems[0] ? (
              <div className="mt-4 rounded-md border border-poly-line bg-poly-panel/70 p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-poly-text">{fieldText(candidateExplanationItems[0], ["candidate_id"], "candidate")}</p>
                    <p className="mt-1 text-xs text-poly-muted">{fieldText(candidateExplanationItems[0], ["operator_summary"], "No summary returned")}</p>
                  </div>
                  <StatusPill value={fieldText(candidateExplanationItems[0], ["explanation_state"], "EXPLAINED_UNKNOWN")} />
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  <MiniFact label="Outcome" value={fieldText(candidateExplanationItems[0], ["final_outcome"], "UNKNOWN")} detail={`Final blocker: ${fieldText(candidateExplanationItems[0], ["final_blocker"], "NONE")}`} />
                  <MiniFact label="Risk / Exit" value={`${fieldText(asRecord(candidateExplanationItems[0].results), ["risk_result"], "UNKNOWN")} / ${fieldText(asRecord(candidateExplanationItems[0].results), ["exit_result"], "UNKNOWN")}`} />
                  <MiniFact label="Next" value={fieldText(candidateExplanationItems[0], ["next_possible_state"], "UNKNOWN")} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {asArray(candidateExplanationItems[0].required_to_pass).slice(0, 5).map((item, index) => (
                    <span key={`${String(item)}-${index}`} className="rounded-md border border-poly-line bg-poly-bg px-2 py-1 text-xs text-poly-muted">
                      {String(item)}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Section>

        <Section title="Eligible To Intent Bridge" eyebrow="No silent eligible gap" icon={<Database size={18} />} emphasis>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-xl font-semibold text-poly-text">Bridge truth</h3>
              <StatusPill value={eligibleIntentBridge.data?.status} detail={eligibleIntentBridge.data?.truth_state} />
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <MiniFact label="Eligible" value={fieldText(bridgeCounts, ["eligible_candidates"], "0")} />
              <MiniFact label="Paper intents" value={fieldText(bridgeCounts, ["paper_intents"], "0")} />
              <MiniFact label="Without intent" value={fieldText(bridgeCounts, ["eligible_without_intent"], "0")} />
              <MiniFact label="Explained without intent" value={fieldText(bridgeGap, ["explained_without_intent"], "0")} detail={`Unexplained: ${fieldText(bridgeGap, ["unexplained_without_intent"], "0")}`} />
              <MiniFact label="Already has intent" value={fieldText(bridgeCounts, ["already_has_intent"], "0")} />
              <MiniFact label="Waiting refresh" value={fieldText(bridgeCounts, ["waiting_for_refresh"], "0")} />
              <MiniFact label="Runtime blocked" value={fieldText(bridgeCounts, ["blocked_by_runtime"], "0")} detail={`Paper sim: ${fieldText(bridgeCounts, ["blocked_by_paper_simulation"], "0")}`} />
              <MiniFact label="Ready for intent" value={fieldText(bridgeCounts, ["ready_for_intent"], "0")} />
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="rounded-md border border-poly-line bg-poly-panel/70 p-3">
                <p className="text-sm font-semibold text-poly-text">Top bridge outcomes</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {topBridgeOutcomes.length ? (
                    topBridgeOutcomes.slice(0, 8).map((item, index) => (
                      <span key={`${fieldText(item, ["outcome"], "OUTCOME")}-${index}`} className="rounded-md border border-poly-line bg-poly-bg px-2 py-1 text-xs text-poly-muted">
                        {fieldText(item, ["outcome"], "UNKNOWN")} ({fieldText(item, ["count"], "0")})
                      </span>
                    ))
                  ) : (
                    <span className="rounded-md border border-poly-missing/60 bg-poly-missing/10 px-2 py-1 text-xs font-semibold text-poly-muted">NO_OUTCOMES_RETURNED</span>
                  )}
                </div>
              </div>
              <div className="rounded-md border border-poly-line bg-poly-panel/70 p-3">
                <p className="text-sm font-semibold text-poly-text">Top bridge blockers</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {topBridgeBlockers.length ? (
                    topBridgeBlockers.slice(0, 8).map((item, index) => (
                      <span key={`${fieldText(item, ["blocker"], "BLOCKER")}-${index}`} className="rounded-md border border-poly-locked/60 bg-poly-locked/10 px-2 py-1 text-xs font-semibold text-poly-locked">
                        {fieldText(item, ["blocker"], "UNKNOWN")} ({fieldText(item, ["count"], "0")})
                      </span>
                    ))
                  ) : (
                    <span className="rounded-md border border-poly-missing/60 bg-poly-missing/10 px-2 py-1 text-xs font-semibold text-poly-muted">NO_BLOCKERS_RETURNED</span>
                  )}
                </div>
              </div>
            </div>
            {bridgeItems[0] ? (
              <div className="mt-4 rounded-md border border-poly-line bg-poly-panel/70 p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-poly-text">{fieldText(bridgeItems[0], ["candidate_id"], "eligible candidate")}</p>
                    <p className="mt-1 text-xs text-poly-muted">{fieldText(bridgeItems[0], ["operator_summary"], "No bridge summary returned")}</p>
                  </div>
                  <StatusPill value={fieldText(bridgeItems[0], ["bridge_outcome"], "UNKNOWN_WITH_EXPLANATION")} detail={fieldText(bridgeItems[0], ["bridge_state"], "UNKNOWN")} />
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  <MiniFact label="Can create now" value={fieldText(bridgeItems[0], ["can_create_intent_now"], "false")} />
                  <MiniFact label="Would create if enabled" value={fieldText(bridgeItems[0], ["would_create_intent_if_enabled"], "false")} />
                  <MiniFact label="Existing intent" value={fieldText(bridgeItems[0], ["existing_intent_id"], "NONE")} detail={fieldText(bridgeItems[0], ["intent_status"], "No intent status")} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {asArray(bridgeItems[0].required_to_create_intent).slice(0, 6).map((item, index) => (
                    <span key={`${String(item)}-${index}`} className="rounded-md border border-poly-line bg-poly-bg px-2 py-1 text-xs text-poly-muted">
                      {String(item)}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Section>

        <Section title="Current Run / Action Guidance" eyebrow="Full Monitor Run state machine" icon={<Radar size={18} />} emphasis>
          <div className={`rounded-md border p-4 ${runGuide.state === "LOCKED" ? "border-poly-locked/60 bg-poly-locked/10" : "border-poly-line bg-poly-bg/50"}`}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-xl font-semibold text-poly-text">{runGuide.title}</h3>
              <StatusPill value={runGuide.rawStatus} />
            </div>
            <p className="mt-3 text-sm leading-6 text-poly-muted">{runGuide.detail}</p>
            <p className="mt-3 rounded-md border border-poly-line bg-poly-panel/70 p-3 text-sm font-semibold text-poly-text">Diagnostic note: {runGuide.nextStep}</p>
            <p className="mt-3 rounded-md border border-poly-cyan/40 bg-poly-cyan/10 p-3 text-sm font-semibold text-poly-cyan">
              <span>Paper simulation requires explicit PAPER SIMULATION ON and remains simulated only.</span>
              <span className="mt-1 block">Full Monitor Run is a diagnostic/report action. SYSTEM ON owns normal continuous monitoring.</span>
            </p>
            {Object.keys(runState.visible).length ? (
              <div className="mt-4 grid gap-3 md:grid-cols-4">
                <MiniFact label="Run ID" value={fieldText(runState.visible, ["run_id"])} />
                <MiniFact label="Status" value={operatorStatus(fieldText(runState.visible, ["status"], "UNKNOWN")).label} />
                <MiniFact label="Elapsed" value={secondsLabel(runState.visible.elapsed_seconds)} />
                <MiniFact label="Remaining" value={secondsLabel(runState.visible.remaining_seconds)} />
                <MiniFact label="Next cycle" value={fieldText(runState.visible, ["next_cycle_in_seconds"], "") ? secondsLabel(runState.visible.next_cycle_in_seconds) : "Not scheduled"} />
                <MiniFact label="Cycles" value={fieldText(runState.visible, ["cycles_completed"], "0")} />
                <MiniFact label="Markets" value={fieldText(runState.visible, ["markets_checked"], "0")} />
                <MiniFact label="Events" value={fieldText(runState.visible, ["events_seen", "events_created"], "0")} />
                <MiniFact label="Opportunities" value={fieldText(runState.visible, ["opportunities_found"], "0")} />
                <MiniFact label="No-Trades" value={fieldText(runState.visible, ["no_trades_logged"], "0")} />
                <MiniFact label="Warnings" value={asArray(runState.visible.warnings).length} />
                <MiniFact label="Errors" value={asArray(runState.visible.errors).length} />
                <MiniFact label="Execution enabled" value={fieldText(runState.visible, ["execution_enabled"], "false")} />
              </div>
            ) : null}
            {fieldText(runState.visible, ["report_path"], "") ? (
              <p className="mt-4 break-words rounded-md border border-poly-line bg-poly-panel/70 p-3 text-sm text-poly-muted">
                Report path: <span className="font-semibold text-poly-text">{fieldText(runState.visible, ["report_path"])}</span>
              </p>
            ) : null}
          </div>
        </Section>

        <Section title="Live Brain Feed" eyebrow="Readable system motion" icon={<Activity size={18} />} emphasis>
          <div className="grid gap-3 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold text-poly-text">Live System Feed</h3>
              {feedEvents.length ? (
                <div className="space-y-2">
                  {feedEvents.map((row, index) => (
                    <div key={`${eventLabel(row)}-${index}`} className="rounded-md border border-poly-line bg-poly-bg/50 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-poly-text">{eventLabel(row)}</p>
                          <p className="mt-1 text-xs text-poly-muted">{eventSummary(row)}</p>
                        </div>
                        <span className="text-right text-[11px] text-poly-muted">{eventTime(row)}</span>
                      </div>
                      <p className="mt-2 text-[11px] uppercase text-poly-cyan">Source: {eventSource(row)}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
                  <p className="text-sm font-semibold text-poly-text">No live events received yet.</p>
                  <p className="mt-2 text-sm text-poly-muted">Start a Full Monitor Run or check source ingestion.</p>
                </div>
              )}
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-poly-text">Brain Dialogue Preview</h3>
              {dialogues.length ? (
                <div className="space-y-2">
                  {dialogues.slice(0, 4).map((row, index) => (
                    <div key={`${dialogueTitle(row)}-${index}`} className="rounded-md border border-poly-line bg-poly-bg/50 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm font-semibold text-poly-text">{dialogueTitle(row)}</p>
                        <span className="text-right text-[11px] text-poly-muted">{eventTime(row)}</span>
                      </div>
                      <p className="mt-1 line-clamp-3 text-xs text-poly-muted">{dialogueMessage(row)}</p>
                    </div>
                  ))}
                  <p className="text-xs text-poly-cyan">Open Mesh Dialogues in Advanced for full detail.</p>
                </div>
              ) : (
                <p className="rounded-md border border-poly-line bg-poly-bg/50 p-4 text-sm text-poly-muted">No mesh dialogue events recorded yet.</p>
              )}
            </div>
          </div>
        </Section>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Section title="Decision / Blockers" eyebrow="Why no trade?" icon={<Target size={18} />}>
          <div className="grid gap-3">
            <MiniFact label="Decision State" value={<StatusPill value={riskEvidence.data?.status} detail={riskEvidence.data?.source ?? undefined} />} detail={riskEvidence.data?.source ?? "Risk source pending."} />
            <MiniFact label="No-Trade Reason" value={firstReason(noTradePayload, blockerPayload)} detail="NO_TRADE remains a first-class decision." />
            <MiniFact label="Closest to Actionable" value={closestCandidates.length} detail={closestCandidates[0] ? fieldText(closestCandidates[0], ["subject_id", "market_id", "candidate_id"], "candidate returned") : "No candidate promoted without truth_state."} />
            <MiniFact label="Risk Blocker Types" value={Object.keys(asRecord(riskPayload.blocker_subtypes)).length} />
          </div>
        </Section>

        <Section title="Money Verdict" eyebrow="Ledger / positions" icon={<WalletCards size={18} />}>
          <div className="grid gap-3">
            <MiniFact label="Money Verdict" value={moneyState} detail="Verdict uses only ledger and positions envelopes." />
            <MiniFact label="Ledger Status" value={<StatusPill value={pnl.data?.status} detail={pnl.data?.source ?? undefined} />} detail={pnl.data?.source ?? "Ledger source pending."} />
            <MiniFact label="Realized PnL" value={fieldText(pnlPayload, ["realized_pnl", "paper_realized_pnl"], "WITHHELD")} detail="Ledger-backed only; no invented PnL." />
            <MiniFact label="Positions" value={positionRows.length || fieldText(positionPayload, ["count", "position_count"], "WITHHELD")} detail={positions.data?.source ?? "Position source pending."} />
          </div>
        </Section>

        <Section title="Attention / Problems" eyebrow="What needs review" icon={<AlertTriangle size={18} />}>
          <div className="grid gap-3">
            <MiniFact label="Warnings" value={warningsCount} detail="Warnings are visible, not hidden." />
            <MiniFact label="Errors" value={errorsCount} detail="Errors require operator review." />
            <MiniFact label="Safety Boundary" value="GATED" detail="No order entry, no blocker bypass, no raw runtime endpoint." />
            <MiniFact label="Advanced Detail" value="Available below" detail="Raw source coverage and endpoints are de-emphasized from the cockpit." />
          </div>
        </Section>
      </div>

      <details className="rounded-md border border-poly-line bg-poly-panel p-4 shadow-truth">
        <summary className="cursor-pointer list-none text-lg font-semibold text-poly-text">
          <span className="mr-2 inline-flex rounded-md border border-poly-line bg-poly-bg/60 p-2 text-poly-cyan">
            <Database size={18} />
          </span>
          Advanced Diagnostics
        </summary>
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
            <h3 className="text-sm font-semibold text-poly-text">Source Coverage</h3>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {Object.entries(sourceCounts).slice(0, 10).map(([source, count]) => (
                <div key={source} className="rounded-md border border-poly-line bg-poly-panel/70 p-3">
                  <p className="text-xs uppercase text-poly-muted">{source}</p>
                  <p className="mt-1 text-lg font-semibold text-poly-text">{String(count)}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-poly-muted">Latest Source Rows: {Object.keys(latestRows).length ? Object.keys(latestRows).join(", ") : "No latest source row map returned."}</p>
          </div>
          <div className="rounded-md border border-poly-line bg-poly-bg/50 p-4">
            <h3 className="text-sm font-semibold text-poly-text">Protected Boundary</h3>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <MiniFact label="KILL SWITCH" value="PROTECTED" detail="Requires actor, reason, and KILL confirmation." />
              <MiniFact label="PnL" value="LEDGER ONLY" detail="No money value is invented without source." />
              <MiniFact label="Dialogue" value="SOURCE ONLY" detail="No mesh line is invented." />
              <MiniFact label="Actions" value="WRAPPER ONLY" detail="/dashboard/api/v2/control/actions/{action_name}" />
            </div>
          </div>
        </div>
      </details>
    </div>
  );
}
