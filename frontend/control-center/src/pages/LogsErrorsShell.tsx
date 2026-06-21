import { PageShell } from "./PageShell";
import { PAGE_SHELLS } from "./pageRegistry";

export function LogsErrorsShell() {
  return <PageShell config={PAGE_SHELLS[13]} />;
}
