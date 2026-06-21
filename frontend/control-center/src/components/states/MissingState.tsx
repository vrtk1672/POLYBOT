import { MinusCircle } from "lucide-react";

export function MissingState({ warnings, source }: { warnings: string[]; source: string | null }) {
  return (
    <div className="mt-3 rounded-md border border-poly-missing/50 bg-poly-missing/10 p-3 text-sm text-poly-muted">
      <div className="flex items-center gap-2 font-semibold text-poly-text">
        <MinusCircle aria-hidden="true" size={16} />
        MISSING
      </div>
      <p className="mt-2">Source: {source ?? "SOURCE_MISSING"}</p>
      <ul className="mt-2 list-disc pl-5">
        {(warnings.length ? warnings : ["Required source or data is missing."]).map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}
