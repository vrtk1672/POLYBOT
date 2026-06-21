import { StatusCard } from "../components/truth";
import { useOptionalControlCenterQuery } from "../api/useControlCenterQueries";
import type { TruthEnvelope } from "../lib/truth-contract";
import { PageHeader } from "../layout/PageHeader";
import { Panel } from "../layout/Panel";
import { GenericSafePreview, LiveFlowVisibility, LogsErrorsVisibility, OrganHealthVisibility, OverviewVisibility } from "./coreVisibility";
import {
  BlockerCenterVisibility,
  ClosestActionableVisibility,
  DecisionXRayVisibility,
  LifecycleGovernanceVisibility,
  MeshDialoguesVisibility,
  RiskEvidenceMeshVisibility,
  TruthStateVisibility
} from "./decisionIntelligence";
import { CapitalVisibility, NoTradeVisibility, PnlLedgerVisibility, PositionsVisibility } from "./moneyVisibility";
import type { PageShellConfig } from "./pageRegistry";

function makeEnvelope(config: PageShellConfig): TruthEnvelope {
  return {
    status: config.status,
    source: config.status === "MISSING" ? null : config.endpoint,
    last_updated: null,
    stale_after_seconds: null,
    truth_state: config.status === "PARTIAL" ? "REFRESH_REQUIRED" : "UNKNOWN",
    data: {},
    warnings: config.notes,
    errors: []
  };
}

function loadingEnvelope(config: PageShellConfig): TruthEnvelope {
  return {
    status: "PARTIAL",
    source: config.endpoint,
    last_updated: null,
    stale_after_seconds: null,
    truth_state: "REFRESH_REQUIRED",
    data: {},
    warnings: ["Loading read-only Truth Contract envelope."],
    errors: []
  };
}

function queryErrorEnvelope(error: Error): TruthEnvelope {
  return {
    status: "ERROR",
    source: "frontend:tanstack_query",
    last_updated: null,
    stale_after_seconds: null,
    truth_state: "UNKNOWN",
    data: {},
    warnings: [],
    errors: [error.message]
  };
}

export function PageShell({ config }: { config: PageShellConfig }) {
  const query = useOptionalControlCenterQuery(config.endpointKey);
  const envelope = query.data ?? (query.error ? queryErrorEnvelope(query.error) : config.endpointKey ? loadingEnvelope(config) : makeEnvelope(config));
  const stateLabel = query.isLoading && config.endpointKey ? "PARTIAL" : envelope.status;

  return (
    <div className="space-y-5" data-testid={`page-${config.id}`}>
      <PageHeader
        title={config.title}
        purpose={config.purpose}
        endpoint={config.endpoint}
        stateLabel={stateLabel}
        onRefresh={config.endpointKey ? () => void query.refetch() : undefined}
        refreshDisabled={query.isFetching}
        refreshLabel="Refresh read-only data"
      />
      <div className="grid gap-4 lg:grid-cols-[1.3fr_0.7fr]">
        <div className="space-y-4">
          <StatusCard title={`${config.title} read-only truth`} envelope={envelope}>
            <div className="space-y-3 text-sm leading-6 text-poly-muted">
              <p>{config.summary}</p>
              <p>Query status: {query.isFetching ? "FETCHING_READ_ONLY" : config.endpointKey ? "READ_ONLY_IDLE" : "NO_ENDPOINT"}</p>
            </div>
          </StatusCard>
          <PageSpecificPreview config={config} envelope={envelope} />
        </div>
        <Panel title="Stage 8 Safety Boundary" eyebrow="GET only">
          <div className="space-y-3 text-sm text-poly-muted">
            <p>READ_ONLY_API_LAYER / VISIBILITY_GET_ONLY</p>
            <p>This page can only call its Stage 5 read-only Control Center endpoint.</p>
            <p>No runtime action, order creation, fill creation, or position creation is exposed.</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function PageSpecificPreview({ config, envelope }: { config: PageShellConfig; envelope: TruthEnvelope }) {
  if (config.id === "overview") {
    return <OverviewVisibility envelope={envelope} />;
  }

  if (config.id === "decision-xray") {
    return <DecisionXRayVisibility envelope={envelope} />;
  }

  if (config.id === "blocker-center") {
    return <BlockerCenterVisibility envelope={envelope} />;
  }

  if (config.id === "closest-actionable") {
    return <ClosestActionableVisibility envelope={envelope} />;
  }

  if (config.id === "truth-state") {
    return <TruthStateVisibility envelope={envelope} />;
  }

  if (config.id === "risk-evidence-mesh") {
    return <RiskEvidenceMeshVisibility envelope={envelope} />;
  }

  if (config.id === "lifecycle-governance") {
    return <LifecycleGovernanceVisibility envelope={envelope} />;
  }

  if (config.id === "mesh-dialogues") {
    return <MeshDialoguesVisibility envelope={envelope} />;
  }

  if (config.id === "live-flow") {
    return <LiveFlowVisibility envelope={envelope} />;
  }

  if (config.id === "logs-errors") {
    return <LogsErrorsVisibility envelope={envelope} />;
  }

  if (config.id === "pnl-ledger") {
    return <PnlLedgerVisibility envelope={envelope} />;
  }

  if (config.id === "positions") {
    return <PositionsVisibility envelope={envelope} />;
  }

  if (config.id === "capital") {
    return <CapitalVisibility envelope={envelope} />;
  }

  if (config.id === "no-trade") {
    return <NoTradeVisibility envelope={envelope} />;
  }

  if (config.id === "organ-health") {
    return <OrganHealthVisibility envelope={envelope} />;
  }

  return <GenericSafePreview summary={config.summary} envelope={envelope} />;
}
