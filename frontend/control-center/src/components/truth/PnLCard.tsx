import type { PnLData, TruthEnvelope } from "../../lib/truth-contract";
import { hasUsableSource } from "../../lib/truth-contract";
import { StatusCard } from "./StatusCard";

export function PnLCard({ envelope }: { envelope: TruthEnvelope<PnLData> }) {
  const canRenderPnl = hasUsableSource(envelope) && envelope.data.fake_pnl !== true && envelope.status === "REAL";
  return (
    <StatusCard title="PnL Ledger" envelope={envelope}>
      {canRenderPnl ? (
        <dl className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <dt className="text-poly-muted">Realized</dt>
            <dd className="text-poly-text">{envelope.data.realized_pnl ?? "UNKNOWN"}</dd>
          </div>
          <div>
            <dt className="text-poly-muted">Unrealized</dt>
            <dd className="text-poly-text">{envelope.data.unrealized_pnl ?? "UNKNOWN"}</dd>
          </div>
          <div>
            <dt className="text-poly-muted">Net</dt>
            <dd className="text-poly-text">{envelope.data.net_pnl ?? "UNKNOWN"}</dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-poly-muted">PnL hidden until ledger or capital source is present.</p>
      )}
    </StatusCard>
  );
}
