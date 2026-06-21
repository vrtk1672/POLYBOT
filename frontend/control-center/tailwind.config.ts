import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        poly: {
          bg: "#05070d",
          panel: "#101827",
          panelStrong: "#162033",
          line: "#2d3f5f",
          text: "#eef5ff",
          muted: "#a9b8d0",
          subtle: "#667896",
          cyan: "#20d6ff",
          stale: "#f2b84b",
          missing: "#8794aa",
          error: "#ff4d6d",
          locked: "#b779ff",
          partial: "#8ab4ff"
        }
      },
      boxShadow: {
        truth: "0 18px 60px rgba(0, 0, 0, 0.28)"
      }
    }
  },
  plugins: []
} satisfies Config;
