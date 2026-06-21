import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { TruthEnvelope } from "../lib/truth-contract";

function envelope(overrides: Partial<TruthEnvelope> = {}): TruthEnvelope {
  return {
    status: "PARTIAL",
    source: "stage11_test_source",
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

function overviewEnvelope() {
  return envelope({
    status: "PARTIAL",
    source: "control_overview",
    data: {
      capital: {
        reconciliation_status: "RECONCILED",
        current_balance: 1000,
        available_capital: 800,
        locked_capital: 50,
        open_exposure: 150
      },
      source_counts: { paper_capital_ledger: 1 }
    },
    warnings: ["overview capital coverage partial"]
  });
}

function pnlEnvelope() {
  return envelope({
    status: "REAL",
    source: "paper_pnl_ledger",
    truth_state: "ACTIVE_FRESH",
    data: {
      pnl_ledger: {
        status: "OK",
        reconciliation_status: "RECONCILED",
        current_balance: 1000,
        available_balance: 900,
        locked_balance: 100,
        realized_pnl: 12.5,
        unrealized_pnl: -1.25,
        ledger_rows: [
          {
            ledger_id: "ledger-1",
            event_type: "CAPITAL_LOCK",
            amount: 100,
            market_id: "market-1",
            created_at: "2026-06-08T00:01:00+00:00"
          }
        ]
      },
      fake_pnl: false
    },
    warnings: ["ledger warning"],
    errors: ["ledger error detail"]
  });
}

function positionsEnvelope(rows = true) {
  return envelope({
    status: "REAL",
    source: "paper_positions",
    truth_state: "ACTIVE_FRESH",
    data: {
      positions: rows
        ? {
            status: "OK",
            count: 1,
            positions: [
              {
                position_id: "pos-1",
                market_id: "market-1",
                side: "YES",
                size: 5,
                entry_price: 0.4,
                current_price: 0.55,
                unrealized_pnl: 0.75,
                status: "OPEN",
                opened_at: "2026-06-08T00:02:00+00:00"
              }
            ],
            orders: [{ order_id: "order-should-not-render", market_id: "market-1" }]
          }
        : {
            status: "OK",
            count: 0,
            positions: [],
            orders: [{ order_id: "order-should-not-render", market_id: "market-1" }],
            fills: [{ fill_id: "fill-should-not-render", market_id: "market-1" }]
          },
      fake_positions: false
    }
  });
}

function noTradeEnvelope() {
  return envelope({
    status: "REAL",
    source: "no_trade_log",
    truth_state: "ACTIVE_FRESH",
    data: {
      no_trade: {
        status: "OK",
        total_no_trade_records: 2,
        top_no_trade_reasons: [{ reason: "MISSING_EXIT_PLAN", count: 1 }],
        latest_no_trade: [
          {
            no_trade_id: "nt-1",
            candidate_id: "cand-1",
            market_id: "market-1",
            decision_status: "NO_TRADE",
            primary_reason: "RISK_BLOCKED",
            blocked_by: "RISK_BLOCKED",
            missing_data: ["ORDERBOOK"],
            risk_flags: ["STALE_RISK"],
            created_at: "2026-06-08T00:03:00+00:00"
          }
        ]
      },
      first_class_decision: true
    }
  });
}

function responseForUrl(url: string) {
  if (url.includes("/overview")) return overviewEnvelope();
  if (url.includes("/pnl-ledger")) return pnlEnvelope();
  if (url.includes("/positions")) return positionsEnvelope();
  if (url.includes("/no-trade")) return noTradeEnvelope();
  return envelope({ source: "unrelated_stage11_source" });
}

function mockFetch(handler: (url: string) => TruthEnvelope = responseForUrl) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => Promise.resolve(jsonResponse(handler(String(input)))))
  );
}

describe("Stage 11 money visibility pages", () => {
  beforeEach(() => {
    mockFetch();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders PnL and ledger values only from a ledger-backed envelope", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Money/i }));

    expect(await screen.findByText("ledger-1")).toBeInTheDocument();
    expect(screen.getAllByText("paper_pnl_ledger").length).toBeGreaterThan(0);
    expect(screen.getAllByText("12.5").length).toBeGreaterThan(0);
    expect(screen.getAllByText("-1.25").length).toBeGreaterThan(0);
    expect(screen.getByText(/CAPITAL_LOCK/)).toBeInTheDocument();
    expect(screen.getByText("ledger warning")).toBeInTheDocument();
    expect(screen.getByText("ledger error detail")).toBeInTheDocument();
  });

  it("withholds PnL values when the source is missing or non-ledger", async () => {
    mockFetch((url) => {
      if (url.includes("/pnl-ledger")) {
        return envelope({
          status: "MISSING",
          source: null,
          data: {
            pnl_ledger: {
              realized_pnl: 999999,
              ledger_rows: [{ ledger_id: "should-not-render" }]
            }
          }
        });
      }
      return responseForUrl(url);
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Money/i }));

    expect(await screen.findByText("PnL source missing or non-ledger; money values are withheld.")).toBeInTheDocument();
    expect(screen.queryByText("999999")).not.toBeInTheDocument();
    expect(screen.queryByText("should-not-render")).not.toBeInTheDocument();
  });

  it("renders Capital from overview when overview contains capital reconciliation", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /^Capital$/i }));

    expect(await screen.findByText("Capital Reconciliation")).toBeInTheDocument();
    expect(screen.getAllByText("RECONCILED").length).toBeGreaterThan(0);
    expect(screen.getAllByText("800").length).toBeGreaterThan(0);
    expect(screen.getAllByText("50").length).toBeGreaterThan(0);
    expect(screen.getAllByText("150").length).toBeGreaterThan(0);
  });

  it("marks Capital partial when overview lacks a capital section", async () => {
    mockFetch((url) => {
      if (url.includes("/overview")) {
        return envelope({
          status: "PARTIAL",
          source: "control_overview",
          data: { source_counts: { system_state: 1 } }
        });
      }
      return responseForUrl(url);
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /^Capital$/i }));

    expect(await screen.findByText("Capital reconciliation source missing or partial; overview does not expose a dedicated capital section.")).toBeInTheDocument();
  });

  it("renders canonical Positions from paper_positions and ignores order rows", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /^Positions$/i }));

    expect(await screen.findByText("pos-1")).toBeInTheDocument();
    expect(screen.getAllByText("paper_positions").length).toBeGreaterThan(0);
    expect(screen.getByText(/market_id: market-1/i)).toBeInTheDocument();
    expect(screen.queryByText("order-should-not-render")).not.toBeInTheDocument();
  });

  it("does not treat orders or fills as Positions", async () => {
    mockFetch((url) => (url.includes("/positions") ? positionsEnvelope(false) : responseForUrl(url)));
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /^Positions$/i }));

    expect(await screen.findByText("No canonical position rows were returned; orders and fills are not displayed as positions.")).toBeInTheDocument();
    expect(screen.queryByText("order-should-not-render")).not.toBeInTheDocument();
    expect(screen.queryByText("fill-should-not-render")).not.toBeInTheDocument();
  });

  it("renders backend-supplied No-Trade reasons and latest records", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /^No-Trade$/i }));

    expect(await screen.findByText("nt-1")).toBeInTheDocument();
    expect(screen.getByText(/cand-1/)).toBeInTheDocument();
    expect(screen.getByText("MISSING_EXIT_PLAN")).toBeInTheDocument();
    expect(screen.getAllByText(/RISK_BLOCKED/).length).toBeGreaterThan(0);
    expect(screen.getByText(/ORDERBOOK/)).toBeInTheDocument();
  });

  it("does not invent No-Trade reasons when source is missing", async () => {
    mockFetch((url) => {
      if (url.includes("/no-trade")) {
        return envelope({
          status: "MISSING",
          source: null,
          data: { no_trade: {}, first_class_decision: true }
        });
      }
      return responseForUrl(url);
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /^No-Trade$/i }));

    expect(await screen.findByText("No-trade source missing; reasons are withheld instead of invented.")).toBeInTheDocument();
    expect(screen.getByText("No no-trade records were returned. The UI will not invent no-trade reasons.")).toBeInTheDocument();
    expect(screen.queryByText("MISSING_EXIT_PLAN")).not.toBeInTheDocument();
  });

  it("keeps money pages read-only with manual refresh using the existing GET fetch layer", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /Money/i }));
    await screen.findByText("ledger-1");

    const page = screen.getByTestId("page-pnl-ledger");
    expect(within(page).getByText("READ_ONLY_API_LAYER / VISIBILITY_GET_ONLY")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: /Refresh read-only data/i })).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: /buy|sell|execute|order|fill|position create/i })).not.toBeInTheDocument();
  });
});
