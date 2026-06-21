import { OctagonAlert } from "lucide-react";

import type { TruthEnvelope } from "../../lib/truth-contract";
import { StatusCard } from "./StatusCard";

export function BlockerCard({ envelope }: { envelope: TruthEnvelope }) {
  return (
    <StatusCard title="Blocker" envelope={envelope}>
      <div className="flex items-center gap-2 text-sm text-poly-muted">
        <OctagonAlert aria-hidden="true" size={16} className="text-poly-error" />
        Blockers must cite real risk, no-trade, or missing-evidence sources.
      </div>
    </StatusCard>
  );
}
