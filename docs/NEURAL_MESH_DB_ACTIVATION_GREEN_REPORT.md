# Neural Mesh DB Activation — GREEN Report

**Date:** 2026-05-21  
**Task mode:** SAFE_BUILD  
**Author:** Claude (Secondary Builder)

---

## Status: GREEN

Migrations 0059, 0060, and 0061 are applied to the production DB. The neural mesh DB foundation is operational.

---

## What Was Applied

| Migration | Tables Created | Seed Data |
|---|---|---|
| `0059_v2_neural_mesh_signal_contract.sql` | `neuron_signals`, `neuron_signal_entities`, `neuron_signal_evidence` | none |
| `0060_v2_neural_mesh_neuron_registry.sql` | `neuron_registry`, `neuron_health` | 22 neurons seeded |
| `0061_v2_neural_mesh_signal_event_binding.sql` | `neuron_producers`, `neuron_signal_bindings` | 6 producers seeded |

**Applied via:** `docker compose run --rm migrate`

**`schema_migrations` column:** `version` (not `migration_name`)

---

## Verified Row Counts (post-apply)

| Table | Count | Notes |
|---|---|---|
| `neuron_registry` | 22 | All named neurons seeded |
| `neuron_health` | 22 | One health row per registry entry |
| `neuron_producers` | 6 | 3 active adapters, 3 disabled future placeholders |
| `neuron_signals` | 36 | Signals written by runtime after migration |
| `neuron_signal_entities` | 0 | Not yet populated |
| `neuron_signal_evidence` | 0 | Not yet populated |
| `neuron_signal_bindings` | 0 | Not yet populated — see remaining gap below |

---

## Safety Verification

| Check | Result |
|---|---|
| `paper_orders` after migration | 0 — unchanged |
| `shadow_orders` after migration | 0 — unchanged |
| `live_orders` after migration | 0 — unchanged |
| Live trading enabled | NO — `LIVE=false`, `KILL=true` |
| State Governor mode | DATA_ONLY — paper/shadow/live permissions blocked |
| Trade keys in `neuron_signals.evidence_json` | Blocked at DB level by `neuron_signals_no_trade_action_payload` CHECK constraint |

No orders were placed. No live mutation occurred. No secrets were exposed.

---

## Test Results

24/24 targeted Neural Mesh Part 1 tests passed in Docker against isolated `polybot_test` DB:

- `test_v2_neuron_registry_contract.py` — 4/4 passed
- `test_v2_neuron_signal_contract.py` — 8/8 passed
- `test_v2_signal_event_binding_contract.py` — 4/4 passed
- `test_v2_neuron_registry_repository.py` — 6/6 passed (includes `test_neuron_registry_does_not_mutate_order_tables`)
- `test_v2_dashboard_signal_lineage.py` — 2/2 passed

---

## Remaining Gap

`neuron_signal_bindings` is at 0. The DB tables and producers are seeded, but the runtime cycle is not yet calling the lineage service to write binding rows. This is a wiring task, not a schema task.

**Next step:** wire source-status and rules-resolution adapters to call `SignalLineageService` and write `neuron_signal_bindings` rows on each runtime refresh cycle.

This does not affect V2.20 PAPER evidence gates, which remain a separate requirement.

---

## Documentation Updated

- `docs/V2_CURRENT_ACTIVATION_STATUS.md` — migration count, neural mesh table counts, V2.1 row, Section 4/5/7/9 updated.
- `docs/POLYBOT_CONTEXT_INDEX.md` — Neural Mesh Part 1A/1B/1C and DB Activation entries added; `schema_migrations.version` note added; Important Boundaries updated.
- `POLYBOT_CURRENT_REALITY_AUDIT.md` — deprecation notice added at top (file is stale: 2026-05-09, wrong path).
