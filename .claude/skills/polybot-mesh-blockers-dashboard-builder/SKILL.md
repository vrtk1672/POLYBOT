---
name: polybot-mesh-blockers-dashboard-builder
description: Build read-only dashboard truth and API endpoints exposing Mesh Hardening blockers. Use during the Mesh Blockers Dashboard phase. Shows real blocker status — no mock data, no trading control, no decorative panels.
---

# POLYBOT Mesh Blockers Dashboard Builder

## Purpose

Help Claude Code expose Mesh Hardening blockers in dashboard and API truth. The goal is a single clear view of what is blocking the neural mesh from operating at full quality: link coverage gaps, signal quality failures, lineage gaps, and producer health issues.

This skill is about **visibility** — making the current blocker state honest, real, and readable. It does not fix blockers. It does not control trading. It does not show fake GREEN to make the dashboard look clean.

---

## When to Use

- During the Mesh Blockers Dashboard phase of Mesh Hardening.
- When you need a dashboard panel or API endpoint that summarizes the current mesh health and blocker state.
- When existing dashboard data is missing mesh-specific status fields.
- When the mesh health is YELLOW and you need a clear read-only surface to show the gap.

---

## Scope

Allowed to inspect or create:

- `app/api/` or `app/routers/` — read-only dashboard/API endpoints
- `app/dashboard/` — dashboard panel wiring (read-only truth fields only)
- `app/validators/` — mesh health aggregators
- `app/signals/` — signal quality/coverage reader logic
- `app/db/models/` — read-only DB queries for mesh state
- `tests/` — dashboard truth tests
- `scripts/` — read-only mesh status scripts
- `docs/` — dashboard spec and gap reports

---

## Out of Scope

The following must **never** be touched by this skill, regardless of context:

- Risk Governor core
- Execution Cortex
- Exit Cortex
- Capital Allocator
- State Governor core
- Order creation logic
- Fill creation logic
- Position creation logic
- Paper / Shadow Live / Live activation
- Production DB migrations
- Secrets or `.env` values
- Any trading control path
- Any code that fabricates dashboard data (no mock data pretending to be live)
- Any panel that shows GREEN without real backing data

---

## Safety Rules

- Dashboard panels must show real truth. No mock data pretending to be live state.
- Every panel must include stale and error states (what to show when data is missing or old).
- Prefer DB/runtime truth over decorative UI. If a field cannot be verified from real data, show it as unknown — not as GREEN.
- Blocker severity must be honest: if a blocker is YELLOW or RED, show it as YELLOW or RED.
- Do not add any trading controls, trade buttons, or mode-switch controls.
- Do not bypass State Governor or Risk Gate.
- If a hard boundary is reached, report RED and stop.
- Secrets must never be printed or logged.

---

## Required Investigation Before Building

Before writing any code, Claude must:

1. Read the existing dashboard implementation in `app/api/` or `app/dashboard/` to understand current panel structure.
2. Read `docs/V2_18_DASHBOARD_V2.md` for the dashboard architecture.
3. Inspect current mesh health fields already exposed in the API.
4. Read `docs/NEURAL_MESH_SIGNAL_BINDING_RUNTIME_WIRING_REPORT.md` for the current binding/signal state.
5. Identify which blockers already have data sources (link coverage, signal quality, lineage, producer health).
6. Confirm what fields are real DB queries vs fabricated defaults before touching them.

---

## Required Implementation Standards

### Dashboard Panels Required

The following mesh blocker status panels must be present:

1. **Signal Quality Status** — percentage of signals passing quality gates; count of invalid/warning signals; last updated timestamp
2. **Link Coverage Status** — percentage of signals with valid market links; unlinked count by reason; last updated timestamp
3. **Lineage Coverage Status** — percentage of signals with full provenance; unbound count by reason; last updated timestamp
4. **Producer Health Status** — count of active/stale/failing producers; last seen timestamps; last updated timestamp
5. **Dry-Run Provenance Status** — confirms dry-run signals are marked and separated from runtime signals

### Blocker Severity

Each blocker must carry a severity field:

- `GREEN` — metric is within acceptable range, no action needed
- `YELLOW` — metric is degraded but system can operate; human review recommended
- `RED` — metric is critically degraded; block or escalate

### Stale and Error States

Every panel must handle:

- **Stale**: data older than the configured staleness threshold — show timestamp and flag as stale
- **Error**: data query failed — show error state, not a fake value
- **No data**: no signals/producers found — show "no data" explicitly, not zero-as-success

### API Truth Format

Each endpoint must return:

```json
{
  "status": "GREEN" | "YELLOW" | "RED" | "UNKNOWN",
  "summary": { ... },
  "blockers": [ { "type": ..., "severity": ..., "detail": ... }, ... ],
  "last_updated": "ISO8601 timestamp",
  "is_stale": true | false,
  "data_source": "db" | "runtime" | "cache"
}
```

---

## Required Tests

Before reporting GREEN, the following tests must pass:

1. **Real data test** — dashboard endpoint returns data sourced from real DB query, not hardcoded values.
2. **Stale state test** — when data is older than the staleness threshold, `is_stale = true` is returned.
3. **Error state test** — when DB query fails, endpoint returns error state, not fake GREEN.
4. **Blocker severity test** — a known YELLOW blocker state returns `status: "YELLOW"`, not `"GREEN"`.
5. **No mock data test** — no hardcoded mock signal counts, quality percentages, or producer statuses exist in the dashboard code.
6. **No trading control test** — dashboard endpoint contains no code that creates orders, fills, or positions.
7. **Signal quality status test** — quality panel reflects actual quality gate results.
8. **Link coverage status test** — coverage panel reflects actual link coverage audit results.

---

## Verification Expectations

- Run: `pytest tests/ -k "mesh_dashboard or mesh_blockers" -v`
- All 8 test categories above must pass.
- Dashboard endpoint must be reachable and return real data when runtime is running.
- No runtime process started during unit tests.
- No migration applied.

---

## Expected Outputs

1. `mesh_blockers_summary` — combined blocker severity across all mesh health domains
2. `signal_quality_status` — quality gate pass/fail with counts and severity
3. `link_coverage_status` — link coverage percentage and unlinked-by-reason breakdown
4. `lineage_coverage_status` — lineage coverage percentage and unbound-by-reason breakdown
5. `producer_health_status` — active/stale/failing producer counts
6. `dry_run_provenance_status` — dry-run signal separation confirmed or flagged
7. Dashboard API endpoint(s) — read-only, no trading controls
8. Tests for real-data-only guarantee

---

## Final Output Format

Every run of this skill must end with:

1. Summary
2. Files created
3. Files changed
4. Tests run
5. Exact test results
6. Safety checklist
7. Remaining risks
8. Status: GREEN / YELLOW / RED
9. Can continue: YES / NO

---

## GREEN / YELLOW / RED Rules

**GREEN:**
All 8 test categories pass. Dashboard shows real DB/runtime truth. No mock data. Stale and error states implemented. No trading controls added. No forbidden files touched.

**YELLOW:**
Dashboard endpoint created but one or more test categories missing. Or: stale/error states not yet fully implemented. Or: one or more mesh domains not yet wired to real data.

**RED:**
Any mock data pretending to be live state introduced. Any trading control added. Any test failed that checks for order/fill/position mutation. Any forbidden file (Risk Governor, Execution Cortex, State Governor, Capital Allocator, Exit Cortex) modified.
