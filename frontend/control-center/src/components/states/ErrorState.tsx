import { AlertTriangle } from "lucide-react";

export function ErrorState({ errors }: { errors: string[] }) {
  return (
    <div className="mt-3 rounded-md border border-poly-error/50 bg-poly-error/10 p-3 text-sm text-poly-error">
      <div className="flex items-center gap-2 font-semibold">
        <AlertTriangle aria-hidden="true" size={16} />
        ERROR
      </div>
      <ul className="mt-2 list-disc pl-5">
        {(errors.length ? errors : ["Unknown error"]).map((error) => (
          <li key={error}>{error}</li>
        ))}
      </ul>
    </div>
  );
}
