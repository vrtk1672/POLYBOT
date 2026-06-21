import type { DecisionStepData, TruthEnvelope } from "../../lib/truth-contract";
import { DecisionStep } from "./DecisionStep";

export function DecisionChain({ steps }: { steps: Array<{ label: string; envelope: TruthEnvelope<DecisionStepData> }> }) {
  return (
    <div className="grid gap-3">
      {steps.map((step) => (
        <DecisionStep key={step.label} label={step.label} envelope={step.envelope} />
      ))}
    </div>
  );
}
