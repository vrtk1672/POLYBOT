import { Cable } from "lucide-react";

export function NotConnectedBanner() {
  return (
    <div className="rounded-lg border border-poly-missing/40 bg-poly-panelStrong px-4 py-3 text-sm text-poly-text">
      <div className="flex items-center gap-2 font-semibold">
        <Cable aria-hidden="true" size={16} />
        NOT_CONNECTED_TO_RUNTIME
      </div>
      <p className="mt-1 text-poly-muted">
        No API calls, subscriptions, runtime workers, scheduler actions, or control actions are active in Stage 7.
      </p>
    </div>
  );
}
