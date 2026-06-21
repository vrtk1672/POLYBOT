import { FileSearch } from "lucide-react";

import type { TruthEnvelope } from "../../lib/truth-contract";
import { StatusCard } from "./StatusCard";

export function EvidenceCard({ envelope, title = "Evidence" }: { envelope: TruthEnvelope; title?: string }) {
  return (
    <StatusCard title={title} envelope={envelope}>
      <div className="flex items-center gap-2 text-sm text-poly-muted">
        <FileSearch aria-hidden="true" size={16} className="text-poly-partial" />
        Evidence is shown only as source-backed context.
      </div>
    </StatusCard>
  );
}
