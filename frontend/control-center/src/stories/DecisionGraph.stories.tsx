import type { Meta, StoryObj } from "@storybook/react";

import { DecisionGraph } from "../pages/DecisionGraph";
import { decisionXrayFixture, lifecycleFixture, meshDialogueFixture, riskEvidenceFixture, STORYBOOK_NOTICE, StorybookFrame } from "./fixtures/truthFixtures";

const meta = {
  title: "Visibility Pages/Stage 12 React Flow",
  parameters: { controls: { disable: true } }
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const DecisionXRayGraph: Story = {
  render: () => (
    <StorybookFrame title={`Decision Graph - ${STORYBOOK_NOTICE}`}>
      <DecisionGraph kind="decision-xray" envelope={decisionXrayFixture} />
    </StorybookFrame>
  )
};

export const ConflictMapGraph: Story = {
  render: () => (
    <StorybookFrame title={`Conflict Map - ${STORYBOOK_NOTICE}`}>
      <DecisionGraph kind="conflict-map" envelope={riskEvidenceFixture} />
    </StorybookFrame>
  )
};

export const CandidateLifecycleGraph: Story = {
  render: () => (
    <StorybookFrame title={`Candidate Lifecycle - ${STORYBOOK_NOTICE}`}>
      <DecisionGraph kind="candidate-lifecycle" envelope={lifecycleFixture} />
    </StorybookFrame>
  )
};

export const BrainFlowGraphEmpty: Story = {
  render: () => (
    <StorybookFrame title={`Brain Flow Empty State - ${STORYBOOK_NOTICE}`}>
      <DecisionGraph kind="brain-flow" envelope={meshDialogueFixture} />
    </StorybookFrame>
  )
};
