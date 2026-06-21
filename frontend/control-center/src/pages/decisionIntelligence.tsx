import { AlertTriangle, Brain, CheckCircle2, CircleSlash, GitBranch, MessageSquareText, ShieldAlert, Target } from "lucide-react";

import type { TruthEnvelope } from "../lib/truth-contract";
import { MetricTile } from "../layout/MetricTile";
import { Panel } from "../layout/Panel";
import { DecisionGraph } from "./DecisionGraph";
import { asArray, asRecord, entriesOf, fieldNumber, fieldText, latestTimestamp, type UnknownRecord } from "./visibilityUtils";

const TRUTH_STATES = ["ACTIVE_FRESH", "LAST_KNOWN", "HISTORICAL_ONLY", "REFRESH_REQUIRED", "UNKNOWN"] as const;

function ReadOnlyEmpty({ message }: { message: string }) {
  return <div className="rounded-md border border-poly-missing/50 bg-poly-missing/10 p-3 text-sm text-poly-muted">{message}</div>;
}

function WarningsErrors({ envelope }: { envelope: TruthEnvelope }) {
  const messages = [
    ...envelope.warnings.map((text) => ({ kind: "warning", text })),
    ...envelope.errors.map((text) => ({ kind: "error", text }))
  ];

  return (
    <Panel title="Warnings & Errors" eyebrow={messages.length ? "Operator attention" : "No envelope messages"}>
      {messages.length ? (
        <ul className="space-y-2 text-sm">
          {messages.map((item) => (
            <li key={`${item.kind}:${item.text}`} className={item.kind === "error" ? "text-poly-error" : "text-poly-stale"}>
              {item.text}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-poly-muted">No warnings or errors were included in this Truth Contract envelope.</p>
      )}
    </Panel>
  );
}

function FactGrid({ title, eyebrow, facts }: { title: string; eyebrow: string; facts: Array<[string, unknown]> }) {
  const visible = facts.filter(([, value]) => value !== undefined && value !== null && value !== "");
  return (
    <Panel title={title} eyebrow={eyebrow}>
      {visible.length ? (
        <div className="grid gap-2 text-sm md:grid-cols-2">
          {visible.map(([key, value]) => (
            <div key={key} className="rounded-md border border-poly-line bg-poly-bg/40 p-3">
              <p className="text-xs uppercase text-poly-muted">{key}</p>
              <p className="mt-1 break-words text-poly-text">{String(value)}</p>
            </div>
          ))}
        </div>
      ) : (
        <ReadOnlyEmpty message="No scalar facts were present in this source-backed envelope section." />
      )}
    </Panel>
  );
}

function CountMapPanel({ title, eyebrow, map }: { title: string; eyebrow: string; map: UnknownRecord }) {
  const entries = Object.entries(map);
  return (
    <Panel title={title} eyebrow={eyebrow}>
      {entries.length ? (
        <div className="grid gap-2 md:grid-cols-3">
          {entries.map(([name, count]) => (
            <div key={name} className="rounded-md border border-poly-line bg-poly-bg/40 p-3">
              <p className="text-xs uppercase text-poly-muted">{name}</p>
              <p className="mt-2 text-xl font-semibold text-poly-text">{typeof count === "number" ? count : String(count)}</p>
            </div>
          ))}
        </div>
      ) : (
        <ReadOnlyEmpty message="No count map was present in the backend envelope." />
      )}
    </Panel>
  );
}

function ObjectListPanel({
  title,
  eyebrow,
  rows,
  icon: Icon,
  empty,
  labelKeys,
  detailKeys = [],
  limit = 12
}: {
  title: string;
  eyebrow: string;
  rows: UnknownRecord[];
  icon: typeof AlertTriangle;
  empty: string;
  labelKeys: string[];
  detailKeys?: string[];
  limit?: number;
}) {
  return (
    <Panel title={title} eyebrow={`${rows.length} rows`}>
      {rows.length ? (
        <div className="space-y-2">
          {rows.slice(0, limit).map((row, index) => {
            const label = fieldText(row, labelKeys, `${title} ${index + 1}`);
            return (
              <div key={`${title}-${label}-${index}`} className="rounded-md border border-poly-line bg-poly-bg/40 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold text-poly-text">
                    <Icon aria-hidden="true" size={16} className="text-poly-cyan" />
                    {label}
                  </div>
                  <span className="text-xs text-poly-muted">{latestTimestamp(row, ["created_at", "updated_at", "last_updated", "generated_at", "timestamp"])}</span>
                </div>
                {detailKeys.length ? (
                  <div className="mt-2 grid gap-2 text-xs text-poly-muted md:grid-cols-2">
                    {detailKeys.map((key) => (
                      <p key={key} className="break-words">
                        {key}: {fieldText(row, [key], "UNKNOWN")}
                      </p>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <ReadOnlyEmpty message={empty} />
      )}
    </Panel>
  );
}

function SafeRawPreview({ data }: { data: UnknownRecord }) {
  return (
    <Panel title="Raw-Safe Preview" eyebrow="Backend data">
      <pre className="max-h-80 overflow-auto rounded-md border border-poly-line bg-poly-bg/60 p-3 text-xs text-poly-muted">
        {JSON.stringify(data, null, 2)}
      </pre>
    </Panel>
  );
}

function nestedData(envelope: TruthEnvelope, key: string) {
  return asRecord(asRecord(envelope.data)[key]);
}

export function DecisionXRayVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const riskEvidence = asRecord(data.risk_evidence);
  const latest = asArray(riskEvidence.latest_evaluations);
  const blockers = asRecord(riskEvidence.blocker_subtypes);
  const criticalMissing = asRecord(riskEvidence.critical_missing_counts);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Decision Truth" value={envelope.status} detail="Truth Contract status from the decision-xray endpoint." />
        <MetricTile label="Truth State" value={envelope.truth_state} detail="Preserved exactly from the backend envelope." />
        <MetricTile label="Approval Claimed" value={fieldText(data, ["approval_claimed"], "false")} detail="The UI never upgrades this flag." />
        <MetricTile label="Evidence Rows" value={fieldNumber(riskEvidence, ["total_evaluations"]) ?? latest.length} detail="Risk Evidence rows available to explain decision state." />
      </div>
      <FactGrid
        title="Decision Evidence Summary"
        eyebrow="Source-backed"
        facts={[
          ["source", envelope.source ?? "SOURCE_MISSING"],
          ["last_updated", envelope.last_updated ?? "UNKNOWN"],
          ["decision_visibility", fieldText(data, ["decision_visibility"])],
          ["risk_gate_bypassed", fieldText(data, ["risk_gate_bypassed"], "false")],
          ["avg_evidence_quality_score", fieldText(riskEvidence, ["avg_evidence_quality_score"])],
          ["security_governance_status", fieldText(riskEvidence, ["security_governance_status"])]
        ]}
      />
      <DecisionGraph kind="decision-xray" envelope={envelope} />
      <CountMapPanel title="Blocked By" eyebrow="Risk blocker subtypes" map={blockers} />
      <CountMapPanel title="Missing Evidence" eyebrow="Critical evidence gaps" map={criticalMissing} />
      <ObjectListPanel
        title="Recent Decision Evidence"
        eyebrow="Decision chain"
        rows={latest}
        icon={GitBranch}
        empty="No decision evidence rows were returned. The page will not claim a decision path exists."
        labelKeys={["subject_id", "evaluation_id", "risk_decision"]}
        detailKeys={["risk_decision", "risk_blocker_subtype", "edge_source_type", "truth_state"]}
      />
      <WarningsErrors envelope={envelope} />
    </div>
  );
}

export function BlockerCenterVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const blockersData = nestedData(envelope, "blockers");
  const noTrade = asRecord(blockersData.no_trade);
  const riskEvidence = asRecord(blockersData.risk_evidence);
  const latestNoTrade = asArray(noTrade.latest_no_trade);
  const reasons = asArray(noTrade.top_no_trade_reasons);
  const missingRequirements = asArray(noTrade.missing_requirements_summary);
  const riskSourceSelection = asArray(riskEvidence.risk_source_selection_summary);
  const traces = asArray(riskEvidence.latest_risk_review_traces);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Blocker Truth" value={envelope.status} detail="Combined no-trade and risk-evidence status." />
        <MetricTile label="No-Trade Rows" value={fieldNumber(noTrade, ["total_no_trade_records"]) ?? latestNoTrade.length} detail="No invented blocker rows." />
        <MetricTile label="Risk Blocks" value={fieldNumber(riskEvidence, ["RISK_BLOCK"]) ?? "UNKNOWN"} detail="Risk Evidence hard-block count if present." />
        <MetricTile label="Legacy Risk Ignored" value={fieldText(riskEvidence, ["stale_legacy_risk_block_ignored_count", "legacy_risk_ignored_count"])} detail="Only shown when backend summary provides it." />
      </div>
      <ObjectListPanel
        title="No-Trade Blockers"
        eyebrow="Latest records"
        rows={latestNoTrade}
        icon={CircleSlash}
        empty="No no-trade blocker records were returned."
        labelKeys={["reason", "category", "subject_id", "market_id"]}
        detailKeys={["category", "market_id", "side", "truth_state"]}
      />
      <ObjectListPanel
        title="Top Blocker Reasons"
        eyebrow="No-trade summary"
        rows={reasons}
        icon={AlertTriangle}
        empty="No top no-trade reasons were supplied."
        labelKeys={["reason", "blocker", "category", "name"]}
        detailKeys={["count", "severity", "truth_state"]}
      />
      <ObjectListPanel
        title="Missing Requirements"
        eyebrow="Unblock hints"
        rows={missingRequirements}
        icon={Target}
        empty="No missing requirement summary was supplied."
        labelKeys={["requirement", "reason", "blocker", "name"]}
        detailKeys={["count", "severity", "truth_state"]}
      />
      <CountMapPanel title="Risk Blocker Subtypes" eyebrow="Risk vs non-risk evidence" map={asRecord(riskEvidence.blocker_subtypes)} />
      <ObjectListPanel
        title="Risk Source Selection"
        eyebrow="Stale legacy risk handling"
        rows={riskSourceSelection}
        icon={ShieldAlert}
        empty="No risk-source selection summary was supplied."
        labelKeys={["selected_risk_source", "source", "name"]}
        detailKeys={["selected_risk_source_freshness", "count"]}
      />
      <ObjectListPanel
        title="Risk Review Traces"
        eyebrow="Non-risk blockers still block"
        rows={traces}
        icon={GitBranch}
        empty="No Risk Review trace rows were returned."
        labelKeys={["subject_id", "decision_id", "actionability_class"]}
        detailKeys={["actionability_class", "market_id", "side"]}
      />
      <WarningsErrors envelope={envelope} />
    </div>
  );
}

export function ClosestActionableVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const candidates = asArray(data.candidates);
  const visibleCandidates = candidates.filter((candidate) => fieldText(candidate, ["truth_state"], "") !== "");
  const omitted = candidates.length - visibleCandidates.length;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Candidate Truth" value={envelope.status} detail="Endpoint status is preserved." />
        <MetricTile label="Candidates" value={visibleCandidates.length} detail="Only candidates with truth_state are shown." />
        <MetricTile label="Omitted" value={omitted} detail="Candidates missing truth_state are withheld." />
        <MetricTile label="Last Updated" value={envelope.last_updated ?? "UNKNOWN"} detail="From Truth Contract envelope." />
      </div>
      <Panel title="Candidates Closest To Actionable" eyebrow="truth_state required">
        {visibleCandidates.length ? (
          <div className="space-y-2">
            {visibleCandidates.slice(0, 20).map((candidate, index) => (
              <div key={`${fieldText(candidate, ["subject_id", "candidate_id", "market_id"], `candidate-${index}`)}-${index}`} className="rounded-md border border-poly-line bg-poly-bg/40 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold text-poly-text">{fieldText(candidate, ["subject_id", "candidate_id", "market_id"], "UNKNOWN_CANDIDATE")}</p>
                  <span className="text-xs text-poly-muted">{fieldText(candidate, ["truth_state"])}</span>
                </div>
                <div className="mt-2 grid gap-2 text-xs text-poly-muted md:grid-cols-2">
                  <p>market: {fieldText(candidate, ["market_id", "condition_id", "subject"])}</p>
                  <p>actionability: {fieldText(candidate, ["actionability_class", "risk_decision", "edge_status"])}</p>
                  <p>blockers: {JSON.stringify(candidate.critical_evidence_missing_json ?? candidate.critical_missing ?? candidate.blockers ?? [])}</p>
                  <p>one thing preventing actionability: {fieldText(candidate, ["risk_blocker_subtype", "blocker", "missing_requirement", "reason"])}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <ReadOnlyEmpty message="No candidate with truth_state was returned. The UI will not mark anything actionable." />
        )}
      </Panel>
      {omitted > 0 ? <ReadOnlyEmpty message={`${omitted} candidate row(s) were omitted because truth_state was missing.`} /> : null}
      <WarningsErrors envelope={envelope} />
    </div>
  );
}

export function TruthStateVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const counts = asRecord(data.truth_state_counts);
  const sourceStateCounts = asArray(data.source_state_counts);
  const latest = asArray(data.latest_truth);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-5">
        {TRUTH_STATES.map((state) => (
          <MetricTile key={state} label={state} value={fieldNumber(counts, [state]) ?? 0} detail="Count supplied by truth_state_registry summary." />
        ))}
      </div>
      <FactGrid
        title="Freshness Summary"
        eyebrow="Decision permissions"
        facts={[
          ["total_truth_records", fieldText(data, ["total_truth_records"])],
          ["can_authorize_count", fieldText(data, ["can_authorize_count"])],
          ["refresh_required_count", fieldText(data, ["refresh_required_count"])],
          ["historical_memory_count", fieldText(data, ["historical_memory_count"])],
          ["stale_same_market_guard_count", fieldText(data, ["stale_same_market_guard_count"])],
          ["old_intents_requiring_refresh", fieldText(data, ["old_intents_requiring_refresh"])]
        ]}
      />
      <ObjectListPanel
        title="Source Map"
        eyebrow="Source state counts"
        rows={sourceStateCounts}
        icon={GitBranch}
        empty="No source-state map was returned."
        labelKeys={["source_type", "source", "name"]}
        detailKeys={["truth_state", "count"]}
      />
      <ObjectListPanel
        title="Latest Truth Records"
        eyebrow="Registry evidence"
        rows={latest}
        icon={CheckCircle2}
        empty="No truth registry rows were returned."
        labelKeys={["source_type", "truth_id", "subject_id"]}
        detailKeys={["truth_state", "decision_permission", "freshness_reason"]}
      />
      <WarningsErrors envelope={envelope} />
    </div>
  );
}

export function RiskEvidenceMeshVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const riskEvidence = asRecord(data.risk_evidence);
  const latest = asArray(riskEvidence.latest_evaluations);
  const traces = asArray(riskEvidence.latest_risk_review_traces);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Risk Evidence Truth" value={envelope.status} detail="Truth Contract status from risk-evidence endpoint." />
        <MetricTile label="Risk Gate Bypassed" value={fieldText(data, ["risk_gate_bypassed"], "false")} detail="Must remain false." />
        <MetricTile label="Approval Claimed" value={fieldText(data, ["approval_claimed"], "false")} detail="Risk Evidence display cannot grant execution approval." />
        <MetricTile label="Total Evaluations" value={fieldNumber(riskEvidence, ["total_evaluations"]) ?? latest.length} detail="Source-backed evaluation count." />
      </div>
      <div className="grid gap-4 md:grid-cols-4">
        {["RISK_SUPPORT", "RISK_WATCH", "RISK_REVIEW", "RISK_BLOCK"].map((key) => (
          <MetricTile key={key} label={key} value={fieldNumber(riskEvidence, [key]) ?? 0} detail="Backend-provided risk decision count." />
        ))}
      </div>
      <FactGrid
        title="Selected Risk Source"
        eyebrow="Evidence priority"
        facts={[
          ["source", envelope.source ?? "SOURCE_MISSING"],
          ["security_governance_status", fieldText(riskEvidence, ["security_governance_status"])],
          ["stale_legacy_risk_block_ignored_count", fieldText(riskEvidence, ["stale_legacy_risk_block_ignored_count"])],
          ["legacy_risk_ignored_count", fieldText(riskEvidence, ["legacy_risk_ignored_count"])],
          ["avg_evidence_quality_score", fieldText(riskEvidence, ["avg_evidence_quality_score"])]
        ]}
      />
      <DecisionGraph kind="conflict-map" envelope={envelope} />
      <CountMapPanel title="Source-Backed Edge" eyebrow="Edge source types" map={asRecord(riskEvidence.edge_source_type_counts)} />
      <CountMapPanel title="Critical Blockers" eyebrow="Critical missing evidence" map={asRecord(riskEvidence.critical_missing_counts)} />
      <CountMapPanel title="Supporting / Optional Evidence Gaps" eyebrow="Optional context missing" map={asRecord(riskEvidence.optional_missing_counts)} />
      <ObjectListPanel
        title="Latest Risk Evidence"
        eyebrow="Read-only evaluations"
        rows={latest}
        icon={ShieldAlert}
        empty="No risk evidence rows were returned."
        labelKeys={["subject_id", "evaluation_id", "risk_decision"]}
        detailKeys={["risk_decision", "risk_blocker_subtype", "edge_source_type", "evidence_quality_score"]}
      />
      <ObjectListPanel
        title="Risk Review Traces"
        eyebrow="Legacy risk replacement evidence"
        rows={traces}
        icon={GitBranch}
        empty="No Risk Review trace rows were returned."
        labelKeys={["subject_id", "decision_id", "actionability_class"]}
        detailKeys={["actionability_class", "market_id", "side"]}
      />
      <WarningsErrors envelope={envelope} />
    </div>
  );
}

export function LifecycleGovernanceVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const lifecycle = nestedData(envelope, "lifecycle_governance");
  const latest = asArray(lifecycle.latest_decisions);
  const traces = asArray(lifecycle.latest_risk_review_traces);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Governance Truth" value={envelope.status} detail="Lifecycle Governance envelope status." />
        <MetricTile label="Hard Blocked" value={fieldText(lifecycle, ["hard_block_count"])} detail="Backend actionability count." />
        <MetricTile label="Promoted To Watch" value={fieldText(lifecycle, ["risk_review_promoted_to_watch_count"])} detail="Fresh non-blocking Risk Evidence can promote only when blockers allow it." />
        <MetricTile label="Actionable Count" value={fieldText(lifecycle, ["risk_review_actionable_count"])} detail="Count only; this page exposes no action controls." />
      </div>
      <FactGrid
        title="Governance Outcome"
        eyebrow="Read-only gate summary"
        facts={[
          ["allow_paper_intent_count", fieldText(lifecycle, ["allow_paper_intent_count"])],
          ["allow_paper_execution_count", fieldText(lifecycle, ["allow_paper_execution_count"])],
          ["legacy_risk_ignored_count", fieldText(lifecycle, ["legacy_risk_ignored_count"])],
          ["stale_legacy_risk_block_ignored_count", fieldText(lifecycle, ["stale_legacy_risk_block_ignored_count"])],
          ["risk_review_kept_blocked_count", fieldText(lifecycle, ["risk_review_kept_blocked_count"])],
          ["security_governance_status", fieldText(lifecycle, ["security_governance_status"])]
        ]}
      />
      <DecisionGraph kind="candidate-lifecycle" envelope={envelope} />
      <CountMapPanel title="Actionability Classes" eyebrow="Governance state" map={asRecord(lifecycle.decisions_by_actionability)} />
      <ObjectListPanel
        title="Critical Gates"
        eyebrow="Non-risk blockers still block"
        rows={asArray(lifecycle.critical_blockers_top)}
        icon={AlertTriangle}
        empty="No critical gate summary was returned."
        labelKeys={["value", "blocker", "name"]}
        detailKeys={["count"]}
      />
      <ObjectListPanel
        title="Risk Source Selection"
        eyebrow="Freshness selection"
        rows={asArray(lifecycle.risk_source_selection_summary)}
        icon={ShieldAlert}
        empty="No risk-source selection summary was returned."
        labelKeys={["selected_risk_source", "source", "name"]}
        detailKeys={["selected_risk_source_freshness", "count"]}
      />
      <ObjectListPanel
        title="Latest Governance Decisions"
        eyebrow="Actionability evidence"
        rows={latest}
        icon={GitBranch}
        empty="No lifecycle governance decisions were returned."
        labelKeys={["subject_id", "decision_id", "actionability_class"]}
        detailKeys={["actionability_class", "allow_paper_intent", "allow_paper_execution", "reason"]}
      />
      <ObjectListPanel
        title="Latest Risk Review Traces"
        eyebrow="Stale legacy risk handling"
        rows={traces}
        icon={Target}
        empty="No lifecycle Risk Review traces were returned."
        labelKeys={["subject_id", "decision_id", "actionability_class"]}
        detailKeys={["actionability_class", "market_id", "side"]}
      />
      <WarningsErrors envelope={envelope} />
    </div>
  );
}

export function MeshDialoguesVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const dialogues = asRecord(data.mesh_dialogues);
  const events = asArray(dialogues.events);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Dialogue Truth" value={envelope.status} detail="Truth Contract status from brain_dialogue_events." />
        <MetricTile label="Events" value={fieldNumber(dialogues, ["count"]) ?? events.length} detail="Actual dialogue event rows only." />
        <MetricTile label="Dialogue Invented" value={fieldText(data, ["dialogue_invented"], "false")} detail="Must remain false." />
        <MetricTile label="Latest Event" value={fieldText(dialogues, ["latest_event_at", "generated_at"])} detail="Backend timestamp." />
      </div>
      <DecisionGraph kind="brain-flow" envelope={envelope} />
      <ObjectListPanel
        title="Brain / Mesh Dialogue Events"
        eyebrow="No invented dialogue"
        rows={events}
        icon={MessageSquareText}
        empty="No brain dialogue events were returned. The UI will not invent dialogue."
        labelKeys={["brain_name", "source", "event_type", "role", "speaker", "name"]}
        detailKeys={["message", "opinion", "confidence", "status", "conflict", "coordinator_summary", "final_summary"]}
        limit={20}
      />
      <FactGrid title="Dialogue Source" eyebrow="Read-only" facts={entriesOf(dialogues).slice(0, 8)} />
      <WarningsErrors envelope={envelope} />
      {events.length ? null : <SafeRawPreview data={data} />}
    </div>
  );
}
