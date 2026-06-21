import { EndpointSourceHint } from "./EndpointSourceHint";

export function PageHeader({
  title,
  purpose,
  endpoint,
  stateLabel,
  onRefresh,
  refreshDisabled,
  refreshLabel = "Refresh read-only data"
}: {
  title: string;
  purpose: string;
  endpoint: string | null;
  stateLabel: string;
  onRefresh?: () => void;
  refreshDisabled?: boolean;
  refreshLabel?: string;
}) {
  return (
    <header className="grid gap-4 border-b border-poly-line pb-5 lg:grid-cols-[1fr_320px]">
      <div>
        <p className="text-xs font-bold uppercase text-poly-cyan">{stateLabel}</p>
        <h1 className="mt-2 text-2xl font-semibold text-poly-text md:text-3xl">{title}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-poly-muted">{purpose}</p>
        {onRefresh ? (
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshDisabled}
            className="mt-4 rounded-md border border-poly-line bg-poly-panel px-3 py-2 text-sm font-semibold text-poly-text transition hover:border-poly-cyan hover:text-poly-cyan disabled:cursor-not-allowed disabled:opacity-60"
          >
            {refreshLabel}
          </button>
        ) : null}
      </div>
      <EndpointSourceHint endpoint={endpoint} />
    </header>
  );
}
