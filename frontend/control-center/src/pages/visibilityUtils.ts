export type UnknownRecord = Record<string, unknown>;

export function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as UnknownRecord) : {};
}

export function asArray(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

export function fieldText(record: UnknownRecord, keys: string[], fallback = "UNKNOWN") {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
  }
  return fallback;
}

export function fieldNumber(record: UnknownRecord, keys: string[]) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

export function latestTimestamp(record: UnknownRecord, keys = ["latest_at", "latest_heartbeat_at", "generated_at", "stored_at", "occurred_at", "updated_at"]) {
  return fieldText(record, keys);
}

export function entriesOf(record: UnknownRecord) {
  return Object.entries(record).filter(([, value]) => typeof value !== "object" || value === null);
}
