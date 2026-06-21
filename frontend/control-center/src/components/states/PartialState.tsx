import { CircleSlash } from "lucide-react";

export function PartialState({ warnings }: { warnings: string[] }) {
  return (
    <div className="mt-3 rounded-md border border-poly-partial/50 bg-poly-partial/10 p-3 text-sm text-poly-partial">
      <div className="flex items-center gap-2 font-semibold">
        <CircleSlash aria-hidden="true" size={16} />
        PARTIAL
      </div>
      <p className="mt-2">{warnings[0] ?? "Only partial source coverage is available."}</p>
    </div>
  );
}
