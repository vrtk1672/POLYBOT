import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function TruthStateShell() {
  return <PageShell config={PAGE_SHELLS[4]} />;
}
