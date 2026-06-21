import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { ControlCenterActionEnvelope } from "../api/controlCenterActions";
import type { TruthEnvelope } from "../lib/truth-contract";

function envelope(overrides: Partial<TruthEnvelope> = {}): TruthEnvelope {
  return {
    status: "PARTIAL",
    source: "stage17_certification_source",
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

function actionEnvelope(action: string): ControlCenterActionEnvelope {
  return {
    action,
    status: "ACCEPTED",
    actor: "operator",
    reason: "stage 17 certification",
    timestamp: "2026-06-08T00:00:01+00:00",
    audit_id: action === "start-full-monitor-run" ? "control_center_full_monitor_run:stage17" : "audit:stage17",
    state_before: {},
    state_after: {},
    safety_checks: [{ name: "no_live_execution", status: "PASS", detail: "No live execution is exposed." }],
    result:
      action === "start-full-monitor-run"
        ? {
            run_id: "full_monitor_run_stage17",
            status: "COMPLETED",
            cycles_completed: 1,
            markets_checked: 0,
            opportunities_found: 0,
            no_trades_logged: 0,
            paper_orders: 0,
            paper_fills: 0,
            positions_updated: 0,
            audit_id: "control_center_full_monitor_run:stage17",
            requested_duration_minutes: 5,
            elapsed_seconds: 0,
            module_results: [
              { module: "paper_execution", status: "SKIPPED", behavior: "Paper execution is skipped." },
              { module: "live_execution", status: "SKIPPED", behavior: "Live execution is forbidden." }
            ]
          }
        : {},
    warnings: [],
    errors: []
  };
}

function responseForUrl(url: string, init?: RequestInit) {
  if (init?.method === "POST" && url.includes("/dashboard/api/v2/control/actions/")) {
    const parts = url.split("/");
    return actionEnvelope(parts[parts.length - 1] ?? "unknown");
  }

  if (url.includes("/overview")) {
    return envelope({
      status: "STALE",
      source: "control_overview",
      truth_state: "REFRESH_REQUIRED",
      warnings: ["overview heartbeat stale"],
      data: {
        source_counts: { service_health: 1 },
        latest_rows: { service_health: { last_heartbeat_at: "2026-06-08T00:00:00+00:00" } },
        read_only: true,
        mutating_actions_exposed: []
      }
    });
  }

  if (url.includes("/pnl-ledger")) {
    return envelope({
      status: "MISSING",
      source: null,
      truth_state: "UNKNOWN",
      data: {
        pnl_ledger: {
          realized_pnl: 999999,
          ledger_rows: [{ ledger_id: "invented-ledger-row" }]
        }
      },
      warnings: ["ledger source missing"]
    });
  }

  if (url.includes("/decision-xray") || url.includes("/risk-evidence")) {
    return envelope({
      status: "PARTIAL",
      source: "risk_evidence_mesh",
      data: {
        approval_claimed: false,
        risk_evidence: {
          blocker_subtypes: { MISSING_EXIT_PLAN: 1 },
          latest_evaluations: [
            {
              evaluation_id: "risk-1",
              risk_decision: "NO_TRADE",
              risk_blocker_subtype: "MISSING_EXIT_PLAN",
              truth_state: "REFRESH_REQUIRED"
            }
          ]
        }
      }
    });
  }

  if (url.includes("/truth-state")) {
    return envelope({
      status: "REAL",
      source: "truth_state_registry",
      truth_state: "ACTIVE_FRESH",
      data: {
        truth_state_counts: {
          ACTIVE_FRESH: 2,
          UNKNOWN: 1,
          REFRESH_REQUIRED: 1,
          LAST_KNOWN: 1,
          HISTORICAL_ONLY: 1
        }
      }
    });
  }

  if (url.includes("/full-monitor-run")) {
    return envelope({
      status: "MISSING",
      source: "control_center:full_monitor_run",
      truth_state: "UNKNOWN",
      data: { run_type: "FULL_MONITOR_RUN", current: null, latest: null, available: true }
    });
  }

  return envelope();
}

describe("Stage 17 Control Center safety certification", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => Promise.resolve(jsonResponse(responseForUrl(String(input), init))))
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows stale/missing truth explicitly and does not convert it to fake green", async () => {
    render(<App />);

    const overview = await screen.findByTestId("page-overview");
    await waitFor(() => expect(within(overview).getAllByText("STALE").length).toBeGreaterThan(0));
    expect(within(overview).getAllByText("overview heartbeat stale").length).toBeGreaterThan(0);
    expect(within(overview).queryByText(/^GREEN$/i)).not.toBeInTheDocument();
  });

  it("withholds PnL facts when the ledger source is missing", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Money/i }));

    const page = await screen.findByTestId("page-pnl-ledger");
    expect(await within(page).findByText("PnL source missing or non-ledger; money values are withheld.")).toBeInTheDocument();
    expect(within(page).queryByText("999999")).not.toBeInTheDocument();
    expect(within(page).queryByText("invented-ledger-row")).not.toBeInTheDocument();
  });

  it("keeps decision pages blocker-first and never invents approval", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Decision" }));

    const page = await screen.findByTestId("page-decision-xray");
    await waitFor(() => expect(within(page).getAllByText("MISSING_EXIT_PLAN").length).toBeGreaterThan(0));
    expect(within(page).queryByText(/^APPROVED$/i)).not.toBeInTheDocument();
  });

  it("renders truth-state vocabulary from backend data", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Truth State" }));

    const page = await screen.findByTestId("page-truth-state");
    for (const state of ["ACTIVE_FRESH", "LAST_KNOWN", "HISTORICAL_ONLY", "REFRESH_REQUIRED", "UNKNOWN"]) {
      expect((await within(page).findAllByText(state)).length).toBeGreaterThan(0);
    }
  });

  it("exposes only Control Center wrapper actions and no manual trade controls", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));

    const page = await screen.findByTestId("page-settings");
    expect(within(page).getAllByText(/\/dashboard\/api\/v2\/control\/actions\//).length).toBeGreaterThan(0);
    expect(within(page).queryByRole("button", { name: /manual trade|approve trade|override blocker|disable risk|disable governance|engine budget/i })).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "LOCKED" })).toBeDisabled();
  });

  it("posts start full monitor run through the audited wrapper only", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    await user.type(screen.getByPlaceholderText("operator id"), "operator");
    await user.type(screen.getByPlaceholderText("required audit reason"), "stage 17 certification");
    await user.clear(screen.getByLabelText(/Duration minutes/i));
    await user.type(screen.getByLabelText(/Duration minutes/i), "5");
    await user.clear(screen.getByLabelText(/Interval seconds/i));
    await user.type(screen.getByLabelText(/Interval seconds/i), "10");
    await user.click(screen.getByRole("button", { name: /Request START MONITORING RUN/i }));

    await screen.findByText("full_monitor_run_stage17");
    const postCalls = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
    expect(postCalls).toHaveLength(1);
    expect(String(postCalls[0][0])).toBe("/dashboard/api/v2/control/actions/start-full-monitor-run");
    expect(JSON.parse(String(postCalls[0][1]?.body))).toMatchObject({
      actor: "operator",
      reason: "stage 17 certification",
      duration_minutes: 5,
      interval_seconds: 10
    });
  });
});
