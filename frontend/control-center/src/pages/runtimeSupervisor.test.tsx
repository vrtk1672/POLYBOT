import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { TruthEnvelope } from "../lib/truth-contract";

function envelope(overrides: Partial<TruthEnvelope> = {}): TruthEnvelope {
  return {
    status: "PARTIAL",
    source: "test:read_only",
    last_updated: "2026-06-10T00:00:00+00:00",
    stale_after_seconds: 300,
    truth_state: "REFRESH_REQUIRED",
    data: {},
    warnings: [],
    errors: [],
    ...overrides
  };
}

function supervisorEnvelope(status = "RUNNING"): TruthEnvelope {
  return envelope({
    status: status === "RUNNING" ? "REAL" : "PARTIAL",
    source: "control_center:runtime_supervisor",
    truth_state: status === "RUNNING" ? "ACTIVE_FRESH" : "REFRESH_REQUIRED",
    data: {
      supervisor_available: true,
      supervisor_status: status,
      session_id: "runtime_supervisor_test",
      system_power: "ON",
      mode: "DATA_ONLY",
      interval_seconds: 60,
      last_cycle_at: "2026-06-10T00:01:00+00:00",
      next_cycle_at: "2026-06-10T00:02:00+00:00",
      current_cycle_status: "COMPLETED",
      elapsed_seconds: 62,
      cycles_completed: 2,
      cycles_failed: 0,
      markets_checked: 24,
      events_seen: 2,
      opportunities_found: 2,
      no_trades_logged: 1,
      ai_calls: 2,
      ai_failures: 0,
      execution_enabled: false,
      paper_execution_enabled: false,
      report_path: status === "STOPPED" ? "run_reports/control_center_supervisor_sessions/runtime_supervisor_test.md" : null
    }
  });
}

function overviewEnvelope(power = "ON"): TruthEnvelope {
  return envelope({
    status: "PARTIAL",
    source: "runtime_state_service_health_event_log",
    data: {
      source_counts: { event_log: 10 },
      latest_rows: {
        system_state: {
          current_mode: "DATA_ONLY",
          system_power: power
        }
      }
    }
  });
}

function actionEnvelope(action: string, supervisorStatus = "RUNNING") {
  return {
    action,
    status: "ACCEPTED",
    actor: "harel",
    reason: "stage 27",
    timestamp: "2026-06-10T00:00:00+00:00",
    audit_id: "transition-test",
    state_before: {},
    state_after: {},
    safety_checks: [{ name: "runtime_supervisor", status: "PASS", detail: "Supervisor updated." }],
    result: {
      system_power: action === "system-off" ? "OFF" : "ON",
      monitoring_enabled: action === "system-on",
      execution_enabled: false,
      paper_execution_enabled: false,
      supervisor: supervisorEnvelope(supervisorStatus).data
    },
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

describe("Stage 27 Runtime Supervisor cockpit", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST") {
          const action = url.split("/").pop() ?? "";
          return Promise.resolve(jsonResponse(actionEnvelope(action, action === "system-off" ? "STOPPED" : "RUNNING")));
        }
        if (url.includes("/runtime-supervisor")) return Promise.resolve(jsonResponse(supervisorEnvelope("RUNNING")));
        if (url.includes("/overview")) return Promise.resolve(jsonResponse(overviewEnvelope("ON")));
        if (url.includes("/full-monitor-run")) return Promise.resolve(jsonResponse(envelope({ source: "control_center:full_monitor_run", data: { current: null, latest: null } })));
        return Promise.resolve(jsonResponse(envelope()));
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows supervisor heartbeat, DATA_ONLY badge, and paper switch state", async () => {
    render(<App />);

    expect(await screen.findByText("Runtime Supervisor Heartbeat")).toBeInTheDocument();
    expect(await screen.findByText("POLYBOT is monitoring in DATA_ONLY mode.")).toBeInTheDocument();
    expect(screen.getByText("DATA_ONLY monitoring")).toBeInTheDocument();
    expect(screen.getByText("Live execution disabled")).toBeInTheDocument();
    expect(screen.getByText("Paper Simulation Flow")).toBeInTheDocument();
    expect(screen.getByText("Cycles completed")).toBeInTheDocument();
    expect(screen.getByText("runtime_supervisor_test")).toBeInTheDocument();
  });

  it("SYSTEM ON uses the safe action wrapper and refreshes supervisor truth", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.mocked(globalThis.fetch);
    render(<App />);

    await user.type(screen.getByLabelText("Actor"), "harel");
    await user.type(screen.getByLabelText("Reason"), "stage 27 supervisor start test");
    await user.click(screen.getAllByRole("button", { name: /SYSTEM ON/i })[0]);

    await waitFor(() => expect(fetchSpy.mock.calls.some(([input]) => String(input).includes("/runtime-supervisor"))).toBe(true));
    const postCalls = fetchSpy.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(String(postCalls[0][0])).toBe("/dashboard/api/v2/control/actions/system-on");
    expect(fetchSpy.mock.calls.some(([input]) => String(input).includes("/runtime-supervisor"))).toBe(true);
  });

  it("shows degraded copy when ON but supervisor is stopped", async () => {
    vi.mocked(globalThis.fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST") return Promise.resolve(jsonResponse(actionEnvelope(url.split("/").pop() ?? "")));
      if (url.includes("/runtime-supervisor")) return Promise.resolve(jsonResponse(supervisorEnvelope("STOPPED")));
      if (url.includes("/overview")) return Promise.resolve(jsonResponse(overviewEnvelope("ON")));
      return Promise.resolve(jsonResponse(envelope()));
    });

    render(<App />);

    expect(await screen.findByText("System is ON but supervisor is not running.")).toBeInTheDocument();
  });

  it("shows OFF copy and session report path", async () => {
    vi.mocked(globalThis.fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST") return Promise.resolve(jsonResponse(actionEnvelope(url.split("/").pop() ?? "", "STOPPED")));
      if (url.includes("/runtime-supervisor")) return Promise.resolve(jsonResponse(supervisorEnvelope("STOPPED")));
      if (url.includes("/overview")) return Promise.resolve(jsonResponse(overviewEnvelope("OFF")));
      return Promise.resolve(jsonResponse(envelope()));
    });

    render(<App />);

    expect(await screen.findByText("System is OFF. Press SYSTEM ON to start monitoring.")).toBeInTheDocument();
    expect(await screen.findByText(/runtime_supervisor_test\.md/)).toBeInTheDocument();
  });
});
