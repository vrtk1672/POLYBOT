import type { Meta, StoryObj } from "@storybook/react";

import { EventRow } from "../components/truth/EventRow";
import { OrganHealthRow } from "../components/truth/OrganHealthRow";
import { PnLCard } from "../components/truth/PnLCard";
import { PositionCard } from "../components/truth/PositionCard";
import { partialEnvelopeFixture, pnlFixture, positionFixture, realEnvelopeFixture, staleEnvelopeFixture, STORYBOOK_NOTICE, StorybookFrame } from "./fixtures/truthFixtures";

const meta = {
  title: "Truth Components/Operational Rows",
  parameters: { controls: { disable: true } }
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const OrganAndEventRows: Story = {
  render: () => (
    <StorybookFrame title={`Organ, Event, Money, Position Components - ${STORYBOOK_NOTICE}`}>
      <div className="grid gap-4 xl:grid-cols-2">
        <OrganHealthRow name="Market Service Fixture" envelope={staleEnvelopeFixture} />
        <OrganHealthRow name="Event Service Fixture" envelope={partialEnvelopeFixture} />
        <EventRow label="STORYBOOK_DATA_OBSERVED" envelope={realEnvelopeFixture} />
        <EventRow label="STORYBOOK_REFRESH_REQUIRED" envelope={staleEnvelopeFixture} />
        <PnLCard envelope={pnlFixture} />
        <PositionCard envelope={positionFixture} />
      </div>
    </StorybookFrame>
  )
};
