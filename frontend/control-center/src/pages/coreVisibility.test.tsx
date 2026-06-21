import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { TruthEnvelope } from "../lib/truth-contract";

function envelope(overrides: Partial<TruthEnvelope> = {}): TruthEnvelope {
  return {
    status: "MISSING",
    source: "stage9_test_source",
    last_updated: "2026-06-08T00:00:00+00:00",
    stale_after_seconds: 300,
    truth_state: "UNKNOWN",
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

function stage9EnvelopeForUrl(url: string) {
  if (url.includes("/overview")) {
    return envelope({
      status: "PARTIAL",
      source: "control_overview",
      truth_state: "REFRESH_REQUIRED",
      data: {
        source_counts: { system_state: 1, service_health: 2 },
        latest_rows: {
          system_state: { updated_at: "2026-06-08T00:01:00+00:00" },
          service_health: { last_heartbeat_at: "2026-06-08T00:02:00+00:00" }
        },
        control_endpoints: ["/dashboard/api/v2/control/overview", "/dashboard/api/v2/control/organs"],
        read_only: true,
        mutating_actions_exposed: []
      },
      warnings: ["overview source coverage partial"]
    });
  }

  if (url.includes("/organs")) {
    return envelope({
      status: "REAL",
      source: "service_health",
      truth_state: "ACTIVE_FRESH",
      data: {
        services: [
          {
            service_name: "market-service",
            status: "HEARTBEAT_SEEN",
            last_heartbeat_at: "2026-06-08T00:03:00+00:00"
          }
        ],
        count: 1,
        latest_heartbeat_at: "2026-06-08T00:03:00+00:00",
        read_only: true
      }
    });
  }

  if (url.includes("/live-flow")) {
    return envelope({
      status: "REAL",
      source: "event_log",
      truth_state: "ACTIVE_FRESH",
      data: {
        events: [
          {
            id: "event-1",
            event_type: "runtime.cycle.completed",
            stored_at: "2026-06-08T00:04:00+00:00"
          }
        ],
        count: 1,
        latest_at: "2026-06-08T00:04:00+00:00",
        read_only: true
      }
    });
  }

  if (url.includes("/logs")) {
    return envelope({
      status: "REAL",
      source: "runtime_incidents:event_delivery_attempts:event_log",
      truth_state: "ACTIVE_FRESH",
      data: {
        runtime_incidents: [{ id: "incident-1", incident_type: "db_disconnect", last_seen_at: "2026-06-08T00:05:00+00:00" }],
        event_delivery_attempts: [{ attempt_id: "attempt-1", consumer: "consumer-a", finished_at: "2026-06-08T00:06:00+00:00" }],
        events: [{ id: "log-event-1", event_type: "runtime.event", stored_at: "2026-06-08T00:07:00+00:00" }],
        latest_at: "2026-06-08T00:07:00+00:00",
        read_only: true
      }
    });
  }

  return envelope({
    status: "PARTIAL",
    source: "unrelated_stage9_source",
    truth_state: "REFRESH_REQUIRED",
    warnings: ["unrelated endpoint fallback"]
  });
}

const dangerousControlLabels = [/^SYSTEM ON$/i, /^SYSTEM OFF$/i, /^START RUN$/i, /^STOP RUN$/i, /^KILL$/i, /^RESET BALANCE$/i];

describe("Stage 9 core visibility pages", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => Promise.resolve(jsonResponse(stage9EnvelopeForUrl(String(input))))));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders Overview from the Stage 8 overview hook data", async () => {
    render(<App />);

    const page = await screen.findByTestId("page-overview");
    await waitFor(() => expect(within(page).getAllByText("system_state").length).toBeGreaterThan(0));
    expect(within(page).getByText("Source Coverage")).toBeInTheDocument();
    expect(within(page).getAllByText("system_state").length).toBeGreaterThan(0);
    expect(within(page).getAllByText("service_health").length).toBeGreaterThan(0);
    expect(within(page).getByText("Latest Source Rows")).toBeInTheDocument();
    expect(within(page).getAllByText("overview source coverage partial").length).toBeGreaterThan(0);
  });

  it("renders Organ Health heartbeat evidence without control actions", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Organ Health" }));

    const page = await screen.findByTestId("page-organ-health");
    await waitFor(() => expect(within(page).getByText("market-service")).toBeInTheDocument());
    expect(within(page).getByText("Organs / Services")).toBeInTheDocument();
    expect(within(page).getByText("market-service")).toBeInTheDocument();
    expect(within(page).getByText("Reported state: HEARTBEAT_SEEN")).toBeInTheDocument();

    for (const label of dangerousControlLabels) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
  });

  it("renders Live Flow event evidence from read-only hook data", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Live" }));

    const page = await screen.findByTestId("page-live-flow");
    await waitFor(() => expect(within(page).getByText("runtime.cycle.completed")).toBeInTheDocument());
    expect(within(page).getByText("Event Stream")).toBeInTheDocument();
    expect(within(page).getByText("runtime.cycle.completed")).toBeInTheDocument();
    expect(within(page).getByText("ID: event-1")).toBeInTheDocument();
  });

  it("renders Logs & Errors incidents, delivery attempts, and recent events", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Logs & Errors" }));

    const page = await screen.findByTestId("page-logs-errors");
    await waitFor(() => expect(within(page).getByText("db_disconnect")).toBeInTheDocument());
    expect(within(page).getByText("Runtime Incidents")).toBeInTheDocument();
    expect(within(page).getByText("db_disconnect")).toBeInTheDocument();
    expect(within(page).getByText("Event Delivery Attempts")).toBeInTheDocument();
    expect(within(page).getByText("consumer-a")).toBeInTheDocument();
    expect(within(page).getByText("Recent Events")).toBeInTheDocument();
    expect(within(page).getByText("runtime.event")).toBeInTheDocument();
  });
});
