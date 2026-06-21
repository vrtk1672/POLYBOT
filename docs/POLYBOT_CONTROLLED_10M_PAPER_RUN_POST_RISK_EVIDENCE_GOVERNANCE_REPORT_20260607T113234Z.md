# POLYBOT Controlled 10m PAPER Run Post Risk Evidence Governance Report - 20260607T113234Z

- run_id: `controlled_10m_paper_run_post_risk_evidence_governance_20260607T113234Z`
- security_governance_status: `YELLOW_ACCEPTED_BY_OPERATOR`
- rebuild_deploy_status: `SEE_FINAL_OUTPUT`
- preflight_status: `RED`
- run_started: `NO`
- phase_status: `RED`
- start_utc: `2026-06-07T11:32:34.165096+00:00`
- end_utc: `2026-06-07T11:32:44.219635+00:00`
- start_local: `2026-06-07T14:32:34.165096+03:00`
- end_local: `2026-06-07T14:32:44.219635+03:00`
- duration_seconds: `10.1`
- cycles: `0`
- hard_stop: `YES`
- hard_stop_reason: `PREFLIGHT_RED`
- log_path: `logs\observation\controlled_10m_paper_run_post_risk_evidence_governance_20260607T113234Z.log`
- report_path: `docs\POLYBOT_CONTROLLED_10M_PAPER_RUN_POST_RISK_EVIDENCE_GOVERNANCE_REPORT_20260607T113234Z.md`

## Preflight
- blockers: `['REAL_ORDERS_PRESENT']`
- warnings: `["SAFE_YELLOW_AI:['COMPLETED', 'OK', 'OLLAMA_TIMEOUT']"]`
- runtime_mode: `PAPER`
- live_enabled: `False`
- shadow_enabled: `False`
- capital_reconciliation_status: `OK`

## Cycle Status
- no cycles ran

## Deltas
```json
{}
```

## Final Risk Evidence And Governance
```json
{
  "risk_evidence_decisions": null,
  "risk_evidence_blockers": null,
  "risk_evidence_edge_source_types": null,
  "risk_source_selection": null,
  "governance_actionability": null,
  "allow_paper_intent_count": null,
  "allow_paper_execution_count": null
}
```

## Capital
```json
{
  "before": null,
  "after": null
}
```

## Paper Result
- paper trades opened: `NO`
- paper trades closed: `NO`
- paper deltas: `{}`

## Blockers / Closest To Actionable
- top critical blockers: `None`
- top optional missing: `None`
- latest risk review traces: `None`

## Safety Checks
- bypass_paths_found: `None`
- stale_data_authorized_paper: `NO_EVIDENCE`
- historical_exposure_hard_block_as_active: `NO_EVIDENCE`
- secret_exposure_check: `PASS`
- final_system_state: `None`

## Validation Answers
1. API rebuild/redeploy succeeded: `SEE_FINAL_OUTPUT`
2. SYSTEM ON stayed active: `NO`
3. Runtime PAPER: `PAPER`
4. Cycles ran: `0`
5. Risk Evidence Mesh ran each cycle: `NO`
6. Lifecycle Governance used fresh Risk Evidence: `NO`
7. Stale legacy Risk ignored when fresh Risk Evidence existed: `NO`
8. RISK_REVIEW promoted to WATCH_FOR_CONFIRMATION: `NO`
9. RISK_REVIEW became ACTIONABLE_SMALL_PAPER: `NO`
10. If not, blocker: `NONE`
11. Paper Intent created: `NO`
12. Paper Order/Fill/Position created: `NO`
13. Capital stayed OK: `NO`
14. Any bypass: `NO`
15. Final SYSTEM state: `None`
16. Recommended next step: `Review top critical blockers before longer Paper validation.`

## Raw First Sample
```json
{}
```

## Raw Final Sample
```json
{}
```
