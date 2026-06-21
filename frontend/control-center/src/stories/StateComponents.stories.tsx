import type { Meta, StoryObj } from "@storybook/react";

import { ErrorState } from "../components/states/ErrorState";
import { LockedState } from "../components/states/LockedState";
import { MissingState } from "../components/states/MissingState";
import { NotImplementedState } from "../components/states/NotImplementedState";
import { PartialState } from "../components/states/PartialState";
import { StaleState } from "../components/states/StaleState";
import { STORYBOOK_NOTICE, StorybookFrame } from "./fixtures/truthFixtures";

const meta = {
  title: "Truth Components/State Components",
  parameters: { controls: { disable: true } }
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const AllSafeFallbackStates: Story = {
  render: () => (
    <StorybookFrame title={`Fallback States - ${STORYBOOK_NOTICE}`}>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">
          <ErrorState errors={["Storybook fixture error; no backend request was made."]} />
        </div>
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">
          <MissingState warnings={["Storybook fixture source is absent."]} source={null} />
        </div>
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">
          <StaleState warnings={["Storybook fixture represents last-known data."]} />
        </div>
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">
          <PartialState warnings={["Storybook fixture has partial source coverage."]} />
        </div>
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">
          <LockedState warnings={["Storybook fixture is locked; no permission is implied."]} />
        </div>
        <div className="rounded-lg border border-poly-line bg-poly-panel p-4">
          <NotImplementedState warnings={["Storybook fixture surface is not implemented."]} />
        </div>
      </div>
    </StorybookFrame>
  )
};
