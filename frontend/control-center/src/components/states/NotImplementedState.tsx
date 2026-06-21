import { Wrench } from "lucide-react";

export function NotImplementedState({ warnings }: { warnings: string[] }) {
  return (
    <div className="mt-3 rounded-md border border-poly-subtle bg-poly-subtle/10 p-3 text-sm text-poly-muted">
      <div className="flex items-center gap-2 font-semibold text-poly-text">
        <Wrench aria-hidden="true" size={16} />
        NOT_IMPLEMENTED
      </div>
      <p className="mt-2">This surface is not implemented and is not connected to runtime data.</p>
      <ul className="mt-2 list-disc pl-5">
        {(warnings.length ? warnings : ["No live data is displayed."]).map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}
