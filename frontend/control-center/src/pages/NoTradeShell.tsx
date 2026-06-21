import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function NoTradeShell() {
  return <PageShell config={PAGE_SHELLS[16]} />;
}
