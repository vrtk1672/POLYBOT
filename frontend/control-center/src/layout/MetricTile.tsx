import type { ReactNode } from "react";

export function MetricTile({ label, value, detail }: { label: string; value: ReactNode; detail: string }) {
  return (
    <div className="min-h-28 rounded-lg border border-poly-line bg-poly-bg/40 p-4">
      <p className="text-xs font-semibold uppercase text-poly-muted">{label}</p>
      <div className="mt-3 text-lg font-semibold text-poly-text">{value}</div>
      <p className="mt-2 text-xs text-poly-muted">{detail}</p>
    </div>
  );
}
