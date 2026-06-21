import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { TruthEnvelope } from "../lib/truth-contract";

function envelope(): TruthEnvelope {
  return {
    status: "PARTIAL",
    source: "control_actions_test_source",
    last_updated: "2026-06-08T00:00:00+00:00",
    stale_after_seconds: 300,
    truth_state: "REFRESH_REQUIRED",
    data: {},
    warnings: [],
    errors: []
  };
}

function actionEnvelope(overrides: Record<string, unknown> = {}) {
  return {
    action: "system-off",
    status: "ACCEPTED",
    actor: "operator",
    reason: "manual safety check",
    timestamp: "2026-06-08T00:01:00+00:00",
    audit_id: "transition-off",
    state_before: {},
    state_after: {},
    safety_checks: [{ name: "state_governor_loaded", status: "PASS", detail: "Current runtime state loaded." }],
    result: { system_power: "OFF" },
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

describe("Stage 15 Control Actions panel", () => {
  beforeEach(() => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:polybot-control-center"),
      revokeObjectURL: vi.fn()
    });
    vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      const element = document.createElementNS("http://www.w3.org/1999/xhtml", tagName) as HTMLElement;
      if (tagName === "a") {
        Object.assign(element, { click: vi.fn() });
      }
      return element as HTMLElement;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (init?.method === "POST") {
          return Promise.resolve(jsonResponse(actionEnvelope({ action: url.split("/").pop() })));
        }
        return Promise.resolve(jsonResponse(envelope()));
      })
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders allowed action set and no forbidden trading controls", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    const panel = screen.getByTestId("page-settings");

    expect(within(panel).getByText("SYSTEM ON")).toBeInTheDocument();
    expect(within(panel).getByText("SYSTEM OFF")).toBeInTheDocument();
    expect(within(panel).getByText("START MONITORING RUN")).toBeInTheDocument();
    expect(within(panel).getByText("STOP CURRENT RUN")).toBeInTheDocument();
    expect(within(panel).getByText("KILL SWITCH")).toBeInTheDocument();
    expect(within(panel).getByText("RESET PAPER BALANCE")).toBeInTheDocument();

    expect(screen.queryByText(/manual trade/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/approve trade/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/override blocker/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/disable risk/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/disable governance/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/live trading/i)).not.toBeInTheDocument();
  });

  it("requires actor and reason before enabled backend action request", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    const requestSystemOff = screen.getByRole("button", { name: "Request SYSTEM OFF" });
    expect(requestSystemOff).toBeDisabled();

    await user.type(screen.getByLabelText("Actor"), "operator");
    expect(requestSystemOff).toBeDisabled();
    await user.type(screen.getByLabelText("Reason"), "manual safety check");
    expect(requestSystemOff).toBeEnabled();
  });

  it("requires KILL confirmation before kill switch request", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    await user.type(screen.getByLabelText("Actor"), "operator");
    await user.type(screen.getByLabelText("Reason"), "emergency stop");

    const killButton = screen.getByRole("button", { name: "Request KILL SWITCH" });
    expect(killButton).toBeDisabled();
    await user.type(screen.getByPlaceholderText("KILL"), "KILL");
    expect(killButton).toBeEnabled();
  });

  it("keeps reset paper balance locked while monitor run actions are active", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));

    expect(screen.getByRole("button", { name: "Request START MONITORING RUN" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Request STOP CURRENT RUN" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "LOCKED" })).toBeDisabled();
    expect(screen.getByText(/paper-only reset contract/i)).toBeInTheDocument();
  });

  it("posts only to safe Control Center action wrapper endpoints and displays audit result", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.mocked(globalThis.fetch);
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    await user.type(screen.getByLabelText("Actor"), "operator");
    await user.type(screen.getByLabelText("Reason"), "manual safety check");
    await user.click(screen.getByRole("button", { name: "Request SYSTEM OFF" }));

    await waitFor(() => expect(screen.getByText("transition-off")).toBeInTheDocument());
    expect(screen.getByText("state_governor_loaded")).toBeInTheDocument();

    const postCalls = fetchSpy.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(postCalls).toHaveLength(1);
    expect(String(postCalls[0][0])).toBe("/dashboard/api/v2/control/actions/system-off");
    expect(String(postCalls[0][0])).not.toMatch(/\/runtime|\/execution|\/risk|\/paper|\/system\/power|live/i);
  });

  it("exports a read-only frontend snapshot without posting", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.mocked(globalThis.fetch);
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    await user.click(screen.getByRole("button", { name: "Export read-only snapshot" }));

    expect(screen.getByText(/Read-only snapshot export prepared/i)).toBeInTheDocument();
    const postCalls = fetchSpy.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(postCalls).toHaveLength(0);
  });
});
