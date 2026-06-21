import { StatusCard } from "./StatusCard";
import type { TruthEnvelope } from "../../lib/truth-contract";

export function OrganHealthRow({ name, envelope }: { name: string; envelope: TruthEnvelope }) {
  return (
    <StatusCard title={name} envelope={envelope}>
      <p className="text-sm text-poly-muted">
        Health is source-backed only when heartbeat or service_health evidence is present.
      </p>
    </StatusCard>
  );
}
