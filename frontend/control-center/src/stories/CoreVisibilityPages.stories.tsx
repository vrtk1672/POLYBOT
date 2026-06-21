import type { Meta, StoryObj } from "@storybook/react";

import { LiveFlowVisibility, LogsErrorsVisibility, OrganHealthVisibility, OverviewVisibility } from "../pages/coreVisibility";
import { liveFlowFixture, logsErrorsFixture, organHealthFixture, overviewFixture, STORYBOOK_NOTICE, StorybookFrame } from "./fixtures/truthFixtures";

const meta = {
  title: "Visibility Pages/Stage 9 Core",
  parameters: { controls: { disable: true } }
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Overview: Story = {
  render: () => (
    <StorybookFrame title={`Overview Visibility - ${STORYBOOK_NOTICE}`}>
      <OverviewVisibility envelope={overviewFixture} />
    </StorybookFrame>
  )
};

export const OrganHealth: Story = {
  render: () => (
    <StorybookFrame title={`Organ Health Visibility - ${STORYBOOK_NOTICE}`}>
      <OrganHealthVisibility envelope={organHealthFixture} />
    </StorybookFrame>
  )
};

export const LiveFlow: Story = {
  render: () => (
    <StorybookFrame title={`Live Flow Visibility - ${STORYBOOK_NOTICE}`}>
      <LiveFlowVisibility envelope={liveFlowFixture} />
    </StorybookFrame>
  )
};

export const LogsAndErrors: Story = {
  render: () => (
    <StorybookFrame title={`Logs And Errors Visibility - ${STORYBOOK_NOTICE}`}>
      <LogsErrorsVisibility envelope={logsErrorsFixture} />
    </StorybookFrame>
  )
};
