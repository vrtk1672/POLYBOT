import type { PositionData, TruthEnvelope } from "../../lib/truth-contract";
import { hasUsableSource } from "../../lib/truth-contract";
import { StatusCard } from "./StatusCard";

export function PositionCard({ envelope }: { envelope: TruthEnvelope<PositionData> }) {
  const canRenderPosition = hasUsableSource(envelope) && envelope.data.fake_positions !== true && envelope.status === "REAL";
  return (
    <StatusCard title="Position" envelope={envelope}>
      {canRenderPosition ? (
        <div className="grid gap-1 text-sm text-poly-muted">
          <span>Position: {envelope.data.position_id ?? "UNKNOWN"}</span>
          <span>Market: {envelope.data.market ?? "UNKNOWN"}</span>
          <span>Side: {envelope.data.side ?? "UNKNOWN"}</span>
        </div>
      ) : (
        <p className="text-sm text-poly-muted">Position truth hidden until canonical position source is present.</p>
      )}
    </StatusCard>
  );
}
