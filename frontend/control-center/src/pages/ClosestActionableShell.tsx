import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function ClosestActionableShell() {
  return <PageShell config={PAGE_SHELLS[3]} />;
}
