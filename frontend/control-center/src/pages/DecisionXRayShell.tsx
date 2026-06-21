import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function DecisionXRayShell() {
  return <PageShell config={PAGE_SHELLS[1]} />;
}
