import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { TruthEnvelope } from "../lib/truth-contract";

function envelope(overrides: Partial<TruthEnvelope> = {}): TruthEnvelope {
  return {
    status: "MISSING",
    source: "control_center:full_monitor_run",
    last_updated: null,
    stale_after_seconds: null,
    truth_state: "UNKNOWN",
    data: { run_type: "FULL_MONITOR_RUN", latest: null },
    warnings: ["No Full Monitor Run has been started."],
    errors: [],
    ...overrides
  };
}

function runResult() {
  return {
    run_id: "full_monitor_run_test",
    status: "COMPLETED",
    requested_duration_minutes: 5,
    interval_seconds: 10,
    elapsed_seconds: 0.2,
    remaining_seconds: 0,
    cycles_completed: 1,
    markets_checked: 12,
    events_created: 0,
    opportunities_found: 1,
    no_trades_logged: 1,
    paper_orders: 0,
    paper_fills: 0,
    positions_updated: 0,
    execution_enabled: false,
    report_path: "run_reports/control_center_monitor_runs/full_monitor_run_test.md",
    audit_id: "control_center_full_monitor_run:test",
    module_results: [
      { module: "market_scan", status: "COMPLETED", behavior: "Read-only overview source and market coverage summary." },
      { module: "orderbook", status: "SKIPPED", behavior: "No safe Control Center read-only orderbook monitor endpoint exists." },
      { module: "live_execution", status: "SKIPPED", behavior: "Live execution is forbidden." }
    ],
    warnings: ["Stage 16 monitor run is synchronous, bounded, and read-only/evaluation-only."],
    errors: []
  };
}

function actionEnvelope(action: string) {
  return {
    action,
    status: "ACCEPTED",
    actor: "operator",
    reason: "monitor body",
    timestamp: "2026-06-08T00:00:00+00:00",
    audit_id: action === "start-full-monitor-run" ? "control_center_full_monitor_run:test" : "control_center_full_monitor_stop:test",
    state_before: {},
    state_after: {},
    safety_checks: [{ name: "state_governor_checked", status: "PASS", detail: "State Governor checked." }],
    result: action === "start-full-monitor-run" ? runResult() : { ...runResult(), status: "STOPPED" },
    warnings: [],
    errors: []
  };
}

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

describe("Stage 16 Full Monitor Run controls", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST") {
          return Promise.resolve(jsonResponse(actionEnvelope(url.split("/").pop() ?? "")));
        }
        if (url.includes("/full-monitor-run")) {
          return Promise.resolve(jsonResponse(envelope()));
        }
        return Promise.resolve(jsonResponse(envelope({ source: "test:read_only", warnings: [] })));
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("start requires duration, actor, and reason", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    const start = screen.getByRole("button", { name: "Request START MONITORING RUN" });
    expect(start).toBeDisabled();

    await user.type(screen.getByLabelText("Actor"), "operator");
    await user.type(screen.getByLabelText("Reason"), "monitor body");
    expect(start).toBeEnabled();

    await user.clear(screen.getByLabelText("Duration minutes"));
    await user.type(screen.getByLabelText("Duration minutes"), "0");
    expect(start).toBeDisabled();
  }, 15000);

  it("start posts only to the safe wrapper endpoint and displays counters/skipped modules", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.mocked(globalThis.fetch);
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    await user.type(screen.getByLabelText("Actor"), "operator");
    await user.type(screen.getByLabelText("Reason"), "monitor body");
    await user.clear(screen.getByLabelText("Duration minutes"));
    await user.type(screen.getByLabelText("Duration minutes"), "5");
    await user.clear(screen.getByLabelText("Interval seconds"));
    await user.type(screen.getByLabelText("Interval seconds"), "10");
    await user.click(screen.getByRole("button", { name: "Request START MONITORING RUN" }));

    await waitFor(() => expect(screen.getByText("full_monitor_run_test")).toBeInTheDocument());
    expect(screen.getByText("Markets")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getAllByText("No-Trade").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SKIPPED").length).toBeGreaterThan(0);
    expect(screen.getByText("orderbook")).toBeInTheDocument();

    const postCalls = fetchSpy.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(postCalls).toHaveLength(1);
    expect(String(postCalls[0][0])).toBe("/dashboard/api/v2/control/actions/start-full-monitor-run");
    expect(JSON.parse(String(postCalls[0][1]?.body)).interval_seconds).toBe(10);
    expect(String(postCalls[0][0])).not.toMatch(/\/runtime|\/execution|\/risk|\/paper|\/system\/power|live/i);
  }, 15000);

  it("stop requires actor and reason and uses only the safe wrapper endpoint", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.mocked(globalThis.fetch);
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    const stop = screen.getByRole("button", { name: "Request STOP CURRENT RUN" });
    expect(stop).toBeDisabled();

    await user.type(screen.getByLabelText("Actor"), "operator");
    await user.type(screen.getByLabelText("Reason"), "stop monitor");
    expect(stop).toBeEnabled();
    await user.click(stop);

    await waitFor(() => expect(screen.getByText("STOPPED")).toBeInTheDocument());
    const postCalls = fetchSpy.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(String(postCalls[0][0])).toBe("/dashboard/api/v2/control/actions/stop-current-run");
  });

  it("does not expose forbidden controls", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    const page = screen.getByTestId("page-settings");
    expect(within(page).queryByText(/manual trade/i)).not.toBeInTheDocument();
    expect(within(page).queryByText(/approve trade/i)).not.toBeInTheDocument();
    expect(within(page).queryByText(/override blocker/i)).not.toBeInTheDocument();
    expect(within(page).queryByText(/disable risk/i)).not.toBeInTheDocument();
    expect(within(page).queryByText(/disable governance/i)).not.toBeInTheDocument();
  });
});
