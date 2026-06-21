import type { Meta, StoryObj } from "@storybook/react";

import { StatusCard } from "../components/truth/StatusCard";
import { allStatusEnvelopes, STORYBOOK_NOTICE, StorybookFrame } from "./fixtures/truthFixtures";

const meta = {
  title: "Truth Components/Status Cards",
  parameters: { controls: { disable: true } }
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const AllTruthContractStatuses: Story = {
  render: () => (
    <StorybookFrame title={`StatusCard Truth Contract States - ${STORYBOOK_NOTICE}`}>
      <div className="grid gap-4 lg:grid-cols-2">
        {allStatusEnvelopes.map((envelope) => (
          <StatusCard key={envelope.status} title={`${envelope.status} Fixture`} envelope={envelope}>
            <p className="text-sm text-poly-muted">{STORYBOOK_NOTICE}</p>
          </StatusCard>
        ))}
      </div>
    </StorybookFrame>
  )
};
