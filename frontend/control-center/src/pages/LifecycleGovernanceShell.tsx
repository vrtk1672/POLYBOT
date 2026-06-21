import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function LifecycleGovernanceShell() {
  return <PageShell config={PAGE_SHELLS[6]} />;
}
