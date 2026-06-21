import { ShieldAlert } from "lucide-react";

export function TopSystemBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-poly-line bg-poly-bg/95 px-4 py-3 backdrop-blur md:px-6">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className="text-xs font-bold uppercase text-poly-cyan">Control Center V1.5</p>
          <h1 className="text-lg font-semibold text-poly-text">Reality-First + Decision X-Ray</h1>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase">
          <span className="rounded-md border border-poly-cyan/40 bg-poly-cyan/10 px-2.5 py-1 text-poly-cyan">
            READ_ONLY_API_LAYER
          </span>
          <span className="rounded-md border border-poly-missing/40 bg-poly-panelStrong px-2.5 py-1 text-poly-muted">
            VISIBILITY_GET_ACTIONS_POST
          </span>
          <span className="rounded-md border border-poly-locked/40 bg-poly-locked/10 px-2.5 py-1 text-poly-locked">
            No live controls active
          </span>
          <span className="inline-flex items-center gap-1 rounded-md border border-poly-error/40 bg-poly-error/10 px-2.5 py-1 text-poly-error">
            <ShieldAlert aria-hidden="true" size={13} />
            Gated runtime actions only
          </span>
        </div>
      </div>
    </header>
  );
}
