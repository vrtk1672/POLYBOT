import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function CapitalShell() {
  return <PageShell config={PAGE_SHELLS[10]} />;
}
