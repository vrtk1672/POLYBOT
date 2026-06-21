import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function BlockerCenterShell() {
  return <PageShell config={PAGE_SHELLS[2]} />;
}
