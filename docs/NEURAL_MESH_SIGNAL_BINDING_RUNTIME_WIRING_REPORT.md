# Neural Mesh Signal Binding Runtime Wiring Report

**Task mode:** CONTROLLED_FEATURE  
**Date:** 2026-05-21  
**Author:** Claude (Secondary Builder)  
**Scope:** Verify and confirm runtime signal binding wiring. Add missing duplicate-binding safety test.

---

## 1. Summary

The runtime signal binding emission wiring is **already complete** in the existing service layer. No runtime code changes were required. The `neuron_signal_bindings=0` production count is a pre-migration artifact — the 36 existing `neuron_signals` rows were created during a window when `neuron_signal_bindings` did not yet exist (before migration 0061 was applied); all failures were silently swallowed. After migration 0061 was applied, the binding path is fully operational. New signals written on each runtime refresh cycle will have binding rows.

One missing test was added: `test_no_duplicate_binding_for_same_signal` verifies the `ON CONFLICT (signal_id) DO UPDATE` idempotency guard.

**17/17 targeted tests passed.**

---

## 2. Runtime Binding Chain (already wired)

### Source-status path

```
SourceStatusService.get_dashboard_source_status(persist=True)
  └─ _record_signals_safely(checks)
       └─ NeuronSignalService().record_source_status_signals([check.to_api_dict() ...])
            └─ _record_many(signals, lineages=lineages)
                 └─ per signal: SignalLineageRepository.attach_signal_binding(conn, lineage_item)
                      └─ INSERT INTO neuron_signal_bindings ON CONFLICT (signal_id) DO UPDATE
```

**Producer assigned:** `clob_source_status_adapter` if `source_name.startswith("polymarket_clob")`, else `source_status_adapter`.

### Rules-resolution path

```
RulesResolutionTruthService.get_dashboard_rules_status()
  └─ _record_rules_signals_safely(self._factory, serialized_markets)
       └─ NeuronSignalService().record_rules_status_signals(markets)
            └─ _record_many(signals, lineages=lineages)
                 └─ per signal: SignalLineageRepository.attach_signal_binding(conn, lineage_item)
                      └─ INSERT INTO neuron_signal_bindings ON CONFLICT (signal_id) DO UPDATE
```

**Producer assigned:** always `rules_resolution_adapter`.

Both paths are called on every dashboard refresh cycle by the existing runtime.

---

## 3. Why neuron_signal_bindings = 0 (pre-existing explanation)

| Period | What happened |
|---|---|
| Before migration 0059 | `neuron_signals` table did not exist; no signals possible |
| After 0059, before 0061 | `neuron_signals` exists; `neuron_signal_bindings` does not; `record_source_status_signals` wrote signals but `attach_signal_binding` threw a DB error — silently swallowed by `try/except: return` |
| After 0061 applied (2026-05-21) | `neuron_signal_bindings` exists; full binding chain operational; new signals get bound rows |

The 36 pre-existing `neuron_signals` rows remain unbound. They are valid historical data. The binding gap will self-heal: on the next runtime refresh, new signals are written with bindings.

---

## 4. Code Locations (no changes made)

| File | Role |
|---|---|
| `app/services/source_status.py:481-489` | `_record_signals_safely` — calls `record_source_status_signals`, swallows exceptions |
| `app/services/rules_resolution_truth.py:219,232-241` | `get_dashboard_rules_status` + `_record_rules_signals_safely` — calls `record_rules_status_signals`, swallows exceptions |
| `app/services/neuron_signals.py:135-161` | `record_source_status_signals`, `record_rules_status_signals`, `_record_many` — core binding write path |
| `app/repositories/signal_lineage_repository.py` | `attach_signal_binding` — idempotent INSERT ON CONFLICT (signal_id) DO UPDATE |

---

## 5. Files Changed

| File | Change |
|---|---|
| `tests/test_v2_signal_event_binding_repository.py` | Added `test_no_duplicate_binding_for_same_signal` |

No runtime, service, or migration files were modified.

---

## 6. Files Created

| File | Purpose |
|---|---|
| `docs/NEURAL_MESH_SIGNAL_BINDING_RUNTIME_WIRING_REPORT.md` | This report |

---

## 7. Tests Run

```
powershell -ExecutionPolicy Bypass -File .\scripts\test_in_docker.ps1
  tests/test_v2_signal_event_binding_contract.py
  tests/test_v2_signal_event_binding_repository.py
  tests/test_v2_neuron_signal_repository.py
  tests/test_v2_dashboard_signal_lineage.py
  -v
```

Run against isolated `polybot_test` DB via Docker.

---

## 8. Exact Test Results

```
platform linux -- Python 3.11.15, pytest-8.4.2, pluggy-1.6.0
collected 17 items

tests/test_v2_signal_event_binding_contract.py::test_signal_lineage_contract_accepts_reference_only_payload PASSED
tests/test_v2_signal_event_binding_contract.py::test_signal_lineage_requires_producer_name PASSED
tests/test_v2_signal_event_binding_contract.py::test_source_status_adapter_adds_correlation_and_ref PASSED
tests/test_v2_signal_event_binding_contract.py::test_rules_adapter_adds_correlation_and_ref PASSED
tests/test_v2_signal_event_binding_repository.py::test_create_signal_with_producer_source_lineage PASSED
tests/test_v2_signal_event_binding_repository.py::test_create_signal_without_event_log_id_still_works PASSED
tests/test_v2_signal_event_binding_repository.py::test_lineage_queries_by_correlation_source_and_producer PASSED
tests/test_v2_signal_event_binding_repository.py::test_unbound_and_summary_counts_are_accurate PASSED
tests/test_v2_signal_event_binding_repository.py::test_source_status_adapter_creates_lineage_with_source_status_id PASSED
tests/test_v2_signal_event_binding_repository.py::test_rules_adapter_creates_lineage PASSED
tests/test_v2_signal_event_binding_repository.py::test_no_duplicate_binding_for_same_signal PASSED
tests/test_v2_signal_event_binding_repository.py::test_lineage_does_not_mutate_order_tables PASSED
tests/test_v2_neuron_signal_repository.py::test_signal_repository_persists_and_lists_signals PASSED
tests/test_v2_neuron_signal_repository.py::test_signal_summary_counts_stale_and_unprocessed PASSED
tests/test_v2_neuron_signal_repository.py::test_signal_store_does_not_mutate_order_tables PASSED
tests/test_v2_dashboard_signal_lineage.py::test_dashboard_signal_lineage_endpoint_returns_truth PASSED
tests/test_v2_dashboard_signal_lineage.py::test_dashboard_signals_includes_lineage_summary PASSED

17 passed in 5.76s
```

**Total: 17 / 17 passed. 0 failed. 0 skipped.**

---

## 9. Required Test Coverage Map

| Required test | Covered by |
|---|---|
| source_status_adapter writes a signal binding row | `test_source_status_adapter_creates_lineage_with_source_status_id` |
| rules_resolution_adapter writes a signal binding row | `test_rules_adapter_creates_lineage` |
| No duplicate binding for same signal | `test_no_duplicate_binding_for_same_signal` (new) |
| Dashboard signal-lineage reports bound_signals_24h > 0 | `test_unbound_and_summary_counts_are_accurate`, `test_dashboard_signals_includes_lineage_summary` |
| No paper_orders / shadow_orders / live_orders mutated | `test_lineage_does_not_mutate_order_tables` |

---

## 10. Safety Checklist

| Check | Result |
|---|---|
| Runtime code modified | NO |
| Trading logic modified | NO |
| Execution / Risk / Capital / Exit code modified | NO |
| Orders / fills / positions created | NO |
| PAPER / SHADOW_LIVE / live trading enabled | NO |
| State Governor bypassed | NO |
| Risk Gate bypassed | NO |
| Fake dashboard data created | NO |
| Duplicate DB truth created | NO |
| Secrets exposed | NO |
| Migrations applied | NO |
| Order tables mutated by any test | VERIFIED NO — `test_lineage_does_not_mutate_order_tables` |

---

## 11. Remaining Gaps

| Gap | Notes |
|---|---|
| 36 existing `neuron_signals` are unbound | Pre-0061 artifact; valid historical data; will not auto-backfill; safe to leave as-is |
| `neuron_signal_bindings` count in production is unknown | Count will increase on next runtime refresh cycle; no action required |
| V2.20 PAPER evidence (24h/72h/7d) | Still YELLOW; unrelated to this wiring task |
| `orderbook_snapshots` still blocking full PAPER readiness | Separate gap; not affected by this task |

---

## 12. Status: GREEN

- Wiring is confirmed complete in existing code.
- 17/17 tests passed.
- No trading logic changed.
- No safety checks bypassed.
- No fake data.
- One safety test added (duplicate binding guard).

## Can Continue: YES

Next logical step: V2.20 DATA_ONLY and PAPER evidence run (independent of this wiring task, which is now closed).
