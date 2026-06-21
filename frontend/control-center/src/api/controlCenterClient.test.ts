import { describe, expect, it, vi } from "vitest";

import { controlCenterClient, fetchControlCenterEnvelope } from "./controlCenterClient";
import { controlCenterEndpointKeys, controlCenterEndpoints } from "./controlCenterEndpoints";
import { refreshPolicyMs } from "./refreshPolicy";

const validEnvelope = {
  status: "PARTIAL",
  source: "test_source",
  last_updated: "2026-06-08T00:00:00+00:00",
  stale_after_seconds: 300,
  truth_state: "REFRESH_REQUIRED",
  data: { value: "test" },
  warnings: ["test warning"],
  errors: []
} as const;

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init
  });
}

describe("Control Center endpoint map and client", () => {
  it("contains all Stage 6 read-only endpoints plus monitor/supervisor status", () => {
    expect(controlCenterEndpoints).toEqual({
      overview: "/dashboard/api/v2/control/overview",
      organs: "/dashboard/api/v2/control/organs",
      liveFlow: "/dashboard/api/v2/control/live-flow",
      decisionXray: "/dashboard/api/v2/control/decision-xray",
      blockers: "/dashboard/api/v2/control/blockers",
      closestActionable: "/dashboard/api/v2/control/closest-actionable",
      truthState: "/dashboard/api/v2/control/truth-state",
      riskEvidence: "/dashboard/api/v2/control/risk-evidence",
      lifecycleGovernance: "/dashboard/api/v2/control/lifecycle-governance",
      meshDialogues: "/dashboard/api/v2/control/mesh-dialogues",
      pnlLedger: "/dashboard/api/v2/control/pnl-ledger",
      positions: "/dashboard/api/v2/control/positions",
      noTrade: "/dashboard/api/v2/control/no-trade",
      ai: "/dashboard/api/v2/control/ai",
      logs: "/dashboard/api/v2/control/logs",
      truthContract: "/dashboard/api/v2/control/truth-contract",
      runtimeReadiness: "/dashboard/api/v2/control/runtime-readiness",
      supervisorLifePath: "/dashboard/api/v2/control/supervisor-life-path",
      candidateProducerFreshness: "/dashboard/api/v2/control/candidate-producer-freshness",
      paperReadiness: "/dashboard/api/v2/control/paper-readiness",
      candidateExplanations: "/dashboard/api/v2/control/candidate-explanations",
      eligibleIntentBridge: "/dashboard/api/v2/control/eligible-intent-bridge",
      orderbookPriceReadiness: "/dashboard/api/v2/control/orderbook-price-readiness",
      candidatePricePath: "/dashboard/api/v2/control/candidate-price-path",
      eventMeshProof: "/dashboard/api/v2/control/event-mesh-proof",
      meshEvidenceBundles: "/dashboard/api/v2/control/mesh-evidence-bundles",
      candidateEventCorrelation: "/dashboard/api/v2/control/candidate-event-correlation",
      candidateScopedEvents: "/dashboard/api/v2/control/candidate-scoped-events",
      paperActionability: "/dashboard/api/v2/control/paper-actionability",
      prePaperSafety: "/dashboard/api/v2/control/pre-paper-safety",
      paperCertificationPlan: "/dashboard/api/v2/control/paper-certification-plan",
      fullMonitorRun: "/dashboard/api/v2/control/full-monitor-run",
      runtimeSupervisor: "/dashboard/api/v2/control/runtime-supervisor",
      paperSimulation: "/dashboard/api/v2/control/paper-simulation"
    });
    expect(controlCenterEndpointKeys).toHaveLength(34);
  });

  it("defines the central polling policy", () => {
    expect(refreshPolicyMs.overview).toBe(10000);
    expect(refreshPolicyMs.liveFlow).toBe(5000);
    expect(refreshPolicyMs.organs).toBe(10000);
    expect(refreshPolicyMs.pnlLedger).toBe(30000);
    expect(refreshPolicyMs.truthContract).toBe(false);
    expect(refreshPolicyMs.runtimeReadiness).toBe(3000);
    expect(refreshPolicyMs.supervisorLifePath).toBe(3000);
    expect(refreshPolicyMs.candidateProducerFreshness).toBe(3000);
    expect(refreshPolicyMs.paperReadiness).toBe(3000);
    expect(refreshPolicyMs.candidateExplanations).toBe(10000);
    expect(refreshPolicyMs.eligibleIntentBridge).toBe(10000);
    expect(refreshPolicyMs.orderbookPriceReadiness).toBe(3000);
    expect(refreshPolicyMs.candidatePricePath).toBe(3000);
    expect(refreshPolicyMs.eventMeshProof).toBe(3000);
    expect(refreshPolicyMs.meshEvidenceBundles).toBe(3000);
    expect(refreshPolicyMs.candidateEventCorrelation).toBe(3000);
    expect(refreshPolicyMs.candidateScopedEvents).toBe(3000);
    expect(refreshPolicyMs.paperActionability).toBe(3000);
    expect(refreshPolicyMs.prePaperSafety).toBe(3000);
    expect(refreshPolicyMs.paperCertificationPlan).toBe(30000);
    expect(refreshPolicyMs.fullMonitorRun).toBe(3000);
    expect(refreshPolicyMs.runtimeSupervisor).toBe(3000);
    expect(refreshPolicyMs.paperSimulation).toBe(3000);
  });

  it("uses GET only for read-only requests", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(validEnvelope));
    const result = await fetchControlCenterEnvelope("overview", { fetcher });

    expect(fetcher).toHaveBeenCalledWith("/dashboard/api/v2/control/overview", {
      method: "GET",
      headers: { Accept: "application/json" }
    });
    expect(result.status).toBe("PARTIAL");
  });

  it("does not expose POST PUT PATCH DELETE helpers", () => {
    expect(Object.keys(controlCenterClient)).toEqual(["fetchEnvelope"]);
    expect("post" in controlCenterClient).toBe(false);
    expect("put" in controlCenterClient).toBe(false);
    expect("patch" in controlCenterClient).toBe(false);
    expect("delete" in controlCenterClient).toBe(false);
  });

  it("converts invalid Truth Contract responses into safe ERROR envelopes", async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ status: "GREEN", data: [] }));
    const result = await fetchControlCenterEnvelope("overview", { fetcher });

    expect(result.status).toBe("ERROR");
    expect(result.source).toBe("frontend:zod_validation");
    expect(result.truth_state).toBe("UNKNOWN");
    expect(result.errors.join(" ")).toMatch(/Truth Contract validation failed/);
  });

  it("normalizes non-OK and network failures into ERROR envelopes", async () => {
    const httpResult = await fetchControlCenterEnvelope("logs", {
      fetcher: vi.fn().mockResolvedValue(jsonResponse({ error: "bad" }, { status: 503 }))
    });
    expect(httpResult.status).toBe("ERROR");
    expect(httpResult.source).toBe("frontend:http");

    const networkResult = await fetchControlCenterEnvelope("logs", {
      fetcher: vi.fn().mockRejectedValue(new Error("offline"))
    });
    expect(networkResult.status).toBe("ERROR");
    expect(networkResult.errors.join(" ")).toMatch(/offline/);
  });
});
