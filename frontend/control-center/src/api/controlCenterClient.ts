import { ZodError } from "zod";

import { TruthEnvelopeSchema, type TruthEnvelope } from "../lib/truth-contract";
import { controlCenterEndpoints, type ControlCenterEndpointKey } from "./controlCenterEndpoints";

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type ControlCenterClientOptions = {
  basePath?: string;
  fetcher?: FetchLike;
};

function errorEnvelope(message: string, source = "frontend:network"): TruthEnvelope {
  return {
    status: "ERROR",
    source,
    last_updated: null,
    stale_after_seconds: null,
    truth_state: "UNKNOWN",
    data: {},
    warnings: [],
    errors: [message]
  };
}

function normalizeError(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function normalizeValidationError(error: unknown) {
  if (error instanceof ZodError) {
    return error.issues.map((issue) => `${issue.path.join(".") || "response"}: ${issue.message}`).join("; ");
  }
  return normalizeError(error, "Response does not match Truth Contract");
}

function buildUrl(path: string, basePath = "") {
  if (!basePath) return path;
  return `${basePath.replace(/\/$/, "")}${path}`;
}

export async function fetchControlCenterEnvelope(
  endpointKey: ControlCenterEndpointKey,
  options: ControlCenterClientOptions = {}
): Promise<TruthEnvelope> {
  const fetcher = options.fetcher ?? globalThis.fetch?.bind(globalThis);
  if (!fetcher) {
    return errorEnvelope("Fetch API is unavailable in this environment.");
  }

  const path = controlCenterEndpoints[endpointKey];
  try {
    const response = await fetcher(buildUrl(path, options.basePath), {
      method: "GET",
      headers: { Accept: "application/json" }
    });

    if (!response.ok) {
      return errorEnvelope(`Read-only GET failed for ${path}: HTTP ${response.status}`, "frontend:http");
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch (error) {
      return errorEnvelope(`Invalid JSON from ${path}: ${normalizeError(error, "JSON parse failed")}`, "frontend:json");
    }

    try {
      return TruthEnvelopeSchema.parse(payload);
    } catch (error) {
      return errorEnvelope(`Truth Contract validation failed for ${path}: ${normalizeValidationError(error)}`, "frontend:zod_validation");
    }
  } catch (error) {
    return errorEnvelope(`Network error for ${path}: ${normalizeError(error, "request failed")}`);
  }
}

export const controlCenterClient = {
  fetchEnvelope: fetchControlCenterEnvelope
};
