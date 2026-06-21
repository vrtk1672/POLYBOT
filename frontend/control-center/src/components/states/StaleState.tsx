import { Clock3 } from "lucide-react";

export function StaleState({ warnings }: { warnings: string[] }) {
  return (
    <div className="mt-3 rounded-md border border-poly-stale/50 bg-poly-stale/10 p-3 text-sm text-poly-stale">
      <div className="flex items-center gap-2 font-semibold">
        <Clock3 aria-hidden="true" size={16} />
        STALE
      </div>
      <p className="mt-2">{warnings[0] ?? "Last known data needs refresh before trust."}</p>
    </div>
  );
}
