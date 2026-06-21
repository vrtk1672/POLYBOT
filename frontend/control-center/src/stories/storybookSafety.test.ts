import { describe, expect, it } from "vitest";

declare global {
  interface ImportMeta {
    glob(pattern: string, options: { query: string; import: string; eager: true }): Record<string, string>;
  }
}

const storyModules = import.meta.glob("./**/*.stories.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const fixtureModules = import.meta.glob("./fixtures/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const storybookModules = import.meta.glob("../../.storybook/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const packageModules = import.meta.glob("../../package.json", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

const storyFiles = Object.keys(storyModules);
const storyContent = Object.values(storyModules).join("\n");
const fixtureContent = Object.values(fixtureModules).join("\n");
const storybookContent = Object.values(storybookModules).join("\n");
const packageJson = Object.values(packageModules).join("\n");

describe("Storybook safety coverage", () => {
  it("has local Storybook config and stories", () => {
    expect(Object.keys(storybookModules)).toEqual(expect.arrayContaining([expect.stringContaining("main.ts"), expect.stringContaining("preview.ts")]));
    expect(storyFiles).toEqual(
      expect.arrayContaining([
        expect.stringContaining("TruthBadges.stories.tsx"),
        expect.stringContaining("StateComponents.stories.tsx"),
        expect.stringContaining("StatusCards.stories.tsx"),
        expect.stringContaining("DecisionComponents.stories.tsx"),
        expect.stringContaining("OperationalRows.stories.tsx"),
        expect.stringContaining("CoreVisibilityPages.stories.tsx"),
        expect.stringContaining("DecisionVisibilityPages.stories.tsx"),
        expect.stringContaining("MoneyVisibilityPages.stories.tsx"),
        expect.stringContaining("DecisionGraph.stories.tsx")
      ])
    );
  });

  it("marks fixtures as Storybook-only and runtime-disconnected", () => {
    expect(fixtureContent).toContain("STORYBOOK_ONLY");
    expect(fixtureContent).toContain("NOT_CONNECTED_TO_RUNTIME");
    expect(fixtureContent).toContain("NOT_REAL_DATA");
    expect(fixtureContent).toContain("storybook:fixture");
    expect(storyContent).toContain("STORYBOOK_NOTICE");
  });

  it("covers every Truth Contract status and truth_state", () => {
    for (const status of ["REAL", "STALE", "MISSING", "ERROR", "LOCKED", "NOT_IMPLEMENTED", "PARTIAL"]) {
      expect(storyContent).toContain(status);
    }

    for (const truthState of ["ACTIVE_FRESH", "LAST_KNOWN", "HISTORICAL_ONLY", "REFRESH_REQUIRED", "UNKNOWN"]) {
      expect(storyContent).toContain(truthState);
    }
  });

  it("keeps Storybook disconnected from APIs and query hooks", () => {
    const forbiddenApiPatterns = [
      /from\s+["'].*\/api\//,
      /useControlCenterQueries/,
      /controlCenterClient/,
      /fetchControlCenterEnvelope/,
      /fetch\s*\(/
    ];

    for (const pattern of forbiddenApiPatterns) {
      expect(storyContent).not.toMatch(pattern);
      expect(storybookContent).not.toMatch(pattern);
    }
  });

  it("does not add unsafe operator claims or paid cloud Storybook packages", () => {
    const forbiddenClaims = [
      /SYSTEM ON/i,
      /SYSTEM OFF/i,
      /START RUN/i,
      /STOP RUN/i,
      /KILL SWITCH/i,
      /RESET BALANCE/i,
      /approved trade/i,
      /system online/i,
      /system healthy/i,
      /green status/i,
      /live money/i,
      /live position/i
    ];

    for (const pattern of forbiddenClaims) {
      expect(storyContent).not.toMatch(pattern);
    }

    expect(packageJson).not.toMatch(/chromatic|storybook-cloud|licenseKey|license-key/i);
  });
});
