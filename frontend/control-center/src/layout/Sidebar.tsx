import { Activity, Brain, CircleSlash, FileWarning, Gauge, Layers3, Lock, MessageSquareText, Radio, Scale, ScrollText, Shield, Target, WalletCards, Waypoints, XCircle } from "lucide-react";

import { cn } from "../lib/utils";
import type { PageId, PageShellConfig } from "../pages/pageRegistry";

const PRIMARY_PAGES: PageId[] = ["overview", "decision-xray", "pnl-ledger", "live-flow", "settings"];
const SECONDARY_PAGES: PageId[] = [
  "organ-health",
  "truth-state",
  "risk-evidence-mesh",
  "lifecycle-governance",
  "mesh-dialogues",
  "ai-brain",
  "logs-errors",
  "positions",
  "blocker-center",
  "closest-actionable",
  "capital",
  "no-trade"
];

const navIcons: Record<PageId, typeof Gauge> = {
  overview: Gauge,
  "decision-xray": Waypoints,
  "blocker-center": XCircle,
  "closest-actionable": Target,
  "truth-state": CircleSlash,
  "risk-evidence-mesh": Shield,
  "lifecycle-governance": Layers3,
  "live-flow": Radio,
  "pnl-ledger": ScrollText,
  positions: Activity,
  capital: WalletCards,
  "organ-health": Scale,
  "ai-brain": Brain,
  "logs-errors": FileWarning,
  settings: Lock,
  "mesh-dialogues": MessageSquareText,
  "no-trade": CircleSlash
};

export function Sidebar({
  pages,
  activePageId,
  onSelect
}: {
  pages: PageShellConfig[];
  activePageId: PageId;
  onSelect: (pageId: PageId) => void;
}) {
  const pageById = Object.fromEntries(pages.map((page) => [page.id, page])) as Record<PageId, PageShellConfig>;
  const primaryPages = PRIMARY_PAGES.map((pageId) => pageById[pageId]).filter(Boolean);
  const secondaryPages = SECONDARY_PAGES.map((pageId) => pageById[pageId]).filter(Boolean);

  function renderPageButton(page: PageShellConfig) {
    const Icon = navIcons[page.id];
    const active = page.id === activePageId;
    return (
      <button
        key={page.id}
        type="button"
        aria-current={active ? "page" : undefined}
        onClick={() => onSelect(page.id)}
        className={cn(
          "flex min-w-max items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition md:w-full",
          active
            ? "border-poly-cyan/60 bg-poly-cyan/10 text-poly-text"
            : "border-transparent text-poly-muted hover:border-poly-line hover:bg-poly-panel hover:text-poly-text"
        )}
      >
        <Icon aria-hidden="true" size={16} />
        <span>{page.label}</span>
      </button>
    );
  }

  return (
    <aside className="border-b border-poly-line bg-poly-panelStrong/70 md:min-h-screen md:w-72 md:border-b-0 md:border-r">
      <div className="border-b border-poly-line px-4 py-5">
        <p className="text-xs font-bold uppercase text-poly-cyan">POLYBOT</p>
        <p className="mt-1 text-sm font-semibold text-poly-text">Command Cockpit</p>
        <p className="mt-2 text-xs leading-5 text-poly-muted">Upside open. Downside defined. Gated actions only.</p>
      </div>
      <nav aria-label="Control Center navigation" className="flex gap-2 overflow-x-auto p-3 md:block md:space-y-4 md:overflow-visible">
        <div className="flex gap-2 md:block md:space-y-1">
          <p className="hidden px-3 pb-1 text-[11px] font-semibold uppercase text-poly-subtle md:block">Primary</p>
          {primaryPages.map(renderPageButton)}
        </div>
        <div className="flex gap-2 md:block md:space-y-1">
          <p className="hidden px-3 pb-1 text-[11px] font-semibold uppercase text-poly-subtle md:block">Advanced</p>
          {secondaryPages.map(renderPageButton)}
        </div>
      </nav>
    </aside>
  );
}
