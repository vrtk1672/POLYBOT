import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function PnLLedgerShell() {
  return <PageShell config={PAGE_SHELLS[8]} />;
}
