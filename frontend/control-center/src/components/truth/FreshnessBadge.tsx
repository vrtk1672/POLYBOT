import { cn } from "../../lib/utils";
import { truthStateCopy, type TruthState } from "../../lib/truth-contract";

const stateStyles: Record<TruthState, string> = {
  ACTIVE_FRESH: "border-poly-cyan/50 text-poly-cyan",
  LAST_KNOWN: "border-poly-stale/50 text-poly-stale",
  HISTORICAL_ONLY: "border-poly-subtle/60 text-poly-muted",
  REFRESH_REQUIRED: "border-poly-error/50 text-poly-error",
  UNKNOWN: "border-poly-missing/50 text-poly-muted"
};

export function FreshnessBadge({ truthState, className }: { truthState: TruthState; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center rounded-md border bg-poly-bg/40 px-2 text-xs font-semibold",
        stateStyles[truthState],
        className
      )}
      title={truthStateCopy[truthState]}
    >
      {truthState}
    </span>
  );
}
