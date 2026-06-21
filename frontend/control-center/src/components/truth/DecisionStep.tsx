import { GitBranch } from "lucide-react";

import type { DecisionStepData, TruthEnvelope } from "../../lib/truth-contract";
import { canShowPositiveTruth, hasUsableSource } from "../../lib/truth-contract";
import { cn } from "../../lib/utils";
import { SourceLabel } from "./SourceLabel";
import { TruthBadge } from "./TruthBadge";

export function DecisionStep({ label, envelope }: { label: string; envelope: TruthEnvelope<DecisionStepData> }) {
  const evidencePresent = Boolean(envelope.data.evidence_source) && hasUsableSource(envelope);
  const mayShowApproved = canShowPositiveTruth(envelope) && evidencePresent && envelope.data.approved === true;
  return (
    <div className="rounded-md border border-poly-line bg-poly-bg/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-poly-text">
          <GitBranch aria-hidden="true" size={16} className="text-poly-partial" />
          {label}
        </div>
        <TruthBadge status={envelope.status} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <SourceLabel source={envelope.source} />
        <SourceLabel source={envelope.data.evidence_source ?? null} />
      </div>
      <p
        className={cn(
          "mt-3 text-sm",
          mayShowApproved ? "text-poly-cyan" : "text-poly-muted"
        )}
      >
        {mayShowApproved ? "Evidence-backed approval signal" : "No approval claim without evidence/source."}
      </p>
    </div>
  );
}
