import { Database, TriangleAlert } from "lucide-react";

import { cn } from "../../lib/utils";

export function SourceLabel({ source, className }: { source: string | null; className?: string }) {
  const hasSource = Boolean(source);
  const Icon = hasSource ? Database : TriangleAlert;
  return (
    <span
      className={cn(
        "inline-flex min-h-7 items-center gap-1.5 rounded-md border px-2 text-xs",
        hasSource ? "border-poly-line text-poly-muted" : "border-poly-error/50 text-poly-error",
        className
      )}
    >
      <Icon aria-hidden="true" size={14} />
      {hasSource ? source : "SOURCE_MISSING"}
    </span>
  );
}
