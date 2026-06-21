import { FlaskConical } from "lucide-react";

export function DemoOnlyBanner() {
  return (
    <div className="rounded-lg border border-poly-cyan/30 bg-poly-cyan/10 px-4 py-3 text-sm text-poly-text">
      <div className="flex items-center gap-2 font-semibold">
        <FlaskConical aria-hidden="true" size={16} />
        DEMO_ONLY
      </div>
      <p className="mt-1 text-poly-muted">
        This frontend shell uses static placeholders only. It is not connected to runtime data or Stage 5 APIs.
      </p>
    </div>
  );
}
