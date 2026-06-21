import type { ReactNode } from "react";

import { PAGE_SHELLS, type PageId } from "../pages/pageRegistry";
import { Sidebar } from "./Sidebar";
import { TopSystemBar } from "./TopSystemBar";

export function AppShell({
  activePageId,
  onPageChange,
  children
}: {
  activePageId: PageId;
  onPageChange: (pageId: PageId) => void;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-poly-bg text-poly-text">
      <div className="md:flex">
        <Sidebar pages={PAGE_SHELLS} activePageId={activePageId} onSelect={onPageChange} />
        <div className="min-w-0 flex-1">
          <TopSystemBar />
          <main className="mx-auto w-full max-w-7xl px-4 py-5 md:px-6 lg:py-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
