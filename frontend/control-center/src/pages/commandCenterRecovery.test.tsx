import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { TruthEnvelope } from "../lib/truth-contract";

function envelope(overrides: Partial<TruthEnvelope> = {}): TruthEnvelope {
  return {
    status: "PARTIAL",
    source: "stage19_recovery_source",
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

type MockCockpitState = { systemOn: boolean; runStarted: boolean; emptyRun: boolean };

function responseForUrl(url: string, init?: RequestInit, state: MockCockpitState = { systemOn: false, runStarted: false, emptyRun: false }) {
  if (url.includes("/overview")) {
    return envelope({
      status: "REAL",
      source: "control_overview",
      truth_state: "ACTIVE_FRESH",
      data: {
        current_mode: state.systemOn ? "DATA_ONLY" : "PAPER",
        system_power: state.systemOn ? "ON" : "OFF",
        source_counts: { system_state: 1, service_health: 2, paper_pnl_ledger: 1 }
      }
    });
  }
  if (url.includes("/dashboard/api/v2/control/actions/system-on")) {
    state.systemOn = true;
    return {
      action: "system-on",
      status: "ACCEPTED",
      actor: "harel",
      reason: "stage 24 unlock test",
      timestamp: "2026-06-08T00:00:01+00:00",
      audit_id: "transition-on",
      state_before: { state: { current_mode: "PAPER", system_power: "OFF" } },
      state_after: { state: { current_mode: "DATA_ONLY", system_power: "ON" }, permissions: { can_collect_data: true, can_create_live_orders: false } },
      safety_checks: [{ name: "safe_monitoring_mode", status: "PASS", detail: "SYSTEM ON ensures DATA_ONLY monitoring mode before allowing runtime work." }],
      result: { system_power: "ON", current_mode: "DATA_ONLY", safe_monitoring_mode: { from_mode: "PAPER", to_mode: "DATA_ONLY", changed: true } },
      warnings: ["System power actions do not enable live trading and do not create execution artifacts."],
      errors: []
    };
  }
  if (url.includes("/dashboard/api/v2/control/actions/start-full-monitor-run")) {
    if (state.systemOn) {
      state.runStarted = true;
      return {
        action: "start-full-monitor-run",
        status: "ACCEPTED",
        actor: "harel",
          reason: "stage 25 monitoring test",
        timestamp: "2026-06-08T00:00:02+00:00",
        audit_id: "control_center_full_monitor_run:stage24",
        state_before: {},
        state_after: {},
        safety_checks: [{ name: "state_governor_checked", status: "PASS", detail: "Full Monitor Run service checked State Governor before start." }],
        result: {
          run_id: "full_monitor_run_stage24",
          status: "COMPLETED",
          elapsed_seconds: 60,
          remaining_seconds: 0,
          interval_seconds: 10,
          cycles_completed: 1,
          opportunities_found: 20,
          no_trades_logged: 0,
          paper_orders: 0,
          paper_fills: 0,
          positions_updated: 0,
          execution_enabled: false,
          report_path: "run_reports/control_center_monitor_runs/full_monitor_run_stage24.md"
        },
        warnings: ["Stage 16 monitor run is synchronous, bounded, and read-only/evaluation-only."],
        errors: []
      };
    }
    return {
      action: "start-full-monitor-run",
      status: "LOCKED",
      actor: "harel",
      reason: "browser audit test",
      timestamp: "2026-06-08T00:00:01+00:00",
      audit_id: "audit-locked-run",
      state_before: {},
      state_after: {},
      safety_checks: [{ name: "state_governor_mode", status: "LOCKED", detail: "State Governor does not allow monitoring/data collection in the current mode." }],
      result: {},
      warnings: ["State Governor does not allow monitoring/data collection in the current mode."],
      errors: []
    };
  }
  if (url.includes("/organs")) {
    return envelope({ status: "REAL", source: "service_health", data: { services: [{ service_name: "runtime" }] } });
  }
  if (url.includes("/live-flow")) {
    return envelope({
      status: "REAL",
      source: "event_log",
      data: { events: [{ id: "event-1", event_type: "MARKET_SCAN", summary: "Read-only source event.", created_at: "2026-06-08T00:00:00+00:00" }] }
    });
  }
  if (url.includes("/full-monitor-run")) {
    if (state.runStarted) {
      return envelope({
        status: "REAL",
        source: "control_center:full_monitor_run",
        truth_state: "LAST_KNOWN",
        data: {
          latest: {
            run_id: "full_monitor_run_stage24",
            status: "COMPLETED",
            elapsed_seconds: 60,
            remaining_seconds: 0,
            interval_seconds: 10,
            cycles_completed: 1,
            opportunities_found: 20,
            no_trades_logged: 0,
            paper_orders: 0,
            paper_fills: 0,
            positions_updated: 0,
            audit_id: "control_center_full_monitor_run:stage24",
            execution_enabled: false,
            report_path: "run_reports/control_center_monitor_runs/full_monitor_run_stage24.md",
            module_results: [
              { module: "market_scan", status: "COMPLETED", behavior: "Read-only overview source." },
              { module: "live_execution", status: "SKIPPED", behavior: "Live execution is forbidden." }
            ]
          }
        }
      });
    }
    if (state.emptyRun) {
      return envelope({
        status: "MISSING",
        source: "control_center:full_monitor_run",
        truth_state: "UNKNOWN",
        data: { current: null, latest: null, available: true },
        warnings: ["No Full Monitor Run has been started in this process."]
      });
    }
    return envelope({
      status: "REAL",
      source: "control_center:full_monitor_run",
      truth_state: "LAST_KNOWN",
      data: {
        latest: {
          run_id: "full_monitor_run_recovery",
          status: "COMPLETED",
          cycles_completed: 1,
          paper_orders: 0,
          paper_fills: 0,
          audit_id: "control_center_full_monitor_run:recovery",
          module_results: [
            { module: "market_scan", status: "COMPLETED", behavior: "Read-only overview source." },
            { module: "orderbook", status: "SKIPPED", behavior: "No safe read-only orderbook monitor endpoint exists." },
            { module: "live_execution", status: "SKIPPED", behavior: "Live execution is forbidden." }
          ]
        }
      }
    });
  }
  if (url.includes("/blockers")) {
    return envelope({
      status: "PARTIAL",
      source: "no_trade_log:risk_evidence_mesh",
      data: {
        blockers: {
          no_trade: {
            top_no_trade_reasons: [{ reason: "MISSING_EXIT_PLAN", count: 1 }]
          }
        }
      }
    });
  }
  if (url.includes("/risk-evidence")) {
    return envelope({
      status: "PARTIAL",
      source: "risk_evidence_mesh",
      data: { risk_evidence: { blocker_subtypes: { STALE_ORDERBOOK: 1 } } }
    });
  }
  if (url.includes("/pnl-ledger")) {
    return envelope({
      status: "REAL",
      source: "paper_pnl_ledger",
      truth_state: "ACTIVE_FRESH",
      data: { pnl_ledger: { realized_pnl: 12.5, unrealized_pnl: -1.25, ledger_rows: [{ ledger_id: "ledger-1" }] } }
    });
  }
  if (url.includes("/logs")) {
    return envelope({
      status: "REAL",
      source: "runtime_incidents:event_log",
      data: { runtime_incidents: [{ id: "incident-1" }], events: [{ id: "event-1" }] }
    });
  }
  if (url.includes("/mesh-dialogues")) {
    return envelope({
      status: "REAL",
      source: "brain_dialogue_events",
      truth_state: "ACTIVE_FRESH",
      data: {
        mesh_dialogues: {
          events: [
            {
              event_type: "brain_dialogue.mesh_coordinator.decision",
              source: "Coordinator",
              message: "Protective caution wins by forcing WATCH.",
              created_at: "2026-06-08T00:00:00+00:00"
            }
          ],
          count: 1
        },
        dialogue_invented: false
      }
    });
  }
  if (url.includes("/closest-actionable")) {
    return envelope({
      status: "PARTIAL",
      source: "closest_actionable",
      data: { candidates: [{ candidate_id: "candidate-1", truth_state: "REFRESH_REQUIRED" }] }
    });
  }
  if (url.includes("/positions")) {
    return envelope({
      status: "REAL",
      source: "paper_positions",
      data: { positions: { positions: [{ position_id: "position-1" }] } }
    });
  }
  return envelope();
}

describe("Stage 21 Operator Cockpit home", () => {
  let state: MockCockpitState;

  beforeEach(() => {
    state = { systemOn: false, runStarted: false, emptyRun: false };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => Promise.resolve(jsonResponse(responseForUrl(String(input), init, state)))));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("answers the operator's first-screen questions with Stage 23 cockpit guidance", async () => {
    render(<App />);

    const page = await screen.findByTestId("page-overview");
    await waitFor(() => expect(within(page).getByRole("heading", { name: "Command Cockpit", level: 1 })).toBeInTheDocument());

    expect(within(page).getByText("POLYBOT Operator Cockpit")).toBeInTheDocument();
    expect(within(page).getByText("Primary Action Strip")).toBeInTheDocument();
    expect(within(page).getByText("POLYBOT Status")).toBeInTheDocument();
    expect(within(page).getByText("Health verdict")).toBeInTheDocument();
    expect(within(page).getByText("Backend")).toBeInTheDocument();
    expect(within(page).getByText("Database")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /SYSTEM ON/i })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /SYSTEM OFF/i })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /START MONITORING RUN/i })).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: /STOP CURRENT RUN/i })).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /KILL SWITCH/i })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /REFRESH/i })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /EXPORT REPORT/i })).toBeInTheDocument();
    expect(within(page).getByText("Current Run / Action Guidance")).toBeInTheDocument();
    expect(within(page).getAllByText("full_monitor_run_recovery").length).toBeGreaterThan(0);
    expect(within(page).getByText("Full Monitor Run Completed.")).toBeInTheDocument();
    expect(within(page).getByText("Cycles")).toBeInTheDocument();
    expect(within(page).getByText("Live System Feed")).toBeInTheDocument();
    expect(within(page).getByText("Technical event: MARKET SCAN")).toBeInTheDocument();
    expect(within(page).getByText("Brain Dialogue Preview")).toBeInTheDocument();
    expect(within(page).getByText("Protective caution wins by forcing WATCH.")).toBeInTheDocument();
    expect(within(page).getByText("Decision / Blockers")).toBeInTheDocument();
    expect(within(page).getByText("MISSING_EXIT_PLAN")).toBeInTheDocument();
    expect(within(page).getByText("Closest to Actionable")).toBeInTheDocument();
    expect(within(page).getAllByText("Money Verdict").length).toBeGreaterThan(0);
    expect(within(page).getByText("Ledger data and positions available")).toBeInTheDocument();
    expect(within(page).getAllByText("12.5").length).toBeGreaterThan(0);
    expect(within(page).getByText("Attention / Problems")).toBeInTheDocument();
    expect(within(page).getByText("Advanced Diagnostics")).toBeInTheDocument();
    expect(within(page).queryByText(/^GREEN$/i)).not.toBeInTheDocument();
    expect(within(page).queryByText(/fake pnl/i)).not.toBeInTheDocument();
    expect(within(page).queryByText(/fake dialogue/i)).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: /manual trade|approve trade|override blocker|disable risk|disable governance|engine budget/i })).not.toBeInTheDocument();
  });

  it("renders a guided locked state when Full Monitor Run is blocked", async () => {
    const user = userEvent.setup();
    render(<App />);

    const page = await screen.findByTestId("page-overview");
    await user.type(within(page).getByLabelText("Actor"), "harel");
    await user.type(within(page).getByLabelText("Reason"), "browser audit test");
    await user.clear(within(page).getByLabelText("Duration minutes"));
    await user.type(within(page).getByLabelText("Duration minutes"), "1");
    await user.clear(within(page).getByLabelText("Interval seconds"));
    await user.type(within(page).getByLabelText("Interval seconds"), "10");
    await user.click(within(page).getByRole("button", { name: /START MONITORING RUN/i }));

    expect(await within(page).findByText("Full Monitor Run is locked by system mode.")).toBeInTheDocument();
    expect(within(page).getByText(/Step 1: SYSTEM ON\. Step 2: START MONITORING RUN/i)).toBeInTheDocument();
    expect(within(page).getAllByText(/State Governor does not allow monitoring\/data collection/i).length).toBeGreaterThan(0);
    expect(within(page).getByRole("button", { name: /START MONITORING RUN/i })).toBeInTheDocument();
    expect(within(page).queryByText(/^RUNNING$/i)).not.toBeInTheDocument();
  });

  it("shows SYSTEM ON as step 1 and then allows a completed Full Monitor Run when backend reports ready", async () => {
    const user = userEvent.setup();
    state.emptyRun = true;
    render(<App />);

    const page = await screen.findByTestId("page-overview");
    await waitFor(() => expect(within(page).getByText("PAPER")).toBeInTheDocument());
    expect(within(page).getByText(/Step 1: SYSTEM ON if power is OFF\. Step 2: START MONITORING RUN/i)).toBeInTheDocument();

    await user.type(within(page).getByLabelText("Actor"), "harel");
    await user.type(within(page).getByLabelText("Reason"), "stage 24 unlock test");
    await user.click(within(page).getByRole("button", { name: /SYSTEM ON/i }));

    expect(await within(page).findByText("Safe monitoring mode is on.")).toBeInTheDocument();
    expect(within(page).getByText(/Current mode after SYSTEM ON: DATA_ONLY/i)).toBeInTheDocument();
    expect(within(page).getByText(/Step 2: START MONITORING RUN/i)).toBeInTheDocument();

    await user.clear(within(page).getByLabelText("Reason"));
    await user.type(within(page).getByLabelText("Reason"), "stage 24 full monitor test");
    await user.clear(within(page).getByLabelText("Duration minutes"));
    await user.type(within(page).getByLabelText("Duration minutes"), "1");
    await user.clear(within(page).getByLabelText("Interval seconds"));
    await user.type(within(page).getByLabelText("Interval seconds"), "10");
    await user.click(within(page).getByRole("button", { name: /START MONITORING RUN/i }));

    expect(await within(page).findByText("Full Monitor Run Completed.")).toBeInTheDocument();
    expect(within(page).getAllByText("full_monitor_run_stage24").length).toBeGreaterThan(0);
    expect(within(page).getByText("Paper simulation requires explicit PAPER SIMULATION ON and remains simulated only.")).toBeInTheDocument();
    expect(within(page).getByText(/run_reports\/control_center_monitor_runs\/full_monitor_run_stage24\.md/)).toBeInTheDocument();
    expect(within(page).queryByText(/^RUNNING$/i)).not.toBeInTheDocument();
    expect(within(page).queryByText(/fake pnl/i)).not.toBeInTheDocument();
    expect(within(page).queryByText(/fake dialogue/i)).not.toBeInTheDocument();
  }, 15000);
});
