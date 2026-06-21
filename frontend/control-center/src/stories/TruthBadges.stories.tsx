import type { Meta, StoryObj } from "@storybook/react";

import { FreshnessBadge } from "../components/truth/FreshnessBadge";
import { SourceLabel } from "../components/truth/SourceLabel";
import { TruthBadge } from "../components/truth/TruthBadge";
import type { TruthState, TruthStatus } from "../lib/truth-contract";
import { STORYBOOK_NOTICE, STORYBOOK_SOURCE, StorybookFrame } from "./fixtures/truthFixtures";

const meta = {
  title: "Truth Components/Badges",
  parameters: { controls: { disable: true } }
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const statuses: TruthStatus[] = ["REAL", "STALE", "MISSING", "ERROR", "LOCKED", "NOT_IMPLEMENTED", "PARTIAL"];
const truthStates: TruthState[] = ["ACTIVE_FRESH", "LAST_KNOWN", "HISTORICAL_ONLY", "REFRESH_REQUIRED", "UNKNOWN"];

export const TruthStatuses: Story = {
  render: () => (
    <StorybookFrame title={`TruthBadge States - ${STORYBOOK_NOTICE}`}>
      <div className="flex flex-wrap gap-3 rounded-lg border border-poly-line bg-poly-panel p-4">
        {statuses.map((status) => (
          <TruthBadge key={status} status={status} />
        ))}
      </div>
    </StorybookFrame>
  )
};

export const FreshnessStates: Story = {
  render: () => (
    <StorybookFrame title={`FreshnessBadge States - ${STORYBOOK_NOTICE}`}>
      <div className="flex flex-wrap gap-3 rounded-lg border border-poly-line bg-poly-panel p-4">
        {truthStates.map((truthState) => (
          <FreshnessBadge key={truthState} truthState={truthState} />
        ))}
      </div>
    </StorybookFrame>
  )
};

export const SourceLabels: Story = {
  render: () => (
    <StorybookFrame title={`SourceLabel States - ${STORYBOOK_NOTICE}`}>
      <div className="flex flex-wrap gap-3 rounded-lg border border-poly-line bg-poly-panel p-4">
        <SourceLabel source={STORYBOOK_SOURCE} />
        <SourceLabel source={null} />
      </div>
    </StorybookFrame>
  )
};
