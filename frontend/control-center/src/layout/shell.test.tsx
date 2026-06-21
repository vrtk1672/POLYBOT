import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { PAGE_SHELLS } from "../pages";

const readOnlyEnvelope = {
  status: "PARTIAL",
  source: "shell_test_read_only_source",
  last_updated: "2026-06-08T00:00:00+00:00",
  stale_after_seconds: 300,
  truth_state: "REFRESH_REQUIRED",
  data: {},
  warnings: ["shell test warning"],
  errors: []
};

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

const fakeRuntimeClaims = [
  /fake system online/i,
  /fake healthy/i,
  /fake pnl/i,
  /fake positions/i,
  /fake orders/i,
  /fake fills/i,
  /^SYSTEM ONLINE$/i,
  /^SYSTEM HEALTHY$/i,
  /^CURRENT MODE$/i
];

describe("Control Center frontend shell", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(readOnlyEnvelope))));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders every required sidebar entry", () => {
    render(<App />);

    for (const page of PAGE_SHELLS) {
      expect(screen.getByRole("button", { name: page.label })).toBeInTheDocument();
    }
  });

  it("changes active page using local sidebar state", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Decision" }));
    expect(screen.getByTestId("page-decision-xray")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Decision X-Ray", level: 1 })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Controls" }));
    expect(screen.getByTestId("page-settings")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Controls", level: 1 })).toBeInTheDocument();
  });

  it("top system bar declares demo-only and runtime-disconnected state", () => {
    render(<App />);

    expect(screen.getByText("READ_ONLY_API_LAYER")).toBeInTheDocument();
    expect(screen.getByText("VISIBILITY_GET_ACTIONS_POST")).toBeInTheDocument();
    expect(screen.getByText("No live controls active")).toBeInTheDocument();
    expect(screen.getByText("Gated runtime actions only")).toBeInTheDocument();
  });

  it("does not render fake runtime success claims", () => {
    render(<App />);

    for (const claim of fakeRuntimeClaims) {
      expect(screen.queryByText(claim)).not.toBeInTheDocument();
    }
  });

  it("every page shell includes an explicit placeholder state", async () => {
    const user = userEvent.setup();
    render(<App />);

    for (const page of PAGE_SHELLS) {
      await user.click(screen.getByRole("button", { name: page.label }));
      const pageShell = screen.getByTestId(`page-${page.id}`);
      const expectedState = page.endpoint ? readOnlyEnvelope.status : page.stateLabel;
      expect(within(pageShell).getAllByText(expectedState).length).toBeGreaterThan(0);
      expect(
        within(pageShell).queryAllByText(/NOT_IMPLEMENTED|PARTIAL|DEMO_ONLY|LOCKED|MISSING/).length
      ).toBeGreaterThan(0);
    }
  }, 15000);

  it("shows future endpoint labels for pages with expected read-only sources", async () => {
    const user = userEvent.setup();
    render(<App />);

    for (const page of PAGE_SHELLS.filter((item) => item.endpoint)) {
      await user.click(screen.getByRole("button", { name: page.label }));
      expect(screen.getAllByText(page.endpoint as string).length).toBeGreaterThan(0);
    }
  }, 15000);

  it("settings page exposes only gated Control Center wrapper actions", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Controls" }));
    expect(screen.getByTestId("page-settings")).toBeInTheDocument();
    expect(screen.getByText("CONTROL_ACTIONS_GATED")).toBeInTheDocument();
    expect(screen.getAllByText("/dashboard/api/v2/control/actions").length).toBeGreaterThan(0);
    expect(screen.queryByText(/manual trade/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/approve trade/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/override blocker/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/disable risk/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/disable governance/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/engine budget/i)).not.toBeInTheDocument();
  });

  it("does not expose forbidden trading or override controls anywhere", () => {
    render(<App />);

    expect(screen.queryByText(/manual trade/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/approve trade/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/override blocker/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/disable risk/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/disable governance/i)).not.toBeInTheDocument();
  });
});
