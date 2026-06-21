# Phase 2.1 Resolution Source Extraction Report

## 1. Executive summary

Phase 2.1 added deterministic resolution-source extraction and refresh support for the Rules / Resolution Truth layer.

The system now distinguishes:

- `EXPLICIT`: structured metadata/source URL exists.
- `RULES_DERIVED`: rules text names a clear resolution authority.
- `FAMILY_DERIVED`: family/source wording gives a high-confidence but non-explicit source.
- `AMBIGUOUS`: rules mention competing or fallback authorities.
- `MISSING`: no credible source evidence found.

Runtime remains healthy and safe. The dashboard remains truthfully `DEGRADED` because active markets currently include 9 ambiguous resolution sources and 1 missing resolution source.

Final status: **GREEN for Phase 2.1 implementation, YELLOW dashboard truth for current market data**.

## 2. Root cause

Gamma/raw market metadata and rules text contained resolution wording, but the earlier Phase 2 implementation only treated structured fields/URLs as resolution sources. Current active markets had rules text, but no explicit `resolutionSource` value in raw metadata. This made all active markets appear as missing explicit resolution source even when the rules text included usable evidence.

## 3. Existing data fields inspected

Inspected code and DB surfaces:

- `markets_v2.raw_market_json`
- `markets_v2.resolution_source`
- `market_rules.rules_text`
- `market_rules.resolution_source`
- `market_rules.resolution_source_url`
- `market_rules.raw_rules_json`
- `rules_analysis`
- `resolution_sources`
- `no_trade_log`
- Gamma-derived `description`, `rules`, `resolutionSource`, `resolutionSourceUrl`, `endDate`, `category`, `market_family`, `question`

Observed live examples included:

- “resolution source ... government of the UK, however a consensus of credible reporting will also suffice”
- “primary resolution source ... official information from NATO, the EU, or member states..., however consensus...”
- “primary resolution source ... information from MSTR and on-chain data, however consensus...”

These are evidence-bearing but ambiguous, not explicit.

## 4. Extraction strategy

The extractor is deterministic and read-only:

- Prefer explicit metadata fields/URLs.
- Derive from clear rules text patterns such as “The resolution source for this market will be ...”.
- Keep fallback or multi-authority wording marked `AMBIGUOUS`.
- Treat generic phrases such as “final official certification” as missing, not as a source.
- Keep derived sources labeled as derived; do not upgrade them to explicit.
- Missing rules remain hard-block capable.
- Missing resolution source with rules present remains a soft penalty, not a hard `NO_TRADE`.

No Claude/AI is required for this phase.

## 5. Files changed

- `app/rules_neuron/resolution_source_parser.py`
- `app/rules_neuron/rules_ingestion.py`
- `app/data_foundation/contracts.py`
- `app/data_foundation/market_rules_store.py`
- `app/repositories/market_rules_repository.py`
- `app/services/rules_resolution_truth.py`
- `app/db/migrations/0058_v2_21_resolution_source_extraction.sql`
- `scripts/refresh_rules_truth.ps1`
- `tests/test_v2_22_rules_resolution_truth.py`
- `docs/PHASE2_1_RESOLUTION_SOURCE_EXTRACTION_REPORT.md`

## 6. DB/migration changes

Added idempotent migration `0058_v2_21_resolution_source_extraction.sql`.

New `market_rules` columns:

- `resolution_source_status`
- `resolution_source_type`
- `resolution_source_evidence`
- `resolution_source_confidence`
- `resolution_source_penalty`
- `resolution_source_hard_block`

New index:

- `idx_market_rules_resolution_source_status`

Production migration status: `docker compose run --rm migrate` returned `No pending migrations.` after the migration was applied by compose startup.

Test migration status: `docker compose --profile test run --rm test_migrate` returned `No pending migrations.` after applying the migration to `polybot_test`.

## 7. Dashboard response before/after

Before this phase, the Rules dashboard had 10/10 active markets missing explicit resolution source.

After extraction and refresh:

- `/dashboard/api/v2/rules` works.
- `mock_data=false`
- `stale=false`
- status remains `DEGRADED` truthfully.
- active market coverage remains 10/10.
- missing rules count is 0.
- resolution source truth now shows ambiguity/missing instead of hiding everything as absent.

## 8. Resolution source coverage

Current active market coverage after refresh:

- `active_markets`: 10
- `with_rules`: 10
- `missing_rules`: 0
- `explicit_resolution_source_count`: 0
- `rules_derived_resolution_source_count`: 0
- `family_derived_resolution_source_count`: 0
- `derived_resolution_source_count`: 0
- `ambiguous_resolution_source_count`: 9
- `missing_resolution_source_count`: 1
- `analyzed_markets`: 10
- `coverage_pct`: 100.0

Current endpoint warning reasons:

- one or more active markets are missing resolution source
- one or more active markets have ambiguous resolution source

## 9. Hard NO_TRADE status

Current active market state:

- `hard_no_trade_count`: 0
- `no_trade_rule_blocks`: 0
- `penalize_heavily_count`: 6

Hard `NO_TRADE` remains connected for hard-block cases such as missing rules. Soft missing/ambiguous resolution source does not create hard `NO_TRADE` rows.

## 10. PENALIZE_HEAVILY status

Current active latest rules recommendations:

- `PENALIZE_HEAVILY`: 6
- `TRADE_ALLOWED`: 4

Important: `TRADE_ALLOWED` here means the current rules neuron did not hard-block the market. Ambiguous resolution-source evidence is still exposed in dashboard warnings and source verification status.

## 11. Tests run and exact results

Host syntax:

- `python -m compileall app\rules_neuron\resolution_source_parser.py app\rules_neuron\rules_ingestion.py app\data_foundation\market_rules_store.py app\repositories\market_rules_repository.py app\services\rules_resolution_truth.py tests\test_v2_22_rules_resolution_truth.py`
- Result: passed.

Targeted Docker tests:

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_22_rules_resolution_truth.py -q`
- Result: `9 passed in 29.34s`

Nearby regression tests:

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_5_resolution_source_parser.py tests/test_v2_2_market_rules_store.py tests/test_v2_5_rules_service_integration.py tests/test_v2_5_rules_api.py tests/test_v2_18_dashboard_v2_api.py -q`
- Result: `13 passed in 27.25s`

Test DB isolation:

- Production query for test market IDs returned `0`.

## 12. Runtime verification

Commands run:

- `docker compose config` passed.
- `docker compose --profile test config` passed.
- `docker compose build api migrate` passed.
- `docker compose --profile test build test test_migrate` passed.
- `docker compose up -d` passed.
- `docker compose ps` showed API/Postgres/Redis healthy.
- `docker compose run --rm migrate` returned `No pending migrations.`
- `docker compose --profile test run --rm test_migrate` returned `No pending migrations.`
- `.\scripts\refresh_rules_truth.ps1 50` returned `status= OK`, `candidate_count= 3`, `analyzed= 3`, `failed= 0`.
- All-active refresh returned `status= OK`, `candidate_count= 10`, `analyzed= 10`, `failed= 0`.

Runtime endpoints:

- `/healthz`: `status=ok`, `ready=true`
- `/runtime/health`: `overall_status=HEALTHY`
- `/dashboard/api/v2/overview`: `status=OK`, `mock_data=false`, `stale=false`
- `/dashboard/api/v2/source-status`: `status=OK`, `mock_data=false`, sources active/disabled as expected
- `/dashboard/api/v2/rules`: `status=DEGRADED`, `mock_data=false`, `stale=false`

## 13. Safety verification

Safety command output:

- `MODE= PAPER`
- `BACKEND= paper`
- `LIVE= false`
- `KILL= true`

DB verification:

- `live_orders`: 0

No order, cancel, signing, private-key, or live mutation path was touched.

## 14. Remaining gaps

- Current active markets still do not provide explicit resolution source URLs.
- Most current sources are ambiguous because Polymarket rules include fallback wording like “consensus of credible reporting.”
- One active market remains missing credible resolution source.
- `compliance_blocks` can accumulate repeated warning rows from repeated analysis; this is not a live-safety issue but should be cleaned up in a later observability/data hygiene pass.
- Current `TRADE_ALLOWED` recommendations can coexist with ambiguous source warnings; the next rules-risk phase should decide whether ambiguous source should force `PENALIZE_HEAVILY` consistently for selected families before PAPER.

## 15. Recommendation for next phase

Proceed to the next phase only in DATA_ONLY/PAPER development mode.

Recommended next phase:

1. Add selected-family policy for Politics/Macro and Sports.
2. Decide whether ambiguous resolution source is always a hard pre-trade blocker or a scoring penalty.
3. Add official resolution-source enrichment for the first two market families.
4. Deduplicate active compliance warning blocks.
5. Keep Claude optional and cache-first for only difficult rule ambiguity cases.

## 16. Final status

Final implementation status: **GREEN**.

Current rules dashboard truth: **YELLOW/DEGRADED by design** because active markets contain ambiguous/missing resolution source evidence.

Can continue to next phase: **YES**, with live trading still disabled.
