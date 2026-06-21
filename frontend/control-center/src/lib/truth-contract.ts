import { z } from "zod";

export const TruthStatusSchema = z.enum([
  "REAL",
  "STALE",
  "MISSING",
  "ERROR",
  "LOCKED",
  "NOT_IMPLEMENTED",
  "PARTIAL"
]);

export const TruthStateSchema = z.enum([
  "ACTIVE_FRESH",
  "LAST_KNOWN",
  "HISTORICAL_ONLY",
  "REFRESH_REQUIRED",
  "UNKNOWN"
]);

export const FreshnessStateSchema = z.enum(["FRESH", "STALE", "MISSING"]);
export const RuntimeStateSchema = z.enum(["RUNNING", "REGISTERED", "BLOCKED", "STOPPED", "STALE", "UNKNOWN"]);
export const ReadinessStateSchema = z.enum(["READY", "NOT_READY", "PARTIAL", "BLOCKED", "UNKNOWN"]);

export const TruthEnvelopeSchema = z.object({
  status: TruthStatusSchema,
  source: z.string().nullable(),
  last_updated: z.string().nullable(),
  stale_after_seconds: z.number().int().nonnegative().nullable(),
  age_seconds: z.number().nonnegative().nullable().optional(),
  freshness_state: FreshnessStateSchema.optional(),
  runtime_state: RuntimeStateSchema.optional(),
  truth_state: TruthStateSchema,
  readiness_state: ReadinessStateSchema.optional(),
  data: z.record(z.unknown()),
  warnings: z.array(z.string()),
  errors: z.array(z.string())
});

export const DemoTruthEnvelopeSchema = TruthEnvelopeSchema.extend({
  demo_label: z.literal("DEMO_ONLY").optional(),
  runtime_connection: z.literal("NOT_CONNECTED_TO_RUNTIME").optional()
});

export type TruthStatus = z.infer<typeof TruthStatusSchema>;
export type TruthState = z.infer<typeof TruthStateSchema>;
export type FreshnessState = z.infer<typeof FreshnessStateSchema>;
export type RuntimeState = z.infer<typeof RuntimeStateSchema>;
export type ReadinessState = z.infer<typeof ReadinessStateSchema>;
export type TruthEnvelope<TData extends Record<string, unknown> = Record<string, unknown>> =
  Omit<z.infer<typeof TruthEnvelopeSchema>, "data"> & { data: TData };

export type DemoTruthEnvelope<TData extends Record<string, unknown> = Record<string, unknown>> =
  TruthEnvelope<TData> & {
    demo_label: "DEMO_ONLY";
    runtime_connection: "NOT_CONNECTED_TO_RUNTIME";
  };

export type PnLData = {
  realized_pnl?: number | null;
  unrealized_pnl?: number | null;
  net_pnl?: number | null;
  fake_pnl?: boolean;
};

export type PositionData = {
  position_id?: string;
  market?: string;
  side?: string;
  quantity?: number | null;
  fake_positions?: boolean;
};

export type DecisionStepData = {
  label?: string;
  evidence_source?: string | null;
  approved?: boolean;
  reason?: string;
};

export const statusCopy: Record<TruthStatus, string> = {
  REAL: "Real source-backed truth",
  STALE: "Last known truth; refresh required",
  MISSING: "Required source or data is missing",
  ERROR: "Source returned an error",
  LOCKED: "Locked until explicit evidence or permission exists",
  NOT_IMPLEMENTED: "Not implemented",
  PARTIAL: "Partial source coverage"
};

export const truthStateCopy: Record<TruthState, string> = {
  ACTIVE_FRESH: "Active fresh",
  LAST_KNOWN: "Last known",
  HISTORICAL_ONLY: "Historical only",
  REFRESH_REQUIRED: "Refresh required",
  UNKNOWN: "Unknown"
};

export function hasUsableSource(envelope: Pick<TruthEnvelope, "source">) {
  return Boolean(envelope.source && envelope.source.trim().length > 0);
}

export function canShowPositiveTruth(envelope: TruthEnvelope) {
  return envelope.status === "REAL" && envelope.truth_state === "ACTIVE_FRESH" && hasUsableSource(envelope);
}
