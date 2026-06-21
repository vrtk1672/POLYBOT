import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { TruthEnvelope } from "../lib/truth-contract";
import { ControlCenterQueryProvider, createControlCenterQueryClient } from "./queryClient";
import { useOverviewQuery } from "./useControlCenterQueries";

function envelope(overrides: Partial<TruthEnvelope> = {}): TruthEnvelope {
  return {
    status: "MISSING",
    source: "test_source",
    last_updated: "2026-06-08T00:00:00+00:00",
    stale_after_seconds: 300,
    truth_state: "UNKNOWN",
    data: {},
    warnings: ["test warning"],
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

function renderWithClient(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false, gcTime: Infinity }
    }
  });
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

function HookProbe() {
  const query = useOverviewQuery();
  return (
    <div>
      <p>{query.data?.status ?? "loading"}</p>
      <p>{query.data?.source ?? "source_missing"}</p>
    </div>
  );
}

describe("Control Center query hooks and provider", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("wires a QueryProvider", () => {
    render(
      <ControlCenterQueryProvider>
        <div>provider child</div>
      </ControlCenterQueryProvider>
    );
    expect(screen.getByText("provider child")).toBeInTheDocument();
    expect(createControlCenterQueryClient()).toBeInstanceOf(QueryClient);
  });

  it("hooks preserve MISSING PARTIAL STALE NOT_IMPLEMENTED and never convert to REAL", async () => {
    const fetchMock = vi.mocked(fetch);
    for (const status of ["MISSING", "PARTIAL", "STALE", "NOT_IMPLEMENTED"] as const) {
      fetchMock.mockResolvedValueOnce(jsonResponse(envelope({ status, truth_state: status === "PARTIAL" ? "REFRESH_REQUIRED" : "UNKNOWN" })));
      renderWithClient(<HookProbe />);
      expect(await screen.findByText(status)).toBeInTheDocument();
      expect(screen.queryByText("REAL")).not.toBeInTheDocument();
    }
  });

  it("pages render fetched backend truth status and source", async () => {
    vi.mocked(fetch).mockImplementation(() =>
      Promise.resolve(jsonResponse(
        envelope({
          status: "STALE",
          source: "stage5_read_only_source",
          truth_state: "LAST_KNOWN",
          warnings: ["backend stale warning"],
          data: { source_kind: "test-only mock" }
        })
      ))
    );

    render(<App />);

    expect((await screen.findAllByText("STALE")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("stage5_read_only_source").length).toBeGreaterThan(0);
    expect(screen.getAllByText("backend stale warning").length).toBeGreaterThan(0);
  });

  it("manual refresh button only refetches read-only data and exposes no forbidden controls", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse(envelope({ status: "PARTIAL", source: "refresh_source", truth_state: "REFRESH_REQUIRED" })))
    );

    render(<App />);

    const refresh = await screen.findByRole("button", { name: "Refresh read-only data" });
    await user.click(refresh);

    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(1));
    expect(screen.getByRole("button", { name: /^SYSTEM ON$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^SYSTEM OFF$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^START RUN$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^STOP RUN$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^KILL$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^RESET BALANCE$/i })).not.toBeInTheDocument();
  });
});
