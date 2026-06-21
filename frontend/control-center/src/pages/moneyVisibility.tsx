import type { TruthEnvelope } from "../lib/truth-contract";
import { MetricTile } from "../layout/MetricTile";
import { Panel } from "../layout/Panel";
import { asArray, asRecord, entriesOf, fieldNumber, fieldText, latestTimestamp, type UnknownRecord } from "./visibilityUtils";

function ReadOnlyEmpty({ message }: { message: string }) {
  return <div className="rounded-md border border-poly-missing/50 bg-poly-missing/10 p-3 text-sm text-poly-muted">{message}</div>;
}

function operatorWarningText(text: string) {
  return text.replace(/fake pnl/gi, "invented PnL");
}

function WarningsErrors({ envelope }: { envelope: TruthEnvelope }) {
  const messages = [
    ...envelope.warnings.map((text) => ({ kind: "warning", text: operatorWarningText(text) })),
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

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "UNKNOWN";
  if (Array.isArray(value)) return value.length ? value.map(String).join(", ") : "[]";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
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
              <p className="mt-1 break-words text-poly-text">{formatValue(value)}</p>
            </div>
          ))}
        </div>
      ) : (
        <ReadOnlyEmpty message="No scalar facts were present in this source-backed envelope section." />
      )}
    </Panel>
  );
}

function ObjectListPanel({
  title,
  rows,
  empty,
  labelKeys,
  detailKeys,
  limit = 20
}: {
  title: string;
  rows: UnknownRecord[];
  empty: string;
  labelKeys: string[];
  detailKeys: string[];
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
                  <p className="break-words text-sm font-semibold text-poly-text">{label}</p>
                  <span className="text-xs text-poly-muted">{latestTimestamp(row, ["created_at", "updated_at", "opened_at", "closed_at", "stored_at", "timestamp"])}</span>
                </div>
                <div className="mt-2 grid gap-2 text-xs text-poly-muted md:grid-cols-2">
                  {detailKeys.map((key) => (
                    <p key={key} className="break-words">
                      {key}: {formatValue(row[key])}
                    </p>
                  ))}
                </div>
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

function nestedData(envelope: TruthEnvelope, key: string) {
  return asRecord(asRecord(envelope.data)[key]);
}

function sourceIncludes(envelope: TruthEnvelope, terms: string[]) {
  const source = String(envelope.source ?? "").toLowerCase();
  return terms.some((term) => source.includes(term));
}

function firstArray(record: UnknownRecord, keys: string[]) {
  for (const key of keys) {
    const rows = asArray(record[key]);
    if (rows.length) return rows;
  }
  return [];
}

function firstSection(data: UnknownRecord, keys: string[]) {
  for (const key of keys) {
    const section = asRecord(data[key]);
    if (Object.keys(section).length) return section;
  }
  return {};
}

export function PnlLedgerVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const ledger = nestedData(envelope, "pnl_ledger");
  const sourceBacked = sourceIncludes(envelope, ["paper_pnl_ledger", "paper_daily_pnl", "paper_trade_ledger", "paper_capital_ledger"]);
  const rows = firstArray(ledger, ["ledger_rows", "pnl_rows", "daily_pnl", "events", "entries", "rows"]);

  if (!sourceBacked) {
    return (
      <div className="space-y-4">
        <ReadOnlyEmpty message="PnL source missing or non-ledger; money values are withheld." />
        <WarningsErrors envelope={envelope} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Ledger Truth" value={envelope.status} detail="Truth Contract status from the ledger endpoint." />
        <MetricTile label="Ledger Rows" value={fieldNumber(ledger, ["count", "row_count", "ledger_count"]) ?? rows.length} detail="Rows returned by the ledger source." />
        <MetricTile label="Realized PnL" value={fieldText(ledger, ["realized_pnl", "realized", "paper_realized_pnl"])} detail="Displayed only from the ledger-backed payload." />
        <MetricTile label="Unrealized PnL" value={fieldText(ledger, ["unrealized_pnl", "unrealized", "paper_unrealized_pnl"])} detail="Displayed only from the ledger-backed payload." />
      </div>
      <FactGrid
        title="Ledger Reconciliation"
        eyebrow="Read-only paper truth"
        facts={[
          ["source", envelope.source ?? "SOURCE_MISSING"],
          ["last_updated", envelope.last_updated ?? "UNKNOWN"],
          ["status", fieldText(ledger, ["status", "ledger_status"])],
          ["reconciliation_status", fieldText(ledger, ["reconciliation_status", "capital_reconciliation_status"])],
          ["current_balance", fieldText(ledger, ["current_balance", "balance", "paper_balance"])],
          ["available_capital", fieldText(ledger, ["available_capital", "available_balance", "deployable_capital"])],
          ["locked_capital", fieldText(ledger, ["locked_capital", "locked_balance", "reserved_capital"])],
          ["total_pnl", fieldText(ledger, ["total_pnl", "net_pnl", "paper_pnl"])]
        ]}
      />
      <ObjectListPanel
        title="Ledger Rows"
        rows={rows}
        empty="No ledger rows were returned by the canonical ledger source."
        labelKeys={["ledger_id", "id", "event_type", "date"]}
        detailKeys={["event_type", "amount", "realized_pnl", "unrealized_pnl", "market_id", "paper_position_id"]}
      />
      <WarningsErrors envelope={envelope} />
    </div>
  );
}

export function CapitalVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const data = asRecord(envelope.data);
  const capital = firstSection(data, ["capital", "capital_reconciliation", "capital_summary", "paper_capital", "paper_capital_ledger"]);
  const hasCapital = Object.keys(capital).length > 0;

  if (!hasCapital) {
    return (
      <div className="space-y-4">
        <ReadOnlyEmpty message="Capital reconciliation source missing or partial; overview does not expose a dedicated capital section." />
        <FactGrid
          title="Overview Source"
          eyebrow="Capital page limitation"
          facts={[
            ["source", envelope.source ?? "SOURCE_MISSING"],
            ["status", envelope.status],
            ["truth_state", envelope.truth_state],
            ["last_updated", envelope.last_updated ?? "UNKNOWN"]
          ]}
        />
        <WarningsErrors envelope={envelope} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Capital Truth" value={envelope.status} detail="Capital is rendered from overview because no dedicated endpoint exists." />
        <MetricTile label="Available" value={fieldText(capital, ["available_capital", "available_balance", "deployable_capital"])} detail="Backend-provided deployable amount only." />
        <MetricTile label="Locked" value={fieldText(capital, ["locked_capital", "locked_balance", "reserved_capital"])} detail="Backend-provided reserved amount only." />
        <MetricTile label="Exposure" value={fieldText(capital, ["open_exposure", "total_exposure", "exposure"])} detail="Open exposure if supplied by overview." />
      </div>
      <FactGrid
        title="Capital Reconciliation"
        eyebrow="Overview-backed"
        facts={[
          ["source", envelope.source ?? "SOURCE_MISSING"],
          ["last_updated", envelope.last_updated ?? "UNKNOWN"],
          ["reconciliation_status", fieldText(capital, ["reconciliation_status", "status"])],
          ["current_balance", fieldText(capital, ["current_balance", "balance", "paper_balance"])],
          ["available_capital", fieldText(capital, ["available_capital", "available_balance", "deployable_capital"])],
          ["locked_capital", fieldText(capital, ["locked_capital", "locked_balance", "reserved_capital"])],
          ["open_exposure", fieldText(capital, ["open_exposure", "total_exposure", "exposure"])],
          ["limits", capital.limits ?? capital.constraints]
        ]}
      />
      <WarningsErrors envelope={envelope} />
    </div>
  );
}

export function PositionsVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const positionsPayload = nestedData(envelope, "positions");
  const sourceBacked = sourceIncludes(envelope, ["paper_positions"]);
  const rows = sourceBacked ? firstArray(positionsPayload, ["positions", "paper_positions", "open_positions", "rows"]) : [];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="Position Truth" value={envelope.status} detail="Truth Contract status from the positions endpoint." />
        <MetricTile label="Canonical Rows" value={rows.length} detail="Only paper_positions rows are counted here." />
        <MetricTile label="Open Positions" value={fieldNumber(positionsPayload, ["open_positions", "open_count", "count"]) ?? rows.length} detail="Backend count from canonical position truth." />
        <MetricTile label="Source" value={envelope.source ?? "SOURCE_MISSING"} detail="Orders and fills are not used as position rows." />
      </div>
      {!sourceBacked ? <ReadOnlyEmpty message="Position source missing or non-canonical; position rows are withheld." /> : null}
      <ObjectListPanel
        title="Canonical Positions"
        rows={rows}
        empty="No canonical position rows were returned; orders and fills are not displayed as positions."
        labelKeys={["position_id", "paper_position_id", "id", "market_id"]}
        detailKeys={["market_id", "side", "intended_outcome", "size", "quantity", "entry_price", "avg_entry", "current_price", "mark_price", "unrealized_pnl", "unrealized", "current_status", "status"]}
      />
      <FactGrid title="Position Source Summary" eyebrow="Canonical source only" facts={entriesOf(positionsPayload).slice(0, 12)} />
      <WarningsErrors envelope={envelope} />
    </div>
  );
}

export function NoTradeVisibility({ envelope }: { envelope: TruthEnvelope }) {
  const noTrade = nestedData(envelope, "no_trade");
  const sourceBacked = sourceIncludes(envelope, ["no_trade_log", "no_trade"]);
  const latest = sourceBacked ? firstArray(noTrade, ["latest_no_trade", "no_trade_records", "recent_no_trade", "items", "rows"]) : [];
  const reasons = sourceBacked ? firstArray(noTrade, ["top_no_trade_reasons", "reasons", "reason_counts"]) : [];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <MetricTile label="No-Trade Truth" value={envelope.status} detail="Truth Contract status from the no-trade endpoint." />
        <MetricTile label="First-Class Decision" value={fieldText(asRecord(envelope.data), ["first_class_decision"], "UNKNOWN")} detail="Preserved from the backend envelope." />
        <MetricTile label="Records" value={fieldNumber(noTrade, ["total_no_trade_records", "count", "record_count"]) ?? latest.length} detail="No-trade ledger records returned." />
        <MetricTile label="Source" value={envelope.source ?? "SOURCE_MISSING"} detail="No frontend reason synthesis." />
      </div>
      {!sourceBacked ? <ReadOnlyEmpty message="No-trade source missing; reasons are withheld instead of invented." /> : null}
      <ObjectListPanel
        title="Latest No-Trade Records"
        rows={latest}
        empty="No no-trade records were returned. The UI will not invent no-trade reasons."
        labelKeys={["no_trade_id", "candidate_id", "market_id", "subject_id", "primary_reason", "no_trade_reason"]}
        detailKeys={["candidate_id", "market_id", "side", "decision_status", "primary_reason", "no_trade_reason", "no_trade_category", "blocked_by", "missing_data", "risk_flags", "truth_state"]}
      />
      <ObjectListPanel
        title="Top No-Trade Reasons"
        rows={reasons}
        empty="No top no-trade reasons were supplied by the backend."
        labelKeys={["reason", "primary_reason", "no_trade_reason", "category"]}
        detailKeys={["count", "severity", "no_trade_category", "truth_state"]}
      />
      <FactGrid
        title="No-Trade Summary"
        eyebrow="First-class no-trade"
        facts={[
          ["source", envelope.source ?? "SOURCE_MISSING"],
          ["last_updated", envelope.last_updated ?? "UNKNOWN"],
          ["status", fieldText(noTrade, ["status", "no_trade_status"])],
          ["total_no_trade_records", fieldText(noTrade, ["total_no_trade_records", "record_count", "count"])],
          ["unaccounted_candidates", fieldText(noTrade, ["unaccounted_candidates"])],
          ["missing_requirements", noTrade.missing_requirements_summary]
        ]}
      />
      <WarningsErrors envelope={envelope} />
    </div>
  );
}
