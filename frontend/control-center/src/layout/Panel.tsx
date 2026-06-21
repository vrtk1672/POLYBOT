import type { ReactNode } from "react";

import { cn } from "../lib/utils";

export function Panel({
  title,
  eyebrow,
  children,
  className
}: {
  title?: string;
  eyebrow?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-poly-line bg-poly-panel p-4 shadow-truth", className)}>
      {eyebrow ? <p className="text-xs font-semibold uppercase text-poly-cyan">{eyebrow}</p> : null}
      {title ? <h2 className="mt-1 text-base font-semibold text-poly-text">{title}</h2> : null}
      <div className={title || eyebrow ? "mt-3" : undefined}>{children}</div>
    </section>
  );
}
