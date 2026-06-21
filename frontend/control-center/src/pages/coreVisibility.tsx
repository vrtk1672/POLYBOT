import { AlertTriangle, Activity, Database, Radio, Server } from "lucide-react";

import type { TruthEnvelope } from "../lib/truth-contract";
import { MetricTile } from "../layout/MetricTile";
import { Panel } from "../layout/Panel";
import { asArray, asRecord, fieldNumber, fieldText, latestTimestamp } from "./visibilityUtils";

function EmptyReadOnlyState({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-poly-missing/50 bg-poly-missing/10 p-3 text-sm text-poly-muted">
      {message}
    </div>
  );
}

function WarningErrorPanel({ envelope }: { envelope: TruthEnvelope }) {
  const items = [
    ...envelope.warnings.map((item) => ({ type: "warning", text: item })),
    ...envelope.errors.map((item) => ({ type: "error", text: item }))
  ];

  return (
    <Panel title="Warnings & Errors" eyebrow={items.length ? "Operator attention" : "No envelope messages"}>
      {items.length ? (
        <ul className="space-y-2 text-sm">
          {items.map((item) => (
            <li key={`${item.type}:${item.text}`} className={item.type === "error" ? "text-poly-error" : "text-poly-stale"}>
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

export function OverviewVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const sourceCounts = asRecord(data.source_counts);
  const latestRows = asRecord(data.latest_rows);
  const endpointCount = Array.isArray(data.control_endpoints) ? data.control_endpoints.length : null;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Body Truth" value={envelope.status} detail="From the overview Truth Contract status." />
        <MetricTile label="Freshness" value={envelope.truth_state} detail="Never upgraded by frontend logic." />
        <MetricTile label="Source Tables" value={Object.keys(sourceCounts).length} detail="Tables observed by the read-only overview probe." />
        <MetricTile label="Read-Only Endpoints" value={endpointCount ?? "UNKNOWN"} detail="Endpoint list supplied by the backend envelope." />
      </div>

      <Panel title="Source Coverage" eyebrow="Body map">
        {Object.keys(sourceCounts).length ? (
          <div className="grid gap-2 md:grid-cols-3">
            {Object.entries(sourceCounts).map(([name, count]) => (
              <div key={name} className="rounded-md border border-poly-line bg-poly-bg/40 p-3">
                <p className="text-xs uppercase text-poly-muted">{name}</p>
                <p className="mt-2 text-xl font-semibold text-poly-text">{typeof count === "number" ? count : "UNKNOWN"}</p>
              </div>
            ))}
          </div>
        ) : (
          <EmptyReadOnlyState message="No source-count coverage was present. Missing source coverage means the body cannot be called alive." />
        )}
      </Panel>

      <Panel title="Latest Source Rows" eyebrow="Last known evidence">
        {Object.keys(latestRows).length ? (
          <div className="space-y-2">
            {Object.entries(latestRows).map(([table, row]) => {
              const record = asRecord(row);
              return (
                <div key={table} className="rounded-md border border-poly-line bg-poly-bg/40 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-poly-text">{table}</span>
                    <span className="text-poly-muted">{latestTimestamp(record)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyReadOnlyState message="No latest source rows were present in the overview envelope." />
        )}
      </Panel>

      <WarningErrorPanel envelope={envelope} />
    </div>
  );
}

export function OrganHealthVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const services = asArray(data.services);
  const count = fieldNumber(data, ["count"]) ?? services.length;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricTile label="Organ Truth" value={envelope.status} detail="Envelope status from service_health heartbeat source." />
        <MetricTile label="Services Reported" value={count} detail="Rows returned by the read-only service_health query." />
        <MetricTile label="Latest Heartbeat" value={fieldText(data, ["latest_heartbeat_at", "generated_at"])} detail="Timestamp supplied by backend truth." />
      </div>

      <Panel title="Organs / Services" eyebrow="Heartbeat evidence">
        {services.length ? (
          <div className="space-y-2">
            {services.slice(0, 20).map((service, index) => (
              <div key={`${fieldText(service, ["service_name", "service", "name", "component"], `service-${index}`)}-${index}`} className="rounded-md border border-poly-line bg-poly-bg/40 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold text-poly-text">
                    <Server aria-hidden="true" size={16} className="text-poly-cyan" />
                    {fieldText(service, ["service_name", "service", "name", "component"], "UNKNOWN_SERVICE")}
                  </div>
                  <span className="text-xs text-poly-muted">{fieldText(service, ["last_heartbeat_at", "updated_at", "created_at"])}</span>
                </div>
                <p className="mt-2 text-sm text-poly-muted">Reported state: {fieldText(service, ["status", "health", "state", "mode"])}</p>
              </div>
            ))}
          </div>
        ) : (
          <EmptyReadOnlyState message="No service heartbeat rows were returned. The UI will not claim any organ is healthy." />
        )}
      </Panel>

      <WarningErrorPanel envelope={envelope} />
    </div>
  );
}

export function LiveFlowVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const events = asArray(data.events);
  const count = fieldNumber(data, ["count"]) ?? events.length;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricTile label="Flow Truth" value={envelope.status} detail="Envelope status from the event_log source." />
        <MetricTile label="Events Returned" value={count} detail="Read-only event rows in this envelope." />
        <MetricTile label="Latest Event" value={latestTimestamp(data)} detail="Latest timestamp supplied by backend truth." />
      </div>

      <Panel title="Event Stream" eyebrow="Read-only live flow">
        {events.length ? (
          <div className="space-y-2">
            {events.slice(0, 25).map((event, index) => {
              const label = fieldText(event, ["event_type", "type", "name", "topic"], `event-${index + 1}`);
              return (
                <div key={`${label}-${index}`} className="rounded-md border border-poly-line bg-poly-bg/40 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-sm font-semibold text-poly-text">
                      <Radio aria-hidden="true" size={16} className="text-poly-cyan" />
                      {label}
                    </div>
                    <span className="text-xs text-poly-muted">{fieldText(event, ["stored_at", "occurred_at", "created_at", "timestamp"])}</span>
                  </div>
                  <p className="mt-2 text-xs text-poly-muted">ID: {fieldText(event, ["id", "event_id", "event_key"])}</p>
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyReadOnlyState message="No event rows were returned. Missing live flow means the body cannot be assumed active." />
        )}
      </Panel>

      <WarningErrorPanel envelope={envelope} />
    </div>
  );
}

function LogSection({ title, rows, icon }: { title: string; rows: Record<string, unknown>[]; icon: "incident" | "attempt" | "event" }) {
  const Icon = icon === "incident" ? AlertTriangle : icon === "attempt" ? Activity : Database;
  return (
    <Panel title={title} eyebrow={`${rows.length} rows`}>
      {rows.length ? (
        <div className="space-y-2">
          {rows.slice(0, 12).map((row, index) => {
            const label = fieldText(row, ["type", "event_type", "status", "incident_type", "consumer", "name"], `${title} ${index + 1}`);
            return (
              <div key={`${title}-${label}-${index}`} className="rounded-md border border-poly-line bg-poly-bg/40 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-semibold text-poly-text">
                    <Icon aria-hidden="true" size={16} className={icon === "incident" ? "text-poly-error" : "text-poly-cyan"} />
                    {label}
                  </div>
                  <span className="text-xs text-poly-muted">{fieldText(row, ["last_seen_at", "finished_at", "stored_at", "occurred_at", "updated_at"])}</span>
                </div>
                <p className="mt-2 text-xs text-poly-muted">ID: {fieldText(row, ["id", "event_id", "attempt_id"])}</p>
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyReadOnlyState message={`No ${title.toLowerCase()} rows were returned by the logs endpoint.`} />
      )}
    </Panel>
  );
}

export function LogsErrorsVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const incidents = asArray(data.runtime_incidents);
  const attempts = asArray(data.event_delivery_attempts);
  const events = asArray(data.events);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Logs Truth" value={envelope.status} detail="Envelope status from incident, DLQ, and event sources." />
        <MetricTile label="Incidents" value={incidents.length} detail="runtime_incidents rows." />
        <MetricTile label="Delivery Attempts" value={attempts.length} detail="event_delivery_attempts rows." />
        <MetricTile label="Events" value={events.length} detail="event_log rows." />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <LogSection title="Runtime Incidents" rows={incidents} icon="incident" />
        <LogSection title="Event Delivery Attempts" rows={attempts} icon="attempt" />
        <LogSection title="Recent Events" rows={events} icon="event" />
      </div>

      <WarningErrorPanel envelope={envelope} />
    </div>
  );
}

export function GenericSafePreview({ summary, envelope }: { summary: string; envelope: TruthEnvelope }) {
  return (
    <Panel title="Safe Data Preview" eyebrow={envelope.status}>
      <p className="text-sm leading-6 text-poly-muted">{summary}</p>
      <pre className="mt-3 max-h-80 overflow-auto rounded-md border border-poly-line bg-poly-bg/60 p-3 text-xs text-poly-muted">
        {JSON.stringify(envelope.data, null, 2)}
      </pre>
    </Panel>
  );
}
