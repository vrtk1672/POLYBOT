import type { Preview } from "@storybook/react-vite";

import "@xyflow/react/dist/style.css";
import "../src/styles/globals.css";

const preview: Preview = {
  parameters: {
    actions: { disable: true },
    controls: { disable: true },
    backgrounds: {
      default: "POLYBOT panel",
      values: [{ name: "POLYBOT panel", value: "#07111f" }]
    },
    layout: "fullscreen"
  }
};

export default preview;
