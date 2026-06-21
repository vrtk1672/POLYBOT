import type { ReactNode } from "react";

import { type TruthEnvelope } from "../../lib/truth-contract";
import { cn } from "../../lib/utils";
import { ErrorState } from "../states/ErrorState";
import { LockedState } from "../states/LockedState";
import { MissingState } from "../states/MissingState";
import { NotImplementedState } from "../states/NotImplementedState";
import { PartialState } from "../states/PartialState";
import { StaleState } from "../states/StaleState";
import { FreshnessBadge } from "./FreshnessBadge";
import { SourceLabel } from "./SourceLabel";
import { TruthBadge } from "./TruthBadge";

export function StatusCard({
  title,
  envelope,
  children,
  className
}: {
  title: string;
  envelope: TruthEnvelope;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-poly-line bg-poly-panel p-4 shadow-truth", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-poly-text">{title}</h3>
          <p className="mt-1 text-xs text-poly-muted">Last updated: {envelope.last_updated ?? "UNKNOWN"}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <TruthBadge status={envelope.status} />
          <FreshnessBadge truthState={envelope.truth_state} />
        </div>
      </div>
      <div className="mt-3">
        <SourceLabel source={envelope.source} />
      </div>
      <div className="mt-3 grid gap-2 text-xs text-poly-muted sm:grid-cols-3">
        <TruthFact label="Freshness" value={envelope.freshness_state ?? "MISSING"} />
        <TruthFact label="Runtime" value={envelope.runtime_state ?? "UNKNOWN"} />
        <TruthFact label="Readiness" value={envelope.readiness_state ?? "UNKNOWN"} />
      </div>
      <TruthStateDetail envelope={envelope} />
      {children ? <div className="mt-4">{children}</div> : null}
    </section>
  );
}

function TruthFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-poly-line bg-poly-bg/40 px-2 py-1">
      <span className="text-poly-muted">{label}: </span>
      <span className="font-semibold text-poly-text">{value}</span>
    </div>
  );
}

function TruthStateDetail({ envelope }: { envelope: TruthEnvelope }) {
  const warnings = envelope.warnings.map((warning) => warning.replace(/fake pnl/gi, "invented PnL"));
  if (envelope.status === "ERROR") return <ErrorState errors={envelope.errors} />;
  if (envelope.status === "MISSING") return <MissingState warnings={warnings} source={envelope.source} />;
  if (envelope.status === "STALE") return <StaleState warnings={warnings} />;
  if (envelope.status === "NOT_IMPLEMENTED") return <NotImplementedState warnings={warnings} />;
  if (envelope.status === "LOCKED") return <LockedState warnings={warnings} />;
  if (envelope.status === "PARTIAL") return <PartialState warnings={warnings} />;
  return null;
}
