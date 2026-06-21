param(
    [Parameter(Position = 0)]
    [string]$Command = "status",

    [Alias("defense")]
    [int]$DefenseLevel = -1,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"

function Get-ArgValue {
    param([string[]]$Args, [string[]]$Names, [string]$Default)
    for ($i = 0; $i -lt $Args.Count; $i++) {
        if ($Names -contains $Args[$i]) {
            if (($i + 1) -lt $Args.Count) {
                return $Args[$i + 1]
            }
        }
    }
    return $Default
}

function First-Value {
    param([object[]]$Values)
    foreach ($item in $Values) {
        if ($null -ne $item -and "$item" -ne "") {
            return $item
        }
    }
    return "UNKNOWN"
}

function Invoke-PolybotJson {
    param([string]$Method, [string]$Path, [object]$Body = $null)
    $uri = "$script:BaseUrl$Path"
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $uri -TimeoutSec 120
    }
    $json = $Body | ConvertTo-Json -Depth 10
    return Invoke-RestMethod -Method $Method -Uri $uri -Body $json -ContentType "application/json" -TimeoutSec 120
}

function New-LocalReportDir {
    param([string]$Prefix)
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $suffix = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $root = Join-Path $script:ProjectRoot "run_reports"
    $dir = Join-Path $root ("{0}_{1}_{2}" -f $Prefix, $stamp, $suffix)
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Save-JsonReport {
    param([string]$Path, [object]$Payload)
    $Payload | ConvertTo-Json -Depth 40 | Set-Content -Path $Path -Encoding UTF8
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host $Title
    Write-Host ("-" * $Title.Length)
}

function Write-Kv {
    param([string]$Key, [object]$Value)
    if ($null -eq $Value) { $Value = "" }
    Write-Host ("{0,-34} {1}" -f ($Key + ":"), $Value)
}

function Write-Status {
    param([object]$Overview, [switch]$Full)
    Write-Section "POLYBOT Status"
    Write-Kv "System power" $Overview.system_power
    Write-Kv "Runtime state" $Overview.runtime_state
    Write-Kv "Execution mode" $Overview.execution_mode
    Write-Kv "Paper adapter" $Overview.paper_adapter_state
    Write-Kv "Live adapter" $Overview.live_adapter_state
    Write-Kv "Supervisor" $Overview.supervisor_state
    Write-Kv "Source refresh" $Overview.source_refresh_state
    Write-Kv "Current active cycle" (First-Value @($Overview.runtime_truth.current_active_cycle_id, "none"))
    Write-Kv "Latest completed cycle" (First-Value @($Overview.runtime_truth.latest_completed_cycle_id, "none"))
    Write-Kv "Stale abandoned cycles" (First-Value @($Overview.runtime_truth.stale_abandoned_cycles_count, 0))

    Write-Section "Activity"
    Write-Kv "Market universe total" $Overview.market_universe.total
    Write-Kv "Active markets" $Overview.market_universe.active
    Write-Kv "Token verified" $Overview.market_universe.token_verified
    Write-Kv "High priority markets" (First-Value @($Overview.market_universe.watchlist_priority.HIGH, $Overview.market_universe.priority.HIGH))
    Write-Kv "Memory HIGH markets" $Overview.market_universe.priority.HIGH
    Write-Kv "Recent events" $Overview.sources_events.recent_events
    Write-Kv "Linked events" $Overview.sources_events.linked_events
    Write-Kv "Triggers total" $Overview.triggers.total
    Write-Kv "Candidates generated" $Overview.candidates.seeds_generated
    Write-Kv "Mesh reviewed" $Overview.candidates.mesh_reviewed
    Write-Kv "Paper-ready decisions" $Overview.decisions.paper_ready_decisions
    Write-Kv "Runtime PAPER decisions" $Overview.decisions.runtime_decisions_total
    Write-Kv "Paper-enter decisions" $Overview.decisions.paper_enter_decisions
    Write-Kv "Blocked decisions" $Overview.decisions.blocked_decisions
    Write-Kv "Decision unique markets" (First-Value @($Overview.decisions.unique_market_count, 0))
    Write-Kv "Decision unique sides" (First-Value @($Overview.decisions.unique_side_count, 0))
    Write-Kv "Duplicate suppressed" (First-Value @($Overview.decisions.duplicate_suppression_count, 0))
    Write-Kv "Concentration score" (First-Value @($Overview.decisions.concentration_score, 0))
    Write-Kv "Stale orderbook blockers" (First-Value @($Overview.decisions.stale_orderbook_blocked_count, 0))
    Write-Kv "Last-mile refresh attempts" (First-Value @($Overview.decisions.last_mile_refresh_attempts, 0))
    Write-Kv "Last-mile refresh success" (First-Value @($Overview.decisions.last_mile_refresh_success_count, 0))
    Write-Kv "Last-mile refresh failed" (First-Value @($Overview.decisions.last_mile_refresh_failed_count, 0))

    Write-Section "AI Mesh"
    Write-Kv "AI Mesh status" (First-Value @($Overview.ai_mesh_intelligence.status, "UNKNOWN"))
    Write-Kv "AI mode" (First-Value @($Overview.ai_mesh_intelligence.ai_mode, "UNKNOWN"))
    Write-Kv "Fast JSON model" (First-Value @($Overview.ai_mesh_intelligence.fast_json_model, $Overview.ai_mesh_intelligence.local_model_status.fast_json_model, "UNKNOWN"))
    Write-Kv "JSON reliability" (First-Value @($Overview.ai_mesh_intelligence.json_reliability_status, "UNKNOWN"))
    Write-Kv "Local AI provider" (First-Value @($Overview.ai_mesh_intelligence.local_model_status.provider, "UNKNOWN"))
    Write-Kv "Local AI available" (First-Value @($Overview.ai_mesh_intelligence.local_model_status.available, $false))
    Write-Kv "AI insights" (First-Value @($Overview.ai_mesh_intelligence.total_insights, 0))
    Write-Kv "AI avg latency ms" (First-Value @($Overview.ai_mesh_intelligence.average_latency_ms, 0))
    Write-Kv "AI p95 latency ms" (First-Value @($Overview.ai_mesh_intelligence.p95_latency_ms, 0))
    Write-Kv "AI timeouts" (First-Value @($Overview.ai_mesh_intelligence.timeout_count, 0))
    Write-Kv "AI invalid JSON" (First-Value @($Overview.ai_mesh_intelligence.invalid_json_count, 0))
    Write-Kv "AI schema invalid" (First-Value @($Overview.ai_mesh_intelligence.schema_invalid_count, 0))
    Write-Kv "AI repaired JSON" (First-Value @($Overview.ai_mesh_intelligence.repaired_json_count, 0))
    Write-Kv "AI fallback count" (First-Value @($Overview.ai_mesh_intelligence.fallback_count, 0))
    Write-Kv "AI valid JSON rate" (First-Value @($Overview.ai_mesh_intelligence.valid_json_rate, 0))
    Write-Kv "AI skipped cached" (First-Value @($Overview.ai_mesh_intelligence.skipped_cached, 0))
    Write-Kv "AI skipped budget" (First-Value @($Overview.ai_mesh_intelligence.skipped_budget, 0))
    Write-Kv "AI-upgraded candidates" (First-Value @($Overview.ai_mesh_intelligence.candidates_upgraded_by_ai, 0))
    Write-Kv "AI kept-blocked candidates" (First-Value @($Overview.ai_mesh_intelligence.candidates_kept_blocked_by_ai, 0))
    Write-Kv "Latest AI error" (First-Value @($Overview.ai_mesh_intelligence.latest_ai_error, "none"))

    Write-Section "Execution"
    if ($null -ne $Overview.paper_session -and $null -ne $Overview.paper_session.active_session) {
        Write-Kv "Paper session" $Overview.paper_session.active_session.paper_session_id
        Write-Kv "Session balance start" $Overview.paper_session.active_session.starting_balance
        Write-Kv "Previous session archived" (First-Value @($Overview.paper_session.previous_session.paper_session_id, "none"))
    }
    Write-Kv "Paper intents" $Overview.execution.paper_intents
    Write-Kv "Paper orders" $Overview.execution.paper_orders
    Write-Kv "Paper fills" $Overview.execution.paper_fills
    Write-Kv "Paper positions" $Overview.execution.paper_positions
    Write-Kv "Open paper positions" $Overview.execution.open_paper_positions
    Write-Kv "Live orders" $Overview.execution.live_orders
    Write-Kv "Shadow orders" $Overview.execution.shadow_orders
    Write-Kv "Real orders" $Overview.execution.real_orders
    Write-Kv "Canonical positions" $Overview.execution.canonical_positions

    Write-Section "PnL"
    Write-Kv "Realized" $Overview.pnl.realized
    Write-Kv "Unrealized" $Overview.pnl.unrealized
    Write-Kv "Daily" $Overview.pnl.daily
    Write-Kv "PnL status" $Overview.pnl.status

    if ($Full) {
        Write-Section "Blockers and Errors"
        if ($null -ne $Overview.decisions.top_blockers -and $Overview.decisions.top_blockers.Count -gt 0) {
            Write-Kv "Top blockers" ($Overview.decisions.top_blockers -join "; ")
        } else {
            Write-Kv "Top blockers" "none reported"
        }
        if ($null -ne $Overview.decisions.top_runtime_decisions -and $Overview.decisions.top_runtime_decisions.Count -gt 0) {
            $runtimeDecisionSummary = @()
            foreach ($decision in $Overview.decisions.top_runtime_decisions) {
                $runtimeDecisionSummary += ("{0} {1} {2} score={3} ob_age={4}s refresh={5} final={6}" -f $decision.market_id, $decision.side, $decision.decision, $decision.opportunity_score, (First-Value @($decision.orderbook_age_seconds, "n/a")), (First-Value @($decision.last_mile_refresh_state, "n/a")), (($decision.blockers_json -join ",")))
            }
            Write-Kv "Top runtime decisions" ($runtimeDecisionSummary -join "; ")
        } else {
            Write-Kv "Top runtime decisions" "none reported"
        }
        if ($null -ne $Overview.decisions.top_unique_runtime_decisions -and $Overview.decisions.top_unique_runtime_decisions.Count -gt 0) {
            $uniqueDecisionSummary = @()
            foreach ($decision in $Overview.decisions.top_unique_runtime_decisions) {
                $uniqueDecisionSummary += ("{0} {1} {2} score={3} ob_age={4}s ttl={5}s refresh={6}" -f $decision.market_id, $decision.side, $decision.decision, $decision.opportunity_score, (First-Value @($decision.orderbook_age_seconds, "n/a")), (First-Value @($decision.orderbook_ttl_seconds, "n/a")), (First-Value @($decision.last_mile_refresh_state, "n/a")))
            }
            Write-Kv "Top unique decisions" ($uniqueDecisionSummary -join "; ")
        } else {
            Write-Kv "Top unique decisions" "none reported"
        }
        if ($null -ne $Overview.ai_mesh_intelligence.recent_insights -and $Overview.ai_mesh_intelligence.recent_insights.Count -gt 0) {
            $aiSummary = @()
            foreach ($insight in $Overview.ai_mesh_intelligence.recent_insights) {
                $why = ""
                if ($null -ne $insight.why_not_json -and $insight.why_not_json.Count -gt 0) {
                    $why = " why_not=" + ($insight.why_not_json -join ",")
                }
                $aiSummary += ("{0} {1} {2} action={3}{4}" -f $insight.insight_type, (First-Value @($insight.market_id, "event")), (First-Value @($insight.side, "")), $insight.recommended_mesh_action, $why)
            }
            Write-Kv "Recent AI insights" ($aiSummary -join "; ")
        } else {
            Write-Kv "Recent AI insights" "none reported"
        }
        if ($null -ne $Overview.ai_mesh_intelligence.top_why_not_reasons -and $Overview.ai_mesh_intelligence.top_why_not_reasons.Count -gt 0) {
            Write-Kv "AI why-not" ($Overview.ai_mesh_intelligence.top_why_not_reasons -join "; ")
        } else {
            Write-Kv "AI why-not" "none reported"
        }
        if ($null -ne $Overview.decisions.top_duplicate_blockers_by_market_side -and $Overview.decisions.top_duplicate_blockers_by_market_side.Count -gt 0) {
            Write-Kv "Duplicate market/sides" ($Overview.decisions.top_duplicate_blockers_by_market_side -join "; ")
        } else {
            Write-Kv "Duplicate market/sides" "none reported"
        }
        if ($null -ne $Overview.stale_components -and $Overview.stale_components.Count -gt 0) {
            Write-Kv "Stale components" ($Overview.stale_components -join ", ")
        } else {
            Write-Kv "Stale components" "none reported"
        }
        if ($null -ne $Overview.disconnected_services -and $Overview.disconnected_services.Count -gt 0) {
            Write-Kv "Disconnected services" ($Overview.disconnected_services -join ", ")
        } else {
            Write-Kv "Disconnected services" "none reported"
        }
        if ($null -ne $Overview.errors -and $Overview.errors.Count -gt 0) {
            Write-Kv "Latest errors" ($Overview.errors -join "; ")
        } else {
            Write-Kv "Latest errors" "none reported"
        }
        try {
            $delta = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/paper-delta-autopsy"
            Write-Kv "Paper delta classification" (($delta.items | Select-Object -First 5 | ForEach-Object { "$($_.table)=$($_.classification)" }) -join "; ")
        } catch {
            Write-Kv "Paper delta classification" "unavailable: $($_.Exception.Message)"
        }
        try {
            $paperIntents = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/paper-intents?limit=10"
            $idempotency = $paperIntents.paper_intent_gate_idempotency
            if ($null -ne $idempotency) {
                Write-Kv "Intent duplicate eligibility" ("encountered={0}; reused={1}; skipped={2}; crash_prevented={3}" -f (First-Value @($idempotency.duplicate_eligibility_encountered, 0)), (First-Value @($idempotency.existing_intent_reused, 0)), (First-Value @($idempotency.duplicate_skipped_safely, 0)), (First-Value @($idempotency.duplicate_crash_prevented, $false)))
            } else {
                Write-Kv "Intent duplicate eligibility" "none reported"
            }
        } catch {
            Write-Kv "Intent duplicate eligibility" "unavailable: $($_.Exception.Message)"
        }
        try {
            $enter = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/decision-autopsy/enter?limit=5"
            Write-Kv "ENTER lifecycle" (($enter.items | ForEach-Object { "$($_.market_id) $($_.side) intent=$($_.paper_lifecycle.intent_id) position=$($_.paper_lifecycle.position_id) suspect=$($_.is_bug_suspect)" }) -join "; ")
        } catch {
            Write-Kv "ENTER lifecycle" "unavailable: $($_.Exception.Message)"
        }
        try {
            $hunting = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/hunting-autopsy"
            Write-Kv "Hunting verdict" ("runtime={0}; hunting={1}; lifecycle={2}; bottleneck={3}" -f $hunting.runtime_continuity_verdict, $hunting.hunting_verdict, $hunting.trade_lifecycle_verdict, $hunting.primary_bottleneck)
        } catch {
            Write-Kv "Hunting verdict" "unavailable: $($_.Exception.Message)"
        }
        Write-Host "Run .\tools\polybot.ps1 blockers -limit 20 for full blocker breakdown."
    }

    Write-Section "Next"
    Write-Host $Overview.next_recommended_action
}

function Write-PaperSession {
    param([object]$Session)
    Write-Section "Paper Session"
    Write-Kv "Status" $Session.status
    if ($null -ne $Session.active_session) {
        Write-Kv "Active session" $Session.active_session.paper_session_id
        Write-Kv "Starting balance" $Session.active_session.starting_balance
        Write-Kv "Session status" $Session.active_session.status
        Write-Kv "Defense level" (First-Value @($Session.active_session.defense_level, $Session.paper_defense.defense_level, "100"))
        Write-Kv "Learning report path" (First-Value @($Session.active_session.session_learning_report_path, "none"))
    } else {
        Write-Kv "Active session" "none"
    }
    Write-Kv "Current paper intents" (First-Value @($Session.current_session_counts.paper_intents, 0))
    Write-Kv "Current paper orders" (First-Value @($Session.current_session_counts.paper_orders, 0))
    Write-Kv "Current paper fills" (First-Value @($Session.current_session_counts.paper_fills, 0))
    Write-Kv "Current paper positions" (First-Value @($Session.current_session_counts.paper_positions, 0))
    Write-Kv "Open paper positions" (First-Value @($Session.current_session_counts.open_paper_positions, 0))
    Write-Kv "Session realized PnL" (First-Value @($Session.current_session_pnl.realized, 0))
    Write-Kv "Session unrealized PnL" (First-Value @($Session.current_session_pnl.unrealized, 0))
    Write-Kv "Session net PnL" (First-Value @($Session.current_session_pnl.net, 0))
    Write-Kv "Historical paper intents" (First-Value @($Session.historical_totals.paper_intents, 0))
    Write-Kv "Historical paper orders" (First-Value @($Session.historical_totals.paper_orders, 0))
    Write-Kv "Historical paper fills" (First-Value @($Session.historical_totals.paper_fills, 0))
    Write-Kv "Historical paper positions" (First-Value @($Session.historical_totals.paper_positions, 0))
    if ($null -ne $Session.previous_session_summary) {
        Write-Kv "Previous session" $Session.previous_session_summary.paper_session_id
        Write-Kv "Previous report path" (First-Value @($Session.previous_session_summary.reset_report_path, "none"))
    }
}

function Write-PaperDefense {
    param([object]$Defense)
    Write-Section "Paper Defense"
    Write-Kv "Status" $Defense.status
    Write-Kv "Active session" (First-Value @($Defense.active_session_id, "none"))
    Write-Kv "Defense level" (First-Value @($Defense.defense_level, "100"))
    Write-Kv "Base paper threshold" (First-Value @($Defense.threshold_scaling.base_paper_threshold, $Defense.defense_profile.base_threshold, "60"))
    Write-Kv "Adjusted paper threshold" (First-Value @($Defense.threshold_scaling.adjusted_paper_threshold, $Defense.defense_profile.adjusted_threshold, "60"))
    Write-Kv "Max deployed capital" (First-Value @($Defense.capital_scaling.max_deployed_pct, $Defense.defense_profile.max_deployed_pct, "20"))
    Write-Kv "Max single trade" (First-Value @($Defense.capital_scaling.max_single_trade_pct, $Defense.defense_profile.max_single_trade_pct, "2"))
    Write-Kv "Max open positions" (First-Value @($Defense.capital_scaling.max_open_positions, $Defense.defense_profile.max_open_positions, "2"))
    Write-Kv "Exit fallback" (First-Value @($Defense.defense_profile.exit_fallback_enabled, "false"))
    Write-Kv "Strategic blockers" (First-Value @($Defense.defense_profile.strategic_blocker_mode, "HARD"))
    Write-Kv "Integrity blockers" (First-Value @($Defense.defense_profile.integrity_blocker_mode, "HARD"))
    Write-Section "Learning"
    Write-Kv "Learning entries" (First-Value @($Defense.learning_counts.learning_entries, 0))
    Write-Kv "Ignored blockers" (First-Value @($Defense.learning_counts.ignored_blockers, 0))
    Write-Kv "Softened blockers" (First-Value @($Defense.learning_counts.softened_blockers, 0))
    Write-Kv "Fallback exits" (First-Value @($Defense.learning_counts.fallback_exits, 0))
}

function Write-AutopsySummary {
    param([object]$Payload)
    Write-Section "Decision Autopsy"
    Write-Kv "Active Paper Session" (First-Value @($Payload.active_paper_session_id, "none"))
    Write-Kv "Autopsies" (First-Value @($Payload.count, 0))
    if ($null -ne $Payload.items -and $Payload.items.Count -gt 0) {
        foreach ($item in ($Payload.items | Select-Object -First 8)) {
            Write-Host ("- {0} {1} {2} score={3} stopped_at={4} blockers={5}" -f $item.market_id, $item.side, $item.action, $item.score, $item.lifecycle_stopped_at, (($item.blocker_codes | Select-Object -First 4) -join ","))
        }
    }
}

function Write-BlockerAutopsy {
    param([object]$Payload)
    Write-Section ("Top {0} Blockers" -f (First-Value @($Payload.limit, 20)))
    if ($null -eq $Payload.top_blockers -or $Payload.top_blockers.Count -eq 0) {
        Write-Kv "Top blockers" "none reported"
        return
    }
    $rank = 1
    foreach ($item in $Payload.top_blockers) {
        $example = $item.example
        Write-Host ("{0}. {1}" -f $rank, $item.blocker_code)
        Write-Host ("   Count: {0}" -f $item.count)
        Write-Host ("   Gate: {0}" -f (First-Value @($item.blocking_gate, $item.blocking_organ, "UNMAPPED")))
        Write-Host ("   Type: {0}" -f (First-Value @($item.blocker_type, $item.severity, "UNKNOWN")))
        Write-Host ("   Expected: {0}" -f (First-Value @($item.expected_vs_suspicious, $item.expected, "UNKNOWN")))
        Write-Host ("   Meaning: {0}" -f (First-Value @($item.plain_english_meaning, $item.meaning, "UNMAPPED")))
        Write-Host ("   Example: market {0} {1} score={2}" -f (First-Value @($example.market_id, "UNKNOWN")), (First-Value @($example.side, "UNKNOWN")), (First-Value @($example.score, "UNKNOWN")))
        Write-Host ("   Required/missing: {0}" -f (First-Value @($item.required_value_or_missing_requirement, "UNKNOWN")))
        Write-Host ("   What would make actionable: {0}" -f (First-Value @($item.what_would_make_actionable, "UNKNOWN")))
        Write-Host ("   Current active session: {0}" -f (First-Value @($item.affects_current_active_paper_session, "UNKNOWN")))
        Write-Host ("   Latest runtime cycle: {0}" -f (First-Value @($item.appeared_in_latest_runtime_cycle, "UNKNOWN")))
        Write-Host ("   Trend: {0}" -f (First-Value @($item.trend, "UNKNOWN")))
        $rank += 1
    }
}

function Write-EnterAutopsy {
    param([object]$Payload)
    Write-Section "ENTER Autopsy"
    Write-Kv "ENTER records" (First-Value @($Payload.count, 0))
    foreach ($item in (($Payload.items | Select-Object -First 10))) {
        $life = $item.paper_lifecycle
        Write-Host ("- {0} {1} score={2} final={3} intent={4} order={5} fill={6} position={7} close={8} suspect={9}" -f $item.market_id, $item.side, $item.score, $item.final_status, (First-Value @($life.intent_id, "NO")), (First-Value @($life.order_id, "NO")), (First-Value @($life.fill_id, "NO")), (First-Value @($life.position_id, "NO")), (First-Value @($life.position_close_id, "NO")), $item.is_bug_suspect)
    }
}

function Write-SupervisorAutopsy {
    param([object]$Payload)
    Write-Section "Supervisor Autopsy"
    Write-Kv "Supervisor state" $Payload.supervisor_state
    Write-Kv "Blocks paper entries" $Payload.blocks_paper_entries
    if ($null -ne $Payload.degraded_reasons -and $Payload.degraded_reasons.Count -gt 0) {
        Write-Kv "Reasons" ($Payload.degraded_reasons -join "; ")
    } else {
        Write-Kv "Reasons" "none reported"
    }
    Write-Kv "Explanation" $Payload.explanation
}

function Write-PaperDeltaAutopsy {
    param([object]$Payload)
    Write-Section "Paper Delta Autopsy"
    Write-Kv "Runtime mode" $Payload.runtime_mode
    Write-Kv "Expected activity in latest errors" $Payload.latest_errors_should_include_expected_paper_activity
    foreach ($item in (($Payload.items | Select-Object -First 10))) {
        Write-Host ("- {0}: {1} severity={2} deltas={3}" -f $item.table, $item.classification, $item.severity, ($item.deltas | ConvertTo-Json -Compress))
    }
}

function Write-HuntingAutopsy {
    param([object]$Payload)
    Write-Section "Hunting Autopsy"
    Write-Kv "Runtime continuity" $Payload.runtime_continuity_verdict
    Write-Kv "Hunting verdict" $Payload.hunting_verdict
    Write-Kv "Trade lifecycle" $Payload.trade_lifecycle_verdict
    Write-Kv "Primary bottleneck" $Payload.primary_bottleneck
    Write-Kv "Repair needed" $Payload.repair_needed
    Write-Kv "Evidence" $Payload.evidence_for_bottleneck
    Write-Kv "Active session" (First-Value @($Payload.active_paper_session_id, "none"))
    Write-Kv "Current active cycle" (First-Value @($Payload.runtime_truth.current_active_cycle_id, "none"))
    Write-Kv "Latest completed cycle" (First-Value @($Payload.runtime_truth.latest_completed_cycle_id, "none"))
    Write-Kv "Open cycles" (First-Value @($Payload.runtime_truth.open_cycles, 0))
    Write-Kv "Stale open cycles" (First-Value @($Payload.runtime_truth.stale_open_cycles, 0))
    Write-Kv "Decision markets" (First-Value @($Payload.decision_diversity.unique_markets, 0))
    Write-Kv "Decision market/sides" (First-Value @($Payload.decision_diversity.unique_market_sides, 0))
    Write-Kv "ENTER count" (First-Value @($Payload.decision_diversity.enter_count, 0))
    if ($null -ne $Payload.hunting_progression -and $Payload.hunting_progression.Count -gt 0) {
        foreach ($window in $Payload.hunting_progression) {
            Write-Host ("- {0}: events={1} triggers={2} candidates={3} mesh={4} runtime_runs={5} gate_runs={6} intents={7} orders={8} closes={9}" -f $window.window, $window.events_touched, $window.triggers_touched, $window.candidates_touched, $window.mesh_reviews_touched, $window.runtime_decision_runs, $window.intent_gate_runs, $window.paper_intents_created, $window.paper_orders_created, $window.paper_closes_created)
        }
    }
    if ($null -ne $Payload.decision_diversity.opposing_enter_markets -and $Payload.decision_diversity.opposing_enter_markets.Count -gt 0) {
        Write-Kv "Opposing ENTER markets" (($Payload.decision_diversity.opposing_enter_markets | ForEach-Object { "$($_.market_id):$($_.sides -join '/')" }) -join "; ")
    } else {
        Write-Kv "Opposing ENTER markets" "none reported"
    }
    if ($null -ne $Payload.decision_diversity.top_blockers -and $Payload.decision_diversity.top_blockers.Count -gt 0) {
        Write-Kv "Top blockers" ($Payload.decision_diversity.top_blockers -join "; ")
    }
    Write-Kv "Recommended next action" $Payload.recommended_next_action
}

function Write-ArbitrationAutopsy {
    param([object]$Payload)
    Write-Section "Same-Market Arbitration Autopsy"
    Write-Kv "Active Paper Session" (First-Value @($Payload.active_paper_session_id, "none"))
    Write-Kv "Total conflicts" (First-Value @($Payload.counts.total_conflicts, 0))
    Write-Kv "Resolved conflicts" (First-Value @($Payload.counts.resolved_conflicts, 0))
    Write-Kv "Unresolved conflicts" (First-Value @($Payload.counts.unresolved_conflicts, 0))
    Write-Kv "Tie-broken conflicts" (First-Value @($Payload.counts.tie_broken_count, 0))
    if ($null -eq $Payload.items -or $Payload.items.Count -eq 0) {
        Write-Kv "Latest arbitration" "none reported"
        return
    }
    foreach ($item in ($Payload.items | Select-Object -First 10)) {
        Write-Host ("- market={0} defense={1} YES={2}/{3} NO={4}/{5} selected={6} rejected={7} margin={8} required={9} outcome={10}" -f `
            $item.market_id, $item.defense_level, $item.yes_score, $item.yes_arbitration_score, $item.no_score, $item.no_arbitration_score, `
            (First-Value @($item.selected_side, "NONE")), (First-Value @($item.rejected_side, "NONE")), `
            (First-Value @($item.margin, "n/a")), (First-Value @($item.required_margin, "n/a")), $item.outcome)
        Write-Host ("  Reason: {0}" -f (First-Value @($item.reason, "none reported")))
        if ($null -ne $item.tie_breaker_used -and "$($item.tie_breaker_used)" -ne "") {
            Write-Host ("  Tie breaker: {0}" -f $item.tie_breaker_used)
        }
    }
}

function Write-SideEvidence {
    param([object]$Payload)
    Write-Section "Side Evidence"
    Write-Kv "Status" (First-Value @($Payload.status, "UNKNOWN"))
    Write-Kv "Trusted links with side" (First-Value @($Payload.trusted_links_with_matched_side, 0))
    Write-Kv "Bindings with side" (First-Value @($Payload.bindings_with_matched_side, 0))
    Write-Kv "Side conflicts" (First-Value @($Payload.side_conflicts, 0))
    if ($null -eq $Payload.arbitration_side_evidence -or $Payload.arbitration_side_evidence.Count -eq 0) {
        Write-Kv "Arbitration side evidence" "none reported"
        return
    }
    foreach ($item in ($Payload.arbitration_side_evidence | Select-Object -First 10)) {
        Write-Host ("- market={0} defense={1} YES={2}/{3} NO={4}/{5} selected={6} rejected={7} outcome={8}" -f `
            $item.market_id, $item.defense_level, `
            (First-Value @($item.yes_side_evidence_score, "n/a")), (First-Value @($item.yes_evidence_quality, "UNKNOWN")), `
            (First-Value @($item.no_side_evidence_score, "n/a")), (First-Value @($item.no_evidence_quality, "UNKNOWN")), `
            (First-Value @($item.selected_side, "NONE")), (First-Value @($item.rejected_side, "NONE")), $item.outcome)
        if ($null -ne $item.tie_breaker_used -and "$($item.tie_breaker_used)" -ne "") {
            Write-Host ("  Tie breaker: {0}" -f $item.tie_breaker_used)
        }
        if ($null -ne $item.missing_side_evidence_json -and $item.missing_side_evidence_json.Count -gt 0) {
            Write-Host ("  Missing: {0}" -f (($item.missing_side_evidence_json | Select-Object -First 5) -join "; "))
        }
    }
}

function Write-OpportunityMesh {
    param([object]$Payload)
    Write-Section "Opportunity Mesh"
    Write-Kv "Active session" (First-Value @($Payload.active_paper_session_id, "none"))
    Write-Kv "Active pool size" (First-Value @($Payload.summary.active_pool_size, 0))
    Write-Kv "Ready for intent" (First-Value @($Payload.summary.ready_for_intent, 0))
    Write-Kv "Intent pending execution" (First-Value @($Payload.summary.intent_pending_execution, 0))
    Write-Kv "Intent stuck" (First-Value @($Payload.summary.intent_stuck, 0))
    Write-Kv "Intent expired" (First-Value @($Payload.summary.intent_expired, 0))
    Write-Kv "Intent cancelled" (First-Value @($Payload.summary.intent_cancelled, 0))
    Write-Kv "Blocked integrity" (First-Value @($Payload.summary.blocked_integrity, 0))
    Write-Kv "Blocked strategic" (First-Value @($Payload.summary.blocked_strategic, 0))
    Write-Kv "Softened by defense" (First-Value @($Payload.summary.softened_by_defense, 0))
    Write-Kv "Arbitrated demoted" (First-Value @($Payload.summary.arbitrated_demoted, 0))
    Write-Kv "Skipped duplicate" (First-Value @($Payload.summary.skipped_duplicate, 0))
    Write-Kv "Routed to execution" (First-Value @($Payload.summary.routed_to_execution, 0))
    Write-Kv "Routed to exit" (First-Value @($Payload.summary.routed_to_exit, 0))
    Write-Kv "System errors" (First-Value @($Payload.summary.system_errors, 0))
    if ($null -ne $Payload.items -and $Payload.items.Count -gt 0) {
        foreach ($item in ($Payload.items | Select-Object -First 12)) {
            Write-Host ("- {0} {1} decision={2} state={3} next={4} policy={5} reason={6}" -f `
                (First-Value @($item.market_id, "UNKNOWN")), (First-Value @($item.side, "UNKNOWN")), `
                (First-Value @($item.decision, "UNKNOWN")), $item.lifecycle_state, $item.next_action, $item.consumption_policy, `
                (First-Value @($item.status_reason, "none")))
        }
    }
}

function Write-IntentQueue {
    param([object]$Payload)
    Write-Section "Intent Queue"
    Write-Kv "Active session" (First-Value @($Payload.active_paper_session_id, "none"))
    Write-Kv "Stuck intents" (First-Value @($Payload.stuck_count, 0))
    Write-Kv "Expired intents" (First-Value @($Payload.counts.INTENT_EXPIRED, $Payload.counts.EXPIRED_NO_EXECUTION, 0))
    Write-Kv "Cancelled intents" (First-Value @($Payload.counts.INTENT_CANCELLED, 0))
    if ($null -eq $Payload.items -or $Payload.items.Count -eq 0) {
        Write-Kv "Current session intents" "none"
        return
    }
    foreach ($item in ($Payload.items | Select-Object -First 20)) {
        Write-Host ("- {0} {1} {2} status={3} age={4}s exec={5} stuck={6} expired={7} reason={8} price_source={9} fallback={10} memory={11} order={12} fill={13} position={14}" -f `
            $item.paper_intent_id, $item.market_id, $item.side, $item.intent_status, $item.age_seconds, $item.execution_status, `
            $item.stuck, (First-Value @($item.expired, $false)), (First-Value @($item.intent_lifecycle_reason, $item.execution_block_reason, "none")), `
            (First-Value @($item.execution_price_source, "none")), (First-Value @($item.fallback_reason, $item.fallback_source, "none")), `
            (First-Value @($item.opportunity_memory_id, "none")), `
            (First-Value @($item.order_id, "NO")), (First-Value @($item.fill_id, "NO")), (First-Value @($item.position_id, "NO")))
    }
}

function Write-ExpiredIntents {
    param([object]$Payload)
    Write-Section "Expired Intents"
    Write-Kv "Active session" (First-Value @($Payload.active_paper_session_id, "none"))
    Write-Kv "Policy max pending seconds" (First-Value @($Payload.policy.paper_intent_max_pending_seconds, "unknown"))
    if ($null -ne $Payload.counts) {
        foreach ($prop in $Payload.counts.PSObject.Properties) {
            Write-Kv $prop.Name $prop.Value
        }
    }
    if ($null -eq $Payload.items -or $Payload.items.Count -eq 0) {
        Write-Kv "Expired intent rows" "none"
        return
    }
    foreach ($item in ($Payload.items | Select-Object -First 20)) {
        Write-Host ("- {0} {1} {2} status={3} expired={4} reason={5} memory={6}" -f `
            $item.paper_intent_id, $item.market_id, $item.side, $item.intent_status, `
            (First-Value @($item.expired_at, $item.cancelled_at, "n/a")), `
            (First-Value @($item.intent_lifecycle_reason, "none")), `
            (First-Value @($item.opportunity_memory_id, "none")))
    }
}

function Write-OpportunityMemory {
    param([object]$Payload)
    Write-Section "Opportunity Memory"
    Write-Kv "Active session" (First-Value @($Payload.active_paper_session_id, "none"))
    Write-Kv "Memory enabled" (First-Value @($Payload.policy.paper_opportunity_memory_enabled, "unknown"))
    Write-Kv "Requires new evidence" (First-Value @($Payload.policy.paper_opportunity_reactivation_requires_new_evidence, "unknown"))
    if ($null -ne $Payload.counts) {
        foreach ($prop in $Payload.counts.PSObject.Properties) {
            Write-Kv $prop.Name $prop.Value
        }
    }
    if ($null -eq $Payload.items -or $Payload.items.Count -eq 0) {
        Write-Kv "Remembered opportunities" "none"
        return
    }
    foreach ($item in ($Payload.items | Select-Object -First 20)) {
        Write-Host ("- {0} {1} {2} status={3} score={4} react={5} reason={6}" -f `
            $item.opportunity_memory_id, $item.market_id, $item.side, $item.status, `
            (First-Value @($item.last_score, "n/a")), `
            (First-Value @($item.reactivation_count, 0)), `
            (First-Value @($item.last_reason, "none")))
    }
}

function Write-CandidateConsumption {
    param([object]$Payload)
    Write-Section "Candidate Consumption"
    Write-Kv "Active session" (First-Value @($Payload.active_paper_session_id, "none"))
    Write-Kv "Candidates consumed" (First-Value @($Payload.candidate_consumption.candidates_consumed, 0))
    Write-Kv "Created intents" (First-Value @($Payload.candidate_consumption.created_intents, 0))
    Write-Kv "Skipped duplicate" (First-Value @($Payload.candidate_consumption.skipped_duplicate, 0))
    Write-Kv "Skipped blocked" (First-Value @($Payload.candidate_consumption.skipped_blocked, 0))
    Write-Kv "Routed to execution" (First-Value @($Payload.candidate_consumption.routed_to_execution, 0))
    Write-Kv "Routed to exit" (First-Value @($Payload.candidate_consumption.routed_to_exit, 0))
    Write-Kv "Retry later" (First-Value @($Payload.candidate_consumption.retry_later, 0))
    Write-Kv "Intent stuck" (First-Value @($Payload.candidate_consumption.intent_stuck, 0))
    Write-Kv "System errors" (First-Value @($Payload.candidate_consumption.system_errors, 0))
    if ($null -ne $Payload.items -and $Payload.items.Count -gt 0) {
        foreach ($item in ($Payload.items | Select-Object -First 12)) {
            Write-Host ("- {0} {1} state={2} policy={3} next={4} reason={5}" -f `
                (First-Value @($item.market_id, "UNKNOWN")), (First-Value @($item.side, "UNKNOWN")), `
                $item.lifecycle_state, $item.consumption_policy, $item.next_action, (First-Value @($item.status_reason, "none")))
        }
    }
}

$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$script:BaseUrl = Get-ArgValue -Args $Rest -Names @("-BaseUrl", "--base-url", "-base-url", "-url", "--url") -Default "http://localhost:8000"
$UnicodeDashMode = ([char]0x2013) + "mode"
$Mode = (Get-ArgValue -Args $Rest -Names @("-mode", "--mode", $UnicodeDashMode) -Default "paper").ToLowerInvariant()
$IntervalSeconds = [int](Get-ArgValue -Args $Rest -Names @("-interval", "--interval", "-interval-seconds", "--interval-seconds") -Default "30")
$Balance = [decimal](Get-ArgValue -Args $Rest -Names @("-balance", "--balance") -Default "1000")
$Defense = if ($DefenseLevel -ge 0) { $DefenseLevel } else { [int](Get-ArgValue -Args $Rest -Names @("-defense", "--defense") -Default "-1") }
$NormalizedCommand = $Command.ToLowerInvariant()

try {
    switch ($NormalizedCommand) {
        "health" {
            Write-Section "POLYBOT Health"
            $healthz = Invoke-PolybotJson -Method "GET" -Path "/healthz"
            Write-Kv "/healthz" $healthz.status
            try {
                $runtime = Invoke-PolybotJson -Method "GET" -Path "/runtime/health"
                Write-Kv "/runtime/health" (First-Value @($runtime.status, $runtime.runtime_state, "OK"))
                Write-Kv "Current mode" (First-Value @($runtime.current_mode, $runtime.runtime_mode, "UNKNOWN"))
            } catch {
                Write-Kv "/runtime/health" "ERROR: $($_.Exception.Message)"
            }
            $overview = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/system-overview"
            Write-Kv "API reachable" "YES"
            Write-Kv "DB status" $overview.database.status
            Write-Kv "Execution mode" $overview.execution_mode
        }
        "status" {
            $overview = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/system-overview"
            Write-Status -Overview $overview
        }
        "report" {
            Write-Section "POLYBOT Full Report"
            try {
                $healthz = Invoke-PolybotJson -Method "GET" -Path "/healthz"
                Write-Kv "/healthz" $healthz.status
            } catch {
                Write-Kv "/healthz" "ERROR: $($_.Exception.Message)"
            }
            try {
                $runtime = Invoke-PolybotJson -Method "GET" -Path "/runtime/health"
                Write-Kv "/runtime/health" (First-Value @($runtime.status, $runtime.runtime_state, "OK"))
            } catch {
                Write-Kv "/runtime/health" "ERROR: $($_.Exception.Message)"
            }
            $overview = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/system-overview"
            Write-Status -Overview $overview -Full
            try {
                $defense = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/paper-defense"
                Write-PaperDefense -Defense $defense
            } catch {
                Write-Kv "Paper defense" "unavailable: $($_.Exception.Message)"
            }
            try {
                $arbitration = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/arbitration-autopsy?limit=5"
                Write-ArbitrationAutopsy -Payload $arbitration
            } catch {
                Write-Kv "Same-market arbitration" "unavailable: $($_.Exception.Message)"
            }
            try {
                $sideEvidence = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/side-evidence?limit=5"
                Write-SideEvidence -Payload $sideEvidence
            } catch {
                Write-Kv "Side evidence" "unavailable: $($_.Exception.Message)"
            }
            try {
                $mesh = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/opportunity-mesh?limit=25"
                Write-OpportunityMesh -Payload $mesh
            } catch {
                Write-Kv "Opportunity mesh" "unavailable: $($_.Exception.Message)"
            }
            try {
                $queue = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/intent-queue?limit=25"
                Write-IntentQueue -Payload $queue
            } catch {
                Write-Kv "Intent queue" "unavailable: $($_.Exception.Message)"
            }
            try {
                $memory = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/opportunity-memory?limit=10"
                Write-OpportunityMemory -Payload $memory
            } catch {
                Write-Kv "Opportunity memory" "unavailable: $($_.Exception.Message)"
            }
            try {
                $expired = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/expired-intents?limit=10"
                Write-ExpiredIntents -Payload $expired
            } catch {
                Write-Kv "Expired intents" "unavailable: $($_.Exception.Message)"
            }
        }
        "paper-session-status" {
            $session = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/paper-session"
            Write-PaperSession -Session $session
        }
        "paper-session-history" {
            $history = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/paper-session/history"
            Write-Section "Paper Session History"
            Write-Kv "Status" $history.status
            if ($null -ne $history.sessions) {
                foreach ($item in $history.sessions) {
                    Write-Host ("{0} {1} start={2} status={3} report={4}" -f $item.paper_session_id, $item.session_name, $item.starting_balance, $item.status, (First-Value @($item.reset_report_path, "")))
                }
            }
        }
        "autopsy" {
            $payload = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/decision-autopsy?limit=25"
            Write-AutopsySummary -Payload $payload
        }
        "blockers" {
            $limit = [int](Get-ArgValue -Args $Rest -Names @("-limit", "--limit") -Default "20")
            $payload = Invoke-PolybotJson -Method "GET" -Path ("/dashboard/api/v2/control/decision-autopsy/top-blockers?limit={0}" -f $limit)
            Write-BlockerAutopsy -Payload $payload
        }
        "enter-autopsy" {
            $payload = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/decision-autopsy/enter"
            Write-EnterAutopsy -Payload $payload
        }
        "closest-actionable" {
            $payload = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/decision-autopsy/closest-actionable"
            Write-AutopsySummary -Payload @{ active_paper_session_id = ""; count = $payload.items.Count; items = $payload.items }
        }
        "supervisor-autopsy" {
            $payload = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/supervisor-autopsy"
            Write-SupervisorAutopsy -Payload $payload
        }
        "paper-delta-autopsy" {
            $payload = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/paper-delta-autopsy"
            Write-PaperDeltaAutopsy -Payload $payload
        }
        "hunting-autopsy" {
            $payload = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/hunting-autopsy"
            Write-HuntingAutopsy -Payload $payload
        }
        "arbitration-autopsy" {
            $limit = [int](Get-ArgValue -Args $Rest -Names @("-limit", "--limit") -Default "20")
            $payload = Invoke-PolybotJson -Method "GET" -Path ("/dashboard/api/v2/control/arbitration-autopsy?limit={0}" -f $limit)
            Write-ArbitrationAutopsy -Payload $payload
        }
        "side-evidence" {
            $limit = [int](Get-ArgValue -Args $Rest -Names @("-limit", "--limit") -Default "20")
            $payload = Invoke-PolybotJson -Method "GET" -Path ("/dashboard/api/v2/control/side-evidence?limit={0}" -f $limit)
            Write-SideEvidence -Payload $payload
        }
        "opportunity-mesh" {
            $limit = [int](Get-ArgValue -Args $Rest -Names @("-limit", "--limit") -Default "100")
            $payload = Invoke-PolybotJson -Method "GET" -Path ("/dashboard/api/v2/control/opportunity-mesh?limit={0}" -f $limit)
            Write-OpportunityMesh -Payload $payload
        }
        "intent-queue" {
            $limit = [int](Get-ArgValue -Args $Rest -Names @("-limit", "--limit") -Default "100")
            $payload = Invoke-PolybotJson -Method "GET" -Path ("/dashboard/api/v2/control/intent-queue?limit={0}" -f $limit)
            Write-IntentQueue -Payload $payload
        }
        "candidate-consumption" {
            $limit = [int](Get-ArgValue -Args $Rest -Names @("-limit", "--limit") -Default "100")
            $payload = Invoke-PolybotJson -Method "GET" -Path ("/dashboard/api/v2/control/candidate-consumption?limit={0}" -f $limit)
            Write-CandidateConsumption -Payload $payload
        }
        "opportunity-memory" {
            $limit = [int](Get-ArgValue -Args $Rest -Names @("-limit", "--limit") -Default "100")
            $payload = Invoke-PolybotJson -Method "GET" -Path ("/dashboard/api/v2/control/opportunity-memory?limit={0}" -f $limit)
            Write-OpportunityMemory -Payload $payload
        }
        "expired-intents" {
            $limit = [int](Get-ArgValue -Args $Rest -Names @("-limit", "--limit") -Default "100")
            $payload = Invoke-PolybotJson -Method "GET" -Path ("/dashboard/api/v2/control/expired-intents?limit={0}" -f $limit)
            Write-ExpiredIntents -Payload $payload
        }
        "reset-paper-session" {
            Write-Section "Reset Paper Session"
            $localReportDir = New-LocalReportDir -Prefix "paper_session_reset_cli"
            try {
                $preSession = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/paper-session"
                Save-JsonReport -Path (Join-Path $localReportDir "pre_paper_session.json") -Payload $preSession
            } catch {
                Save-JsonReport -Path (Join-Path $localReportDir "pre_paper_session_error.json") -Payload @{ error = $_.Exception.Message }
            }
            try {
                $preOverview = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/system-overview"
                Save-JsonReport -Path (Join-Path $localReportDir "pre_system_overview.json") -Payload $preOverview
            } catch {
                Save-JsonReport -Path (Join-Path $localReportDir "pre_system_overview_error.json") -Payload @{ error = $_.Exception.Message }
            }
            $body = @{
                balance = $Balance
                start_after_reset = $false
                reason = "CLI official Paper session reset"
                created_by = "polybot-cli"
            }
            if ($Defense -ge 0) {
                $body["defense_level"] = $Defense
            }
            $result = Invoke-PolybotJson -Method "POST" -Path "/dashboard/api/v2/control/paper-session/reset" -Body $body
            Save-JsonReport -Path (Join-Path $localReportDir "reset_response.json") -Payload $result
            Write-Kv "Reset status" $result.status
            Write-Kv "Reset id" $result.reset_id
            Write-Kv "Previous session" $result.previous_session_id
            Write-Kv "New session" $result.new_session_id
            Write-Kv "Balance" $result.requested_balance
            Write-Kv "Closed positions" $result.closed_positions
            Write-Kv "Report dir" $result.report_dir
            Write-Kv "Local report dir" $localReportDir
            if ($result.status -ne "COMPLETED") {
                Write-Kv "Errors" (($result.errors + $result.warnings) -join "; ")
                exit 1
            }
            $session = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/paper-session"
            Save-JsonReport -Path (Join-Path $localReportDir "post_paper_session.json") -Payload $session
            try {
                $postOverview = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/system-overview"
                Save-JsonReport -Path (Join-Path $localReportDir "post_system_overview.json") -Payload $postOverview
            } catch {
                Save-JsonReport -Path (Join-Path $localReportDir "post_system_overview_error.json") -Payload @{ error = $_.Exception.Message }
            }
            Write-PaperSession -Session $session
        }
        "restart-paper-session" {
            Write-Section "Restart Paper Session"
            if ($Defense -ge 0) {
                & $PSCommandPath reset-paper-session -balance $Balance -defense $Defense -BaseUrl $script:BaseUrl
            } else {
                & $PSCommandPath reset-paper-session -balance $Balance -BaseUrl $script:BaseUrl
            }
            & $PSCommandPath health -BaseUrl $script:BaseUrl
            & $PSCommandPath on -mode paper -BaseUrl $script:BaseUrl -interval $IntervalSeconds
        }
        "paper-defense" {
            $defensePayload = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/paper-defense"
            Write-PaperDefense -Defense $defensePayload
        }
        "set-paper-defense" {
            $levelArg = if ($Rest.Count -gt 0 -and $Rest[0] -match '^\d+$') { [int]$Rest[0] } else { $Defense }
            if ($levelArg -lt 0 -or $levelArg -gt 100) {
                throw "Defense level must be 0..100."
            }
            $body = @{
                defense_level = $levelArg
                reason = "CLI PAPER defense update"
                actor = "polybot-cli"
            }
            $result = Invoke-PolybotJson -Method "POST" -Path "/dashboard/api/v2/control/paper-defense" -Body $body
            Write-PaperDefense -Defense $result
        }
        "paper-session-report" {
            $report = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/paper-session/learning-report"
            Write-Section "Paper Session Learning Report"
            Write-Kv "Status" $report.status
            Write-Kv "Schema" $report.schema_version
            Write-Kv "Session" $report.session_metadata.session_id
            Write-Kv "Defense level" $report.session_metadata.defense_level
            Write-Kv "Entries" $report.result_summary.number_of_entries
            Write-Kv "Exits" $report.result_summary.number_of_exits
            Write-Kv "Net PnL" $report.result_summary.net_pnl
            Write-Kv "JSON report" (First-Value @($report.report_paths.json, "none"))
            Write-Kv "Markdown report" (First-Value @($report.report_paths.md, "none"))
            Write-Kv "CSV report" (First-Value @($report.report_paths.csv, "none"))
        }
        "export-paper-session" {
            $format = (Get-ArgValue -Args $Rest -Names @("-format", "--format") -Default "json").ToLowerInvariant()
            $export = Invoke-PolybotJson -Method "GET" -Path ("/dashboard/api/v2/control/paper-session/export?format={0}" -f $format)
            Write-Section "Paper Session Export"
            Write-Kv "Status" $export.status
            Write-Kv "Format" $export.format
            Write-Kv "Path" $export.path
        }
        "on" {
            if ($Mode -ne "paper") {
                throw "Only -mode paper is supported by this safety wrapper. LIVE and SHADOW are intentionally unavailable."
            }
            $body = @{
                actor = "polybot-cli"
                reason = "CLI SYSTEM ON with execution_mode=PAPER paper adapter"
                interval_seconds = $IntervalSeconds
                metadata = @{
                    requested_execution_mode = "PAPER"
                    paper_adapter = $true
                    live_adapter = $false
                    cli = "tools/polybot.ps1"
                }
            }
            $on = Invoke-PolybotJson -Method "POST" -Path "/dashboard/api/v2/control/actions/system-on" -Body $body
            Write-Section "SYSTEM ON"
            Write-Kv "System action" $on.status
            if ($on.status -notin @("ACCEPTED")) {
                Write-Kv "Errors" (($on.errors + $on.warnings) -join "; ")
                exit 1
            }
            $paperBody = @{
                actor = "polybot-cli"
                reason = "CLI enables PAPER execution adapter after SYSTEM ON"
                metadata = @{
                    execution_mode = "PAPER"
                    live_adapter = $false
                    cli = "tools/polybot.ps1"
                }
            }
            $paper = Invoke-PolybotJson -Method "POST" -Path "/dashboard/api/v2/control/actions/enable-paper-simulation" -Body $paperBody
            Write-Kv "Paper adapter action" $paper.status
            Write-Kv "Live adapter" "DISABLED"
            $overview = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/system-overview"
            Write-Status -Overview $overview
        }
        "mode" {
            if ($Mode -ne "paper" -and $Rest.Count -gt 0) {
                $Mode = $Rest[0].ToLowerInvariant()
            }
            if ($Mode -ne "paper") {
                throw "Only paper mode is supported by this safety wrapper."
            }
            & $PSCommandPath on -mode paper -BaseUrl $script:BaseUrl -interval $IntervalSeconds
        }
        "off" {
            $body = @{
                actor = "polybot-cli"
                reason = "CLI SYSTEM OFF"
                metadata = @{
                    cli = "tools/polybot.ps1"
                    live_adapter = $false
                }
            }
            $off = Invoke-PolybotJson -Method "POST" -Path "/dashboard/api/v2/control/actions/system-off" -Body $body
            Write-Section "SYSTEM OFF"
            Write-Kv "System action" $off.status
            Write-Kv "Paper adapter" "DISABLED"
            Write-Kv "Live adapter" "DISABLED"
            $overview = Invoke-PolybotJson -Method "GET" -Path "/dashboard/api/v2/control/system-overview"
            Write-Status -Overview $overview
        }
        default {
            Write-Host "Usage:"
            Write-Host "  .\tools\polybot.ps1 status [-BaseUrl http://localhost:8000]"
            Write-Host "  .\tools\polybot.ps1 on -mode paper [-interval 30]"
            Write-Host "  .\tools\polybot.ps1 off"
            Write-Host "  .\tools\polybot.ps1 report"
            Write-Host "  .\tools\polybot.ps1 health"
            Write-Host "  .\tools\polybot.ps1 reset-paper-session -balance 1000"
            Write-Host "  .\tools\polybot.ps1 restart-paper-session -balance 1000 [-defense 20]"
            Write-Host "  .\tools\polybot.ps1 set-paper-defense 20"
            Write-Host "  .\tools\polybot.ps1 paper-defense"
            Write-Host "  .\tools\polybot.ps1 paper-session-report"
            Write-Host "  .\tools\polybot.ps1 export-paper-session [-format json|md|csv]"
            Write-Host "  .\tools\polybot.ps1 paper-session-status"
            Write-Host "  .\tools\polybot.ps1 paper-session-history"
            Write-Host "  .\tools\polybot.ps1 autopsy"
            Write-Host "  .\tools\polybot.ps1 blockers [-limit 20]"
            Write-Host "  .\tools\polybot.ps1 enter-autopsy"
            Write-Host "  .\tools\polybot.ps1 closest-actionable"
            Write-Host "  .\tools\polybot.ps1 supervisor-autopsy"
            Write-Host "  .\tools\polybot.ps1 paper-delta-autopsy"
            Write-Host "  .\tools\polybot.ps1 hunting-autopsy"
            Write-Host "  .\tools\polybot.ps1 arbitration-autopsy [-limit 20]"
            Write-Host "  .\tools\polybot.ps1 side-evidence [-limit 20]"
            Write-Host "  .\tools\polybot.ps1 opportunity-mesh [-limit 50]"
            Write-Host "  .\tools\polybot.ps1 intent-queue [-limit 50]"
            Write-Host "  .\tools\polybot.ps1 expired-intents [-limit 50]"
            Write-Host "  .\tools\polybot.ps1 opportunity-memory [-limit 50]"
            Write-Host "  .\tools\polybot.ps1 candidate-consumption [-limit 50]"
            exit 2
        }
    }
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
