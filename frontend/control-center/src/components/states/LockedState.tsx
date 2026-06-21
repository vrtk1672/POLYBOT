import { Lock } from "lucide-react";

export function LockedState({ warnings }: { warnings: string[] }) {
  return (
    <div className="mt-3 rounded-md border border-poly-locked/50 bg-poly-locked/10 p-3 text-sm text-poly-locked">
      <div className="flex items-center gap-2 font-semibold">
        <Lock aria-hidden="true" size={16} />
        LOCKED
      </div>
      <p className="mt-2">{warnings[0] ?? "This capability is locked until explicit evidence and permission exist."}</p>
    </div>
  );
}
