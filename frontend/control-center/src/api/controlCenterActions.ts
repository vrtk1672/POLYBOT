import { z } from "zod";

export const controlCenterActionNames = [
  "system-on",
  "system-off",
  "enable-paper-simulation",
  "disable-paper-simulation",
  "start-full-monitor-run",
  "stop-current-run",
  "kill-switch",
  "reset-paper-balance"
] as const;

export type ControlCenterActionName = (typeof controlCenterActionNames)[number];

export const controlCenterActionEndpointPrefix = "/dashboard/api/v2/control/actions";

export const ControlCenterActionStatusSchema = z.enum(["ACCEPTED", "REJECTED", "LOCKED", "NOT_IMPLEMENTED", "ERROR"]);

export const ControlCenterSafetyCheckSchema = z.object({
  name: z.string(),
  status: z.enum(["PASS", "FAIL", "LOCKED", "NOT_IMPLEMENTED"]),
  detail: z.string()
});

export const ControlCenterActionEnvelopeSchema = z.object({
  action: z.string(),
  status: ControlCenterActionStatusSchema,
  actor: z.string(),
  reason: z.string(),
  timestamp: z.string(),
  audit_id: z.string().nullable(),
  state_before: z.record(z.string(), z.unknown()),
  state_after: z.record(z.string(), z.unknown()),
  safety_checks: z.array(ControlCenterSafetyCheckSchema),
  result: z.record(z.string(), z.unknown()),
  warnings: z.array(z.string()),
  errors: z.array(z.string())
});

export type ControlCenterActionStatus = z.infer<typeof ControlCenterActionStatusSchema>;
export type ControlCenterActionEnvelope = z.infer<typeof ControlCenterActionEnvelopeSchema>;

export type ControlCenterActionPayload = {
  actor: string;
  reason: string;
  confirmation?: string;
  duration_minutes?: number;
  interval_seconds?: number;
  max_cycles?: number;
  metadata?: Record<string, unknown>;
};

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type ControlCenterActionClientOptions = {
  basePath?: string;
  fetcher?: FetchLike;
};

function buildUrl(path: string, basePath = "") {
  if (!basePath) return path;
  return `${basePath.replace(/\/$/, "")}${path}`;
}

function errorEnvelope(action: ControlCenterActionName, message: string): ControlCenterActionEnvelope {
  return {
    action,
    status: "ERROR",
    actor: "",
    reason: "",
    timestamp: new Date().toISOString(),
    audit_id: null,
    state_before: {},
    state_after: {},
    safety_checks: [],
    result: {},
    warnings: [],
    errors: [message]
  };
}

function normalizeError(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function controlCenterActionEndpoint(action: ControlCenterActionName) {
  return `${controlCenterActionEndpointPrefix}/${action}`;
}

export async function executeControlCenterAction(
  action: ControlCenterActionName,
  payload: ControlCenterActionPayload,
  options: ControlCenterActionClientOptions = {}
): Promise<ControlCenterActionEnvelope> {
  const fetcher = options.fetcher ?? globalThis.fetch?.bind(globalThis);
  if (!fetcher) {
    return errorEnvelope(action, "Fetch API is unavailable in this environment.");
  }

  const endpoint = controlCenterActionEndpoint(action);
  try {
    const response = await fetcher(buildUrl(endpoint, options.basePath), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    let json: unknown;
    try {
      json = await response.json();
    } catch (error) {
      return errorEnvelope(action, `Invalid JSON from action endpoint: ${normalizeError(error, "JSON parse failed")}`);
    }

    if (!response.ok) {
      return errorEnvelope(action, `Action endpoint returned HTTP ${response.status}`);
    }

    try {
      return ControlCenterActionEnvelopeSchema.parse(json);
    } catch (error) {
      return errorEnvelope(action, `Action response validation failed: ${normalizeError(error, "invalid response")}`);
    }
  } catch (error) {
    return errorEnvelope(action, `Network error for ${endpoint}: ${normalizeError(error, "request failed")}`);
  }
}
