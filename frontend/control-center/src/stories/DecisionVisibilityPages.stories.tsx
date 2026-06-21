import type { Meta, StoryObj } from "@storybook/react";

import {
  BlockerCenterVisibility,
  ClosestActionableVisibility,
  DecisionXRayVisibility,
  LifecycleGovernanceVisibility,
  MeshDialoguesVisibility,
  RiskEvidenceMeshVisibility,
  TruthStateVisibility
} from "../pages/decisionIntelligence";
import {
  blockerCenterFixture,
  decisionXrayFixture,
  lifecycleFixture,
  meshDialogueFixture,
  partialEnvelopeFixture,
  riskEvidenceFixture,
  STORYBOOK_NOTICE,
  StorybookFrame,
  truthStateFixture
} from "./fixtures/truthFixtures";

const meta = {
  title: "Visibility Pages/Stage 10 Decision Intelligence",
  parameters: { controls: { disable: true } }
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const DecisionXRay: Story = {
  render: () => (
    <StorybookFrame title={`Decision X-Ray Visibility - ${STORYBOOK_NOTICE}`}>
      <DecisionXRayVisibility envelope={decisionXrayFixture} />
    </StorybookFrame>
  )
};

export const BlockerCenter: Story = {
  render: () => (
    <StorybookFrame title={`Blocker Center Visibility - ${STORYBOOK_NOTICE}`}>
      <BlockerCenterVisibility envelope={blockerCenterFixture} />
    </StorybookFrame>
  )
};

export const ClosestActionable: Story = {
  render: () => (
    <StorybookFrame title={`Closest Actionable Visibility - ${STORYBOOK_NOTICE}`}>
      <ClosestActionableVisibility envelope={partialEnvelopeFixture} />
    </StorybookFrame>
  )
};

export const TruthState: Story = {
  render: () => (
    <StorybookFrame title={`Truth State Visibility - ${STORYBOOK_NOTICE}`}>
      <TruthStateVisibility envelope={truthStateFixture} />
    </StorybookFrame>
  )
};

export const RiskEvidenceMesh: Story = {
  render: () => (
    <StorybookFrame title={`Risk Evidence Mesh Visibility - ${STORYBOOK_NOTICE}`}>
      <RiskEvidenceMeshVisibility envelope={riskEvidenceFixture} />
    </StorybookFrame>
  )
};

export const LifecycleGovernance: Story = {
  render: () => (
    <StorybookFrame title={`Lifecycle Governance Visibility - ${STORYBOOK_NOTICE}`}>
      <LifecycleGovernanceVisibility envelope={lifecycleFixture} />
    </StorybookFrame>
  )
};

export const MeshDialogues: Story = {
  render: () => (
    <StorybookFrame title={`Mesh Dialogues Visibility - ${STORYBOOK_NOTICE}`}>
      <MeshDialoguesVisibility envelope={meshDialogueFixture} />
    </StorybookFrame>
  )
};
