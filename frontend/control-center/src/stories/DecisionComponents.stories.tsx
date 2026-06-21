import type { Meta, StoryObj } from "@storybook/react";

import { ActionabilityBadge } from "../components/truth/ActionabilityBadge";
import { BlockerCard } from "../components/truth/BlockerCard";
import { DecisionChain } from "../components/truth/DecisionChain";
import { DecisionStep } from "../components/truth/DecisionStep";
import { EvidenceCard } from "../components/truth/EvidenceCard";
import { decisionStepFixtures, lockedEnvelopeFixture, partialEnvelopeFixture, realEnvelopeFixture, STORYBOOK_NOTICE, StorybookFrame } from "./fixtures/truthFixtures";

const meta = {
  title: "Truth Components/Decision Evidence",
  parameters: { controls: { disable: true } }
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const DecisionEvidenceStates: Story = {
  render: () => (
    <StorybookFrame title={`Decision Evidence Components - ${STORYBOOK_NOTICE}`}>
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <DecisionChain steps={decisionStepFixtures} />
          <DecisionStep label="Single Step Fixture" envelope={decisionStepFixtures[0].envelope} />
        </div>
        <div className="space-y-4">
          <BlockerCard envelope={lockedEnvelopeFixture} />
          <EvidenceCard envelope={partialEnvelopeFixture} title="Risk Evidence Fixture" />
          <div className="rounded-lg border border-poly-line bg-poly-panel p-4">
            <p className="mb-3 text-sm text-poly-muted">{STORYBOOK_NOTICE}</p>
            <ActionabilityBadge envelope={realEnvelopeFixture} />
          </div>
        </div>
      </div>
    </StorybookFrame>
  )
};
