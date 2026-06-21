import { Link2Off } from "lucide-react";

export function EndpointSourceHint({ endpoint }: { endpoint: string | null }) {
  const isActionWrapper = endpoint?.includes("/dashboard/api/v2/control/actions");
  return (
    <div className="rounded-md border border-poly-line bg-poly-bg/40 p-3 text-sm">
      <div className="flex items-center gap-2 font-semibold text-poly-text">
        <Link2Off aria-hidden="true" size={15} />
        {isActionWrapper ? "Control action wrapper" : "Future source endpoint"}
      </div>
      <p className="mt-2 font-mono text-xs text-poly-muted">{endpoint ?? "NO_MUTATING_ENDPOINT / NOT_IMPLEMENTED"}</p>
      <p className="mt-2 text-xs text-poly-muted">
        {isActionWrapper
          ? "Stage 15 posts only to this audited wrapper; visibility pages remain GET-only."
          : "Stage 8 may fetch this endpoint with GET only."}
      </p>
    </div>
  );
}
