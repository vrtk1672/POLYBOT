import { Radio } from "lucide-react";

import type { TruthEnvelope } from "../../lib/truth-contract";
import { SourceLabel } from "./SourceLabel";
import { TruthBadge } from "./TruthBadge";

export function EventRow({ envelope, label }: { envelope: TruthEnvelope; label: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-poly-line bg-poly-bg/40 p-3">
      <div className="flex items-center gap-2 text-sm text-poly-text">
        <Radio aria-hidden="true" size={16} className="text-poly-cyan" />
        {label}
      </div>
      <div className="flex flex-wrap gap-2">
        <SourceLabel source={envelope.source} />
        <TruthBadge status={envelope.status} />
      </div>
    </div>
  );
}
