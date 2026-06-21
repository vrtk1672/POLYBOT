import { useMemo, useState } from "react";

import { ControlCenterQueryProvider } from "./api/queryClient";
import { AppShell } from "./layout/AppShell";
import {
  AIBrainShell,
  BlockerCenterShell,
  CapitalShell,
  ClosestActionableShell,
  DecisionXRayShell,
  DEFAULT_PAGE_ID,
  LifecycleGovernanceShell,
  LiveFlowShell,
  LogsErrorsShell,
  MeshDialoguesShell,
  NoTradeShell,
  OrganHealthShell,
  OverviewShell,
  PnLLedgerShell,
  PositionsShell,
  RiskEvidenceMeshShell,
  SettingsShell,
  TruthStateShell,
  type PageId
} from "./pages";

const pageComponents: Record<PageId, JSX.Element> = {
  overview: <OverviewShell />,
  "decision-xray": <DecisionXRayShell />,
  "blocker-center": <BlockerCenterShell />,
  "closest-actionable": <ClosestActionableShell />,
  "truth-state": <TruthStateShell />,
  "risk-evidence-mesh": <RiskEvidenceMeshShell />,
  "lifecycle-governance": <LifecycleGovernanceShell />,
  "live-flow": <LiveFlowShell />,
  "pnl-ledger": <PnLLedgerShell />,
  positions: <PositionsShell />,
  capital: <CapitalShell />,
  "organ-health": <OrganHealthShell />,
  "ai-brain": <AIBrainShell />,
  "logs-errors": <LogsErrorsShell />,
  settings: <SettingsShell />,
  "mesh-dialogues": <MeshDialoguesShell />,
  "no-trade": <NoTradeShell />
};

export default function App() {
  const [activePageId, setActivePageId] = useState<PageId>(DEFAULT_PAGE_ID);
  const activePage = useMemo(() => pageComponents[activePageId], [activePageId]);

  return (
    <ControlCenterQueryProvider>
      <AppShell activePageId={activePageId} onPageChange={setActivePageId}>
        {activePage}
      </AppShell>
    </ControlCenterQueryProvider>
  );
}
