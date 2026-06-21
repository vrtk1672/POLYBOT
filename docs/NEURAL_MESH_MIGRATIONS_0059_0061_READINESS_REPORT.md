# Neural Mesh Migrations 0059–0061 Readiness Report

**Task mode:** SAFE_BUILD  
**Generated:** 2026-05-21  
**Author:** Claude (Secondary Builder)  
**Scope:** Read-only inspection and test verification. No production changes made.

---

## 1. Summary

Migrations 0059, 0060, and 0061 introduce the Neural Mesh signal contract, neuron registry, and signal event binding tables. They have been in the repository since V2 Neural Mesh Part 1A/1B/1C and are applied to the Docker test DB but not yet to the production DB (production is at migration 0058).

All 24 targeted tests pass. The migrations are safe, idempotent, purely observational, and have no trading, order, or position logic. The production DB has all dependency tables already applied. This report confirms readiness to apply these migrations to production.

---

## 2. Migrations Inspected

| File | Migration | Purpose |
|---|---|---|
| `app/db/migrations/0059_v2_neural_mesh_signal_contract.sql` | 0059 | Neural Mesh Part 1A: signal store tables |
| `app/db/migrations/0060_v2_neural_mesh_neuron_registry.sql` | 0060 | Neural Mesh Part 1B: neuron registry + health tables |
| `app/db/migrations/0061_v2_neural_mesh_signal_event_binding.sql` | 0061 | Neural Mesh Part 1C: producer registry + signal binding tables |

**Application order required:** 0059 → 0060 → 0061 (enforced by FK dependencies)

---

## 3. Tables / Schema Changes Detected

### Migration 0059 — Signal Contract Tables

**New tables:**

| Table | Purpose | Key Constraints |
|---|---|---|
| `neuron_signals` | Canonical neutral signal store | `status` enum CHECK, `raw_direction` enum CHECK, `strength/confidence/source_reliability` range 0–1 CHECK, **`neuron_signals_no_trade_action_payload` blocks trade keys in `evidence_json`** |
| `neuron_signal_entities` | Named entities linked to a signal | FK → `neuron_signals(signal_id) ON DELETE CASCADE` |
| `neuron_signal_evidence` | Raw evidence rows linked to a signal | FK → `neuron_signals(signal_id) ON DELETE CASCADE` |

**Indexes (7):** `created_at DESC`, `neuron+created_at`, `market_id`, `status`, `correlation_id`, `processed_by_brain`, `source_name`

**Notable safety constraint in 0059:**
```sql
CONSTRAINT neuron_signals_no_trade_action_payload CHECK (
    NOT (
        evidence_json ? 'buy'
        OR evidence_json ? 'sell'
        OR evidence_json ? 'enter_trade'
        OR evidence_json ? 'exit_trade'
        OR evidence_json ? 'trade_decision'
        OR evidence_json ? 'approved'
        OR evidence_json ? 'rejected'
        OR evidence_json ? 'order_id'
    )
)
```
This prevents trade-action payloads at the DB level — a DB-enforced safety guard.

---

### Migration 0060 — Neuron Registry Tables

**New tables:**

| Table | Purpose | Key Constraints |
|---|---|---|
| `neuron_registry` | Canonical registry of all named neurons | `neuron_name UNIQUE`, `default_status` enum CHECK, `name` not-blank CHECK |
| `neuron_health` | Runtime health per neuron | FK → `neuron_registry(neuron_name) ON DELETE CASCADE`, `runtime_status` + `health_status` enum CHECKs, `stale_after_seconds >= 0` CHECK, `signal_count_*` non-negative CHECKs |

**Seed data:** 22 neurons inserted via `ON CONFLICT (neuron_name) DO NOTHING`

Seeded neurons include: `market`, `orderbook`, `liquidity`, `rules`, `resolution`, `news`, `social`, `whale`, `time`, `fees`, `ai`, `risk`, `capital`, `position`, `exit`, `source`, `execution`, `no_trade`, `opportunity`, `strategy`, `memory`, `learning`

**Safety in seed data:**
- `news` and `social` are seeded with `enabled = FALSE` and `default_status = 'DISABLED'`
- No trading-related columns — purely observational metadata

**Indexes (4):** `category`, `enabled`, `runtime_status`, `health_status`, `is_stale`, `updated_at DESC`

---

### Migration 0061 — Signal Event Binding Tables

**New tables:**

| Table | Purpose | Key Constraints |
|---|---|---|
| `neuron_producers` | Registry of signal producers | FK → `neuron_registry(neuron_name) ON DELETE CASCADE`, `producer_name UNIQUE`, name not-blank CHECK |
| `neuron_signal_bindings` | Links each signal to its producer, source, and event | FK → `neuron_signals(signal_id) ON DELETE CASCADE`, FK → `source_status(id) ON DELETE SET NULL`, FK → `event_log(id) ON DELETE SET NULL`, `generated_from` enum CHECK |

**Seed data:** 6 producers inserted via `ON CONFLICT (producer_name) DO NOTHING`

Seeded producers: `source_status_adapter`, `clob_source_status_adapter`, `rules_resolution_adapter`, `future_news_adapter` (disabled), `future_social_adapter` (disabled), `future_whale_adapter` (disabled)

**FK dependencies on already-existing production tables:**
- `source_status(id)` — created by migration 0057 ✓ already in production
- `event_log(id)` — created by migration 0039 ✓ already in production

**Indexes (9):** signal_id, neuron_name, producer_name, source_name, event_log_id, source_status_id, market_id, correlation_id, created_at DESC

**All FKs on `neuron_signal_bindings` to external tables use `ON DELETE SET NULL`**, not CASCADE — so deleting a source_status or event_log row does not cascade-delete signal bindings.

---

## 4. Related Tests Inspected

| Test File | Tests | Type |
|---|---|---|
| `tests/test_v2_neuron_registry_contract.py` | 4 | Contract (no DB) |
| `tests/test_v2_neuron_signal_contract.py` | 8 | Contract (no DB) |
| `tests/test_v2_signal_event_binding_contract.py` | 4 | Contract (no DB) |
| `tests/test_v2_neuron_registry_repository.py` | 6 | Repository (requires DB) |
| `tests/test_v2_dashboard_signal_lineage.py` | 2 | API + DB |

**Contract test scope:** Validates Pydantic contracts, forbidden field enforcement, status enums, adapter outputs. Pure Python — no DB required.

**Repository test scope:** Tests `NeuronRegistryService` and `NeuronSignalService` against the test DB. Includes a specific safety test (`test_neuron_registry_does_not_mutate_order_tables`) that confirms `paper_orders`, `shadow_orders`, and `live_orders` counts are unchanged after any neuron registry operation.

**Dashboard lineage test scope:** Tests `/dashboard/api/v2/signal-lineage` endpoint returns real DB truth (`mock_data=false`), correct signal/bound/unbound counts.

---

## 5. Tests Run

**Command 1 — Contract tests:**
```
powershell -ExecutionPolicy Bypass -File .\scripts\test_in_docker.ps1
    tests/test_v2_neuron_registry_contract.py
    tests/test_v2_neuron_signal_contract.py
    tests/test_v2_signal_event_binding_contract.py
    -v
```

**Command 2 — Repository + Dashboard tests:**
```
powershell -ExecutionPolicy Bypass -File .\scripts\test_in_docker.ps1
    tests/test_v2_neuron_registry_repository.py
    tests/test_v2_dashboard_signal_lineage.py
    -v
```

Both commands ran via Docker against the isolated `polybot_test` database. The test_migrate service confirmed all pending migrations were applied to the test DB before each run.

---

## 6. Exact Test Results

### Run 1 — Contract tests (16 tests)

```
platform linux -- Python 3.11.15, pytest-8.4.2, pluggy-1.6.0
collected 16 items

tests/test_v2_neuron_registry_contract.py::test_default_neurons_include_required_names PASSED
tests/test_v2_neuron_registry_contract.py::test_registry_entry_requires_name PASSED
tests/test_v2_neuron_registry_contract.py::test_valid_statuses_are_enforced PASSED
tests/test_v2_neuron_registry_contract.py::test_registry_contract_is_observational_only PASSED
tests/test_v2_neuron_signal_contract.py::test_create_valid_signal_without_market_id PASSED
tests/test_v2_neuron_signal_contract.py::test_reject_invalid_strength_outside_range PASSED
tests/test_v2_neuron_signal_contract.py::test_reject_missing_neuron PASSED
tests/test_v2_neuron_signal_contract.py::test_reject_missing_event_type PASSED
tests/test_v2_neuron_signal_contract.py::test_signal_contract_has_no_trade_action_fields PASSED
tests/test_v2_neuron_signal_contract.py::test_reject_decision_keys_in_evidence PASSED
tests/test_v2_neuron_signal_contract.py::test_source_status_adapter_creates_neutral_signal PASSED
tests/test_v2_neuron_signal_contract.py::test_rules_adapter_creates_neutral_resolution_signal PASSED
tests/test_v2_signal_event_binding_contract.py::test_signal_lineage_contract_accepts_reference_only_payload PASSED
tests/test_v2_signal_event_binding_contract.py::test_signal_lineage_requires_producer_name PASSED
tests/test_v2_signal_event_binding_contract.py::test_source_status_adapter_adds_correlation_and_ref PASSED
tests/test_v2_signal_event_binding_contract.py::test_rules_adapter_adds_correlation_and_ref PASSED

16 passed in 1.71s
```

### Run 2 — Repository + Dashboard tests (8 tests)

```
platform linux -- Python 3.11.15, pytest-8.4.2, pluggy-1.6.0
collected 8 items

tests/test_v2_neuron_registry_repository.py::test_default_neurons_are_seeded PASSED
tests/test_v2_neuron_registry_repository.py::test_disabled_neuron_reports_disabled PASSED
tests/test_v2_neuron_registry_repository.py::test_recent_signal_reports_active_and_counts PASSED
tests/test_v2_neuron_registry_repository.py::test_old_signal_reports_stale PASSED
tests/test_v2_neuron_registry_repository.py::test_missing_expected_neuron_reports_missing PASSED
tests/test_v2_neuron_registry_repository.py::test_neuron_registry_does_not_mutate_order_tables PASSED
tests/test_v2_dashboard_signal_lineage.py::test_dashboard_signal_lineage_endpoint_returns_truth PASSED
tests/test_v2_dashboard_signal_lineage.py::test_dashboard_signals_includes_lineage_summary PASSED

8 passed in 6.70s
```

**Total: 24 / 24 passed. 0 failed. 0 skipped.**

---

## 7. Safety Impact

| Safety Property | Status | Notes |
|---|---|---|
| No trading logic added | ✓ SAFE | Purely observational tables and contracts |
| No order creation | ✓ SAFE | No INSERT into paper_orders / shadow_orders / live_orders |
| No live trading enabled | ✓ SAFE | No changes to live path or env |
| State Governor not touched | ✓ SAFE | No changes to runtime/state code |
| Risk Gate not touched | ✓ SAFE | No changes to risk code |
| No secrets exposed | ✓ SAFE | No credentials referenced |
| Dashboard truth maintained | ✓ SAFE | New `/dashboard/api/v2/signal-lineage` returns `mock_data=false` |
| No fake data | ✓ SAFE | All dashboard values derived from DB |
| DB-level safety guard added | ✓ STRENGTHENS SAFETY | `neuron_signals_no_trade_action_payload` CHECK constraint prevents trade keys in signal evidence at the DB level |
| Order table mutation guard tested | ✓ VERIFIED | `test_neuron_registry_does_not_mutate_order_tables` confirms no side effects |

---

## 8. Production Apply Risks

| Risk | Severity | Notes |
|---|---|---|
| FK dependency on `source_status(id)` | LOW | `source_status` was created by 0057, already in production |
| FK dependency on `event_log(id)` | LOW | `event_log` was created by 0039, already in production |
| FK dependency on `neuron_registry(neuron_name)` from 0060→0061 | LOW | Requires 0060 before 0061; standard sequential apply |
| Seed data conflicts | NONE | All INSERTs use `ON CONFLICT (neuron_name/producer_name) DO NOTHING` — safe on re-apply |
| Schema collision with existing tables | NONE | All tables use `CREATE TABLE IF NOT EXISTS` |
| Index creation on large tables | NONE | All target tables are new; no existing data to index |
| Runtime disruption during apply | LOW | FastAPI does not auto-query these tables on startup; apply can happen while API is running |

---

## 9. Rollback Concerns

If rollback is required after applying, tables must be dropped in reverse dependency order:

```sql
-- Reverse of 0061
DROP TABLE IF EXISTS neuron_signal_bindings CASCADE;
DROP TABLE IF EXISTS neuron_producers CASCADE;

-- Reverse of 0060
DROP TABLE IF EXISTS neuron_health CASCADE;
DROP TABLE IF EXISTS neuron_registry CASCADE;

-- Reverse of 0059
DROP TABLE IF EXISTS neuron_signal_evidence CASCADE;
DROP TABLE IF EXISTS neuron_signal_entities CASCADE;
DROP TABLE IF EXISTS neuron_signals CASCADE;
```

**Rollback risk:** LOW. These are new tables with no existing production data. Dropping them removes only the schema objects; no existing rows in other tables are affected.

**Do not rollback by running these manually** — use the standard POLYBOT migration rollback process or coordinate with the Commander/Architect.

---

## 10. Final Status: GREEN

All conditions for GREEN are met:

- [x] All 24 targeted tests passed
- [x] No safety tests failed
- [x] No live safety unclear (live is disabled, DATA_ONLY mode active)
- [x] No secrets exposed
- [x] No fake dashboard data
- [x] State Governor not bypassed
- [x] Risk Gate not bypassed
- [x] No duplicate DB truth created
- [x] Implementation is within scope (observational mesh tables only)
- [x] All external FK dependencies confirmed present in production (0039 `event_log`, 0057 `source_status`)
- [x] Migrations are idempotent (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`)

---

## 11. Can Apply to Production DB: YES

**Recommended apply command:**
```
docker compose run --rm migrate
```

This runs the one-shot migrate service which applies all pending migrations in numeric order (0059 → 0060 → 0061), records each in `schema_migrations`, and exits.

**Verify after apply:**
```
docker exec polybot_postgres psql -U polybot -d polybot \
  -c "SELECT migration_name FROM schema_migrations ORDER BY applied_at DESC LIMIT 5;"
```

Expected last three entries: `0061_v2_neural_mesh_signal_event_binding.sql`, `0060_v2_neural_mesh_neuron_registry.sql`, `0059_v2_neural_mesh_signal_contract.sql`

**After apply, smoke the new endpoints:**
```
curl http://127.0.0.1:8000/dashboard/api/v2/signals
curl http://127.0.0.1:8000/dashboard/api/v2/neurons
curl http://127.0.0.1:8000/dashboard/api/v2/signal-lineage
```

Each should return `mock_data: false`.

---

## Remaining Risks

- Production migration apply has not been done yet — this report covers readiness only
- V2.20 long-duration DATA_ONLY/PAPER evidence runs are still YELLOW; the neural mesh migration does not affect that gate
- `orderbook_snapshots` remain at 0 in production — that gap is separate and still blocks full PAPER readiness
- After migration, the production runtime will need its next refresh cycle to emit actual `neuron_signals` rows via the source-status and rules-resolution adapters
