# POLYBOT Overnight Observation Report

- status: RUNNING
- started_at: 2026-06-02T00:21:07.733724+00:00
- finished_at: NOT_COMPLETED
- samples: 0
- stop_reason: NONE

## Baseline
```json
{
  "mock_data": false,
  "status": "YELLOW",
  "blockers": [],
  "warnings": [
    "SAFE_YELLOW_AI_DEGRADED:['AI_CONTEXT_UNAVAILABLE', 'ANTHROPIC_DEGRADED', 'ANTHROPIC_ERROR', 'OLLAMA_TIMEOUT', 'OPENAI_ERROR', 'OPENAI_RATE_LIMITED']"
  ],
  "ai_required": false,
  "healthz": {
    "status": "ok",
    "app": "polybot",
    "ready": true
  },
  "runtime_health": {
    "overall_status": "SAFE_STOPPED",
    "current_mode": "PAPER",
    "system_power": "OFF",
    "runtime_work_allowed": false,
    "kill_switch_active": false,
    "cooldown_active": false,
    "attack_mode_active": false,
    "active_cycle": {
      "id": 10605,
      "cycle_id": "v2-20260531T173237-e77f241649",
      "mode": "PAPER",
      "status": "RUNNING",
      "started_at": "2026-05-31T17:32:37.973494+00:00",
      "finished_at": null,
      "duration_ms": null,
      "scanner_started": true,
      "scanner_finished": true,
      "intelligence_started": true,
      "intelligence_finished": false,
      "paper_started": false,
      "paper_finished": false,
      "shadow_started": false,
      "shadow_finished": false,
      "live_started": false,
      "live_finished": false,
      "blocked_by_mode": false,
      "error_count": 0,
      "warning_count": 0,
      "metadata_json": {
        "source": "market_service.refresh"
      }
    },
    "services": [
      {
        "id": 14,
        "service_name": "ai_brain",
        "service_type": "intelligence",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.754466+00:00",
        "updated_at": "2026-06-02T00:12:16.181122+00:00"
      },
      {
        "id": 29,
        "service_name": "capital_allocator",
        "service_type": "capital",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.984933+00:00",
        "updated_at": "2026-06-02T00:12:16.515432+00:00"
      },
      {
        "id": 26,
        "service_name": "context_capital_brains",
        "service_type": "brains",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.945136+00:00",
        "updated_at": "2026-06-02T00:12:16.394359+00:00"
      },
      {
        "id": 7,
        "service_name": "dashboard",
        "service_type": "api",
        "status": "STOPPED",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.658918+00:00",
        "updated_at": "2026-06-02T00:12:15.802027+00:00"
      },
      {
        "id": 13,
        "service_name": "data_foundation",
        "service_type": "data",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": "2026-06-01T22:30:59.754485+00:00",
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.739094+00:00",
        "updated_at": "2026-06-02T00:12:16.160415+00:00"
      },
      {
        "id": 10,
        "service_name": "event_bus",
        "service_type": "event_mesh",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.705316+00:00",
        "updated_at": "2026-06-02T00:12:16.084171+00:00"
      },
      {
        "id": 12,
        "service_name": "event_dispatcher",
        "service_type": "event_mesh",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.727903+00:00",
        "updated_at": "2026-06-02T00:12:16.140346+00:00"
      },
      {
        "id": 11,
        "service_name": "event_store",
        "service_type": "event_mesh",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.716652+00:00",
        "updated_at": "2026-06-02T00:12:16.108877+00:00"
      },
      {
        "id": 31,
        "service_name": "execution_cortex_v2",
        "service_type": "execution",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:30.009851+00:00",
        "updated_at": "2026-06-02T00:12:16.595237+00:00"
      },
      {
        "id": 32,
        "service_name": "exit_cortex_v2",
        "service_type": "exits",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:30.029034+00:00",
        "updated_at": "2026-06-02T00:12:16.658349+00:00"
      },
      {
        "id": 1,
        "service_name": "fastapi",
        "service_type": "api",
        "status": "RUNNING",
        "last_heartbeat_at": "2026-06-02T00:21:07.775448+00:00",
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {
          "health_source": "runtime_health_request"
        },
        "created_at": "2026-05-20T23:20:29.574688+00:00",
        "updated_at": "2026-06-02T00:21:07.775448+00:00"
      },
      {
        "id": 34,
        "service_name": "feedback_learning_loop",
        "service_type": "learning",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:30.052400+00:00",
        "updated_at": "2026-06-02T00:12:16.753816+00:00"
      },
      {
        "id": 5,
        "service_name": "intelligence_runtime",
        "service_type": "runtime",
        "status": "STOPPED",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.631520+00:00",
        "updated_at": "2026-06-02T00:12:15.735853+00:00"
      },
      {
        "id": 25,
        "service_name": "market_memory",
        "service_type": "memory",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.932573+00:00",
        "updated_at": "2026-06-02T00:12:16.379627+00:00"
      },
      {
        "id": 24,
        "service_name": "market_neuron",
        "service_type": "technical_truth",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.918857+00:00",
        "updated_at": "2026-06-02T00:12:16.341408+00:00"
      },
      {
        "id": 3,
        "service_name": "market_service",
        "service_type": "runtime",
        "status": "STOPPED",
        "last_heartbeat_at": null,
        "last_success_at": "2026-06-01T22:30:59.736635+00:00",
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.600102+00:00",
        "updated_at": "2026-06-02T00:12:15.643868+00:00"
      },
      {
        "id": 20,
        "service_name": "news_neuron",
        "service_type": "intelligence",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.864891+00:00",
        "updated_at": "2026-06-02T00:12:16.216173+00:00"
      },
      {
        "id": 33,
        "service_name": "no_trade_intelligence",
        "service_type": "no_trade",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:30.042236+00:00",
        "updated_at": "2026-06-02T00:12:16.711922+00:00"
      },
      {
        "id": 27,
        "service_name": "opportunity_cortex",
        "service_type": "opportunity",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.961997+00:00",
        "updated_at": "2026-06-02T00:12:16.421038+00:00"
      },
      {
        "id": 6,
        "service_name": "paper_runtime",
        "service_type": "runtime",
        "status": "STOPPED",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.646410+00:00",
        "updated_at": "2026-06-02T00:12:15.764812+00:00"
      },
      {
        "id": 4,
        "service_name": "postgres",
        "service_type": "persistence",
        "status": "HEALTHY",
        "last_heartbeat_at": "2026-06-02T00:21:07.775448+00:00",
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {
          "health_source": "runtime_health_request"
        },
        "created_at": "2026-05-20T23:20:29.613039+00:00",
        "updated_at": "2026-06-02T00:21:07.775448+00:00"
      },
      {
        "id": 71,
        "service_name": "redis",
        "service_type": "cache",
        "status": "HEALTHY",
        "last_heartbeat_at": "2026-06-02T00:21:07.775448+00:00",
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {
          "host": "redis",
          "port": 6379,
          "error": null,
          "configured": true,
          "health_source": "runtime_health_request"
        },
        "created_at": "2026-05-20T23:41:03.037893+00:00",
        "updated_at": "2026-06-02T00:21:07.775448+00:00"
      },
      {
        "id": 30,
        "service_name": "risk_gate_governor",
        "service_type": "risk",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.997564+00:00",
        "updated_at": "2026-06-02T00:12:16.550821+00:00"
      },
      {
        "id": 21,
        "service_name": "rules_neuron",
        "service_type": "intelligence",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.876637+00:00",
        "updated_at": "2026-06-02T00:12:16.252436+00:00"
      },
      {
        "id": 2,
        "service_name": "scheduler",
        "service_type": "runtime",
        "status": "BLOCKED_BY_MODE",
        "last_heartbeat_at": "2026-06-02T00:20:19.252703+00:00",
        "last_success_at": "2026-06-01T22:30:59.796114+00:00",
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.586357+00:00",
        "updated_at": "2026-06-02T00:20:19.252703+00:00"
      },
      {
        "id": 22,
        "service_name": "social_neuron",
        "service_type": "intelligence",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.894659+00:00",
        "updated_at": "2026-06-02T00:12:16.276889+00:00"
      },
      {
        "id": 9,
        "service_name": "stage4_guard",
        "service_type": "safety",
        "status": "STOPPED",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.686696+00:00",
        "updated_at": "2026-06-02T00:12:15.849582+00:00"
      },
      {
        "id": 28,
        "service_name": "strategy_router",
        "service_type": "strategy",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.974646+00:00",
        "updated_at": "2026-06-02T00:12:16.459154+00:00"
      },
      {
        "id": 8,
        "service_name": "telegram",
        "service_type": "control",
        "status": "STOPPED",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.671826+00:00",
        "updated_at": "2026-06-02T00:12:15.826595+00:00"
      },
      {
        "id": 23,
        "service_name": "whale_neuron",
        "service_type": "intelligence",
        "status": "RUNNING",
        "last_heartbeat_at": null,
        "last_success_at": null,
        "last_error_at": null,
        "error_count": 0,
        "warning_count": 0,
        "lag_seconds": null,
        "details_json": {},
        "created_at": "2026-05-20T23:20:29.908212+00:00",
        "updated_at": "2026-06-02T00:12:16.297526+00:00"
      }
    ],
    "stale_services": [],
    "critical_incidents": [],
    "last_mode_transition": {
      "id": 95,
      "from_mode": "PAPER",
      "to_mode": "PAPER",
      "action": "SYSTEM_OFF",
      "reason": "ai_provider_fix_bounded_smoke_off",
      "actor": "codex",
      "allowed": true,
      "blocked_reason": null,
      "correlation_id": "ai_context_provider_fix_smoke_20260602T001439Z",
      "created_at": "2026-06-02T00:14:57.478105+00:00",
      "metadata_json": {
        "new_power": "OFF",
        "old_power": "ON",
        "power_only_transition": true,
        "system_power_transition_id": "system_power_transition_660464be4b694983bc508c14a5dac1fa"
      }
    },
    "last_successful_cycle": {
      "id": 10618,
      "cycle_id": "v2-20260601T223037-5af74c65b4",
      "mode": "PAPER",
      "status": "COMPLETED",
      "started_at": "2026-06-01T22:30:37.259110+00:00",
      "finished_at": "2026-06-01T22:30:59.674695+00:00",
      "duration_ms": 22416,
      "scanner_started": true,
      "scanner_finished": true,
      "intelligence_started": false,
      "intelligence_finished": false,
      "paper_started": false,
      "paper_finished": false,
      "shadow_started": false,
      "shadow_finished": false,
      "live_started": false,
      "live_finished": false,
      "blocked_by_mode": false,
      "error_count": 0,
      "warning_count": 0,
      "metadata_json": {
        "source": "market_service.refresh",
        "phase1_cycle_id": "5820a2ce-6316-4376-b02a-0c8924311d62"
      }
    },
    "warnings": [
      "system power is OFF; autonomous runtime work is blocked"
    ]
  },
  "system_power": {
    "power": "OFF",
    "system_power": "OFF",
    "runtime_work_allowed": false,
    "last_transition_at": "2026-06-02T00:14:57.478105+00:00",
    "actor": "codex",
    "reason": "ai_provider_fix_bounded_smoke_off",
    "correlation_id": "ai_context_provider_fix_smoke_20260602T001439Z",
    "current_mode": "PAPER",
    "scheduler_allowed": false,
    "market_service_allowed": false,
    "data_intake_allowed": false,
    "neurons_allowed": false,
    "brains_allowed": false,
    "dialogue_allowed": false,
    "paper_allowed": false,
    "paper_simulation_allowed": false,
    "paper_execution_allowed": false,
    "shadow_allowed": false,
    "live_allowed": false,
    "components": {
      "scheduler": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "market_service": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "data_foundation": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "orderbook_refresh": {
        "allowed": false,
        "active": false,
        "wired": false
      },
      "neuron_producers": {
        "allowed": false,
        "active": false,
        "wired": false
      },
      "brain_producer": {
        "allowed": false,
        "active": false,
        "wired": false
      },
      "coordinator": {
        "allowed": false,
        "active": false,
        "wired": false
      },
      "thesis_builder": {
        "allowed": false,
        "active": false,
        "wired": false
      },
      "risk": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "exit": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "eligibility": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "no_trade": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "dashboard_truth": {
        "allowed": true,
        "active": true,
        "wired": true
      },
      "brain_dialogue_feed": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "paper_simulation": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "paper": {
        "allowed": false,
        "active": false,
        "wired": true
      },
      "shadow": {
        "allowed": false,
        "active": false,
        "wired": false
      },
      "live": {
        "allowed": false,
        "active": false,
        "wired": false
      }
    },
    "safety": {
      "live_trading_enabled": false,
      "execution_allowed": false,
      "orders_allowed": false,
      "paper_allowed": false,
      "paper_simulation_allowed": false,
      "shadow_allowed": false,
      "live_allowed": false,
      "real_orders_allowed": false,
      "live_disabled_expected": true
    }
  },
  "source": {
    "status": "OK",
    "mock_data": false,
    "stale": false,
    "updated_at": "2026-06-02T00:21:07.862015+00:00",
    "sources": [
      {
        "source_name": "polymarket_gamma",
        "source_type": "market_discovery",
        "configured": true,
        "key_required": false,
        "key_present": false,
        "key_name": null,
        "endpoint_url": "https://gamma-api.polymarket.com/events",
        "runtime_status": "ACTIVE",
        "freshness_status": "FRESH",
        "read_only": true,
        "mutation_allowed": false,
        "last_success_at": "2026-06-02T00:21:08.198685+00:00",
        "last_error_at": null,
        "latency_ms": 333,
        "details_json": {
          "event_count": 10,
          "sample_market_id": "2169995",
          "sample_token_available": true,
          "token_candidates": 34
        },
        "notes": "Gamma active events check succeeded."
      },
      {
        "source_name": "polymarket_clob_orderbook",
        "source_type": "orderbook",
        "configured": true,
        "key_required": false,
        "key_present": false,
        "key_name": null,
        "endpoint_url": "https://clob.polymarket.com/book",
        "runtime_status": "ACTIVE",
        "freshness_status": "FRESH",
        "read_only": true,
        "mutation_allowed": false,
        "last_success_at": "2026-06-02T00:21:08.474826+00:00",
        "last_error_at": null,
        "latency_ms": 273,
        "details_json": {
          "sample_market_id": "2169995",
          "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
          "attempted_tokens": 1,
          "best_bid": 0.006,
          "best_ask": 0.007,
          "spread": 0.001,
          "depth_1c": 30244589.17,
          "last_trade_price_present": true
        },
        "notes": "CLOB /book read-only check succeeded."
      },
      {
        "source_name": "polymarket_clob_prices",
        "source_type": "prices",
        "configured": true,
        "key_required": false,
        "key_present": false,
        "key_name": null,
        "endpoint_url": "CLOB /book derived best bid/ask/last_trade_price",
        "runtime_status": "ACTIVE",
        "freshness_status": "FRESH",
        "read_only": true,
        "mutation_allowed": false,
        "last_success_at": "2026-06-02T00:21:08.475019+00:00",
        "last_error_at": null,
        "latency_ms": 273,
        "details_json": {
          "sample_market_id": "2169995",
          "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
          "attempted_tokens": 1,
          "best_bid": 0.006,
          "best_ask": 0.007,
          "spread": 0.001,
          "depth_1c": 30244589.17,
          "last_trade_price_present": true
        },
        "notes": "Price truth derived from read-only CLOB book response."
      },
      {
        "source_name": "polymarket_clob_spreads",
        "source_type": "spreads",
        "configured": true,
        "key_required": false,
        "key_present": false,
        "key_name": null,
        "endpoint_url": "CLOB /book derived spread/depth",
        "runtime_status": "ACTIVE",
        "freshness_status": "FRESH",
        "read_only": true,
        "mutation_allowed": false,
        "last_success_at": "2026-06-02T00:21:08.475037+00:00",
        "last_error_at": null,
        "latency_ms": 273,
        "details_json": {
          "sample_market_id": "2169995",
          "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
          "attempted_tokens": 1,
          "best_bid": 0.006,
          "best_ask": 0.007,
          "spread": 0.001,
          "depth_1c": 30244589.17,
          "last_trade_price_present": true
        },
        "notes": "Spread and depth truth derived from read-only CLOB book response."
      },
      {
        "source_name": "polymarket_activity_readonly",
        "source_type": "activity",
        "configured": true,
        "key_required": false,
        "key_present": false,
        "key_name": null,
        "endpoint_url": "https://data-api.polymarket.com/trades",
        "runtime_status": "ACTIVE",
        "freshness_status": "FRESH",
        "read_only": true,
        "mutation_allowed": false,
        "last_success_at": "2026-06-02T00:21:08.775714+00:00",
        "last_error_at": null,
        "latency_ms": 300,
        "details_json": {
          "sample_count": 1
        },
        "notes": "Data API /trades read-only discovery check succeeded."
      },
      {
        "source_name": "ollama_local_model",
        "source_type": "local_ai",
        "configured": true,
        "key_required": false,
        "key_present": false,
        "key_name": null,
        "endpoint_url": "http://host.docker.internal:11434/api/tags",
        "runtime_status": "ACTIVE",
        "freshness_status": "FRESH",
        "read_only": true,
        "mutation_allowed": false,
        "last_success_at": "2026-06-02T00:21:08.829328+00:00",
        "last_error_at": null,
        "latency_ms": 38,
        "details_json": {
          "model_count": 1,
          "configured_models": [
            "qwen3:4b",
            "qwen3:4b",
            "qwen3:4b"
          ],
          "missing_configured_models": [],
          "qwen3_4b_present": true,
          "attempted_endpoints": [
            "http://localhost:11434/api/tags",
            "http://host.docker.internal:11434/api/tags"
          ]
        },
        "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
      },
      {
        "source_name": "news_provider",
        "source_type": "news",
        "configured": false,
        "key_required": true,
        "key_present": true,
        "key_name": "NEWS_API_KEY",
        "endpoint_url": null,
        "runtime_status": "DISABLED",
        "freshness_status": "UNKNOWN",
        "read_only": true,
        "mutation_allowed": false,
        "last_success_at": null,
        "last_error_at": null,
        "latency_ms": null,
        "details_json": {},
        "notes": "News provider is intentionally disabled for V2.21; no real calls made."
      },
      {
        "source_name": "reddit_or_social_provider",
        "source_type": "social",
        "configured": false,
        "key_required": true,
        "key_present": false,
        "key_name": "REDDIT_CLIENT_ID",
        "endpoint_url": null,
        "runtime_status": "DISABLED",
        "freshness_status": "UNKNOWN",
        "read_only": true,
        "mutation_allowed": false,
        "last_success_at": null,
        "last_error_at": null,
        "latency_ms": null,
        "details_json": {},
        "notes": "Social provider is intentionally disabled for V2.21; no real calls made."
      }
    ],
    "degraded_sources": []
  },
  "ai_router": {
    "mock_data": false,
    "status": "OK",
    "generated_at": "2026-06-02T00:21:09.040912+00:00",
    "latest_status": "AI_CONTEXT_UNAVAILABLE",
    "ai_required": false,
    "selected_provider": null,
    "provider_order": [
      "ollama",
      "openai",
      "anthropic"
    ],
    "ollama_status": {
      "status": "FAILED",
      "reason": "OLLAMA_TIMEOUT",
      "last_run_id": "ai_context_provider_fix_smoke_20260602T001439Z"
    },
    "openai_status": {
      "status": "FAILED",
      "reason": "OPENAI_RATE_LIMITED",
      "last_run_id": "ai_context_provider_fix_smoke_20260602T001439Z"
    },
    "anthropic_status": {
      "status": "FAILED",
      "reason": "ANTHROPIC_DEGRADED",
      "last_run_id": "ai_context_provider_fix_smoke_20260602T001439Z"
    },
    "fallback_count": 0,
    "timeout_count": 2,
    "success_count": 0,
    "unavailable_count": 2,
    "latest_runs": [
      {
        "id": 2,
        "run_id": "ai_context_provider_fix_smoke_20260602T001439Z",
        "source_component": "AI Context Brain",
        "session_id": null,
        "market_id": null,
        "candidate_id": null,
        "provider_order_json": [
          "ollama",
          "openai",
          "anthropic"
        ],
        "selected_provider": null,
        "status": "AI_CONTEXT_UNAVAILABLE",
        "final_reason": "ANTHROPIC_DEGRADED",
        "providers_attempted_json": [
          {
            "reason": "OLLAMA_TIMEOUT",
            "status": "FAILED",
            "attempts": [
              {
                "model": "qwen3:4b",
                "reason": "OLLAMA_ERROR",
                "endpoint": "http://localhost:11434"
              },
              {
                "model": "qwen3:4b",
                "reason": "OLLAMA_TIMEOUT",
                "endpoint": "http://host.docker.internal:11434"
              }
            ],
            "provider": "ollama"
          },
          {
            "reason": "OPENAI_RATE_LIMITED",
            "status": "FAILED",
            "provider": "openai",
            "error_summary": "Client error '429 Too Many Requests' for url 'https://api.openai.com/v1/chat/completions'\nFor more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429"
          },
          {
            "reason": "ANTHROPIC_DEGRADED",
            "status": "FAILED",
            "provider": "anthropic",
            "model_attempts": [
              {
                "model": "claude-3-5-haiku-latest",
                "reason": "ANTHROPIC_DEGRADED"
              },
              {
                "model": "claude-3-haiku-20240307",
                "reason": "ANTHROPIC_DEGRADED"
              }
            ]
          }
        ],
        "started_at": "2026-06-02T00:14:39.254603+00:00",
        "finished_at": "2026-06-02T00:14:56.602396+00:00",
        "latency_ms": 17321,
        "prompt_hash": "45812f39a1f0fa2408d734ce6c593feaf35f87678bc782b854afa67dbf327171",
        "response_hash": null,
        "metadata_json": {
          "provider_fix": true,
          "runtime_smoke": true
        }
      },
      {
        "id": 1,
        "run_id": "ai_context_router_runtime_smoke_20260601T2323Z",
        "source_component": "AI Context Brain",
        "session_id": null,
        "market_id": null,
        "candidate_id": null,
        "provider_order_json": [
          "ollama",
          "openai",
          "anthropic"
        ],
        "selected_provider": null,
        "status": "AI_CONTEXT_UNAVAILABLE",
        "final_reason": "ANTHROPIC_ERROR",
        "providers_attempted_json": [
          {
            "reason": "OLLAMA_TIMEOUT",
            "status": "FAILED",
            "attempts": [
              {
                "model": "qwen3:4b",
                "reason": "OLLAMA_ERROR",
                "endpoint": "http://localhost:11434"
              },
              {
                "model": "qwen3:4b",
                "reason": "OLLAMA_TIMEOUT",
                "endpoint": "http://host.docker.internal:11434"
              }
            ],
            "provider": "ollama"
          },
          {
            "reason": "OPENAI_ERROR",
            "status": "FAILED",
            "provider": "openai",
            "error_summary": "Client error '429 Too Many Requests' for url 'https://api.openai.com/v1/chat/completions'\nFor more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429"
          },
          {
            "reason": "ANTHROPIC_ERROR",
            "status": "FAILED",
            "provider": "anthropic",
            "error_summary": "Client error '404 Not Found' for url 'https://api.anthropic.com/v1/messages'\nFor more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/404"
          }
        ],
        "started_at": "2026-06-01T23:23:28.825188+00:00",
        "finished_at": "2026-06-01T23:23:47.654318+00:00",
        "latency_ms": 18788,
        "prompt_hash": "85d2d9941bbb04059e469a25b41613adecdf5727f23ddb8fdea1452ad90742ef",
        "response_hash": null,
        "metadata_json": {
          "runtime_smoke": true
        }
      }
    ],
    "secrets_exposed": false
  },
  "paper": {
    "mock_data": false,
    "generated_at": "2026-06-02T00:21:09.051197+00:00",
    "system_power": "OFF",
    "runtime_health": "OK",
    "paper_status": "GREEN",
    "paper_intents_total": 6,
    "executable_paper_intents": 0,
    "paper_orders_total": 9,
    "paper_fills_total": 6,
    "paper_positions_total": 9,
    "open_paper_positions": 0,
    "active_open_paper_positions": 0,
    "raw_open_paper_positions": 0,
    "closed_paper_positions": 6,
    "quarantined_paper_positions_count": 3,
    "quarantined_paper_positions": [
      {
        "paper_position_id": "0d423170-fc01-4292-9dee-69a690610419",
        "market_id": "678937",
        "side": "NO",
        "entry_price": 0.19,
        "quantity": 31.589,
        "opened_at": "2026-05-30T23:41:27.951263+00:00",
        "invalidated_at": "2026-05-31T01:49:33.353883+00:00",
        "quarantine_reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
        "quarantine_source": "PaperLineageQuarantineService",
        "quarantine_run_id": "paper_lineage_quarantine_3155eebcd63a4063b0e5b4ed34bb7175"
      },
      {
        "paper_position_id": "a0a5a06b-5419-4e2a-afd5-47f56e34af39",
        "market_id": "678929",
        "side": "YES",
        "entry_price": 0.19,
        "quantity": 97.315,
        "opened_at": "2026-05-30T23:41:27.851953+00:00",
        "invalidated_at": "2026-05-31T01:49:33.353883+00:00",
        "quarantine_reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
        "quarantine_source": "PaperLineageQuarantineService",
        "quarantine_run_id": "paper_lineage_quarantine_3155eebcd63a4063b0e5b4ed34bb7175"
      },
      {
        "paper_position_id": "f929eb8a-54cd-4635-86b7-3becae5eba0d",
        "market_id": "629035",
        "side": "YES",
        "entry_price": 0.23,
        "quantity": 60.304,
        "opened_at": "2026-05-30T23:41:27.746835+00:00",
        "invalidated_at": "2026-05-31T01:49:33.353883+00:00",
        "quarantine_reason": "LEGACY_EXECUTION_AWARE_PAPER_POSITION_WITHOUT_FILL_OR_OPEN_LEDGER",
        "quarantine_source": "PaperLineageQuarantineService",
        "quarantine_run_id": "paper_lineage_quarantine_3155eebcd63a4063b0e5b4ed34bb7175"
      }
    ],
    "paper_position_closes": 6,
    "paper_trade_ledger": 12,
    "paper_daily_pnl": 2,
    "latest_paper_intent_at": "2026-05-31T07:52:26.299847+00:00",
    "latest_paper_order_at": "2026-05-31T07:52:26.502921+00:00",
    "latest_paper_fill_at": "2026-05-31T07:52:26.539853+00:00",
    "latest_paper_position_at": "2026-05-31T07:52:26.539853+00:00",
    "latest_exit_check_at": "2026-05-31T21:43:49.517293+00:00",
    "latest_position_close_at": "2026-05-31T07:52:29.684140+00:00",
    "realized_pnl": 23.55,
    "unrealized_pnl": 0.0,
    "daily_pnl": {
      "id": 14,
      "pnl_date": "2026-05-31",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "net_pnl": 23.55,
      "gross_profit": 23.55,
      "gross_loss": 0.0,
      "closed_trades_count": 3,
      "open_positions_count": 0,
      "winning_trades_count": 3,
      "losing_trades_count": 0,
      "stale_price_count": 0,
      "updated_at": "2026-05-31T07:52:29.684140+00:00"
    },
    "gross_profit": 23.55,
    "gross_loss": 0.0,
    "winning_trades_count": 3,
    "losing_trades_count": 0,
    "orphan_positions_count": 0,
    "duplicate_orders_count": 0,
    "duplicate_fills_count": 0,
    "duplicate_positions_count": 0,
    "duplicate_intent_orders_count": 0,
    "duplicate_order_fills_count": 0,
    "duplicate_fill_positions_count": 0,
    "positions_without_fills_count": 0,
    "raw_positions_without_fills_count": 3,
    "fills_without_orders_count": 0,
    "positions_without_open_ledger_count": 0,
    "raw_positions_without_open_ledger_count": 3,
    "closed_positions_without_close_count": 0,
    "closed_positions_without_close_ledger_count": 0,
    "executed_intents_reexecuted_count": 0,
    "paper_lineage_consistency_status": "OK",
    "paper_lineage_consistency_raw_status": "RED",
    "paper_lineage_readiness_status": "OK",
    "stale_price_count": 0,
    "no_fake_pnl": true,
    "live_orders": 0,
    "real_orders_baseline": 1,
    "real_orders_current": 1,
    "orders_v2": 1,
    "fills_v2": 1,
    "canonical_positions": 0,
    "live_enabled": false,
    "shadow_enabled": false,
    "brain_dialogue_latest_at": "2026-06-01T22:30:59.605054+00:00",
    "neuron_dialogue_latest_at": "2026-06-01T22:30:26.414821+00:00",
    "brain_dialogue_events": 55835,
    "neuron_dialogue_events": 23044,
    "top_current_blockers": [
      {
        "blocker": "MISSING_TRUSTED_ORDERBOOK",
        "count": 2565
      },
      {
        "blocker": "INTENT_ALREADY_EXECUTED",
        "count": 1851
      }
    ],
    "capital_summary": {
      "mock_data": false,
      "generated_at": "2026-06-02T00:21:09.351720+00:00",
      "account_id": "paper_default",
      "currency": "USD",
      "initial_balance": 1000.0,
      "current_balance": 1000.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "realized_pnl": 0.0,
      "unrealized_pnl": 0.0,
      "daily_pnl": 0.0,
      "risk_per_trade_pct": 1.0,
      "max_position_size": 25.0,
      "max_daily_loss_pct": 5.0,
      "max_open_positions": 3,
      "max_total_open_exposure_pct": 15.0,
      "active_open_positions": 0,
      "quarantined_positions_excluded": 3,
      "capital_status": "OK",
      "active_guards": [],
      "latest_ledger_events": [
        {
          "id": 1,
          "ledger_id": "paper_capital_default_initialized",
          "account_id": "paper_default",
          "event_type": "ACCOUNT_INITIALIZED",
          "source_type": "MIGRATION",
          "source_id": "0099_paper_capital_account_balance_ledger",
          "paper_intent_id": null,
          "paper_order_id": null,
          "paper_fill_id": null,
          "paper_position_id": null,
          "paper_close_id": null,
          "amount": 1000.0,
          "balance_before": 0.0,
          "balance_after": 1000.0,
          "available_before": 0.0,
          "available_after": 1000.0,
          "locked_before": 0.0,
          "locked_after": 0.0,
          "realized_pnl_delta": 0.0,
          "unrealized_pnl_snapshot": 0.0,
          "reason": "DEFAULT_PAPER_ACCOUNT_INITIALIZED",
          "metadata_json": {
            "paper_only": true
          },
          "created_at": "2026-05-31T20:00:53.074819+00:00"
        }
      ],
      "reconciliation_status": "OK",
      "capital_reconciliation_status": "OK",
      "reconciliation_errors": [],
      "warnings": [],
      "live_orders": 0,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0
    },
    "capital_reconciliation_status": "OK",
    "capital_status": "OK",
    "available_balance": 1000.0,
    "locked_balance": 0.0,
    "open_exposure": 0.0,
    "active_capital_guards": [],
    "warnings": [],
    "readiness_status": "GREEN",
    "latest_runtime": {
      "runtime_health": "OK",
      "scheduler_health": "BLOCKED_BY_MODE",
      "latest_cycle_id": "v2-20260601T223037-5af74c65b4",
      "latest_cycle_at": "2026-06-01T22:30:37.259110+00:00"
    }
  },
  "readiness": {
    "mock_data": false,
    "generated_at": "2026-06-02T00:21:09.833655+00:00",
    "readiness_status": "GREEN",
    "blockers": [],
    "warnings": [
      "QUARANTINED_LEGACY_PAPER_POSITIONS_PRESENT"
    ],
    "safety_status": "GREEN",
    "preflight_counts": {
      "paper_intents_total": 6,
      "executable_paper_intents": 0,
      "paper_orders_total": 9,
      "paper_fills_total": 6,
      "paper_positions_total": 9,
      "open_paper_positions": 0,
      "active_open_paper_positions": 0,
      "raw_open_paper_positions": 0,
      "closed_paper_positions": 6,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "paper_daily_pnl": 2,
      "duplicate_intent_orders_count": 0,
      "duplicate_order_fills_count": 0,
      "duplicate_fill_positions_count": 0,
      "positions_without_fills_count": 0,
      "raw_positions_without_fills_count": 3,
      "positions_without_open_ledger_count": 0,
      "raw_positions_without_open_ledger_count": 3,
      "executed_intents_reexecuted_count": 0,
      "paper_lineage_consistency_status": "OK",
      "paper_lineage_readiness_status": "OK",
      "quarantined_paper_positions_count": 3,
      "brain_dialogue_events": 55835,
      "neuron_dialogue_events": 23044,
      "live_orders": 0,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0
    },
    "required_endpoints_status": {
      "/healthz": "CHECK_EXTERNALLY",
      "/runtime/health": "CHECK_EXTERNALLY",
      "/system/power": "CHECK_EXTERNALLY",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/positions": "OK",
      "/dashboard/api/v2/paper/pnl": "OK",
      "/dashboard/api/v2/brain-dialogue": "CHECK_EXTERNALLY",
      "/dashboard/api/v2/neuron-dialogue": "CHECK_EXTERNALLY"
    },
    "can_start_4h_soak": true
  },
  "overnight": {
    "mock_data": false,
    "status": "OK",
    "generated_at": "2026-06-02T00:21:09.840757+00:00",
    "latest_run": null,
    "event_counts": {
      "source_to_neuron_events": 20,
      "neural_events": 34,
      "mesh_sessions": 24,
      "shared_awareness": 24,
      "brain_opinions": 86,
      "coordinator_decisions": 14,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9
    },
    "new_paper_trades": null,
    "pnl": {
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0
    },
    "source_health": {
      "status": "OK",
      "degraded_sources": [],
      "missing_sources": null
    },
    "safety_status": "GREEN",
    "safety": {
      "live_orders": 0,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_lineage_consistency_status": "OK",
      "capital_reconciliation_status": "OK",
      "mock_data": false
    },
    "open_positions": [],
    "latest_coordinator_decisions": [
      {
        "decision_id": "mesh_decision_mesh_session_global_session_210636cc0bea24de886f1d31",
        "session_id": "mesh_session_global_session_210636cc0bea24de886f1d31",
        "market_id": null,
        "position_id": null,
        "final_stance": "INSUFFICIENT_DATA",
        "final_action": "INSUFFICIENT_DATA",
        "confidence": 0.3213,
        "decision_reason": "Most source brains produced NO_SIGNAL; mesh decision remains insufficient data.",
        "created_at": "2026-06-02T00:14:56.800275+00:00"
      },
      {
        "decision_id": "mesh_decision_mesh_session_global_session_14ac252aff737416e9906285",
        "session_id": "mesh_session_global_session_14ac252aff737416e9906285",
        "market_id": null,
        "position_id": null,
        "final_stance": "INSUFFICIENT_DATA",
        "final_action": "INSUFFICIENT_DATA",
        "confidence": 0.3213,
        "decision_reason": "Most source brains produced NO_SIGNAL; mesh decision remains insufficient data.",
        "created_at": "2026-06-01T23:23:47.957745+00:00"
      },
      {
        "decision_id": "mesh_decision_mesh_session_market_session_dcfa0a59857b88d12087363d",
        "session_id": "mesh_session_market_session_dcfa0a59857b88d12087363d",
        "market_id": "2169995",
        "position_id": null,
        "final_stance": "WATCH",
        "final_action": "WATCH",
        "confidence": 0.5982,
        "decision_reason": "Brain opinions disagree without a hard BLOCK; coordinator resolves to WATCH.",
        "created_at": "2026-06-01T22:30:04.583150+00:00"
      },
      {
        "decision_id": "mesh_decision_mesh_session_global_session_023b283416ce5c3adcba9595",
        "session_id": "mesh_session_global_session_023b283416ce5c3adcba9595",
        "market_id": null,
        "position_id": null,
        "final_stance": "INSUFFICIENT_DATA",
        "final_action": "INSUFFICIENT_DATA",
        "confidence": 0.4,
        "decision_reason": "Most source brains produced NO_SIGNAL; mesh decision remains insufficient data.",
        "created_at": "2026-06-01T22:30:03.633375+00:00"
      },
      {
        "decision_id": "mesh_decision_mesh_session_market_session_627507390eb633cb7ecb183b",
        "session_id": "mesh_session_market_session_627507390eb633cb7ecb183b",
        "market_id": "2354064",
        "position_id": null,
        "final_stance": "WATCH",
        "final_action": "WATCH",
        "confidence": 0.5002,
        "decision_reason": "Brain opinions disagree without a hard BLOCK; coordinator resolves to WATCH.",
        "created_at": "2026-06-01T21:57:09.027139+00:00"
      },
      {
        "decision_id": "mesh_decision_mesh_session_market_session_1e5ec654ea9c1a93914c812d",
        "session_id": "mesh_session_market_session_1e5ec654ea9c1a93914c812d",
        "market_id": "2365093",
        "position_id": null,
        "final_stance": "WATCH",
        "final_action": "WATCH",
        "confidence": 0.3837,
        "decision_reason": "Brain opinions disagree without a hard BLOCK; coordinator resolves to WATCH.",
        "created_at": "2026-06-01T21:57:07.079874+00:00"
      },
      {
        "decision_id": "mesh_decision_mesh_session_position_session_123596d2cec7987df3493dd5",
        "session_id": "mesh_session_position_session_123596d2cec7987df3493dd5",
        "market_id": "824952",
        "position_id": "c4e7b2c0-b565-5a6a-9f0b-3bae3bdf11bd",
        "final_stance": "EXIT_RECOMMENDED",
        "final_action": "EXIT_REVIEW",
        "confidence": 0.6155,
        "decision_reason": "Position session has adverse exit/risk context; route to exit review only.",
        "created_at": "2026-06-01T21:48:39.280182+00:00"
      },
      {
        "decision_id": "mesh_decision_mesh_session_market_session_171480f459cf6413f9c65eb7",
        "session_id": "mesh_session_market_session_171480f459cf6413f9c65eb7",
        "market_id": "0x8e19827705b34f87e142d1112efbdbf8b66e07fcf523aef5deb08af99be057b1",
        "position_id": null,
        "final_stance": "BLOCK",
        "final_action": "BLOCK",
        "confidence": 0.432,
        "decision_reason": "Capital BLOCK beats trade support and prevents candidate approval.",
        "created_at": "2026-06-01T21:48:28.263996+00:00"
      },
      {
        "decision_id": "mesh_decision_mesh_session_market_session_8444ffaa5f56dc0dba1cba84",
        "session_id": "mesh_session_market_session_8444ffaa5f56dc0dba1cba84",
        "market_id": "677404",
        "position_id": null,
        "final_stance": "WATCH",
        "final_action": "WATCH",
        "confidence": 0.5565,
        "decision_reason": "Brain opinions disagree without a hard BLOCK; coordinator resolves to WATCH.",
        "created_at": "2026-06-01T21:48:25.884846+00:00"
      },
      {
        "decision_id": "mesh_decision_mesh_session_global_session_65fbd7ea124c34a9532b98bb",
        "session_id": "mesh_session_global_session_65fbd7ea124c34a9532b98bb",
        "market_id": null,
        "position_id": null,
        "final_stance": "INSUFFICIENT_DATA",
        "final_action": "INSUFFICIENT_DATA",
        "confidence": 0.4,
        "decision_reason": "Most source brains produced NO_SIGNAL; mesh decision remains insufficient data.",
        "created_at": "2026-06-01T21:48:24.870471+00:00"
      }
    ]
  }
}
```

## Final
```json
{}
```

## Samples
```json
[]
```
