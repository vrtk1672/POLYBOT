import { describe, expect, it } from "vitest";

import { TruthEnvelopeSchema, TruthStatusSchema } from "./truth-contract";

const validEnvelope = {
  status: "REAL",
  source: "service_health",
  last_updated: "2026-06-07T00:00:00+00:00",
  stale_after_seconds: 300,
  truth_state: "ACTIVE_FRESH",
  data: {},
  warnings: [],
  errors: []
};

describe("Truth Contract schema", () => {
  it("accepts a valid truth envelope", () => {
    expect(TruthEnvelopeSchema.parse(validEnvelope)).toEqual(validEnvelope);
  });

  it("rejects invalid status", () => {
    expect(() => TruthStatusSchema.parse("GREEN")).toThrow();
    expect(() => TruthEnvelopeSchema.parse({ ...validEnvelope, status: "GREEN" })).toThrow();
  });

  it("rejects missing required arrays and data object shape", () => {
    expect(() => TruthEnvelopeSchema.parse({ ...validEnvelope, warnings: "missing" })).toThrow();
    expect(() => TruthEnvelopeSchema.parse({ ...validEnvelope, errors: "bad" })).toThrow();
    expect(() => TruthEnvelopeSchema.parse({ ...validEnvelope, data: [] })).toThrow();
  });
});
