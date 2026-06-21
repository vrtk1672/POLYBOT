import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { ControlCenterActionEnvelope, ControlCenterActionName } from "../api/controlCenterActions";
import { controlCenterActionEndpoint, controlCenterActionEndpointPrefix } from "../api/controlCenterActions";
import { useControlCenterActionMutation } from "../api/useControlCenterActions";
import { useFullMonitorRunQuery } from "../api/useControlCenterQueries";
import { PageHeader } from "../layout/PageHeader";
import { Panel } from "../layout/Panel";

type ActionAvailability = "available" | "locked" | "not implemented";

type ActionDefinition = {
  action: ControlCenterActionName;
  label: string;
  availability: ActionAvailability;
  requiresConfirmation?: string;
  durationRequired?: boolean;
  reason: string;
};

const ACTIONS: ActionDefinition[] = [
  {
    action: "system-on",
    label: "SYSTEM ON",
    availability: "available",
    reason: "Requests audited system power ON through the Control Center action wrapper."
  },
  {
    action: "system-off",
    label: "SYSTEM OFF",
    availability: "available",
    reason: "Requests audited system power OFF through the Control Center action wrapper."
  },
  {
    action: "start-full-monitor-run",
    label: "START MONITORING RUN",
    availability: "available",
    durationRequired: true,
    reason: "Starts a bounded audited Full Monitor Run through the Control Center action wrapper."
  },
  {
    action: "stop-current-run",
    label: "STOP CURRENT RUN",
    availability: "available",
    reason: "Stops the current Full Monitor Run if one is active; safe no-op if none is running."
  },
  {
    action: "kill-switch",
    label: "KILL SWITCH",
    availability: "available",
    requiresConfirmation: "KILL",
    reason: "Requests KILL only through the State Governor action wrapper."
  },
  {
    action: "reset-paper-balance",
    label: "RESET PAPER BALANCE",
    availability: "locked",
    requiresConfirmation: "RESET PAPER BALANCE",
    reason: "Locked until a paper-only reset contract with audit persistence and ledger trace exists."
  }
];

function statusTone(status?: string) {
  if (status === "ACCEPTED" || status === "COMPLETED" || status === "STOPPED" || status === "RUNNING") return "border-poly-good text-poly-good";
  if (status === "REJECTED" || status === "LOCKED" || status === "NOT_IMPLEMENTED" || status === "SKIPPED") return "border-poly-warn text-poly-warn";
  if (status === "ERROR") return "border-poly-danger text-poly-danger";
  return "border-poly-line text-poly-muted";
}

function exportSnapshot(snapshot: unknown) {
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `polybot-control-center-read-only-snapshot-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ControlActionsPanel() {
  const queryClient = useQueryClient();
  const fullMonitorRunQuery = useFullMonitorRunQuery();
  const actionMutation = useControlCenterActionMutation();
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [confirmationByAction, setConfirmationByAction] = useState<Record<string, string>>({});
  const [durationMinutes, setDurationMinutes] = useState(30);
  const [intervalSeconds, setIntervalSeconds] = useState(10);
  const [lastResult, setLastResult] = useState<ControlCenterActionEnvelope | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);

  const loadedSnapshot = useMemo(() => {
    const entries = queryClient.getQueriesData({ queryKey: ["control-center"] });
    return Object.fromEntries(
      entries.map(([key, value]) => {
        const endpointKey = Array.isArray(key) ? String(key[1] ?? "unknown") : String(key);
        return [endpointKey, value ?? null];
      })
    );
  }, [queryClient]);

  function refreshReadOnlyData() {
    void queryClient.invalidateQueries({ queryKey: ["control-center"] });
    setExportMessage("Refresh requested for read-only Control Center data.");
  }

  function exportReadOnlyReport() {
    const snapshot = {
      report_type: "POLYBOT_CONTROL_CENTER_READ_ONLY_SNAPSHOT",
      generated_at: new Date().toISOString(),
      source: "frontend:tanstack_query_cache",
      note: "Read-only snapshot export. No backend mutation, runtime action, order, fill, or position is created.",
      envelopes: loadedSnapshot
    };
    exportSnapshot(snapshot);
    setExportMessage("Read-only snapshot export prepared from loaded frontend envelopes.");
  }

  function canSubmit(definition: ActionDefinition) {
    if (definition.availability !== "available") return false;
    if (!actor.trim() || !reason.trim()) return false;
    if (definition.durationRequired && (!Number.isFinite(durationMinutes) || durationMinutes < 1 || durationMinutes > 60)) return false;
    if (definition.durationRequired && (!Number.isFinite(intervalSeconds) || intervalSeconds < 10 || intervalSeconds > 300)) return false;
    if (definition.requiresConfirmation && confirmationByAction[definition.action]?.trim() !== definition.requiresConfirmation) return false;
    return !actionMutation.isPending;
  }

  async function submitAction(definition: ActionDefinition) {
    if (!canSubmit(definition)) return;
    const result = await actionMutation.mutateAsync({
      action: definition.action,
      payload: {
        actor,
        reason,
        confirmation: confirmationByAction[definition.action],
        duration_minutes: definition.durationRequired ? durationMinutes : undefined,
        interval_seconds: definition.durationRequired ? intervalSeconds : undefined,
        metadata: { source: "control-center-v1.5-stage-25-monitoring-runtime" }
      }
    });
    setLastResult(result);
    void fullMonitorRunQuery.refetch();
  }

  const runFromAction = lastResult?.result?.run_id ? lastResult.result : null;
  const latestRun = fullMonitorRunQuery.data?.data?.latest && typeof fullMonitorRunQuery.data.data.latest === "object" ? fullMonitorRunQuery.data.data.latest : null;
  const visibleRun = (runFromAction ?? latestRun) as Record<string, unknown> | null;

  return (
    <div className="space-y-5" data-testid="page-settings">
      <div data-testid="control-actions-panel" className="sr-only">
        Stage 15 Control Actions Panel
      </div>
      <PageHeader
        title="Controls"
        purpose="Safety-gated Control Center actions. Frontend-only actions stay read-only; backend actions use only the audited Control Center wrapper."
        endpoint={controlCenterActionEndpointPrefix}
        stateLabel="CONTROL_ACTIONS_GATED"
      />

      <div className="grid gap-4 xl:grid-cols-[0.85fr_1.15fr]">
        <Panel title="Read-Only Actions" eyebrow="No mutation">
          <div className="grid gap-3 text-sm text-poly-muted md:grid-cols-2">
            <button
              type="button"
              onClick={refreshReadOnlyData}
              className="rounded-md border border-poly-line bg-poly-panel-strong px-3 py-2 text-left font-semibold text-poly-text hover:border-poly-cyan hover:text-poly-cyan"
            >
              Refresh read-only data
            </button>
            <button
              type="button"
              onClick={exportReadOnlyReport}
              className="rounded-md border border-poly-line bg-poly-panel-strong px-3 py-2 text-left font-semibold text-poly-text hover:border-poly-cyan hover:text-poly-cyan"
            >
              Export read-only snapshot
            </button>
          </div>
          {exportMessage ? <p className="mt-3 text-sm text-poly-muted">{exportMessage}</p> : null}
        </Panel>

        <Panel title="Operator Fields" eyebrow="Required">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="grid gap-1 text-sm text-poly-muted">
              Actor
              <input
                value={actor}
                onChange={(event) => setActor(event.target.value)}
                className="rounded-md border border-poly-line bg-poly-panel-strong px-3 py-2 text-poly-text outline-none focus:border-poly-cyan"
                placeholder="operator id"
              />
            </label>
            <label className="grid gap-1 text-sm text-poly-muted">
              Reason
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                className="rounded-md border border-poly-line bg-poly-panel-strong px-3 py-2 text-poly-text outline-none focus:border-poly-cyan"
                placeholder="required audit reason"
              />
            </label>
          </div>
        </Panel>
      </div>

      <Panel title="Backend Control Actions" eyebrow="POST wrapper only">
        <div className="grid gap-3 lg:grid-cols-2">
          {ACTIONS.map((definition) => {
            const disabled = !canSubmit(definition);
            return (
              <div key={definition.action} className="rounded-md border border-poly-line bg-poly-panel-strong p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-poly-text">{definition.label}</p>
                    <p className="mt-1 text-xs text-poly-muted">{definition.reason}</p>
                    <p className="mt-2 text-xs text-poly-muted">{controlCenterActionEndpoint(definition.action)}</p>
                  </div>
                  <span className={`rounded-full border px-2 py-1 text-xs font-semibold uppercase ${statusTone(definition.availability === "available" ? undefined : definition.availability)}`}>
                    {definition.availability}
                  </span>
                </div>
                {definition.durationRequired ? (
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <label className="grid gap-1 text-xs text-poly-muted">
                      Duration minutes
                      <input
                        type="number"
                        min={1}
                        max={60}
                        value={durationMinutes}
                        onChange={(event) => setDurationMinutes(Number(event.target.value))}
                        className="rounded-md border border-poly-line bg-poly-panel px-3 py-2 text-poly-text outline-none focus:border-poly-cyan"
                      />
                    </label>
                    <label className="grid gap-1 text-xs text-poly-muted">
                      Interval seconds
                      <input
                        type="number"
                        min={10}
                        max={300}
                        value={intervalSeconds}
                        onChange={(event) => setIntervalSeconds(Number(event.target.value))}
                        className="rounded-md border border-poly-line bg-poly-panel px-3 py-2 text-poly-text outline-none focus:border-poly-cyan"
                      />
                    </label>
                  </div>
                ) : null}
                {definition.requiresConfirmation ? (
                  <label className="mt-3 grid gap-1 text-xs text-poly-muted">
                    Confirmation
                    <input
                      value={confirmationByAction[definition.action] ?? ""}
                      onChange={(event) =>
                        setConfirmationByAction((current) => ({ ...current, [definition.action]: event.target.value }))
                      }
                      className="rounded-md border border-poly-line bg-poly-panel px-3 py-2 text-poly-text outline-none focus:border-poly-cyan"
                      placeholder={definition.requiresConfirmation}
                    />
                  </label>
                ) : null}
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => void submitAction(definition)}
                  className="mt-3 w-full rounded-md border border-poly-line bg-poly-panel px-3 py-2 text-sm font-semibold text-poly-text hover:border-poly-cyan hover:text-poly-cyan disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {definition.availability === "available" ? `Request ${definition.label}` : definition.availability.toUpperCase()}
                </button>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title="Full Monitor Run Status" eyebrow="Read-only status">
        {visibleRun ? (
          <div className="space-y-3 text-sm text-poly-muted">
            <dl className="grid gap-2 md:grid-cols-4">
              {[
                ["Run ID", visibleRun.run_id],
                ["Status", visibleRun.status],
                ["Cycles", visibleRun.cycles_completed],
                ["Markets", visibleRun.markets_checked],
                ["Opportunities", visibleRun.opportunities_found],
                ["No-Trade", visibleRun.no_trades_logged],
                ["Paper Orders", visibleRun.paper_orders],
                ["Paper Fills", visibleRun.paper_fills],
                ["Positions Updated", visibleRun.positions_updated],
                ["Audit", visibleRun.audit_id],
                ["Duration", visibleRun.requested_duration_minutes],
                ["Elapsed", visibleRun.elapsed_seconds]
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-md border border-poly-line p-2">
                  <dt className="text-xs uppercase text-poly-muted">{String(label)}</dt>
                  <dd className="mt-1 break-words text-poly-text">{String(value ?? "UNKNOWN")}</dd>
                </div>
              ))}
            </dl>
            {Array.isArray(visibleRun.module_results) ? (
              <div className="grid gap-2 md:grid-cols-2">
                {visibleRun.module_results.slice(0, 20).map((item, index) => {
                  const row = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
                  return (
                    <div key={`${String(row.module ?? "module")}-${index}`} className="rounded-md border border-poly-line p-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-poly-text">{String(row.module ?? "UNKNOWN")}</span>
                        <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${statusTone(String(row.status ?? ""))}`}>
                          {String(row.status ?? "UNKNOWN")}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-poly-muted">{String(row.behavior ?? "")}</p>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-poly-muted">No Full Monitor Run result is loaded yet.</p>
        )}
      </Panel>

      <Panel title="Last Action Result" eyebrow="Audit / safety">
        {lastResult ? (
          <div className="space-y-3 text-sm text-poly-muted">
            <div className={`inline-flex rounded-full border px-2 py-1 text-xs font-semibold ${statusTone(lastResult.status)}`}>
              {lastResult.status}
            </div>
            <dl className="grid gap-2 md:grid-cols-3">
              <div>
                <dt className="text-xs uppercase text-poly-muted">Action</dt>
                <dd className="text-poly-text">{lastResult.action}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-poly-muted">Audit</dt>
                <dd className="text-poly-text">{lastResult.audit_id ?? "NO_AUDIT_ID"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-poly-muted">Timestamp</dt>
                <dd className="text-poly-text">{lastResult.timestamp}</dd>
              </div>
            </dl>
            <div className="grid gap-2">
              {lastResult.safety_checks.map((check) => (
                <div key={`${check.name}-${check.detail}`} className="rounded-md border border-poly-line p-2">
                  <span className="font-semibold text-poly-text">{check.name}</span>: {check.status} / {check.detail}
                </div>
              ))}
            </div>
            {[...lastResult.warnings, ...lastResult.errors].length ? (
              <div className="rounded-md border border-poly-warn/40 p-2 text-poly-warn">
                {[...lastResult.warnings, ...lastResult.errors].join(" ")}
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-poly-muted">No backend control action has been requested in this session.</p>
        )}
      </Panel>
    </div>
  );
}
