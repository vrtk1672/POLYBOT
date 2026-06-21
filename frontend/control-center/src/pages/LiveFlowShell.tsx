import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function LiveFlowShell() {
  return <PageShell config={PAGE_SHELLS[7]} />;
}
