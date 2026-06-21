import type { ControlCenterEndpointKey } from "./controlCenterEndpoints";

export const refreshPolicyMs: Record<ControlCenterEndpointKey, number | false> = {
  overview: 10000,
  liveFlow: 5000,
  organs: 10000,
  decisionXray: 10000,
  blockers: 10000,
  closestActionable: 10000,
  truthState: 15000,
  riskEvidence: 15000,
  lifecycleGovernance: 15000,
  meshDialogues: 15000,
  pnlLedger: 30000,
  positions: 15000,
  noTrade: 30000,
  ai: 30000,
  logs: 15000,
  truthContract: false,
  runtimeReadiness: 3000,
  supervisorLifePath: 3000,
  candidateProducerFreshness: 3000,
  paperReadiness: 3000,
  candidateExplanations: 10000,
  eligibleIntentBridge: 10000,
  orderbookPriceReadiness: 3000,
  candidatePricePath: 3000,
  eventMeshProof: 3000,
  meshEvidenceBundles: 3000,
  candidateEventCorrelation: 3000,
  candidateScopedEvents: 3000,
  paperActionability: 3000,
  prePaperSafety: 3000,
  paperCertificationPlan: 30000,
  fullMonitorRun: 3000,
  runtimeSupervisor: 3000,
  paperSimulation: 3000
};

export function getRefreshInterval(endpointKey: ControlCenterEndpointKey) {
  return refreshPolicyMs[endpointKey];
}
