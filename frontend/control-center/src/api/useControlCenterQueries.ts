import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import type { TruthEnvelope } from "../lib/truth-contract";
import type { ControlCenterEndpointKey } from "./controlCenterEndpoints";
import { fetchControlCenterEnvelope } from "./controlCenterClient";
import { getRefreshInterval } from "./refreshPolicy";

export type ControlCenterQueryResult = UseQueryResult<TruthEnvelope, Error>;

function useControlCenterQuery(endpointKey: ControlCenterEndpointKey): ControlCenterQueryResult {
  return useQuery({
    queryKey: ["control-center", endpointKey],
    queryFn: () => fetchControlCenterEnvelope(endpointKey),
    refetchInterval: getRefreshInterval(endpointKey)
  });
}

export function useOptionalControlCenterQuery(endpointKey: ControlCenterEndpointKey | null): ControlCenterQueryResult {
  return useQuery({
    queryKey: ["control-center", endpointKey ?? "disabled"],
    queryFn: () =>
      endpointKey
        ? fetchControlCenterEnvelope(endpointKey)
        : Promise.resolve({
            status: "LOCKED",
            source: null,
            last_updated: null,
            stale_after_seconds: null,
            truth_state: "UNKNOWN",
            data: {},
            warnings: ["No read-only endpoint is configured for this page."],
            errors: []
          } satisfies TruthEnvelope),
    enabled: Boolean(endpointKey),
    refetchInterval: endpointKey ? getRefreshInterval(endpointKey) : false
  });
}

export function useOverviewQuery() {
  return useControlCenterQuery("overview");
}

export function useOrgansQuery() {
  return useControlCenterQuery("organs");
}

export function useLiveFlowQuery() {
  return useControlCenterQuery("liveFlow");
}

export function useDecisionXrayQuery() {
  return useControlCenterQuery("decisionXray");
}

export function useBlockersQuery() {
  return useControlCenterQuery("blockers");
}

export function useClosestActionableQuery() {
  return useControlCenterQuery("closestActionable");
}

export function useTruthStateQuery() {
  return useControlCenterQuery("truthState");
}

export function useRiskEvidenceQuery() {
  return useControlCenterQuery("riskEvidence");
}

export function useLifecycleGovernanceQuery() {
  return useControlCenterQuery("lifecycleGovernance");
}

export function useMeshDialoguesQuery() {
  return useControlCenterQuery("meshDialogues");
}

export function usePnlLedgerQuery() {
  return useControlCenterQuery("pnlLedger");
}

export function usePositionsQuery() {
  return useControlCenterQuery("positions");
}

export function useNoTradeQuery() {
  return useControlCenterQuery("noTrade");
}

export function useAiQuery() {
  return useControlCenterQuery("ai");
}

export function useLogsQuery() {
  return useControlCenterQuery("logs");
}

export function useTruthContractQuery() {
  return useControlCenterQuery("truthContract");
}

export function useRuntimeReadinessQuery() {
  return useControlCenterQuery("runtimeReadiness");
}

export function useSupervisorLifePathQuery() {
  return useControlCenterQuery("supervisorLifePath");
}

export function useCandidateProducerFreshnessQuery() {
  return useControlCenterQuery("candidateProducerFreshness");
}

export function usePaperReadinessQuery() {
  return useControlCenterQuery("paperReadiness");
}

export function useCandidateExplanationsQuery() {
  return useControlCenterQuery("candidateExplanations");
}

export function useEligibleIntentBridgeQuery() {
  return useControlCenterQuery("eligibleIntentBridge");
}

export function useOrderbookPriceReadinessQuery() {
  return useControlCenterQuery("orderbookPriceReadiness");
}

export function useCandidatePricePathQuery() {
  return useControlCenterQuery("candidatePricePath");
}

export function useEventMeshProofQuery() {
  return useControlCenterQuery("eventMeshProof");
}

export function useMeshEvidenceBundlesQuery() {
  return useControlCenterQuery("meshEvidenceBundles");
}

export function useCandidateEventCorrelationQuery() {
  return useControlCenterQuery("candidateEventCorrelation");
}

export function useCandidateScopedEventsQuery() {
  return useControlCenterQuery("candidateScopedEvents");
}

export function usePaperActionabilityQuery() {
  return useControlCenterQuery("paperActionability");
}

export function usePrePaperSafetyQuery() {
  return useControlCenterQuery("prePaperSafety");
}

export function usePaperCertificationPlanQuery() {
  return useControlCenterQuery("paperCertificationPlan");
}

export function useFullMonitorRunQuery() {
  return useControlCenterQuery("fullMonitorRun");
}

export function useRuntimeSupervisorQuery() {
  return useControlCenterQuery("runtimeSupervisor");
}

export function usePaperSimulationQuery() {
  return useControlCenterQuery("paperSimulation");
}

export const controlCenterQueryHooks = {
  overview: useOverviewQuery,
  organs: useOrgansQuery,
  liveFlow: useLiveFlowQuery,
  decisionXray: useDecisionXrayQuery,
  blockers: useBlockersQuery,
  closestActionable: useClosestActionableQuery,
  truthState: useTruthStateQuery,
  riskEvidence: useRiskEvidenceQuery,
  lifecycleGovernance: useLifecycleGovernanceQuery,
  meshDialogues: useMeshDialoguesQuery,
  pnlLedger: usePnlLedgerQuery,
  positions: usePositionsQuery,
  noTrade: useNoTradeQuery,
  ai: useAiQuery,
  logs: useLogsQuery,
  truthContract: useTruthContractQuery,
  runtimeReadiness: useRuntimeReadinessQuery,
  supervisorLifePath: useSupervisorLifePathQuery,
  candidateProducerFreshness: useCandidateProducerFreshnessQuery,
  paperReadiness: usePaperReadinessQuery,
  candidateExplanations: useCandidateExplanationsQuery,
  eligibleIntentBridge: useEligibleIntentBridgeQuery,
  orderbookPriceReadiness: useOrderbookPriceReadinessQuery,
  candidatePricePath: useCandidatePricePathQuery,
  eventMeshProof: useEventMeshProofQuery,
  meshEvidenceBundles: useMeshEvidenceBundlesQuery,
  candidateEventCorrelation: useCandidateEventCorrelationQuery,
  candidateScopedEvents: useCandidateScopedEventsQuery,
  paperActionability: usePaperActionabilityQuery,
  prePaperSafety: usePrePaperSafetyQuery,
  paperCertificationPlan: usePaperCertificationPlanQuery,
  fullMonitorRun: useFullMonitorRunQuery,
  runtimeSupervisor: useRuntimeSupervisorQuery,
  paperSimulation: usePaperSimulationQuery
} satisfies Record<ControlCenterEndpointKey, () => ControlCenterQueryResult>;
