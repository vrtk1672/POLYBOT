import { AlertTriangle, CheckCircle2, CircleSlash, Clock3, Lock, MinusCircle, Wrench } from "lucide-react";

import { cn } from "../../lib/utils";
import { statusCopy, type TruthStatus } from "../../lib/truth-contract";

const statusStyles: Record<TruthStatus, string> = {
  REAL: "border-poly-cyan/50 bg-poly-cyan/10 text-poly-cyan",
  STALE: "border-poly-stale/60 bg-poly-stale/10 text-poly-stale",
  MISSING: "border-poly-missing/60 bg-poly-missing/10 text-poly-muted",
  ERROR: "border-poly-error/60 bg-poly-error/10 text-poly-error",
  LOCKED: "border-poly-locked/60 bg-poly-locked/10 text-poly-locked",
  NOT_IMPLEMENTED: "border-poly-subtle/60 bg-poly-subtle/10 text-poly-muted",
  PARTIAL: "border-poly-partial/60 bg-poly-partial/10 text-poly-partial"
};

const statusIcons = {
  REAL: CheckCircle2,
  STALE: Clock3,
  MISSING: MinusCircle,
  ERROR: AlertTriangle,
  LOCKED: Lock,
  NOT_IMPLEMENTED: Wrench,
  PARTIAL: CircleSlash
};

export function TruthBadge({ status, className }: { status: TruthStatus; className?: string }) {
  const Icon = statusIcons[status];
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs font-semibold",
        statusStyles[status],
        className
      )}
      title={statusCopy[status]}
    >
      <Icon aria-hidden="true" size={14} />
      {status}
    </span>
  );
}
