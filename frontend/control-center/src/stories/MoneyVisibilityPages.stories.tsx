import type { Meta, StoryObj } from "@storybook/react";

import { CapitalVisibility, NoTradeVisibility, PnlLedgerVisibility, PositionsVisibility } from "../pages/moneyVisibility";
import { capitalFixture, noTradeFixture, pnlLedgerFixture, positionsFixture, STORYBOOK_NOTICE, StorybookFrame } from "./fixtures/truthFixtures";

const meta = {
  title: "Visibility Pages/Stage 11 Money Visibility",
  parameters: { controls: { disable: true } }
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const PnlLedger: Story = {
  render: () => (
    <StorybookFrame title={`PnL Ledger Visibility - ${STORYBOOK_NOTICE}`}>
      <PnlLedgerVisibility envelope={pnlLedgerFixture} />
    </StorybookFrame>
  )
};

export const Capital: Story = {
  render: () => (
    <StorybookFrame title={`Capital Visibility - ${STORYBOOK_NOTICE}`}>
      <CapitalVisibility envelope={capitalFixture} />
    </StorybookFrame>
  )
};

export const Positions: Story = {
  render: () => (
    <StorybookFrame title={`Positions Visibility - ${STORYBOOK_NOTICE}`}>
      <PositionsVisibility envelope={positionsFixture} />
    </StorybookFrame>
  )
};

export const NoTrade: Story = {
  render: () => (
    <StorybookFrame title={`No-Trade Visibility - ${STORYBOOK_NOTICE}`}>
      <NoTradeVisibility envelope={noTradeFixture} />
    </StorybookFrame>
  )
};
