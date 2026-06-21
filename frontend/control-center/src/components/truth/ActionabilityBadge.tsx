import { TruthBadge } from "./TruthBadge";
import type { TruthEnvelope } from "../../lib/truth-contract";

export function ActionabilityBadge({ envelope }: { envelope: TruthEnvelope }) {
  return <TruthBadge status={envelope.status} className="uppercase" />;
}
