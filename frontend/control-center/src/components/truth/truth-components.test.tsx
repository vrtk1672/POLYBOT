import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ErrorState } from "../states/ErrorState";
import { MissingState } from "../states/MissingState";
import { NotImplementedState } from "../states/NotImplementedState";
import { DecisionStep } from "./DecisionStep";
import { FreshnessBadge } from "./FreshnessBadge";
import { PnLCard } from "./PnLCard";
import { PositionCard } from "./PositionCard";
import { StatusCard } from "./StatusCard";
import { TruthBadge } from "./TruthBadge";
import type { DecisionStepData, PnLData, PositionData, TruthEnvelope, TruthState, TruthStatus } from "../../lib/truth-contract";

const statuses: TruthStatus[] = ["REAL", "STALE", "MISSING", "ERROR", "LOCKED", "NOT_IMPLEMENTED", "PARTIAL"];
const truthStates: TruthState[] = ["ACTIVE_FRESH", "LAST_KNOWN", "HISTORICAL_ONLY", "REFRESH_REQUIRED", "UNKNOWN"];

function envelope<TData extends Record<string, unknown> = Record<string, unknown>>(
  overrides: Partial<TruthEnvelope<TData>> = {}
): TruthEnvelope<TData> {
  return {
    status: "PARTIAL",
    source: "demo_source",
    last_updated: "2026-06-07T00:00:00+00:00",
    stale_after_seconds: 300,
    truth_state: "REFRESH_REQUIRED",
    data: {} as TData,
    warnings: [],
    errors: [],
    ...overrides
  };
}

describe("truth components", () => {
  it("TruthBadge renders all status values", () => {
    render(
      <div>
        {statuses.map((status) => (
          <TruthBadge key={status} status={status} />
        ))}
      </div>
    );
    for (const status of statuses) {
      expect(screen.getByText(status)).toBeInTheDocument();
    }
  });

  it("FreshnessBadge renders all truth_state values", () => {
    render(
      <div>
        {truthStates.map((truthState) => (
          <FreshnessBadge key={truthState} truthState={truthState} />
        ))}
      </div>
    );
    for (const truthState of truthStates) {
      expect(screen.getByText(truthState)).toBeInTheDocument();
    }
  });

  it("StatusCard exposes source and last_updated", () => {
    render(<StatusCard title="Runtime" envelope={envelope({ status: "REAL", truth_state: "ACTIVE_FRESH" })} />);
    expect(screen.getByText("demo_source")).toBeInTheDocument();
    expect(screen.getByText(/2026-06-07T00:00:00/)).toBeInTheDocument();
  });

  it("ErrorState renders errors", () => {
    render(<ErrorState errors={["source failed"]} />);
    expect(screen.getByText("source failed")).toBeInTheDocument();
  });

  it("MissingState renders missing context", () => {
    render(<MissingState source={null} warnings={["ledger missing"]} />);
    expect(screen.getByText(/SOURCE_MISSING/)).toBeInTheDocument();
    expect(screen.getByText("ledger missing")).toBeInTheDocument();
  });

  it("NotImplementedState does not imply live data", () => {
    render(<NotImplementedState warnings={["not connected"]} />);
    expect(screen.getByText("NOT_IMPLEMENTED")).toBeInTheDocument();
    expect(screen.getByText(/not connected to runtime data/i)).toBeInTheDocument();
    expect(screen.queryByText(/live data is displayed/i)).not.toBeInTheDocument();
  });

  it("PnLCard does not render fake PnL if source is missing", () => {
    const pnl = envelope<PnLData>({
      status: "MISSING",
      source: null,
      truth_state: "UNKNOWN",
      data: { realized_pnl: 100, fake_pnl: false },
      warnings: ["ledger missing"]
    });
    render(<PnLCard envelope={pnl} />);
    expect(screen.getByText(/PnL hidden until ledger or capital source is present/i)).toBeInTheDocument();
    expect(screen.queryByText("100")).not.toBeInTheDocument();
  });

  it("PositionCard does not render fake position truth if source is missing", () => {
    const position = envelope<PositionData>({
      status: "MISSING",
      source: null,
      truth_state: "UNKNOWN",
      data: { position_id: "paper_position_1", fake_positions: false },
      warnings: ["position source missing"]
    });
    render(<PositionCard envelope={position} />);
    expect(screen.getByText(/Position truth hidden until canonical position source is present/i)).toBeInTheDocument();
    expect(screen.queryByText(/paper_position_1/)).not.toBeInTheDocument();
  });

  it("DecisionStep does not render approved signal if evidence/source is missing", () => {
    const decision = envelope<DecisionStepData>({
      status: "MISSING",
      source: null,
      truth_state: "UNKNOWN",
      data: { label: "risk", approved: true, evidence_source: null },
      warnings: ["evidence missing"]
    });
    render(<DecisionStep label="Risk gate" envelope={decision} />);
    expect(screen.getByText(/No approval claim without evidence\/source/i)).toBeInTheDocument();
    expect(screen.queryByText(/Evidence-backed approval signal/i)).not.toBeInTheDocument();
  });
});
