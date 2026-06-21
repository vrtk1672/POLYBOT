# POLYBOT Active 30m Observation Report

- run_id: active_30m_observation_20260602T091845Z
- status: GREEN
- started_at: 2026-06-02T09:18:45.199898+00:00
- finished_at: 2026-06-02T09:48:49.837301+00:00
- samples: 9
- stop_reason: NONE

## Preflight
```json
{
  "mock_data": false,
  "status": "YELLOW",
  "blockers": [],
  "warnings": [
    "SAFE_YELLOW_AI:['COMPLETED', 'OK', 'OLLAMA_ERROR', 'OPENAI_QUOTA_EXCEEDED']"
  ],
  "payload_summary": {
    "/healthz": {
      "status": "ok",
      "mock_data": null,
      "secrets_exposed": null
    },
    "/runtime/health": {
      "status": "SAFE_STOPPED",
      "mock_data": null,
      "secrets_exposed": null
    },
    "/system/power": {
      "status": "OK",
      "mock_data": null,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/source-to-neuron-flow": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": false
    },
    "/dashboard/api/v2/ai-context-router": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": false
    },
    "/dashboard/api/v2/neural-bus": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/mesh-sessions": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/shared-awareness": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/multi-brain-consumption": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/mesh-coordinator": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/capital-brain": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/positions-awareness": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/paper": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/paper/trade-forensics": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/overnight/status": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    },
    "/dashboard/api/v2/source-status": {
      "status": "OK",
      "mock_data": false,
      "secrets_exposed": null
    }
  }
}
```

## First Sample
```json
{
  "timestamp": "2026-06-02T09:19:47.036538+00:00",
  "system_power": "ON",
  "runtime_health": "HEALTHY",
  "endpoint_status": {
    "/healthz": "OK",
    "/runtime/health": "OK",
    "/system/power": "OK",
    "/dashboard/api/v2/source-to-neuron-flow": "OK",
    "/dashboard/api/v2/ai-context-router": "OK",
    "/dashboard/api/v2/neural-bus": "OK",
    "/dashboard/api/v2/mesh-sessions": "OK",
    "/dashboard/api/v2/shared-awareness": "OK",
    "/dashboard/api/v2/multi-brain-consumption": "OK",
    "/dashboard/api/v2/mesh-coordinator": "OK",
    "/dashboard/api/v2/capital-brain": "OK",
    "/dashboard/api/v2/positions-awareness": "OK",
    "/dashboard/api/v2/paper": "OK",
    "/dashboard/api/v2/paper/trade-forensics": "OK",
    "/dashboard/api/v2/overnight/status": "OK",
    "/dashboard/api/v2/source-status": "OK"
  },
  "mock_data_endpoints": [],
  "secret_exposed": false,
  "source_health": "OK",
  "degraded_sources": [],
  "ai_router": {
    "latest_status": "OK",
    "selected_provider": "anthropic",
    "ollama_status": {
      "status": "FAILED",
      "reason": "OLLAMA_TIMEOUT",
      "last_run_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1"
    },
    "anthropic_status": {
      "status": "OK",
      "reason": "COMPLETED",
      "last_run_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1"
    },
    "openai_status": {
      "status": "FAILED",
      "reason": "OPENAI_QUOTA_EXCEEDED",
      "last_run_id": "post_env_ai_router_verification_20260602"
    },
    "success_count": 2,
    "unavailable_count": 2,
    "secrets_exposed": false
  },
  "events_by_type": {
    "ORDERBOOK_REFRESHED": 11,
    "NEWS_DETECTED": 8,
    "LIQUIDITY_CHANGED": 4,
    "MARKET_REPRICING": 4,
    "RISK_CHANGED": 4,
    "SPREAD_CHANGED": 4,
    "AI_CONTEXT_UNAVAILABLE": 2,
    "AI_CONTEXT_UPDATED": 2,
    "PNL_CHANGED": 2,
    "WHALE_DETECTED": 1
  },
  "neural_events": 42,
  "mesh_sessions": 27,
  "shared_awareness": 27,
  "brain_opinions": 81,
  "mesh_coordinator_decisions": 17,
  "mesh_conflicts_detected": 11,
  "source_brain_count_avg": 4.05,
  "capital_evaluations": 15,
  "capital_decisions": {
    "CAPITAL_SUPPORT": 13,
    "CAPITAL_BLOCK": 1,
    "CAPITAL_RELEASE_REVIEW": 1
  },
  "position_awareness": 1,
  "position_reactions": {
    "PNL_RISING": 2,
    "CAPITAL_PRESSURE": 1,
    "PNL_FALLING": 1,
    "POSITION_AGING": 1
  },
  "paper": {
    "live_orders": 0,
    "live_enabled": false,
    "shadow_enabled": false,
    "real_orders_current": 1,
    "orders_v2": 1,
    "fills_v2": 1,
    "canonical_positions": 0,
    "paper_intents": 6,
    "paper_orders": 9,
    "paper_fills": 6,
    "paper_positions": 9,
    "paper_position_closes": 6,
    "paper_trade_ledger": 12,
    "open_positions": 0,
    "closed_positions": 6,
    "active_positions_without_fills": 0,
    "paper_lineage": "OK",
    "capital_reconciliation": "OK",
    "realized_pnl": 23.55,
    "unrealized_pnl": 0.0,
    "available_balance": 1000.0,
    "locked_balance": 0.0,
    "open_exposure": 0.0,
    "top_blockers": [
      {
        "blocker": "MISSING_TRUSTED_ORDERBOOK",
        "count": 2568
      },
      {
        "blocker": "INTENT_ALREADY_EXECUTED",
        "count": 1854
      }
    ]
  },
  "forensics_active_count": 6,
  "forensics_quarantined_count": 3,
  "cycle_index": 1,
  "active_cycle": {
    "correlation_id": "active_30m_observation_20260602T091845Z_cycle_1",
    "outputs": {
      "source_to_neuron": {
        "mock_data": false,
        "status": "OK",
        "run_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1",
        "blocked": false,
        "providers_checked": [
          "polymarket_gamma",
          "polymarket_clob_orderbook",
          "polymarket_clob_prices",
          "polymarket_clob_spreads",
          "polymarket_activity_readonly",
          "ollama_local_model",
          "news_provider",
          "reddit_or_social_provider"
        ],
        "provider_status": {
          "polymarket_gamma": {
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
            "last_success_at": "2026-06-02T09:18:52.285827+00:00",
            "last_error_at": null,
            "latency_ms": 141,
            "details_json": {
              "event_count": 10,
              "sample_market_id": "2169995",
              "sample_token_available": true,
              "token_candidates": 34
            },
            "notes": "Gamma active events check succeeded."
          },
          "polymarket_clob_orderbook": {
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
            "last_success_at": "2026-06-02T09:18:52.585173+00:00",
            "last_error_at": null,
            "latency_ms": 297,
            "details_json": {
              "sample_market_id": "2169995",
              "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
              "attempted_tokens": 1,
              "best_bid": 0.006,
              "best_ask": 0.007,
              "spread": 0.001,
              "depth_1c": 50134627.49,
              "last_trade_price_present": true
            },
            "notes": "CLOB /book read-only check succeeded."
          },
          "polymarket_clob_prices": {
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
            "last_success_at": "2026-06-02T09:18:52.585223+00:00",
            "last_error_at": null,
            "latency_ms": 297,
            "details_json": {
              "sample_market_id": "2169995",
              "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
              "attempted_tokens": 1,
              "best_bid": 0.006,
              "best_ask": 0.007,
              "spread": 0.001,
              "depth_1c": 50134627.49,
              "last_trade_price_present": true
            },
            "notes": "Price truth derived from read-only CLOB book response."
          },
          "polymarket_clob_spreads": {
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
            "last_success_at": "2026-06-02T09:18:52.585228+00:00",
            "last_error_at": null,
            "latency_ms": 297,
            "details_json": {
              "sample_market_id": "2169995",
              "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
              "attempted_tokens": 1,
              "best_bid": 0.006,
              "best_ask": 0.007,
              "spread": 0.001,
              "depth_1c": 50134627.49,
              "last_trade_price_present": true
            },
            "notes": "Spread and depth truth derived from read-only CLOB book response."
          },
          "polymarket_activity_readonly": {
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
            "last_success_at": "2026-06-02T09:18:52.677741+00:00",
            "last_error_at": null,
            "latency_ms": 91,
            "details_json": {
              "sample_count": 1
            },
            "notes": "Data API /trades read-only discovery check succeeded."
          },
          "ollama_local_model": {
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
            "last_success_at": "2026-06-02T09:18:52.736195+00:00",
            "last_error_at": null,
            "latency_ms": 57,
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
                "http://host.docker.internal:11434/api/tags"
              ]
            },
            "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
          },
          "news_provider": {
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
          "reddit_or_social_provider": {
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
          },
          "ai_context_router": {
            "runtime_status": "ACTIVE",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "secret_value_exposed": false
          }
        },
        "events_created": 7,
        "events_by_type": {
          "MARKET_REPRICING": 1,
          "NEWS_DETECTED": 2,
          "ORDERBOOK_REFRESHED": 1,
          "SPREAD_CHANGED": 1,
          "LIQUIDITY_CHANGED": 1,
          "AI_CONTEXT_UPDATED": 1
        },
        "sessions_updated": 7,
        "awareness_domains_updated": 67,
        "brain_opinions_created": 15,
        "coordinator_decisions_created": 3,
        "latest_items": [
          {
            "event_id": "neural_event_d86498a8c4e74f7096274a786dc560be",
            "event_type": "MARKET_REPRICING",
            "market_id": "2169995",
            "candidate_id": null,
            "position_id": null,
            "provider": "polymarket_gamma",
            "neuron": "Market Neuron",
            "source_table": "source_status",
            "source_record_id": "polymarket_gamma:source_to_neuron_f0ab320a500c415686b76d34b22bc1d1",
            "created_at": "2026-06-02T09:18:53.062802+00:00"
          },
          {
            "event_id": "neural_event_7552b74f57f54febb524a8498821556a",
            "event_type": "NEWS_DETECTED",
            "market_id": null,
            "candidate_id": null,
            "position_id": null,
            "provider": "rss",
            "neuron": "News Neuron",
            "source_table": "news_normalized_events",
            "source_record_id": "news_evt_74ac858a79a145fc8272c293432425ee",
            "created_at": "2026-06-02T09:18:54.503427+00:00"
          },
          {
            "event_id": "neural_event_59a319184721490fa2f44727d1d071e5",
            "event_type": "NEWS_DETECTED",
            "market_id": "598936",
            "candidate_id": null,
            "position_id": null,
            "provider": "newsapi",
            "neuron": "News Neuron",
            "source_table": "news_normalized_events",
            "source_record_id": "news_evt_c68d714deff648c8b1ca2bf4098c0b79",
            "created_at": "2026-06-02T09:18:56.753620+00:00"
          },
          {
            "event_id": "neural_event_f99a1814c03143b48f202ae1c392f40e",
            "event_type": "ORDERBOOK_REFRESHED",
            "market_id": "2169995",
            "candidate_id": null,
            "position_id": null,
            "provider": "polymarket_clob",
            "neuron": "Orderbook Neuron",
            "source_table": "orderbook_snapshots",
            "source_record_id": "ob_bf0da55e9ac946e7b89efec09e3d0002",
            "created_at": "2026-06-02T09:18:57.563284+00:00"
          },
          {
            "event_id": "neural_event_cada5e772d68422ea7f03ee067f9dca5",
            "event_type": "SPREAD_CHANGED",
            "market_id": "2169995",
            "candidate_id": null,
            "position_id": null,
            "provider": "polymarket_clob",
            "neuron": "Liquidity Neuron",
            "source_table": "orderbook_snapshots",
            "source_record_id": "ob_bf0da55e9ac946e7b89efec09e3d0002:SPREAD_CHANGED",
            "created_at": "2026-06-02T09:18:57.893993+00:00"
          },
          {
            "event_id": "neural_event_fd5386ec350d4f0cb78c234c04ec9d9a",
            "event_type": "LIQUIDITY_CHANGED",
            "market_id": "2169995",
            "candidate_id": null,
            "position_id": null,
            "provider": "polymarket_clob",
            "neuron": "Liquidity Neuron",
            "source_table": "orderbook_snapshots",
            "source_record_id": "ob_bf0da55e9ac946e7b89efec09e3d0002:LIQUIDITY_CHANGED",
            "created_at": "2026-06-02T09:18:58.341502+00:00"
          },
          {
            "event_id": "neural_event_bcbbf77fbd4d4a66954b7a047b3e2b3d",
            "event_type": "AI_CONTEXT_UPDATED",
            "market_id": null,
            "candidate_id": null,
            "position_id": null,
            "provider": "anthropic",
            "neuron": "AI Context Brain",
            "source_table": "ai_responses",
            "source_record_id": "ai_resp_context_router_428d6dbe73a5605029cdeb8a",
            "created_at": "2026-06-02T09:19:14.719284+00:00"
          }
        ],
        "errors": [],
        "missing_providers": [],
        "degraded_providers": [],
        "whale_status": "NO_WHALE_EVENT_FOUND",
        "secrets_exposed": false,
        "ai_context_router": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1",
          "selected_provider": "anthropic",
          "final_reason": "AI_CONTEXT_UPDATED",
          "providers_attempted": [
            {
              "provider": "ollama",
              "status": "FAILED",
              "reason": "OLLAMA_TIMEOUT",
              "attempts": [
                {
                  "endpoint": "http://host.docker.internal:11434",
                  "model": "qwen3:4b",
                  "reason": "OLLAMA_TIMEOUT"
                }
              ]
            },
            {
              "provider": "anthropic",
              "status": "OK",
              "reason": "COMPLETED",
              "model": "claude-haiku-4-5-20251001",
              "latency_ms": 4217,
              "response_hash": "0d0f9143d23400c6ad29f3d9b59b8c677b581e2b1e1661fef19d2b4e537a5ad1"
            }
          ],
          "event": {
            "id": 45,
            "event_id": "neural_event_bcbbf77fbd4d4a66954b7a047b3e2b3d",
            "event_type": "AI_CONTEXT_UPDATED",
            "correlation_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1",
            "market_id": null,
            "candidate_id": null,
            "position_id": null,
            "source_component": "AI Context Brain",
            "source_type": "brain",
            "priority": 5,
            "payload_json": {
              "model": "claude-haiku-4-5-20251001",
              "status": "COMPLETED",
              "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input. Capable of processing: provider data, news feeds, orderbook snapshots, whale activity, and PnL metrics. Output limited to context analysis only. Trade creation, risk bypass, capital allocation, and position management remain exclusively within Risk, Exit, Capital, Coordinator, and State Governor modules.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"can_do\": [\n      \"analyze_source_evidence\",\n      \"correlate_multi_source_data\",\n      \"return_context_json\",\n      \"flag_anomalies\",\n      \"timestamp_observations\"\n    ],\n    \"cannot_do\": [\n      \"create_trades\",\n      \"bypass_risk_controls\",\n      \"allocate_capital\",\n      \"generate_orders\",\n      \"modify_positions\",\n      \"override_governance\"\n    ]\n  },\n  \"awaiting\": \"source-backed evidence payload\"\n}\n```\n\n**Ready for bounded context analysis. Provide evidence sources.**",
              "attempts": [
                {
                  "reason": "OLLAMA_TIMEOUT",
                  "status": "FAILED",
                  "attempts": [
                    {
                      "model": "qwen3:4b",
                      "reason": "OLLAMA_TIMEOUT",
                      "endpoint": "http://host.docker.internal:11434"
                    }
                  ],
                  "provider": "ollama"
                },
                {
                  "model": "claude-haiku-4-5-20251001",
                  "reason": "COMPLETED",
                  "status": "OK",
                  "provider": "anthropic",
                  "latency_ms": 4217,
                  "response_hash": "0d0f9143d23400c6ad29f3d9b59b8c677b581e2b1e1661fef19d2b4e537a5ad1"
                }
              ],
              "provider": "anthropic",
              "confidence": 0.5,
              "source_refs": [
                {
                  "source_table": "ai_responses",
                  "source_record_id": "ai_resp_context_router_428d6dbe73a5605029cdeb8a"
                }
              ]
            },
            "created_at": "2026-06-02T09:19:14.719284+00:00",
            "consumed_count": 0,
            "status": "PUBLISHED",
            "source_table": "ai_responses",
            "source_record_id": "ai_resp_context_router_428d6dbe73a5605029cdeb8a",
            "schema_version": 1,
            "metadata_json": {
              "router": "ai_context_fallback",
              "provider": "anthropic",
              "source_to_neuron": true
            }
          },
          "ai_request_id": "ai_req_context_router_805f7de0ed0cb297c90d60d2",
          "ai_response_id": "ai_resp_context_router_428d6dbe73a5605029cdeb8a",
          "latency_ms": 14504,
          "secrets_exposed": false
        },
        "safety_before": {
          "live_orders": 0,
          "paper_orders": 9,
          "paper_fills": 6,
          "paper_positions": 9,
          "paper_intents": 6,
          "paper_capital_ledger": 1,
          "risk_decisions": 10332,
          "exit_plans": 10332,
          "coordinator_decisions": 10636,
          "brain_outputs": 10672,
          "orders_v2": 1,
          "fills_v2": 1,
          "positions": 0,
          "paper_account_balances": {
            "current_balance": 1000.0,
            "available_balance": 1000.0,
            "locked_balance": 0.0,
            "open_exposure": 0.0
          }
        },
        "safety_after": {
          "live_orders": 0,
          "paper_orders": 9,
          "paper_fills": 6,
          "paper_positions": 9,
          "paper_intents": 6,
          "paper_capital_ledger": 1,
          "risk_decisions": 10332,
          "exit_plans": 10332,
          "coordinator_decisions": 10636,
          "brain_outputs": 10672,
          "orders_v2": 1,
          "fills_v2": 1,
          "positions": 0,
          "paper_account_balances": {
            "current_balance": 1000.0,
            "available_balance": 1000.0,
            "locked_balance": 0.0,
            "open_exposure": 0.0
          }
        },
        "trading_mutation_detected": false
      },
      "paper_execution": {
        "mock_data": false,
        "run_id": "paper_execution_48622737ed144ebab0b64bf715ff77ee",
        "cycle_id": "active_30m_observation_20260602T091845Z_cycle_1",
        "system_power": "ON",
        "started_at": "2026-06-02T09:19:32.786592+00:00",
        "finished_at": "2026-06-02T09:19:32.893718+00:00",
        "status": "NO_VALID_PAPER_INTENTS",
        "intents_checked": 3,
        "executable_intents": 0,
        "orders_created": 0,
        "fills_created": 0,
        "positions_created": 0,
        "blocked_intents": 3,
        "duplicate_skipped": 0,
        "block_reasons_json": {
          "INTENT_ALREADY_EXECUTED": 3,
          "MISSING_TRUSTED_ORDERBOOK": 3
        },
        "real_orders_delta": 0,
        "live_orders_delta": 0,
        "fills_v2_delta": 0,
        "positions_delta": 0,
        "error_message": null,
        "metadata_json": {
          "reason": "no executable paper intents"
        }
      },
      "paper_exits": {
        "mock_data": false,
        "run_id": "paper_exit_loop_43f4c3f8130c477194cd37a8d3cb7378",
        "system_power": "ON",
        "status": "NO_OPEN_PAPER_POSITIONS",
        "open_positions_checked": 0,
        "closed_positions_count": 0,
        "marked_positions_count": 0,
        "blocked_positions_count": 0,
        "no_exit_price_count": 0,
        "no_exit_condition_count": 0,
        "duplicate_close_skipped_count": 0,
        "orphan_positions_count": 0,
        "realized_pnl": 0,
        "unrealized_pnl": null,
        "paper_orders_delta": 0,
        "paper_positions_delta": 0,
        "real_orders_delta": 0,
        "fills_delta": 0,
        "live_orders_delta": 0,
        "started_at": "2026-06-02T09:19:32.967839+00:00",
        "finished_at": "2026-06-02T09:19:33.032084+00:00",
        "error_summary": null,
        "metadata": {
          "paper_orders": 9,
          "paper_positions": 9,
          "no_fake_pnl": true
        }
      }
    },
    "errors": []
  },
  "repeated_api_failures": 0,
  "repeated_cycle_failures": 0,
  "deltas": {
    "neural_events": 7,
    "mesh_sessions": 2,
    "shared_awareness": 2,
    "brain_opinions": 8,
    "mesh_coordinator_decisions": 2,
    "capital_evaluations": 2,
    "position_awareness": 0,
    "paper": {
      "paper_intents": 0,
      "paper_orders": 0,
      "paper_fills": 0,
      "paper_positions": 0,
      "paper_position_closes": 0,
      "paper_trade_ledger": 0,
      "orders_v2": 0,
      "fills_v2": 0,
      "canonical_positions": 0,
      "real_orders_current": 0,
      "live_orders": 0
    },
    "events_by_type": {
      "AI_CONTEXT_UNAVAILABLE": 0,
      "AI_CONTEXT_UPDATED": 1,
      "LIQUIDITY_CHANGED": 1,
      "MARKET_REPRICING": 1,
      "NEWS_DETECTED": 2,
      "ORDERBOOK_REFRESHED": 1,
      "PNL_CHANGED": 0,
      "RISK_CHANGED": 0,
      "SPREAD_CHANGED": 1,
      "WHALE_DETECTED": 0
    }
  }
}
```

## Final Sample
```json
{
  "timestamp": "2026-06-02T09:48:49.800097+00:00",
  "system_power": "OFF",
  "runtime_health": "SAFE_STOPPED",
  "endpoint_status": {
    "/healthz": "OK",
    "/runtime/health": "OK",
    "/system/power": "OK",
    "/dashboard/api/v2/source-to-neuron-flow": "OK",
    "/dashboard/api/v2/ai-context-router": "OK",
    "/dashboard/api/v2/neural-bus": "OK",
    "/dashboard/api/v2/mesh-sessions": "OK",
    "/dashboard/api/v2/shared-awareness": "OK",
    "/dashboard/api/v2/multi-brain-consumption": "OK",
    "/dashboard/api/v2/mesh-coordinator": "OK",
    "/dashboard/api/v2/capital-brain": "OK",
    "/dashboard/api/v2/positions-awareness": "OK",
    "/dashboard/api/v2/paper": "OK",
    "/dashboard/api/v2/paper/trade-forensics": "OK",
    "/dashboard/api/v2/overnight/status": "OK",
    "/dashboard/api/v2/source-status": "OK"
  },
  "mock_data_endpoints": [],
  "secret_exposed": false,
  "source_health": "OK",
  "degraded_sources": [],
  "ai_router": {
    "latest_status": "OK",
    "selected_provider": "anthropic",
    "ollama_status": {
      "status": "FAILED",
      "reason": "OLLAMA_TIMEOUT",
      "last_run_id": "source_to_neuron_b22379cdb95c4cab940e970813996c7a"
    },
    "anthropic_status": {
      "status": "OK",
      "reason": "COMPLETED",
      "last_run_id": "source_to_neuron_b22379cdb95c4cab940e970813996c7a"
    },
    "openai_status": {
      "status": "FAILED",
      "reason": "OPENAI_QUOTA_EXCEEDED",
      "last_run_id": "post_env_ai_router_verification_20260602"
    },
    "success_count": 10,
    "unavailable_count": 2,
    "secrets_exposed": false
  },
  "events_by_type": {
    "NEWS_DETECTED": 24,
    "ORDERBOOK_REFRESHED": 19,
    "LIQUIDITY_CHANGED": 12,
    "MARKET_REPRICING": 12,
    "SPREAD_CHANGED": 12,
    "AI_CONTEXT_UPDATED": 10,
    "RISK_CHANGED": 4,
    "AI_CONTEXT_UNAVAILABLE": 2,
    "PNL_CHANGED": 2,
    "WHALE_DETECTED": 2
  },
  "neural_events": 99,
  "mesh_sessions": 36,
  "shared_awareness": 36,
  "brain_opinions": 117,
  "mesh_coordinator_decisions": 26,
  "mesh_conflicts_detected": 19,
  "source_brain_count_avg": 4.0345,
  "capital_evaluations": 24,
  "capital_decisions": {
    "CAPITAL_SUPPORT": 21,
    "CAPITAL_BLOCK": 2,
    "CAPITAL_RELEASE_REVIEW": 1
  },
  "position_awareness": 1,
  "position_reactions": {
    "PNL_RISING": 2,
    "CAPITAL_PRESSURE": 1,
    "PNL_FALLING": 1,
    "POSITION_AGING": 1
  },
  "paper": {
    "live_orders": 0,
    "live_enabled": false,
    "shadow_enabled": false,
    "real_orders_current": 1,
    "orders_v2": 1,
    "fills_v2": 1,
    "canonical_positions": 0,
    "paper_intents": 6,
    "paper_orders": 9,
    "paper_fills": 6,
    "paper_positions": 9,
    "paper_position_closes": 6,
    "paper_trade_ledger": 12,
    "open_positions": 0,
    "closed_positions": 6,
    "active_positions_without_fills": 0,
    "paper_lineage": "OK",
    "capital_reconciliation": "OK",
    "realized_pnl": 23.55,
    "unrealized_pnl": 0.0,
    "available_balance": 1000.0,
    "locked_balance": 0.0,
    "open_exposure": 0.0,
    "top_blockers": [
      {
        "blocker": "MISSING_TRUSTED_ORDERBOOK",
        "count": 2640
      },
      {
        "blocker": "INTENT_ALREADY_EXECUTED",
        "count": 1926
      }
    ]
  },
  "forensics_active_count": 6,
  "forensics_quarantined_count": 3
}
```

## Samples
```json
[
  {
    "timestamp": "2026-06-02T09:19:47.036538+00:00",
    "system_power": "ON",
    "runtime_health": "HEALTHY",
    "endpoint_status": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/source-to-neuron-flow": "OK",
      "/dashboard/api/v2/ai-context-router": "OK",
      "/dashboard/api/v2/neural-bus": "OK",
      "/dashboard/api/v2/mesh-sessions": "OK",
      "/dashboard/api/v2/shared-awareness": "OK",
      "/dashboard/api/v2/multi-brain-consumption": "OK",
      "/dashboard/api/v2/mesh-coordinator": "OK",
      "/dashboard/api/v2/capital-brain": "OK",
      "/dashboard/api/v2/positions-awareness": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/trade-forensics": "OK",
      "/dashboard/api/v2/overnight/status": "OK",
      "/dashboard/api/v2/source-status": "OK"
    },
    "mock_data_endpoints": [],
    "secret_exposed": false,
    "source_health": "OK",
    "degraded_sources": [],
    "ai_router": {
      "latest_status": "OK",
      "selected_provider": "anthropic",
      "ollama_status": {
        "status": "FAILED",
        "reason": "OLLAMA_TIMEOUT",
        "last_run_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1"
      },
      "anthropic_status": {
        "status": "OK",
        "reason": "COMPLETED",
        "last_run_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1"
      },
      "openai_status": {
        "status": "FAILED",
        "reason": "OPENAI_QUOTA_EXCEEDED",
        "last_run_id": "post_env_ai_router_verification_20260602"
      },
      "success_count": 2,
      "unavailable_count": 2,
      "secrets_exposed": false
    },
    "events_by_type": {
      "ORDERBOOK_REFRESHED": 11,
      "NEWS_DETECTED": 8,
      "LIQUIDITY_CHANGED": 4,
      "MARKET_REPRICING": 4,
      "RISK_CHANGED": 4,
      "SPREAD_CHANGED": 4,
      "AI_CONTEXT_UNAVAILABLE": 2,
      "AI_CONTEXT_UPDATED": 2,
      "PNL_CHANGED": 2,
      "WHALE_DETECTED": 1
    },
    "neural_events": 42,
    "mesh_sessions": 27,
    "shared_awareness": 27,
    "brain_opinions": 81,
    "mesh_coordinator_decisions": 17,
    "mesh_conflicts_detected": 11,
    "source_brain_count_avg": 4.05,
    "capital_evaluations": 15,
    "capital_decisions": {
      "CAPITAL_SUPPORT": 13,
      "CAPITAL_BLOCK": 1,
      "CAPITAL_RELEASE_REVIEW": 1
    },
    "position_awareness": 1,
    "position_reactions": {
      "PNL_RISING": 2,
      "CAPITAL_PRESSURE": 1,
      "PNL_FALLING": 1,
      "POSITION_AGING": 1
    },
    "paper": {
      "live_orders": 0,
      "live_enabled": false,
      "shadow_enabled": false,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "open_positions": 0,
      "closed_positions": 6,
      "active_positions_without_fills": 0,
      "paper_lineage": "OK",
      "capital_reconciliation": "OK",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "top_blockers": [
        {
          "blocker": "MISSING_TRUSTED_ORDERBOOK",
          "count": 2568
        },
        {
          "blocker": "INTENT_ALREADY_EXECUTED",
          "count": 1854
        }
      ]
    },
    "forensics_active_count": 6,
    "forensics_quarantined_count": 3,
    "cycle_index": 1,
    "active_cycle": {
      "correlation_id": "active_30m_observation_20260602T091845Z_cycle_1",
      "outputs": {
        "source_to_neuron": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1",
          "blocked": false,
          "providers_checked": [
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
            "polymarket_activity_readonly",
            "ollama_local_model",
            "news_provider",
            "reddit_or_social_provider"
          ],
          "provider_status": {
            "polymarket_gamma": {
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
              "last_success_at": "2026-06-02T09:18:52.285827+00:00",
              "last_error_at": null,
              "latency_ms": 141,
              "details_json": {
                "event_count": 10,
                "sample_market_id": "2169995",
                "sample_token_available": true,
                "token_candidates": 34
              },
              "notes": "Gamma active events check succeeded."
            },
            "polymarket_clob_orderbook": {
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
              "last_success_at": "2026-06-02T09:18:52.585173+00:00",
              "last_error_at": null,
              "latency_ms": 297,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.006,
                "best_ask": 0.007,
                "spread": 0.001,
                "depth_1c": 50134627.49,
                "last_trade_price_present": true
              },
              "notes": "CLOB /book read-only check succeeded."
            },
            "polymarket_clob_prices": {
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
              "last_success_at": "2026-06-02T09:18:52.585223+00:00",
              "last_error_at": null,
              "latency_ms": 297,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.006,
                "best_ask": 0.007,
                "spread": 0.001,
                "depth_1c": 50134627.49,
                "last_trade_price_present": true
              },
              "notes": "Price truth derived from read-only CLOB book response."
            },
            "polymarket_clob_spreads": {
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
              "last_success_at": "2026-06-02T09:18:52.585228+00:00",
              "last_error_at": null,
              "latency_ms": 297,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.006,
                "best_ask": 0.007,
                "spread": 0.001,
                "depth_1c": 50134627.49,
                "last_trade_price_present": true
              },
              "notes": "Spread and depth truth derived from read-only CLOB book response."
            },
            "polymarket_activity_readonly": {
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
              "last_success_at": "2026-06-02T09:18:52.677741+00:00",
              "last_error_at": null,
              "latency_ms": 91,
              "details_json": {
                "sample_count": 1
              },
              "notes": "Data API /trades read-only discovery check succeeded."
            },
            "ollama_local_model": {
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
              "last_success_at": "2026-06-02T09:18:52.736195+00:00",
              "last_error_at": null,
              "latency_ms": 57,
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
                  "http://host.docker.internal:11434/api/tags"
                ]
              },
              "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
            },
            "news_provider": {
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
            "reddit_or_social_provider": {
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
            },
            "ai_context_router": {
              "runtime_status": "ACTIVE",
              "selected_provider": "anthropic",
              "final_reason": "AI_CONTEXT_UPDATED",
              "secret_value_exposed": false
            }
          },
          "events_created": 7,
          "events_by_type": {
            "MARKET_REPRICING": 1,
            "NEWS_DETECTED": 2,
            "ORDERBOOK_REFRESHED": 1,
            "SPREAD_CHANGED": 1,
            "LIQUIDITY_CHANGED": 1,
            "AI_CONTEXT_UPDATED": 1
          },
          "sessions_updated": 7,
          "awareness_domains_updated": 67,
          "brain_opinions_created": 15,
          "coordinator_decisions_created": 3,
          "latest_items": [
            {
              "event_id": "neural_event_d86498a8c4e74f7096274a786dc560be",
              "event_type": "MARKET_REPRICING",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_gamma",
              "neuron": "Market Neuron",
              "source_table": "source_status",
              "source_record_id": "polymarket_gamma:source_to_neuron_f0ab320a500c415686b76d34b22bc1d1",
              "created_at": "2026-06-02T09:18:53.062802+00:00"
            },
            {
              "event_id": "neural_event_7552b74f57f54febb524a8498821556a",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "rss",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_74ac858a79a145fc8272c293432425ee",
              "created_at": "2026-06-02T09:18:54.503427+00:00"
            },
            {
              "event_id": "neural_event_59a319184721490fa2f44727d1d071e5",
              "event_type": "NEWS_DETECTED",
              "market_id": "598936",
              "candidate_id": null,
              "position_id": null,
              "provider": "newsapi",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_c68d714deff648c8b1ca2bf4098c0b79",
              "created_at": "2026-06-02T09:18:56.753620+00:00"
            },
            {
              "event_id": "neural_event_f99a1814c03143b48f202ae1c392f40e",
              "event_type": "ORDERBOOK_REFRESHED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Orderbook Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_bf0da55e9ac946e7b89efec09e3d0002",
              "created_at": "2026-06-02T09:18:57.563284+00:00"
            },
            {
              "event_id": "neural_event_cada5e772d68422ea7f03ee067f9dca5",
              "event_type": "SPREAD_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_bf0da55e9ac946e7b89efec09e3d0002:SPREAD_CHANGED",
              "created_at": "2026-06-02T09:18:57.893993+00:00"
            },
            {
              "event_id": "neural_event_fd5386ec350d4f0cb78c234c04ec9d9a",
              "event_type": "LIQUIDITY_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_bf0da55e9ac946e7b89efec09e3d0002:LIQUIDITY_CHANGED",
              "created_at": "2026-06-02T09:18:58.341502+00:00"
            },
            {
              "event_id": "neural_event_bcbbf77fbd4d4a66954b7a047b3e2b3d",
              "event_type": "AI_CONTEXT_UPDATED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "anthropic",
              "neuron": "AI Context Brain",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_428d6dbe73a5605029cdeb8a",
              "created_at": "2026-06-02T09:19:14.719284+00:00"
            }
          ],
          "errors": [],
          "missing_providers": [],
          "degraded_providers": [],
          "whale_status": "NO_WHALE_EVENT_FOUND",
          "secrets_exposed": false,
          "ai_context_router": {
            "mock_data": false,
            "status": "OK",
            "run_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "providers_attempted": [
              {
                "provider": "ollama",
                "status": "FAILED",
                "reason": "OLLAMA_TIMEOUT",
                "attempts": [
                  {
                    "endpoint": "http://host.docker.internal:11434",
                    "model": "qwen3:4b",
                    "reason": "OLLAMA_TIMEOUT"
                  }
                ]
              },
              {
                "provider": "anthropic",
                "status": "OK",
                "reason": "COMPLETED",
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 4217,
                "response_hash": "0d0f9143d23400c6ad29f3d9b59b8c677b581e2b1e1661fef19d2b4e537a5ad1"
              }
            ],
            "event": {
              "id": 45,
              "event_id": "neural_event_bcbbf77fbd4d4a66954b7a047b3e2b3d",
              "event_type": "AI_CONTEXT_UPDATED",
              "correlation_id": "source_to_neuron_f0ab320a500c415686b76d34b22bc1d1",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "source_component": "AI Context Brain",
              "source_type": "brain",
              "priority": 5,
              "payload_json": {
                "model": "claude-haiku-4-5-20251001",
                "status": "COMPLETED",
                "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input. Capable of processing: provider data, news feeds, orderbook snapshots, whale activity, and PnL metrics. Output limited to context analysis only. Trade creation, risk bypass, capital allocation, and position management remain exclusively within Risk, Exit, Capital, Coordinator, and State Governor modules.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"can_do\": [\n      \"analyze_source_evidence\",\n      \"correlate_multi_source_data\",\n      \"return_context_json\",\n      \"flag_anomalies\",\n      \"timestamp_observations\"\n    ],\n    \"cannot_do\": [\n      \"create_trades\",\n      \"bypass_risk_controls\",\n      \"allocate_capital\",\n      \"generate_orders\",\n      \"modify_positions\",\n      \"override_governance\"\n    ]\n  },\n  \"awaiting\": \"source-backed evidence payload\"\n}\n```\n\n**Ready for bounded context analysis. Provide evidence sources.**",
                "attempts": [
                  {
                    "reason": "OLLAMA_TIMEOUT",
                    "status": "FAILED",
                    "attempts": [
                      {
                        "model": "qwen3:4b",
                        "reason": "OLLAMA_TIMEOUT",
                        "endpoint": "http://host.docker.internal:11434"
                      }
                    ],
                    "provider": "ollama"
                  },
                  {
                    "model": "claude-haiku-4-5-20251001",
                    "reason": "COMPLETED",
                    "status": "OK",
                    "provider": "anthropic",
                    "latency_ms": 4217,
                    "response_hash": "0d0f9143d23400c6ad29f3d9b59b8c677b581e2b1e1661fef19d2b4e537a5ad1"
                  }
                ],
                "provider": "anthropic",
                "confidence": 0.5,
                "source_refs": [
                  {
                    "source_table": "ai_responses",
                    "source_record_id": "ai_resp_context_router_428d6dbe73a5605029cdeb8a"
                  }
                ]
              },
              "created_at": "2026-06-02T09:19:14.719284+00:00",
              "consumed_count": 0,
              "status": "PUBLISHED",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_428d6dbe73a5605029cdeb8a",
              "schema_version": 1,
              "metadata_json": {
                "router": "ai_context_fallback",
                "provider": "anthropic",
                "source_to_neuron": true
              }
            },
            "ai_request_id": "ai_req_context_router_805f7de0ed0cb297c90d60d2",
            "ai_response_id": "ai_resp_context_router_428d6dbe73a5605029cdeb8a",
            "latency_ms": 14504,
            "secrets_exposed": false
          },
          "safety_before": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10332,
            "exit_plans": 10332,
            "coordinator_decisions": 10636,
            "brain_outputs": 10672,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "safety_after": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10332,
            "exit_plans": 10332,
            "coordinator_decisions": 10636,
            "brain_outputs": 10672,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "trading_mutation_detected": false
        },
        "paper_execution": {
          "mock_data": false,
          "run_id": "paper_execution_48622737ed144ebab0b64bf715ff77ee",
          "cycle_id": "active_30m_observation_20260602T091845Z_cycle_1",
          "system_power": "ON",
          "started_at": "2026-06-02T09:19:32.786592+00:00",
          "finished_at": "2026-06-02T09:19:32.893718+00:00",
          "status": "NO_VALID_PAPER_INTENTS",
          "intents_checked": 3,
          "executable_intents": 0,
          "orders_created": 0,
          "fills_created": 0,
          "positions_created": 0,
          "blocked_intents": 3,
          "duplicate_skipped": 0,
          "block_reasons_json": {
            "INTENT_ALREADY_EXECUTED": 3,
            "MISSING_TRUSTED_ORDERBOOK": 3
          },
          "real_orders_delta": 0,
          "live_orders_delta": 0,
          "fills_v2_delta": 0,
          "positions_delta": 0,
          "error_message": null,
          "metadata_json": {
            "reason": "no executable paper intents"
          }
        },
        "paper_exits": {
          "mock_data": false,
          "run_id": "paper_exit_loop_43f4c3f8130c477194cd37a8d3cb7378",
          "system_power": "ON",
          "status": "NO_OPEN_PAPER_POSITIONS",
          "open_positions_checked": 0,
          "closed_positions_count": 0,
          "marked_positions_count": 0,
          "blocked_positions_count": 0,
          "no_exit_price_count": 0,
          "no_exit_condition_count": 0,
          "duplicate_close_skipped_count": 0,
          "orphan_positions_count": 0,
          "realized_pnl": 0,
          "unrealized_pnl": null,
          "paper_orders_delta": 0,
          "paper_positions_delta": 0,
          "real_orders_delta": 0,
          "fills_delta": 0,
          "live_orders_delta": 0,
          "started_at": "2026-06-02T09:19:32.967839+00:00",
          "finished_at": "2026-06-02T09:19:33.032084+00:00",
          "error_summary": null,
          "metadata": {
            "paper_orders": 9,
            "paper_positions": 9,
            "no_fake_pnl": true
          }
        }
      },
      "errors": []
    },
    "repeated_api_failures": 0,
    "repeated_cycle_failures": 0,
    "deltas": {
      "neural_events": 7,
      "mesh_sessions": 2,
      "shared_awareness": 2,
      "brain_opinions": 8,
      "mesh_coordinator_decisions": 2,
      "capital_evaluations": 2,
      "position_awareness": 0,
      "paper": {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "paper_position_closes": 0,
        "paper_trade_ledger": 0,
        "orders_v2": 0,
        "fills_v2": 0,
        "canonical_positions": 0,
        "real_orders_current": 0,
        "live_orders": 0
      },
      "events_by_type": {
        "AI_CONTEXT_UNAVAILABLE": 0,
        "AI_CONTEXT_UPDATED": 1,
        "LIQUIDITY_CHANGED": 1,
        "MARKET_REPRICING": 1,
        "NEWS_DETECTED": 2,
        "ORDERBOOK_REFRESHED": 1,
        "PNL_CHANGED": 0,
        "RISK_CHANGED": 0,
        "SPREAD_CHANGED": 1,
        "WHALE_DETECTED": 0
      }
    }
  },
  {
    "timestamp": "2026-06-02T09:23:13.869424+00:00",
    "system_power": "ON",
    "runtime_health": "HEALTHY",
    "endpoint_status": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/source-to-neuron-flow": "OK",
      "/dashboard/api/v2/ai-context-router": "OK",
      "/dashboard/api/v2/neural-bus": "OK",
      "/dashboard/api/v2/mesh-sessions": "OK",
      "/dashboard/api/v2/shared-awareness": "OK",
      "/dashboard/api/v2/multi-brain-consumption": "OK",
      "/dashboard/api/v2/mesh-coordinator": "OK",
      "/dashboard/api/v2/capital-brain": "OK",
      "/dashboard/api/v2/positions-awareness": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/trade-forensics": "OK",
      "/dashboard/api/v2/overnight/status": "OK",
      "/dashboard/api/v2/source-status": "OK"
    },
    "mock_data_endpoints": [],
    "secret_exposed": false,
    "source_health": "OK",
    "degraded_sources": [],
    "ai_router": {
      "latest_status": "OK",
      "selected_provider": "anthropic",
      "ollama_status": {
        "status": "FAILED",
        "reason": "OLLAMA_TIMEOUT",
        "last_run_id": "source_to_neuron_f5bb7a8a35b4447bb4370a718fa036f6"
      },
      "anthropic_status": {
        "status": "OK",
        "reason": "COMPLETED",
        "last_run_id": "source_to_neuron_f5bb7a8a35b4447bb4370a718fa036f6"
      },
      "openai_status": {
        "status": "FAILED",
        "reason": "OPENAI_QUOTA_EXCEEDED",
        "last_run_id": "post_env_ai_router_verification_20260602"
      },
      "success_count": 3,
      "unavailable_count": 2,
      "secrets_exposed": false
    },
    "events_by_type": {
      "ORDERBOOK_REFRESHED": 12,
      "NEWS_DETECTED": 10,
      "LIQUIDITY_CHANGED": 5,
      "MARKET_REPRICING": 5,
      "SPREAD_CHANGED": 5,
      "RISK_CHANGED": 4,
      "AI_CONTEXT_UPDATED": 3,
      "AI_CONTEXT_UNAVAILABLE": 2,
      "PNL_CHANGED": 2,
      "WHALE_DETECTED": 1
    },
    "neural_events": 49,
    "mesh_sessions": 28,
    "shared_awareness": 28,
    "brain_opinions": 85,
    "mesh_coordinator_decisions": 18,
    "mesh_conflicts_detected": 12,
    "source_brain_count_avg": 4.0476,
    "capital_evaluations": 16,
    "capital_decisions": {
      "CAPITAL_SUPPORT": 14,
      "CAPITAL_BLOCK": 1,
      "CAPITAL_RELEASE_REVIEW": 1
    },
    "position_awareness": 1,
    "position_reactions": {
      "PNL_RISING": 2,
      "CAPITAL_PRESSURE": 1,
      "PNL_FALLING": 1,
      "POSITION_AGING": 1
    },
    "paper": {
      "live_orders": 0,
      "live_enabled": false,
      "shadow_enabled": false,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "open_positions": 0,
      "closed_positions": 6,
      "active_positions_without_fills": 0,
      "paper_lineage": "OK",
      "capital_reconciliation": "OK",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "top_blockers": [
        {
          "blocker": "MISSING_TRUSTED_ORDERBOOK",
          "count": 2577
        },
        {
          "blocker": "INTENT_ALREADY_EXECUTED",
          "count": 1863
        }
      ]
    },
    "forensics_active_count": 6,
    "forensics_quarantined_count": 3,
    "cycle_index": 2,
    "active_cycle": {
      "correlation_id": "active_30m_observation_20260602T091845Z_cycle_2",
      "outputs": {
        "source_to_neuron": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_f5bb7a8a35b4447bb4370a718fa036f6",
          "blocked": false,
          "providers_checked": [
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
            "polymarket_activity_readonly",
            "ollama_local_model",
            "news_provider",
            "reddit_or_social_provider"
          ],
          "provider_status": {
            "polymarket_gamma": {
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
              "last_success_at": "2026-06-02T09:22:47.848195+00:00",
              "last_error_at": null,
              "latency_ms": 510,
              "details_json": {
                "event_count": 10,
                "sample_market_id": "2169995",
                "sample_token_available": true,
                "token_candidates": 34
              },
              "notes": "Gamma active events check succeeded."
            },
            "polymarket_clob_orderbook": {
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
              "last_success_at": "2026-06-02T09:22:48.118121+00:00",
              "last_error_at": null,
              "latency_ms": 261,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.007,
                "best_ask": 0.008,
                "spread": 0.001,
                "depth_1c": 48077364.37,
                "last_trade_price_present": true
              },
              "notes": "CLOB /book read-only check succeeded."
            },
            "polymarket_clob_prices": {
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
              "last_success_at": "2026-06-02T09:22:48.118210+00:00",
              "last_error_at": null,
              "latency_ms": 261,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.007,
                "best_ask": 0.008,
                "spread": 0.001,
                "depth_1c": 48077364.37,
                "last_trade_price_present": true
              },
              "notes": "Price truth derived from read-only CLOB book response."
            },
            "polymarket_clob_spreads": {
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
              "last_success_at": "2026-06-02T09:22:48.118223+00:00",
              "last_error_at": null,
              "latency_ms": 261,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.007,
                "best_ask": 0.008,
                "spread": 0.001,
                "depth_1c": 48077364.37,
                "last_trade_price_present": true
              },
              "notes": "Spread and depth truth derived from read-only CLOB book response."
            },
            "polymarket_activity_readonly": {
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
              "last_success_at": "2026-06-02T09:22:48.551553+00:00",
              "last_error_at": null,
              "latency_ms": 432,
              "details_json": {
                "sample_count": 1
              },
              "notes": "Data API /trades read-only discovery check succeeded."
            },
            "ollama_local_model": {
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
              "last_success_at": "2026-06-02T09:22:48.618890+00:00",
              "last_error_at": null,
              "latency_ms": 66,
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
                  "http://host.docker.internal:11434/api/tags"
                ]
              },
              "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
            },
            "news_provider": {
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
            "reddit_or_social_provider": {
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
            },
            "ai_context_router": {
              "runtime_status": "ACTIVE",
              "selected_provider": "anthropic",
              "final_reason": "AI_CONTEXT_UPDATED",
              "secret_value_exposed": false
            }
          },
          "events_created": 7,
          "events_by_type": {
            "MARKET_REPRICING": 1,
            "NEWS_DETECTED": 2,
            "ORDERBOOK_REFRESHED": 1,
            "SPREAD_CHANGED": 1,
            "LIQUIDITY_CHANGED": 1,
            "AI_CONTEXT_UPDATED": 1
          },
          "sessions_updated": 14,
          "awareness_domains_updated": 77,
          "brain_opinions_created": 20,
          "coordinator_decisions_created": 4,
          "latest_items": [
            {
              "event_id": "neural_event_9eb712a3b6f44e62b64191ff99aa36ce",
              "event_type": "MARKET_REPRICING",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_gamma",
              "neuron": "Market Neuron",
              "source_table": "source_status",
              "source_record_id": "polymarket_gamma:source_to_neuron_f5bb7a8a35b4447bb4370a718fa036f6",
              "created_at": "2026-06-02T09:22:48.827136+00:00"
            },
            {
              "event_id": "neural_event_3e6598272fa84cab9221049f9e448589",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "rss",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_e0c8290a7a3c405ba19e4dd7a6e0db9b",
              "created_at": "2026-06-02T09:22:49.811831+00:00"
            },
            {
              "event_id": "neural_event_fe80d876de0440409442e7e5d2841252",
              "event_type": "NEWS_DETECTED",
              "market_id": "598936",
              "candidate_id": null,
              "position_id": null,
              "provider": "newsapi",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_53effd4a2f8c4416831584b25b83c5bc",
              "created_at": "2026-06-02T09:22:51.993312+00:00"
            },
            {
              "event_id": "neural_event_516cdb3c4a6944d8871902c7674f4e87",
              "event_type": "ORDERBOOK_REFRESHED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Orderbook Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_4362c2244ffb40b3b98464b81d0f7ad3",
              "created_at": "2026-06-02T09:22:52.439609+00:00"
            },
            {
              "event_id": "neural_event_fff03c6e93374b1e9b1940eebee82348",
              "event_type": "SPREAD_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_4362c2244ffb40b3b98464b81d0f7ad3:SPREAD_CHANGED",
              "created_at": "2026-06-02T09:22:52.794518+00:00"
            },
            {
              "event_id": "neural_event_dee1b2843556417fb380bf40ba9cc83c",
              "event_type": "LIQUIDITY_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_4362c2244ffb40b3b98464b81d0f7ad3:LIQUIDITY_CHANGED",
              "created_at": "2026-06-02T09:22:53.241295+00:00"
            },
            {
              "event_id": "neural_event_0430a267b5f440019d227baf2b3ac7ea",
              "event_type": "AI_CONTEXT_UPDATED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "anthropic",
              "neuron": "AI Context Brain",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_c660190888cc3a6437be7ef2",
              "created_at": "2026-06-02T09:23:07.272135+00:00"
            }
          ],
          "errors": [],
          "missing_providers": [],
          "degraded_providers": [],
          "whale_status": "NO_WHALE_EVENT_FOUND",
          "secrets_exposed": false,
          "ai_context_router": {
            "mock_data": false,
            "status": "OK",
            "run_id": "source_to_neuron_f5bb7a8a35b4447bb4370a718fa036f6",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "providers_attempted": [
              {
                "provider": "ollama",
                "status": "FAILED",
                "reason": "OLLAMA_TIMEOUT",
                "attempts": [
                  {
                    "endpoint": "http://host.docker.internal:11434",
                    "model": "qwen3:4b",
                    "reason": "OLLAMA_TIMEOUT"
                  }
                ]
              },
              {
                "provider": "anthropic",
                "status": "OK",
                "reason": "COMPLETED",
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 3038,
                "response_hash": "204a61038aa79027ffabb57a63cdacd1c4b15cdd65135760599149871e892125"
              }
            ],
            "event": {
              "id": 61,
              "event_id": "neural_event_0430a267b5f440019d227baf2b3ac7ea",
              "event_type": "AI_CONTEXT_UPDATED",
              "correlation_id": "source_to_neuron_f5bb7a8a35b4447bb4370a718fa036f6",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "source_component": "AI Context Brain",
              "source_type": "brain",
              "priority": 5,
              "payload_json": {
                "model": "claude-haiku-4-5-20251001",
                "status": "COMPLETED",
                "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input from: provider, news, orderbook, whale, PnL collectors. Will return contextual analysis only. Trade creation, risk bypass, capital allocation, and state changes blocked at governance layer.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"trade_creation\": \"blocked\",\n    \"risk_bypass\": \"blocked\",\n    \"capital_allocation\": \"requires_coordinator\",\n    \"state_changes\": \"requires_governor\",\n    \"output_type\": \"context_analysis_only\"\n  },\n  \"ready_for\": [\n    \"provider_data\",\n    \"news_signals\",\n    \"orderbook_snapshots\",\n    \"whale_activity\",\n    \"pnl_metrics\"\n  ]\n}\n```\n\n**Awaiting source-backed evidence input.** Submit bounded data and I will return compact contextual analysis with status, summary, and confidence only.",
                "attempts": [
                  {
                    "reason": "OLLAMA_TIMEOUT",
                    "status": "FAILED",
                    "attempts": [
                      {
                        "model": "qwen3:4b",
                        "reason": "OLLAMA_TIMEOUT",
                        "endpoint": "http://host.docker.internal:11434"
                      }
                    ],
                    "provider": "ollama"
                  },
                  {
                    "model": "claude-haiku-4-5-20251001",
                    "reason": "COMPLETED",
                    "status": "OK",
                    "provider": "anthropic",
                    "latency_ms": 3038,
                    "response_hash": "204a61038aa79027ffabb57a63cdacd1c4b15cdd65135760599149871e892125"
                  }
                ],
                "provider": "anthropic",
                "confidence": 0.5,
                "source_refs": [
                  {
                    "source_table": "ai_responses",
                    "source_record_id": "ai_resp_context_router_c660190888cc3a6437be7ef2"
                  }
                ]
              },
              "created_at": "2026-06-02T09:23:07.272135+00:00",
              "consumed_count": 0,
              "status": "PUBLISHED",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_c660190888cc3a6437be7ef2",
              "schema_version": 1,
              "metadata_json": {
                "router": "ai_context_fallback",
                "provider": "anthropic",
                "source_to_neuron": true
              }
            },
            "ai_request_id": "ai_req_context_router_0b9ba8566b90d86fd5c3b2ab",
            "ai_response_id": "ai_resp_context_router_c660190888cc3a6437be7ef2",
            "latency_ms": 13134,
            "secrets_exposed": false
          },
          "safety_before": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10350,
            "exit_plans": 10350,
            "coordinator_decisions": 10646,
            "brain_outputs": 10682,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "safety_after": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10350,
            "exit_plans": 10350,
            "coordinator_decisions": 10646,
            "brain_outputs": 10682,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "trading_mutation_detected": false
        },
        "paper_execution": {
          "mock_data": false,
          "run_id": "paper_execution_659a6d12085248adb174f6194f63d11f",
          "cycle_id": "active_30m_observation_20260602T091845Z_cycle_2",
          "system_power": "ON",
          "started_at": "2026-06-02T09:23:09.716136+00:00",
          "finished_at": "2026-06-02T09:23:09.779915+00:00",
          "status": "NO_VALID_PAPER_INTENTS",
          "intents_checked": 3,
          "executable_intents": 0,
          "orders_created": 0,
          "fills_created": 0,
          "positions_created": 0,
          "blocked_intents": 3,
          "duplicate_skipped": 0,
          "block_reasons_json": {
            "INTENT_ALREADY_EXECUTED": 3,
            "MISSING_TRUSTED_ORDERBOOK": 3
          },
          "real_orders_delta": 0,
          "live_orders_delta": 0,
          "fills_v2_delta": 0,
          "positions_delta": 0,
          "error_message": null,
          "metadata_json": {
            "reason": "no executable paper intents"
          }
        },
        "paper_exits": {
          "mock_data": false,
          "run_id": "paper_exit_loop_1aa8ca7688f74930bae1c84f559aca0d",
          "system_power": "ON",
          "status": "NO_OPEN_PAPER_POSITIONS",
          "open_positions_checked": 0,
          "closed_positions_count": 0,
          "marked_positions_count": 0,
          "blocked_positions_count": 0,
          "no_exit_price_count": 0,
          "no_exit_condition_count": 0,
          "duplicate_close_skipped_count": 0,
          "orphan_positions_count": 0,
          "realized_pnl": 0,
          "unrealized_pnl": null,
          "paper_orders_delta": 0,
          "paper_positions_delta": 0,
          "real_orders_delta": 0,
          "fills_delta": 0,
          "live_orders_delta": 0,
          "started_at": "2026-06-02T09:23:09.824001+00:00",
          "finished_at": "2026-06-02T09:23:09.862001+00:00",
          "error_summary": null,
          "metadata": {
            "paper_orders": 9,
            "paper_positions": 9,
            "no_fake_pnl": true
          }
        }
      },
      "errors": []
    },
    "repeated_api_failures": 0,
    "repeated_cycle_failures": 0,
    "deltas": {
      "neural_events": 14,
      "mesh_sessions": 3,
      "shared_awareness": 3,
      "brain_opinions": 12,
      "mesh_coordinator_decisions": 3,
      "capital_evaluations": 3,
      "position_awareness": 0,
      "paper": {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "paper_position_closes": 0,
        "paper_trade_ledger": 0,
        "orders_v2": 0,
        "fills_v2": 0,
        "canonical_positions": 0,
        "real_orders_current": 0,
        "live_orders": 0
      },
      "events_by_type": {
        "AI_CONTEXT_UNAVAILABLE": 0,
        "AI_CONTEXT_UPDATED": 2,
        "LIQUIDITY_CHANGED": 2,
        "MARKET_REPRICING": 2,
        "NEWS_DETECTED": 4,
        "ORDERBOOK_REFRESHED": 2,
        "PNL_CHANGED": 0,
        "RISK_CHANGED": 0,
        "SPREAD_CHANGED": 2,
        "WHALE_DETECTED": 0
      }
    }
  },
  {
    "timestamp": "2026-06-02T09:26:49.684227+00:00",
    "system_power": "ON",
    "runtime_health": "HEALTHY",
    "endpoint_status": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/source-to-neuron-flow": "OK",
      "/dashboard/api/v2/ai-context-router": "OK",
      "/dashboard/api/v2/neural-bus": "OK",
      "/dashboard/api/v2/mesh-sessions": "OK",
      "/dashboard/api/v2/shared-awareness": "OK",
      "/dashboard/api/v2/multi-brain-consumption": "OK",
      "/dashboard/api/v2/mesh-coordinator": "OK",
      "/dashboard/api/v2/capital-brain": "OK",
      "/dashboard/api/v2/positions-awareness": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/trade-forensics": "OK",
      "/dashboard/api/v2/overnight/status": "OK",
      "/dashboard/api/v2/source-status": "OK"
    },
    "mock_data_endpoints": [],
    "secret_exposed": false,
    "source_health": "OK",
    "degraded_sources": [],
    "ai_router": {
      "latest_status": "OK",
      "selected_provider": "anthropic",
      "ollama_status": {
        "status": "FAILED",
        "reason": "OLLAMA_TIMEOUT",
        "last_run_id": "source_to_neuron_de75c111255d4363ab4d5674b6a4e57c"
      },
      "anthropic_status": {
        "status": "OK",
        "reason": "COMPLETED",
        "last_run_id": "source_to_neuron_de75c111255d4363ab4d5674b6a4e57c"
      },
      "openai_status": {
        "status": "FAILED",
        "reason": "OPENAI_QUOTA_EXCEEDED",
        "last_run_id": "post_env_ai_router_verification_20260602"
      },
      "success_count": 4,
      "unavailable_count": 2,
      "secrets_exposed": false
    },
    "events_by_type": {
      "ORDERBOOK_REFRESHED": 13,
      "NEWS_DETECTED": 12,
      "LIQUIDITY_CHANGED": 6,
      "MARKET_REPRICING": 6,
      "SPREAD_CHANGED": 6,
      "AI_CONTEXT_UPDATED": 4,
      "RISK_CHANGED": 4,
      "AI_CONTEXT_UNAVAILABLE": 2,
      "PNL_CHANGED": 2,
      "WHALE_DETECTED": 1
    },
    "neural_events": 56,
    "mesh_sessions": 29,
    "shared_awareness": 29,
    "brain_opinions": 89,
    "mesh_coordinator_decisions": 19,
    "mesh_conflicts_detected": 13,
    "source_brain_count_avg": 4.0455,
    "capital_evaluations": 17,
    "capital_decisions": {
      "CAPITAL_SUPPORT": 15,
      "CAPITAL_BLOCK": 1,
      "CAPITAL_RELEASE_REVIEW": 1
    },
    "position_awareness": 1,
    "position_reactions": {
      "PNL_RISING": 2,
      "CAPITAL_PRESSURE": 1,
      "PNL_FALLING": 1,
      "POSITION_AGING": 1
    },
    "paper": {
      "live_orders": 0,
      "live_enabled": false,
      "shadow_enabled": false,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "open_positions": 0,
      "closed_positions": 6,
      "active_positions_without_fills": 0,
      "paper_lineage": "OK",
      "capital_reconciliation": "OK",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "top_blockers": [
        {
          "blocker": "MISSING_TRUSTED_ORDERBOOK",
          "count": 2586
        },
        {
          "blocker": "INTENT_ALREADY_EXECUTED",
          "count": 1872
        }
      ]
    },
    "forensics_active_count": 6,
    "forensics_quarantined_count": 3,
    "cycle_index": 3,
    "active_cycle": {
      "correlation_id": "active_30m_observation_20260602T091845Z_cycle_3",
      "outputs": {
        "source_to_neuron": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_de75c111255d4363ab4d5674b6a4e57c",
          "blocked": false,
          "providers_checked": [
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
            "polymarket_activity_readonly",
            "ollama_local_model",
            "news_provider",
            "reddit_or_social_provider"
          ],
          "provider_status": {
            "polymarket_gamma": {
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
              "last_success_at": "2026-06-02T09:26:15.534236+00:00",
              "last_error_at": null,
              "latency_ms": 1158,
              "details_json": {
                "event_count": 10,
                "sample_market_id": "2169995",
                "sample_token_available": true,
                "token_candidates": 34
              },
              "notes": "Gamma active events check succeeded."
            },
            "polymarket_clob_orderbook": {
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
              "last_success_at": "2026-06-02T09:26:16.359241+00:00",
              "last_error_at": null,
              "latency_ms": 818,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48224544.61,
                "last_trade_price_present": true
              },
              "notes": "CLOB /book read-only check succeeded."
            },
            "polymarket_clob_prices": {
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
              "last_success_at": "2026-06-02T09:26:16.359315+00:00",
              "last_error_at": null,
              "latency_ms": 818,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48224544.61,
                "last_trade_price_present": true
              },
              "notes": "Price truth derived from read-only CLOB book response."
            },
            "polymarket_clob_spreads": {
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
              "last_success_at": "2026-06-02T09:26:16.359354+00:00",
              "last_error_at": null,
              "latency_ms": 818,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48224544.61,
                "last_trade_price_present": true
              },
              "notes": "Spread and depth truth derived from read-only CLOB book response."
            },
            "polymarket_activity_readonly": {
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
              "last_success_at": "2026-06-02T09:26:16.907389+00:00",
              "last_error_at": null,
              "latency_ms": 546,
              "details_json": {
                "sample_count": 1
              },
              "notes": "Data API /trades read-only discovery check succeeded."
            },
            "ollama_local_model": {
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
              "last_success_at": "2026-06-02T09:26:17.011856+00:00",
              "last_error_at": null,
              "latency_ms": 101,
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
                  "http://host.docker.internal:11434/api/tags"
                ]
              },
              "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
            },
            "news_provider": {
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
            "reddit_or_social_provider": {
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
            },
            "ai_context_router": {
              "runtime_status": "ACTIVE",
              "selected_provider": "anthropic",
              "final_reason": "AI_CONTEXT_UPDATED",
              "secret_value_exposed": false
            }
          },
          "events_created": 7,
          "events_by_type": {
            "MARKET_REPRICING": 1,
            "NEWS_DETECTED": 2,
            "ORDERBOOK_REFRESHED": 1,
            "SPREAD_CHANGED": 1,
            "LIQUIDITY_CHANGED": 1,
            "AI_CONTEXT_UPDATED": 1
          },
          "sessions_updated": 21,
          "awareness_domains_updated": 83,
          "brain_opinions_created": 25,
          "coordinator_decisions_created": 5,
          "latest_items": [
            {
              "event_id": "neural_event_52540fe17c3243c990d1c6318caf12cf",
              "event_type": "MARKET_REPRICING",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_gamma",
              "neuron": "Market Neuron",
              "source_table": "source_status",
              "source_record_id": "polymarket_gamma:source_to_neuron_de75c111255d4363ab4d5674b6a4e57c",
              "created_at": "2026-06-02T09:26:17.485128+00:00"
            },
            {
              "event_id": "neural_event_48c4a2323c1344d0ae7d45f6a83ba868",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "rss",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_06565325e9844b9e9100c56795a2e0f3",
              "created_at": "2026-06-02T09:26:19.636351+00:00"
            },
            {
              "event_id": "neural_event_08095151d64c48febb2e359469b4569c",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "newsapi",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_d0a640fa98954e2294a74669e11c66bb",
              "created_at": "2026-06-02T09:26:21.069691+00:00"
            },
            {
              "event_id": "neural_event_6a12511ffbf24113b03f6281373fc79b",
              "event_type": "ORDERBOOK_REFRESHED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Orderbook Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_f3243671a84f4e60894a953454d9c774",
              "created_at": "2026-06-02T09:26:21.635719+00:00"
            },
            {
              "event_id": "neural_event_035f182ed0f942228757fbbfe0dff6a1",
              "event_type": "SPREAD_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_f3243671a84f4e60894a953454d9c774:SPREAD_CHANGED",
              "created_at": "2026-06-02T09:26:22.067776+00:00"
            },
            {
              "event_id": "neural_event_9da15025f6ac4538b0d8a8ec35700dde",
              "event_type": "LIQUIDITY_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_f3243671a84f4e60894a953454d9c774:LIQUIDITY_CHANGED",
              "created_at": "2026-06-02T09:26:22.592325+00:00"
            },
            {
              "event_id": "neural_event_a82633f3189842b5a0a8e98e71da8f79",
              "event_type": "AI_CONTEXT_UPDATED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "anthropic",
              "neuron": "AI Context Brain",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_08daa9baaf6f5345750caf66",
              "created_at": "2026-06-02T09:26:36.893423+00:00"
            }
          ],
          "errors": [],
          "missing_providers": [],
          "degraded_providers": [],
          "whale_status": "NO_WHALE_EVENT_FOUND",
          "secrets_exposed": false,
          "ai_context_router": {
            "mock_data": false,
            "status": "OK",
            "run_id": "source_to_neuron_de75c111255d4363ab4d5674b6a4e57c",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "providers_attempted": [
              {
                "provider": "ollama",
                "status": "FAILED",
                "reason": "OLLAMA_TIMEOUT",
                "attempts": [
                  {
                    "endpoint": "http://host.docker.internal:11434",
                    "model": "qwen3:4b",
                    "reason": "OLLAMA_TIMEOUT"
                  }
                ]
              },
              {
                "provider": "anthropic",
                "status": "OK",
                "reason": "COMPLETED",
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 3502,
                "response_hash": "0eaa69af6c0816e87ac4ec773a82f655b78e1219317a9f820bb6dea52a4fc86d"
              }
            ],
            "event": {
              "id": 79,
              "event_id": "neural_event_a82633f3189842b5a0a8e98e71da8f79",
              "event_type": "AI_CONTEXT_UPDATED",
              "correlation_id": "source_to_neuron_de75c111255d4363ab4d5674b6a4e57c",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "source_component": "AI Context Brain",
              "source_type": "brain",
              "priority": 5,
              "payload_json": {
                "model": "claude-haiku-4-5-20251001",
                "status": "COMPLETED",
                "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input from: provider, news, orderbook, whale, PnL collectors. Will return contextual analysis only. Trade creation, risk bypass, capital allocation, and state changes blocked at governance layer.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"trade_creation\": \"blocked\",\n    \"risk_bypass\": \"blocked\",\n    \"capital_allocation\": \"blocked\",\n    \"state_modification\": \"blocked\",\n    \"output_scope\": \"evidence_context_only\"\n  },\n  \"ready_for\": [\n    \"provider_data\",\n    \"news_signals\",\n    \"orderbook_analysis\",\n    \"whale_activity\",\n    \"pnl_metrics\"\n  ]\n}\n```\n\n**Awaiting source-backed input.** Submit evidence with source attribution and I will return bounded contextual analysis only.",
                "attempts": [
                  {
                    "reason": "OLLAMA_TIMEOUT",
                    "status": "FAILED",
                    "attempts": [
                      {
                        "model": "qwen3:4b",
                        "reason": "OLLAMA_TIMEOUT",
                        "endpoint": "http://host.docker.internal:11434"
                      }
                    ],
                    "provider": "ollama"
                  },
                  {
                    "model": "claude-haiku-4-5-20251001",
                    "reason": "COMPLETED",
                    "status": "OK",
                    "provider": "anthropic",
                    "latency_ms": 3502,
                    "response_hash": "0eaa69af6c0816e87ac4ec773a82f655b78e1219317a9f820bb6dea52a4fc86d"
                  }
                ],
                "provider": "anthropic",
                "confidence": 0.5,
                "source_refs": [
                  {
                    "source_table": "ai_responses",
                    "source_record_id": "ai_resp_context_router_08daa9baaf6f5345750caf66"
                  }
                ]
              },
              "created_at": "2026-06-02T09:26:36.893423+00:00",
              "consumed_count": 0,
              "status": "PUBLISHED",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_08daa9baaf6f5345750caf66",
              "schema_version": 1,
              "metadata_json": {
                "router": "ai_context_fallback",
                "provider": "anthropic",
                "source_to_neuron": true
              }
            },
            "ai_request_id": "ai_req_context_router_54c91c3b882f41765e650f97",
            "ai_response_id": "ai_resp_context_router_08daa9baaf6f5345750caf66",
            "latency_ms": 13580,
            "secrets_exposed": false
          },
          "safety_before": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10360,
            "exit_plans": 10360,
            "coordinator_decisions": 10656,
            "brain_outputs": 10692,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "safety_after": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10360,
            "exit_plans": 10360,
            "coordinator_decisions": 10656,
            "brain_outputs": 10692,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "trading_mutation_detected": false
        },
        "paper_execution": {
          "mock_data": false,
          "run_id": "paper_execution_c1af867c694c4f599cee5c9547080321",
          "cycle_id": "active_30m_observation_20260602T091845Z_cycle_3",
          "system_power": "ON",
          "started_at": "2026-06-02T09:26:44.308553+00:00",
          "finished_at": "2026-06-02T09:26:44.379438+00:00",
          "status": "NO_VALID_PAPER_INTENTS",
          "intents_checked": 3,
          "executable_intents": 0,
          "orders_created": 0,
          "fills_created": 0,
          "positions_created": 0,
          "blocked_intents": 3,
          "duplicate_skipped": 0,
          "block_reasons_json": {
            "INTENT_ALREADY_EXECUTED": 3,
            "MISSING_TRUSTED_ORDERBOOK": 3
          },
          "real_orders_delta": 0,
          "live_orders_delta": 0,
          "fills_v2_delta": 0,
          "positions_delta": 0,
          "error_message": null,
          "metadata_json": {
            "reason": "no executable paper intents"
          }
        },
        "paper_exits": {
          "mock_data": false,
          "run_id": "paper_exit_loop_a71fd072dc03436f8d8548adf3cf378d",
          "system_power": "ON",
          "status": "NO_OPEN_PAPER_POSITIONS",
          "open_positions_checked": 0,
          "closed_positions_count": 0,
          "marked_positions_count": 0,
          "blocked_positions_count": 0,
          "no_exit_price_count": 0,
          "no_exit_condition_count": 0,
          "duplicate_close_skipped_count": 0,
          "orphan_positions_count": 0,
          "realized_pnl": 0,
          "unrealized_pnl": null,
          "paper_orders_delta": 0,
          "paper_positions_delta": 0,
          "real_orders_delta": 0,
          "fills_delta": 0,
          "live_orders_delta": 0,
          "started_at": "2026-06-02T09:26:44.408817+00:00",
          "finished_at": "2026-06-02T09:26:44.467271+00:00",
          "error_summary": null,
          "metadata": {
            "paper_orders": 9,
            "paper_positions": 9,
            "no_fake_pnl": true
          }
        }
      },
      "errors": []
    },
    "repeated_api_failures": 0,
    "repeated_cycle_failures": 0,
    "deltas": {
      "neural_events": 21,
      "mesh_sessions": 4,
      "shared_awareness": 4,
      "brain_opinions": 16,
      "mesh_coordinator_decisions": 4,
      "capital_evaluations": 4,
      "position_awareness": 0,
      "paper": {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "paper_position_closes": 0,
        "paper_trade_ledger": 0,
        "orders_v2": 0,
        "fills_v2": 0,
        "canonical_positions": 0,
        "real_orders_current": 0,
        "live_orders": 0
      },
      "events_by_type": {
        "AI_CONTEXT_UNAVAILABLE": 0,
        "AI_CONTEXT_UPDATED": 3,
        "LIQUIDITY_CHANGED": 3,
        "MARKET_REPRICING": 3,
        "NEWS_DETECTED": 6,
        "ORDERBOOK_REFRESHED": 3,
        "PNL_CHANGED": 0,
        "RISK_CHANGED": 0,
        "SPREAD_CHANGED": 3,
        "WHALE_DETECTED": 0
      }
    }
  },
  {
    "timestamp": "2026-06-02T09:30:15.150845+00:00",
    "system_power": "ON",
    "runtime_health": "HEALTHY",
    "endpoint_status": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/source-to-neuron-flow": "OK",
      "/dashboard/api/v2/ai-context-router": "OK",
      "/dashboard/api/v2/neural-bus": "OK",
      "/dashboard/api/v2/mesh-sessions": "OK",
      "/dashboard/api/v2/shared-awareness": "OK",
      "/dashboard/api/v2/multi-brain-consumption": "OK",
      "/dashboard/api/v2/mesh-coordinator": "OK",
      "/dashboard/api/v2/capital-brain": "OK",
      "/dashboard/api/v2/positions-awareness": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/trade-forensics": "OK",
      "/dashboard/api/v2/overnight/status": "OK",
      "/dashboard/api/v2/source-status": "OK"
    },
    "mock_data_endpoints": [],
    "secret_exposed": false,
    "source_health": "OK",
    "degraded_sources": [],
    "ai_router": {
      "latest_status": "OK",
      "selected_provider": "anthropic",
      "ollama_status": {
        "status": "FAILED",
        "reason": "OLLAMA_TIMEOUT",
        "last_run_id": "source_to_neuron_eb85380bdf1c42f98c94c3c4f5a5a317"
      },
      "anthropic_status": {
        "status": "OK",
        "reason": "COMPLETED",
        "last_run_id": "source_to_neuron_eb85380bdf1c42f98c94c3c4f5a5a317"
      },
      "openai_status": {
        "status": "FAILED",
        "reason": "OPENAI_QUOTA_EXCEEDED",
        "last_run_id": "post_env_ai_router_verification_20260602"
      },
      "success_count": 5,
      "unavailable_count": 2,
      "secrets_exposed": false
    },
    "events_by_type": {
      "NEWS_DETECTED": 14,
      "ORDERBOOK_REFRESHED": 14,
      "LIQUIDITY_CHANGED": 7,
      "MARKET_REPRICING": 7,
      "SPREAD_CHANGED": 7,
      "AI_CONTEXT_UPDATED": 5,
      "RISK_CHANGED": 4,
      "AI_CONTEXT_UNAVAILABLE": 2,
      "PNL_CHANGED": 2,
      "WHALE_DETECTED": 2
    },
    "neural_events": 64,
    "mesh_sessions": 31,
    "shared_awareness": 31,
    "brain_opinions": 97,
    "mesh_coordinator_decisions": 21,
    "mesh_conflicts_detected": 14,
    "source_brain_count_avg": 4.0417,
    "capital_evaluations": 19,
    "capital_decisions": {
      "CAPITAL_SUPPORT": 16,
      "CAPITAL_BLOCK": 2,
      "CAPITAL_RELEASE_REVIEW": 1
    },
    "position_awareness": 1,
    "position_reactions": {
      "PNL_RISING": 2,
      "CAPITAL_PRESSURE": 1,
      "PNL_FALLING": 1,
      "POSITION_AGING": 1
    },
    "paper": {
      "live_orders": 0,
      "live_enabled": false,
      "shadow_enabled": false,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "open_positions": 0,
      "closed_positions": 6,
      "active_positions_without_fills": 0,
      "paper_lineage": "OK",
      "capital_reconciliation": "OK",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "top_blockers": [
        {
          "blocker": "MISSING_TRUSTED_ORDERBOOK",
          "count": 2595
        },
        {
          "blocker": "INTENT_ALREADY_EXECUTED",
          "count": 1881
        }
      ]
    },
    "forensics_active_count": 6,
    "forensics_quarantined_count": 3,
    "cycle_index": 4,
    "active_cycle": {
      "correlation_id": "active_30m_observation_20260602T091845Z_cycle_4",
      "outputs": {
        "source_to_neuron": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_eb85380bdf1c42f98c94c3c4f5a5a317",
          "blocked": false,
          "providers_checked": [
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
            "polymarket_activity_readonly",
            "ollama_local_model",
            "news_provider",
            "reddit_or_social_provider"
          ],
          "provider_status": {
            "polymarket_gamma": {
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
              "last_success_at": "2026-06-02T09:29:50.010992+00:00",
              "last_error_at": null,
              "latency_ms": 132,
              "details_json": {
                "event_count": 10,
                "sample_market_id": "2169995",
                "sample_token_available": true,
                "token_candidates": 34
              },
              "notes": "Gamma active events check succeeded."
            },
            "polymarket_clob_orderbook": {
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
              "last_success_at": "2026-06-02T09:29:50.288746+00:00",
              "last_error_at": null,
              "latency_ms": 276,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 46649018.73,
                "last_trade_price_present": true
              },
              "notes": "CLOB /book read-only check succeeded."
            },
            "polymarket_clob_prices": {
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
              "last_success_at": "2026-06-02T09:29:50.288787+00:00",
              "last_error_at": null,
              "latency_ms": 276,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 46649018.73,
                "last_trade_price_present": true
              },
              "notes": "Price truth derived from read-only CLOB book response."
            },
            "polymarket_clob_spreads": {
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
              "last_success_at": "2026-06-02T09:29:50.288793+00:00",
              "last_error_at": null,
              "latency_ms": 276,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 46649018.73,
                "last_trade_price_present": true
              },
              "notes": "Spread and depth truth derived from read-only CLOB book response."
            },
            "polymarket_activity_readonly": {
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
              "last_success_at": "2026-06-02T09:29:50.550273+00:00",
              "last_error_at": null,
              "latency_ms": 260,
              "details_json": {
                "sample_count": 1
              },
              "notes": "Data API /trades read-only discovery check succeeded."
            },
            "ollama_local_model": {
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
              "last_success_at": "2026-06-02T09:29:50.618853+00:00",
              "last_error_at": null,
              "latency_ms": 68,
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
                  "http://host.docker.internal:11434/api/tags"
                ]
              },
              "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
            },
            "news_provider": {
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
            "reddit_or_social_provider": {
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
            },
            "ai_context_router": {
              "runtime_status": "ACTIVE",
              "selected_provider": "anthropic",
              "final_reason": "AI_CONTEXT_UPDATED",
              "secret_value_exposed": false
            }
          },
          "events_created": 8,
          "events_by_type": {
            "MARKET_REPRICING": 1,
            "NEWS_DETECTED": 2,
            "ORDERBOOK_REFRESHED": 1,
            "SPREAD_CHANGED": 1,
            "LIQUIDITY_CHANGED": 1,
            "WHALE_DETECTED": 1,
            "AI_CONTEXT_UPDATED": 1
          },
          "sessions_updated": 22,
          "awareness_domains_updated": 88,
          "brain_opinions_created": 30,
          "coordinator_decisions_created": 6,
          "latest_items": [
            {
              "event_id": "neural_event_4bc0676d392546e4848cbac68691d457",
              "event_type": "MARKET_REPRICING",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_gamma",
              "neuron": "Market Neuron",
              "source_table": "source_status",
              "source_record_id": "polymarket_gamma:source_to_neuron_eb85380bdf1c42f98c94c3c4f5a5a317",
              "created_at": "2026-06-02T09:29:50.835351+00:00"
            },
            {
              "event_id": "neural_event_16d55bf77f4847809a70353dcff8d0ff",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "rss",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_68919337677f4a618c05e6ea9fa7aee6",
              "created_at": "2026-06-02T09:29:51.861344+00:00"
            },
            {
              "event_id": "neural_event_41d91306c8a14557befbc3c9879b4a7c",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "newsapi",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_0645b0f6efb34de5945e52f92d17388c",
              "created_at": "2026-06-02T09:29:52.527233+00:00"
            },
            {
              "event_id": "neural_event_ceddb3bf80744ee7a66c79c918f6886a",
              "event_type": "ORDERBOOK_REFRESHED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Orderbook Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_2644aaa574b940449165370305da91ef",
              "created_at": "2026-06-02T09:29:52.968796+00:00"
            },
            {
              "event_id": "neural_event_4c911571ef764a5485f6d17c24fa4fc7",
              "event_type": "SPREAD_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_2644aaa574b940449165370305da91ef:SPREAD_CHANGED",
              "created_at": "2026-06-02T09:29:53.572371+00:00"
            },
            {
              "event_id": "neural_event_17d16cbca876416fbaa262d3cec1d4e2",
              "event_type": "LIQUIDITY_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_2644aaa574b940449165370305da91ef:LIQUIDITY_CHANGED",
              "created_at": "2026-06-02T09:29:54.076390+00:00"
            },
            {
              "event_id": "neural_event_4e629448ec144b61ba32f8d00baef46e",
              "event_type": "WHALE_DETECTED",
              "market_id": "0xe35304decf0479f6ea07bd221ed18de7bbe3956e31e08313975418077f7cee4a",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_activity_readonly",
              "neuron": "Whale Neuron",
              "source_table": "whale_events",
              "source_record_id": "whale_clob_30452e56a127d69d8ff45490",
              "created_at": "2026-06-02T09:29:54.738094+00:00"
            },
            {
              "event_id": "neural_event_eea2254845694991b268ce7279af2ea5",
              "event_type": "AI_CONTEXT_UPDATED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "anthropic",
              "neuron": "AI Context Brain",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_f6ca5b2a5dca87e8d69f6888",
              "created_at": "2026-06-02T09:30:07.917770+00:00"
            }
          ],
          "errors": [],
          "missing_providers": [],
          "degraded_providers": [],
          "whale_status": "WHALE_DETECTED",
          "secrets_exposed": false,
          "ai_context_router": {
            "mock_data": false,
            "status": "OK",
            "run_id": "source_to_neuron_eb85380bdf1c42f98c94c3c4f5a5a317",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "providers_attempted": [
              {
                "provider": "ollama",
                "status": "FAILED",
                "reason": "OLLAMA_TIMEOUT",
                "attempts": [
                  {
                    "endpoint": "http://host.docker.internal:11434",
                    "model": "qwen3:4b",
                    "reason": "OLLAMA_TIMEOUT"
                  }
                ]
              },
              {
                "provider": "anthropic",
                "status": "OK",
                "reason": "COMPLETED",
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 2736,
                "response_hash": "047103bbbeb14a50ebb1f40ec591fbd26f6ee0b58cc8ddce693c7660f051f0af"
              }
            ],
            "event": {
              "id": 100,
              "event_id": "neural_event_eea2254845694991b268ce7279af2ea5",
              "event_type": "AI_CONTEXT_UPDATED",
              "correlation_id": "source_to_neuron_eb85380bdf1c42f98c94c3c4f5a5a317",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "source_component": "AI Context Brain",
              "source_type": "brain",
              "priority": 5,
              "payload_json": {
                "model": "claude-haiku-4-5-20251001",
                "status": "COMPLETED",
                "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input. Capable of processing: provider data, news feeds, orderbook snapshots, whale activity, and PnL metrics. Output limited to context analysis only. Trade creation, risk bypass, capital allocation, and position management blocked at governance layer.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"trade_creation\": \"blocked\",\n    \"risk_bypass\": \"blocked\",\n    \"capital_allocation\": \"blocked\",\n    \"position_management\": \"blocked\",\n    \"output_type\": \"context_analysis_only\"\n  },\n  \"ready_for\": [\n    \"provider_evidence\",\n    \"news_evidence\",\n    \"orderbook_evidence\",\n    \"whale_activity_evidence\",\n    \"pnl_evidence\"\n  ]\n}\n```\n\n**Awaiting source-backed input for bounded analysis run.**",
                "attempts": [
                  {
                    "reason": "OLLAMA_TIMEOUT",
                    "status": "FAILED",
                    "attempts": [
                      {
                        "model": "qwen3:4b",
                        "reason": "OLLAMA_TIMEOUT",
                        "endpoint": "http://host.docker.internal:11434"
                      }
                    ],
                    "provider": "ollama"
                  },
                  {
                    "model": "claude-haiku-4-5-20251001",
                    "reason": "COMPLETED",
                    "status": "OK",
                    "provider": "anthropic",
                    "latency_ms": 2736,
                    "response_hash": "047103bbbeb14a50ebb1f40ec591fbd26f6ee0b58cc8ddce693c7660f051f0af"
                  }
                ],
                "provider": "anthropic",
                "confidence": 0.5,
                "source_refs": [
                  {
                    "source_table": "ai_responses",
                    "source_record_id": "ai_resp_context_router_f6ca5b2a5dca87e8d69f6888"
                  }
                ]
              },
              "created_at": "2026-06-02T09:30:07.917770+00:00",
              "consumed_count": 0,
              "status": "PUBLISHED",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_f6ca5b2a5dca87e8d69f6888",
              "schema_version": 1,
              "metadata_json": {
                "router": "ai_context_fallback",
                "provider": "anthropic",
                "source_to_neuron": true
              }
            },
            "ai_request_id": "ai_req_context_router_96f51a4401d3bd1d74f3e707",
            "ai_response_id": "ai_resp_context_router_f6ca5b2a5dca87e8d69f6888",
            "latency_ms": 12862,
            "secrets_exposed": false
          },
          "safety_before": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10370,
            "exit_plans": 10370,
            "coordinator_decisions": 10666,
            "brain_outputs": 10702,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "safety_after": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10370,
            "exit_plans": 10370,
            "coordinator_decisions": 10666,
            "brain_outputs": 10702,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "trading_mutation_detected": false
        },
        "paper_execution": {
          "mock_data": false,
          "run_id": "paper_execution_b5125183b9c9406db470ed5abdce3c39",
          "cycle_id": "active_30m_observation_20260602T091845Z_cycle_4",
          "system_power": "ON",
          "started_at": "2026-06-02T09:30:10.709282+00:00",
          "finished_at": "2026-06-02T09:30:10.773330+00:00",
          "status": "NO_VALID_PAPER_INTENTS",
          "intents_checked": 3,
          "executable_intents": 0,
          "orders_created": 0,
          "fills_created": 0,
          "positions_created": 0,
          "blocked_intents": 3,
          "duplicate_skipped": 0,
          "block_reasons_json": {
            "INTENT_ALREADY_EXECUTED": 3,
            "MISSING_TRUSTED_ORDERBOOK": 3
          },
          "real_orders_delta": 0,
          "live_orders_delta": 0,
          "fills_v2_delta": 0,
          "positions_delta": 0,
          "error_message": null,
          "metadata_json": {
            "reason": "no executable paper intents"
          }
        },
        "paper_exits": {
          "mock_data": false,
          "run_id": "paper_exit_loop_10e695ebf8024c3ebb2b16e7f4359870",
          "system_power": "ON",
          "status": "NO_OPEN_PAPER_POSITIONS",
          "open_positions_checked": 0,
          "closed_positions_count": 0,
          "marked_positions_count": 0,
          "blocked_positions_count": 0,
          "no_exit_price_count": 0,
          "no_exit_condition_count": 0,
          "duplicate_close_skipped_count": 0,
          "orphan_positions_count": 0,
          "realized_pnl": 0,
          "unrealized_pnl": null,
          "paper_orders_delta": 0,
          "paper_positions_delta": 0,
          "real_orders_delta": 0,
          "fills_delta": 0,
          "live_orders_delta": 0,
          "started_at": "2026-06-02T09:30:10.812436+00:00",
          "finished_at": "2026-06-02T09:30:10.870566+00:00",
          "error_summary": null,
          "metadata": {
            "paper_orders": 9,
            "paper_positions": 9,
            "no_fake_pnl": true
          }
        }
      },
      "errors": []
    },
    "repeated_api_failures": 0,
    "repeated_cycle_failures": 0,
    "deltas": {
      "neural_events": 29,
      "mesh_sessions": 6,
      "shared_awareness": 6,
      "brain_opinions": 24,
      "mesh_coordinator_decisions": 6,
      "capital_evaluations": 6,
      "position_awareness": 0,
      "paper": {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "paper_position_closes": 0,
        "paper_trade_ledger": 0,
        "orders_v2": 0,
        "fills_v2": 0,
        "canonical_positions": 0,
        "real_orders_current": 0,
        "live_orders": 0
      },
      "events_by_type": {
        "AI_CONTEXT_UNAVAILABLE": 0,
        "AI_CONTEXT_UPDATED": 4,
        "LIQUIDITY_CHANGED": 4,
        "MARKET_REPRICING": 4,
        "NEWS_DETECTED": 8,
        "ORDERBOOK_REFRESHED": 4,
        "PNL_CHANGED": 0,
        "RISK_CHANGED": 0,
        "SPREAD_CHANGED": 4,
        "WHALE_DETECTED": 1
      }
    }
  },
  {
    "timestamp": "2026-06-02T09:33:43.730364+00:00",
    "system_power": "ON",
    "runtime_health": "HEALTHY",
    "endpoint_status": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/source-to-neuron-flow": "OK",
      "/dashboard/api/v2/ai-context-router": "OK",
      "/dashboard/api/v2/neural-bus": "OK",
      "/dashboard/api/v2/mesh-sessions": "OK",
      "/dashboard/api/v2/shared-awareness": "OK",
      "/dashboard/api/v2/multi-brain-consumption": "OK",
      "/dashboard/api/v2/mesh-coordinator": "OK",
      "/dashboard/api/v2/capital-brain": "OK",
      "/dashboard/api/v2/positions-awareness": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/trade-forensics": "OK",
      "/dashboard/api/v2/overnight/status": "OK",
      "/dashboard/api/v2/source-status": "OK"
    },
    "mock_data_endpoints": [],
    "secret_exposed": false,
    "source_health": "OK",
    "degraded_sources": [],
    "ai_router": {
      "latest_status": "OK",
      "selected_provider": "anthropic",
      "ollama_status": {
        "status": "FAILED",
        "reason": "OLLAMA_TIMEOUT",
        "last_run_id": "source_to_neuron_380840f694b646009ce429d64125232a"
      },
      "anthropic_status": {
        "status": "OK",
        "reason": "COMPLETED",
        "last_run_id": "source_to_neuron_380840f694b646009ce429d64125232a"
      },
      "openai_status": {
        "status": "FAILED",
        "reason": "OPENAI_QUOTA_EXCEEDED",
        "last_run_id": "post_env_ai_router_verification_20260602"
      },
      "success_count": 6,
      "unavailable_count": 2,
      "secrets_exposed": false
    },
    "events_by_type": {
      "NEWS_DETECTED": 16,
      "ORDERBOOK_REFRESHED": 15,
      "LIQUIDITY_CHANGED": 8,
      "MARKET_REPRICING": 8,
      "SPREAD_CHANGED": 8,
      "AI_CONTEXT_UPDATED": 6,
      "RISK_CHANGED": 4,
      "AI_CONTEXT_UNAVAILABLE": 2,
      "PNL_CHANGED": 2,
      "WHALE_DETECTED": 2
    },
    "neural_events": 71,
    "mesh_sessions": 32,
    "shared_awareness": 32,
    "brain_opinions": 101,
    "mesh_coordinator_decisions": 22,
    "mesh_conflicts_detected": 15,
    "source_brain_count_avg": 4.04,
    "capital_evaluations": 20,
    "capital_decisions": {
      "CAPITAL_SUPPORT": 17,
      "CAPITAL_BLOCK": 2,
      "CAPITAL_RELEASE_REVIEW": 1
    },
    "position_awareness": 1,
    "position_reactions": {
      "PNL_RISING": 2,
      "CAPITAL_PRESSURE": 1,
      "PNL_FALLING": 1,
      "POSITION_AGING": 1
    },
    "paper": {
      "live_orders": 0,
      "live_enabled": false,
      "shadow_enabled": false,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "open_positions": 0,
      "closed_positions": 6,
      "active_positions_without_fills": 0,
      "paper_lineage": "OK",
      "capital_reconciliation": "OK",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "top_blockers": [
        {
          "blocker": "MISSING_TRUSTED_ORDERBOOK",
          "count": 2604
        },
        {
          "blocker": "INTENT_ALREADY_EXECUTED",
          "count": 1890
        }
      ]
    },
    "forensics_active_count": 6,
    "forensics_quarantined_count": 3,
    "cycle_index": 5,
    "active_cycle": {
      "correlation_id": "active_30m_observation_20260602T091845Z_cycle_5",
      "outputs": {
        "source_to_neuron": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_380840f694b646009ce429d64125232a",
          "blocked": false,
          "providers_checked": [
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
            "polymarket_activity_readonly",
            "ollama_local_model",
            "news_provider",
            "reddit_or_social_provider"
          ],
          "provider_status": {
            "polymarket_gamma": {
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
              "last_success_at": "2026-06-02T09:33:15.861389+00:00",
              "last_error_at": null,
              "latency_ms": 456,
              "details_json": {
                "event_count": 10,
                "sample_market_id": "2169995",
                "sample_token_available": true,
                "token_candidates": 34
              },
              "notes": "Gamma active events check succeeded."
            },
            "polymarket_clob_orderbook": {
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
              "last_success_at": "2026-06-02T09:33:16.058492+00:00",
              "last_error_at": null,
              "latency_ms": 194,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 46765998.78,
                "last_trade_price_present": true
              },
              "notes": "CLOB /book read-only check succeeded."
            },
            "polymarket_clob_prices": {
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
              "last_success_at": "2026-06-02T09:33:16.058545+00:00",
              "last_error_at": null,
              "latency_ms": 194,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 46765998.78,
                "last_trade_price_present": true
              },
              "notes": "Price truth derived from read-only CLOB book response."
            },
            "polymarket_clob_spreads": {
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
              "last_success_at": "2026-06-02T09:33:16.058551+00:00",
              "last_error_at": null,
              "latency_ms": 194,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 46765998.78,
                "last_trade_price_present": true
              },
              "notes": "Spread and depth truth derived from read-only CLOB book response."
            },
            "polymarket_activity_readonly": {
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
              "last_success_at": "2026-06-02T09:33:16.272650+00:00",
              "last_error_at": null,
              "latency_ms": 213,
              "details_json": {
                "sample_count": 1
              },
              "notes": "Data API /trades read-only discovery check succeeded."
            },
            "ollama_local_model": {
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
              "last_success_at": "2026-06-02T09:33:16.372507+00:00",
              "last_error_at": null,
              "latency_ms": 98,
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
                  "http://host.docker.internal:11434/api/tags"
                ]
              },
              "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
            },
            "news_provider": {
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
            "reddit_or_social_provider": {
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
            },
            "ai_context_router": {
              "runtime_status": "ACTIVE",
              "selected_provider": "anthropic",
              "final_reason": "AI_CONTEXT_UPDATED",
              "secret_value_exposed": false
            }
          },
          "events_created": 7,
          "events_by_type": {
            "MARKET_REPRICING": 1,
            "NEWS_DETECTED": 2,
            "ORDERBOOK_REFRESHED": 1,
            "SPREAD_CHANGED": 1,
            "LIQUIDITY_CHANGED": 1,
            "AI_CONTEXT_UPDATED": 1
          },
          "sessions_updated": 22,
          "awareness_domains_updated": 91,
          "brain_opinions_created": 30,
          "coordinator_decisions_created": 6,
          "latest_items": [
            {
              "event_id": "neural_event_debc4ce3803b4539a6e5734943923f39",
              "event_type": "MARKET_REPRICING",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_gamma",
              "neuron": "Market Neuron",
              "source_table": "source_status",
              "source_record_id": "polymarket_gamma:source_to_neuron_380840f694b646009ce429d64125232a",
              "created_at": "2026-06-02T09:33:16.671322+00:00"
            },
            {
              "event_id": "neural_event_26397cfb94724583b306369e3292d7f2",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "rss",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_5ec1468f78614cb0a589f7f021ed3d06",
              "created_at": "2026-06-02T09:33:17.923320+00:00"
            },
            {
              "event_id": "neural_event_75c2a3000fee4ad08664d221aa14769b",
              "event_type": "NEWS_DETECTED",
              "market_id": "677404",
              "candidate_id": null,
              "position_id": null,
              "provider": "newsapi",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_1ee1a20c6d3240a7afadc883ecab5100",
              "created_at": "2026-06-02T09:33:19.065406+00:00"
            },
            {
              "event_id": "neural_event_a3c91227f3124c7f86c24647e0fd61af",
              "event_type": "ORDERBOOK_REFRESHED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Orderbook Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_bbeae39156c248de8ab3127cc8b1d09c",
              "created_at": "2026-06-02T09:33:19.721873+00:00"
            },
            {
              "event_id": "neural_event_7e69240ce8d1492fb1542d5921b0a537",
              "event_type": "SPREAD_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_bbeae39156c248de8ab3127cc8b1d09c:SPREAD_CHANGED",
              "created_at": "2026-06-02T09:33:20.026051+00:00"
            },
            {
              "event_id": "neural_event_908e98d717384f459e3f999c77c5b7f1",
              "event_type": "LIQUIDITY_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_bbeae39156c248de8ab3127cc8b1d09c:LIQUIDITY_CHANGED",
              "created_at": "2026-06-02T09:33:20.320249+00:00"
            },
            {
              "event_id": "neural_event_6b9b6ece2df44dfda03c7c7b4b3ae877",
              "event_type": "AI_CONTEXT_UPDATED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "anthropic",
              "neuron": "AI Context Brain",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_49c47cec16323d36bc0b40bf",
              "created_at": "2026-06-02T09:33:33.958416+00:00"
            }
          ],
          "errors": [],
          "missing_providers": [],
          "degraded_providers": [],
          "whale_status": "NO_WHALE_EVENT_FOUND",
          "secrets_exposed": false,
          "ai_context_router": {
            "mock_data": false,
            "status": "OK",
            "run_id": "source_to_neuron_380840f694b646009ce429d64125232a",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "providers_attempted": [
              {
                "provider": "ollama",
                "status": "FAILED",
                "reason": "OLLAMA_TIMEOUT",
                "attempts": [
                  {
                    "endpoint": "http://host.docker.internal:11434",
                    "model": "qwen3:4b",
                    "reason": "OLLAMA_TIMEOUT"
                  }
                ]
              },
              {
                "provider": "anthropic",
                "status": "OK",
                "reason": "COMPLETED",
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 2874,
                "response_hash": "0eaa69af6c0816e87ac4ec773a82f655b78e1219317a9f820bb6dea52a4fc86d"
              }
            ],
            "event": {
              "id": 122,
              "event_id": "neural_event_6b9b6ece2df44dfda03c7c7b4b3ae877",
              "event_type": "AI_CONTEXT_UPDATED",
              "correlation_id": "source_to_neuron_380840f694b646009ce429d64125232a",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "source_component": "AI Context Brain",
              "source_type": "brain",
              "priority": 5,
              "payload_json": {
                "model": "claude-haiku-4-5-20251001",
                "status": "COMPLETED",
                "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input from: provider, news, orderbook, whale, PnL collectors. Will return contextual analysis only. Trade creation, risk bypass, capital allocation, and state changes blocked at governance layer.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"trade_creation\": \"blocked\",\n    \"risk_bypass\": \"blocked\",\n    \"capital_allocation\": \"blocked\",\n    \"state_modification\": \"blocked\",\n    \"output_scope\": \"evidence_context_only\"\n  },\n  \"ready_for\": [\n    \"provider_data\",\n    \"news_signals\",\n    \"orderbook_analysis\",\n    \"whale_activity\",\n    \"pnl_metrics\"\n  ]\n}\n```\n\n**Awaiting source-backed input.** Submit evidence with source attribution and I will return bounded contextual analysis only.",
                "attempts": [
                  {
                    "reason": "OLLAMA_TIMEOUT",
                    "status": "FAILED",
                    "attempts": [
                      {
                        "model": "qwen3:4b",
                        "reason": "OLLAMA_TIMEOUT",
                        "endpoint": "http://host.docker.internal:11434"
                      }
                    ],
                    "provider": "ollama"
                  },
                  {
                    "model": "claude-haiku-4-5-20251001",
                    "reason": "COMPLETED",
                    "status": "OK",
                    "provider": "anthropic",
                    "latency_ms": 2874,
                    "response_hash": "0eaa69af6c0816e87ac4ec773a82f655b78e1219317a9f820bb6dea52a4fc86d"
                  }
                ],
                "provider": "anthropic",
                "confidence": 0.5,
                "source_refs": [
                  {
                    "source_table": "ai_responses",
                    "source_record_id": "ai_resp_context_router_49c47cec16323d36bc0b40bf"
                  }
                ]
              },
              "created_at": "2026-06-02T09:33:33.958416+00:00",
              "consumed_count": 0,
              "status": "PUBLISHED",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_49c47cec16323d36bc0b40bf",
              "schema_version": 1,
              "metadata_json": {
                "router": "ai_context_fallback",
                "provider": "anthropic",
                "source_to_neuron": true
              }
            },
            "ai_request_id": "ai_req_context_router_840e735de09592d1f70e4f08",
            "ai_response_id": "ai_resp_context_router_49c47cec16323d36bc0b40bf",
            "latency_ms": 13118,
            "secrets_exposed": false
          },
          "safety_before": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10380,
            "exit_plans": 10380,
            "coordinator_decisions": 10676,
            "brain_outputs": 10712,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "safety_after": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10380,
            "exit_plans": 10380,
            "coordinator_decisions": 10676,
            "brain_outputs": 10712,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "trading_mutation_detected": false
        },
        "paper_execution": {
          "mock_data": false,
          "run_id": "paper_execution_cf39ce16c5724a1bb5479f7f81fb1aa0",
          "cycle_id": "active_30m_observation_20260602T091845Z_cycle_5",
          "system_power": "ON",
          "started_at": "2026-06-02T09:33:39.508258+00:00",
          "finished_at": "2026-06-02T09:33:39.590047+00:00",
          "status": "NO_VALID_PAPER_INTENTS",
          "intents_checked": 3,
          "executable_intents": 0,
          "orders_created": 0,
          "fills_created": 0,
          "positions_created": 0,
          "blocked_intents": 3,
          "duplicate_skipped": 0,
          "block_reasons_json": {
            "INTENT_ALREADY_EXECUTED": 3,
            "MISSING_TRUSTED_ORDERBOOK": 3
          },
          "real_orders_delta": 0,
          "live_orders_delta": 0,
          "fills_v2_delta": 0,
          "positions_delta": 0,
          "error_message": null,
          "metadata_json": {
            "reason": "no executable paper intents"
          }
        },
        "paper_exits": {
          "mock_data": false,
          "run_id": "paper_exit_loop_34707f9c346d46aba9673ef8fad60c4f",
          "system_power": "ON",
          "status": "NO_OPEN_PAPER_POSITIONS",
          "open_positions_checked": 0,
          "closed_positions_count": 0,
          "marked_positions_count": 0,
          "blocked_positions_count": 0,
          "no_exit_price_count": 0,
          "no_exit_condition_count": 0,
          "duplicate_close_skipped_count": 0,
          "orphan_positions_count": 0,
          "realized_pnl": 0,
          "unrealized_pnl": null,
          "paper_orders_delta": 0,
          "paper_positions_delta": 0,
          "real_orders_delta": 0,
          "fills_delta": 0,
          "live_orders_delta": 0,
          "started_at": "2026-06-02T09:33:39.629827+00:00",
          "finished_at": "2026-06-02T09:33:39.684841+00:00",
          "error_summary": null,
          "metadata": {
            "paper_orders": 9,
            "paper_positions": 9,
            "no_fake_pnl": true
          }
        }
      },
      "errors": []
    },
    "repeated_api_failures": 0,
    "repeated_cycle_failures": 0,
    "deltas": {
      "neural_events": 36,
      "mesh_sessions": 7,
      "shared_awareness": 7,
      "brain_opinions": 28,
      "mesh_coordinator_decisions": 7,
      "capital_evaluations": 7,
      "position_awareness": 0,
      "paper": {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "paper_position_closes": 0,
        "paper_trade_ledger": 0,
        "orders_v2": 0,
        "fills_v2": 0,
        "canonical_positions": 0,
        "real_orders_current": 0,
        "live_orders": 0
      },
      "events_by_type": {
        "AI_CONTEXT_UNAVAILABLE": 0,
        "AI_CONTEXT_UPDATED": 5,
        "LIQUIDITY_CHANGED": 5,
        "MARKET_REPRICING": 5,
        "NEWS_DETECTED": 10,
        "ORDERBOOK_REFRESHED": 5,
        "PNL_CHANGED": 0,
        "RISK_CHANGED": 0,
        "SPREAD_CHANGED": 5,
        "WHALE_DETECTED": 1
      }
    }
  },
  {
    "timestamp": "2026-06-02T09:37:10.946937+00:00",
    "system_power": "ON",
    "runtime_health": "HEALTHY",
    "endpoint_status": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/source-to-neuron-flow": "OK",
      "/dashboard/api/v2/ai-context-router": "OK",
      "/dashboard/api/v2/neural-bus": "OK",
      "/dashboard/api/v2/mesh-sessions": "OK",
      "/dashboard/api/v2/shared-awareness": "OK",
      "/dashboard/api/v2/multi-brain-consumption": "OK",
      "/dashboard/api/v2/mesh-coordinator": "OK",
      "/dashboard/api/v2/capital-brain": "OK",
      "/dashboard/api/v2/positions-awareness": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/trade-forensics": "OK",
      "/dashboard/api/v2/overnight/status": "OK",
      "/dashboard/api/v2/source-status": "OK"
    },
    "mock_data_endpoints": [],
    "secret_exposed": false,
    "source_health": "OK",
    "degraded_sources": [],
    "ai_router": {
      "latest_status": "OK",
      "selected_provider": "anthropic",
      "ollama_status": {
        "status": "FAILED",
        "reason": "OLLAMA_TIMEOUT",
        "last_run_id": "source_to_neuron_684a64d3cdfe473bb649fe6e1fd1c8a8"
      },
      "anthropic_status": {
        "status": "OK",
        "reason": "COMPLETED",
        "last_run_id": "source_to_neuron_684a64d3cdfe473bb649fe6e1fd1c8a8"
      },
      "openai_status": {
        "status": "FAILED",
        "reason": "OPENAI_QUOTA_EXCEEDED",
        "last_run_id": "post_env_ai_router_verification_20260602"
      },
      "success_count": 7,
      "unavailable_count": 2,
      "secrets_exposed": false
    },
    "events_by_type": {
      "NEWS_DETECTED": 18,
      "ORDERBOOK_REFRESHED": 16,
      "LIQUIDITY_CHANGED": 9,
      "MARKET_REPRICING": 9,
      "SPREAD_CHANGED": 9,
      "AI_CONTEXT_UPDATED": 7,
      "RISK_CHANGED": 4,
      "AI_CONTEXT_UNAVAILABLE": 2,
      "PNL_CHANGED": 2,
      "WHALE_DETECTED": 2
    },
    "neural_events": 78,
    "mesh_sessions": 33,
    "shared_awareness": 33,
    "brain_opinions": 105,
    "mesh_coordinator_decisions": 23,
    "mesh_conflicts_detected": 16,
    "source_brain_count_avg": 4.0385,
    "capital_evaluations": 21,
    "capital_decisions": {
      "CAPITAL_SUPPORT": 18,
      "CAPITAL_BLOCK": 2,
      "CAPITAL_RELEASE_REVIEW": 1
    },
    "position_awareness": 1,
    "position_reactions": {
      "PNL_RISING": 2,
      "CAPITAL_PRESSURE": 1,
      "PNL_FALLING": 1,
      "POSITION_AGING": 1
    },
    "paper": {
      "live_orders": 0,
      "live_enabled": false,
      "shadow_enabled": false,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "open_positions": 0,
      "closed_positions": 6,
      "active_positions_without_fills": 0,
      "paper_lineage": "OK",
      "capital_reconciliation": "OK",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "top_blockers": [
        {
          "blocker": "MISSING_TRUSTED_ORDERBOOK",
          "count": 2613
        },
        {
          "blocker": "INTENT_ALREADY_EXECUTED",
          "count": 1899
        }
      ]
    },
    "forensics_active_count": 6,
    "forensics_quarantined_count": 3,
    "cycle_index": 6,
    "active_cycle": {
      "correlation_id": "active_30m_observation_20260602T091845Z_cycle_6",
      "outputs": {
        "source_to_neuron": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_684a64d3cdfe473bb649fe6e1fd1c8a8",
          "blocked": false,
          "providers_checked": [
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
            "polymarket_activity_readonly",
            "ollama_local_model",
            "news_provider",
            "reddit_or_social_provider"
          ],
          "provider_status": {
            "polymarket_gamma": {
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
              "last_success_at": "2026-06-02T09:36:44.487527+00:00",
              "last_error_at": null,
              "latency_ms": 548,
              "details_json": {
                "event_count": 10,
                "sample_market_id": "2169995",
                "sample_token_available": true,
                "token_candidates": 34
              },
              "notes": "Gamma active events check succeeded."
            },
            "polymarket_clob_orderbook": {
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
              "last_success_at": "2026-06-02T09:36:44.843772+00:00",
              "last_error_at": null,
              "latency_ms": 354,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.007,
                "best_ask": 0.008,
                "spread": 0.001,
                "depth_1c": 47352272.25,
                "last_trade_price_present": true
              },
              "notes": "CLOB /book read-only check succeeded."
            },
            "polymarket_clob_prices": {
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
              "last_success_at": "2026-06-02T09:36:44.843819+00:00",
              "last_error_at": null,
              "latency_ms": 354,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.007,
                "best_ask": 0.008,
                "spread": 0.001,
                "depth_1c": 47352272.25,
                "last_trade_price_present": true
              },
              "notes": "Price truth derived from read-only CLOB book response."
            },
            "polymarket_clob_spreads": {
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
              "last_success_at": "2026-06-02T09:36:44.843825+00:00",
              "last_error_at": null,
              "latency_ms": 354,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.007,
                "best_ask": 0.008,
                "spread": 0.001,
                "depth_1c": 47352272.25,
                "last_trade_price_present": true
              },
              "notes": "Spread and depth truth derived from read-only CLOB book response."
            },
            "polymarket_activity_readonly": {
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
              "last_success_at": "2026-06-02T09:36:44.967133+00:00",
              "last_error_at": null,
              "latency_ms": 122,
              "details_json": {
                "sample_count": 1
              },
              "notes": "Data API /trades read-only discovery check succeeded."
            },
            "ollama_local_model": {
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
              "last_success_at": "2026-06-02T09:36:45.030161+00:00",
              "last_error_at": null,
              "latency_ms": 62,
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
                  "http://host.docker.internal:11434/api/tags"
                ]
              },
              "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
            },
            "news_provider": {
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
            "reddit_or_social_provider": {
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
            },
            "ai_context_router": {
              "runtime_status": "ACTIVE",
              "selected_provider": "anthropic",
              "final_reason": "AI_CONTEXT_UPDATED",
              "secret_value_exposed": false
            }
          },
          "events_created": 7,
          "events_by_type": {
            "MARKET_REPRICING": 1,
            "NEWS_DETECTED": 2,
            "ORDERBOOK_REFRESHED": 1,
            "SPREAD_CHANGED": 1,
            "LIQUIDITY_CHANGED": 1,
            "AI_CONTEXT_UPDATED": 1
          },
          "sessions_updated": 22,
          "awareness_domains_updated": 93,
          "brain_opinions_created": 30,
          "coordinator_decisions_created": 6,
          "latest_items": [
            {
              "event_id": "neural_event_aec36b09ab9449029257ca21e15ac0fc",
              "event_type": "MARKET_REPRICING",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_gamma",
              "neuron": "Market Neuron",
              "source_table": "source_status",
              "source_record_id": "polymarket_gamma:source_to_neuron_684a64d3cdfe473bb649fe6e1fd1c8a8",
              "created_at": "2026-06-02T09:36:45.442432+00:00"
            },
            {
              "event_id": "neural_event_55f255a46db9440c9e1e3784f4eb9c30",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "rss",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_1f5872e7f22047b88c952e0c6bb7b516",
              "created_at": "2026-06-02T09:36:46.665002+00:00"
            },
            {
              "event_id": "neural_event_ae16324f6b714911a61180a0cbbb51ec",
              "event_type": "NEWS_DETECTED",
              "market_id": "677404",
              "candidate_id": null,
              "position_id": null,
              "provider": "newsapi",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_6cab69d9dfa34ab58e2f11b9b1a0efaa",
              "created_at": "2026-06-02T09:36:47.607575+00:00"
            },
            {
              "event_id": "neural_event_f698675ba8854c0cbd23e96ccd7aa9d8",
              "event_type": "ORDERBOOK_REFRESHED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Orderbook Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_4d38dd88912f43c59d7c6aaa2bb876f7",
              "created_at": "2026-06-02T09:36:48.256683+00:00"
            },
            {
              "event_id": "neural_event_ecb5072601b543b8b9855053decf5480",
              "event_type": "SPREAD_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_4d38dd88912f43c59d7c6aaa2bb876f7:SPREAD_CHANGED",
              "created_at": "2026-06-02T09:36:48.615989+00:00"
            },
            {
              "event_id": "neural_event_0c8135d64cea48469a937b0cea8eccb2",
              "event_type": "LIQUIDITY_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_4d38dd88912f43c59d7c6aaa2bb876f7:LIQUIDITY_CHANGED",
              "created_at": "2026-06-02T09:36:48.994250+00:00"
            },
            {
              "event_id": "neural_event_4b34596c06e74a4096f94018bb9efb04",
              "event_type": "AI_CONTEXT_UPDATED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "anthropic",
              "neuron": "AI Context Brain",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_79037dbd3d17402340276668",
              "created_at": "2026-06-02T09:37:03.136985+00:00"
            }
          ],
          "errors": [],
          "missing_providers": [],
          "degraded_providers": [],
          "whale_status": "NO_WHALE_EVENT_FOUND",
          "secrets_exposed": false,
          "ai_context_router": {
            "mock_data": false,
            "status": "OK",
            "run_id": "source_to_neuron_684a64d3cdfe473bb649fe6e1fd1c8a8",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "providers_attempted": [
              {
                "provider": "ollama",
                "status": "FAILED",
                "reason": "OLLAMA_TIMEOUT",
                "attempts": [
                  {
                    "endpoint": "http://host.docker.internal:11434",
                    "model": "qwen3:4b",
                    "reason": "OLLAMA_TIMEOUT"
                  }
                ]
              },
              {
                "provider": "anthropic",
                "status": "OK",
                "reason": "COMPLETED",
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 3471,
                "response_hash": "73cac9998343867aacc54d24f508f84d4cd8da711dccd3d1f31f4a653ba3f988"
              }
            ],
            "event": {
              "id": 146,
              "event_id": "neural_event_4b34596c06e74a4096f94018bb9efb04",
              "event_type": "AI_CONTEXT_UPDATED",
              "correlation_id": "source_to_neuron_684a64d3cdfe473bb649fe6e1fd1c8a8",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "source_component": "AI Context Brain",
              "source_type": "brain",
              "priority": 5,
              "payload_json": {
                "model": "claude-haiku-4-5-20251001",
                "status": "COMPLETED",
                "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input from: provider, news, orderbook, whale, PnL collectors. Will return factual context only. Trade creation, risk bypass, capital allocation, and state changes blocked at governance layer.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"trade_creation\": \"blocked\",\n    \"risk_bypass\": \"blocked\",\n    \"capital_allocation\": \"requires_coordinator\",\n    \"state_changes\": \"requires_governor\",\n    \"output_scope\": \"context_and_evidence_only\"\n  },\n  \"ready_for\": [\n    \"provider_data\",\n    \"news_signals\",\n    \"orderbook_snapshots\",\n    \"whale_activity\",\n    \"pnl_metrics\"\n  ]\n}\n```\n\n**Awaiting source-backed evidence input.** Submit facts; I will contextualize without creating trades or bypassing governance.",
                "attempts": [
                  {
                    "reason": "OLLAMA_TIMEOUT",
                    "status": "FAILED",
                    "attempts": [
                      {
                        "model": "qwen3:4b",
                        "reason": "OLLAMA_TIMEOUT",
                        "endpoint": "http://host.docker.internal:11434"
                      }
                    ],
                    "provider": "ollama"
                  },
                  {
                    "model": "claude-haiku-4-5-20251001",
                    "reason": "COMPLETED",
                    "status": "OK",
                    "provider": "anthropic",
                    "latency_ms": 3471,
                    "response_hash": "73cac9998343867aacc54d24f508f84d4cd8da711dccd3d1f31f4a653ba3f988"
                  }
                ],
                "provider": "anthropic",
                "confidence": 0.5,
                "source_refs": [
                  {
                    "source_table": "ai_responses",
                    "source_record_id": "ai_resp_context_router_79037dbd3d17402340276668"
                  }
                ]
              },
              "created_at": "2026-06-02T09:37:03.136985+00:00",
              "consumed_count": 0,
              "status": "PUBLISHED",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_79037dbd3d17402340276668",
              "schema_version": 1,
              "metadata_json": {
                "router": "ai_context_fallback",
                "provider": "anthropic",
                "source_to_neuron": true
              }
            },
            "ai_request_id": "ai_req_context_router_bb5667fa9b69e9563117f5dd",
            "ai_response_id": "ai_resp_context_router_79037dbd3d17402340276668",
            "latency_ms": 13528,
            "secrets_exposed": false
          },
          "safety_before": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10390,
            "exit_plans": 10390,
            "coordinator_decisions": 10686,
            "brain_outputs": 10722,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "safety_after": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10390,
            "exit_plans": 10390,
            "coordinator_decisions": 10686,
            "brain_outputs": 10722,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "trading_mutation_detected": false
        },
        "paper_execution": {
          "mock_data": false,
          "run_id": "paper_execution_f69ca149f9fe4db98c55ecb80154eb77",
          "cycle_id": "active_30m_observation_20260602T091845Z_cycle_6",
          "system_power": "ON",
          "started_at": "2026-06-02T09:37:06.014180+00:00",
          "finished_at": "2026-06-02T09:37:06.082408+00:00",
          "status": "NO_VALID_PAPER_INTENTS",
          "intents_checked": 3,
          "executable_intents": 0,
          "orders_created": 0,
          "fills_created": 0,
          "positions_created": 0,
          "blocked_intents": 3,
          "duplicate_skipped": 0,
          "block_reasons_json": {
            "INTENT_ALREADY_EXECUTED": 3,
            "MISSING_TRUSTED_ORDERBOOK": 3
          },
          "real_orders_delta": 0,
          "live_orders_delta": 0,
          "fills_v2_delta": 0,
          "positions_delta": 0,
          "error_message": null,
          "metadata_json": {
            "reason": "no executable paper intents"
          }
        },
        "paper_exits": {
          "mock_data": false,
          "run_id": "paper_exit_loop_383c973563bb41db879a9613c47e84a8",
          "system_power": "ON",
          "status": "NO_OPEN_PAPER_POSITIONS",
          "open_positions_checked": 0,
          "closed_positions_count": 0,
          "marked_positions_count": 0,
          "blocked_positions_count": 0,
          "no_exit_price_count": 0,
          "no_exit_condition_count": 0,
          "duplicate_close_skipped_count": 0,
          "orphan_positions_count": 0,
          "realized_pnl": 0,
          "unrealized_pnl": null,
          "paper_orders_delta": 0,
          "paper_positions_delta": 0,
          "real_orders_delta": 0,
          "fills_delta": 0,
          "live_orders_delta": 0,
          "started_at": "2026-06-02T09:37:06.118474+00:00",
          "finished_at": "2026-06-02T09:37:06.165984+00:00",
          "error_summary": null,
          "metadata": {
            "paper_orders": 9,
            "paper_positions": 9,
            "no_fake_pnl": true
          }
        }
      },
      "errors": []
    },
    "repeated_api_failures": 0,
    "repeated_cycle_failures": 0,
    "deltas": {
      "neural_events": 43,
      "mesh_sessions": 8,
      "shared_awareness": 8,
      "brain_opinions": 32,
      "mesh_coordinator_decisions": 8,
      "capital_evaluations": 8,
      "position_awareness": 0,
      "paper": {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "paper_position_closes": 0,
        "paper_trade_ledger": 0,
        "orders_v2": 0,
        "fills_v2": 0,
        "canonical_positions": 0,
        "real_orders_current": 0,
        "live_orders": 0
      },
      "events_by_type": {
        "AI_CONTEXT_UNAVAILABLE": 0,
        "AI_CONTEXT_UPDATED": 6,
        "LIQUIDITY_CHANGED": 6,
        "MARKET_REPRICING": 6,
        "NEWS_DETECTED": 12,
        "ORDERBOOK_REFRESHED": 6,
        "PNL_CHANGED": 0,
        "RISK_CHANGED": 0,
        "SPREAD_CHANGED": 6,
        "WHALE_DETECTED": 1
      }
    }
  },
  {
    "timestamp": "2026-06-02T09:40:56.048997+00:00",
    "system_power": "ON",
    "runtime_health": "HEALTHY",
    "endpoint_status": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/source-to-neuron-flow": "OK",
      "/dashboard/api/v2/ai-context-router": "OK",
      "/dashboard/api/v2/neural-bus": "OK",
      "/dashboard/api/v2/mesh-sessions": "OK",
      "/dashboard/api/v2/shared-awareness": "OK",
      "/dashboard/api/v2/multi-brain-consumption": "OK",
      "/dashboard/api/v2/mesh-coordinator": "OK",
      "/dashboard/api/v2/capital-brain": "OK",
      "/dashboard/api/v2/positions-awareness": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/trade-forensics": "OK",
      "/dashboard/api/v2/overnight/status": "OK",
      "/dashboard/api/v2/source-status": "OK"
    },
    "mock_data_endpoints": [],
    "secret_exposed": false,
    "source_health": "OK",
    "degraded_sources": [],
    "ai_router": {
      "latest_status": "OK",
      "selected_provider": "anthropic",
      "ollama_status": {
        "status": "FAILED",
        "reason": "OLLAMA_TIMEOUT",
        "last_run_id": "source_to_neuron_257dd99711bc4127a289c2dbace97b10"
      },
      "anthropic_status": {
        "status": "OK",
        "reason": "COMPLETED",
        "last_run_id": "source_to_neuron_257dd99711bc4127a289c2dbace97b10"
      },
      "openai_status": {
        "status": "FAILED",
        "reason": "OPENAI_QUOTA_EXCEEDED",
        "last_run_id": "post_env_ai_router_verification_20260602"
      },
      "success_count": 8,
      "unavailable_count": 2,
      "secrets_exposed": false
    },
    "events_by_type": {
      "NEWS_DETECTED": 20,
      "ORDERBOOK_REFRESHED": 17,
      "LIQUIDITY_CHANGED": 10,
      "MARKET_REPRICING": 10,
      "SPREAD_CHANGED": 10,
      "AI_CONTEXT_UPDATED": 8,
      "RISK_CHANGED": 4,
      "AI_CONTEXT_UNAVAILABLE": 2,
      "PNL_CHANGED": 2,
      "WHALE_DETECTED": 2
    },
    "neural_events": 85,
    "mesh_sessions": 34,
    "shared_awareness": 34,
    "brain_opinions": 109,
    "mesh_coordinator_decisions": 24,
    "mesh_conflicts_detected": 17,
    "source_brain_count_avg": 4.037,
    "capital_evaluations": 22,
    "capital_decisions": {
      "CAPITAL_SUPPORT": 19,
      "CAPITAL_BLOCK": 2,
      "CAPITAL_RELEASE_REVIEW": 1
    },
    "position_awareness": 1,
    "position_reactions": {
      "PNL_RISING": 2,
      "CAPITAL_PRESSURE": 1,
      "PNL_FALLING": 1,
      "POSITION_AGING": 1
    },
    "paper": {
      "live_orders": 0,
      "live_enabled": false,
      "shadow_enabled": false,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "open_positions": 0,
      "closed_positions": 6,
      "active_positions_without_fills": 0,
      "paper_lineage": "OK",
      "capital_reconciliation": "OK",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "top_blockers": [
        {
          "blocker": "MISSING_TRUSTED_ORDERBOOK",
          "count": 2622
        },
        {
          "blocker": "INTENT_ALREADY_EXECUTED",
          "count": 1908
        }
      ]
    },
    "forensics_active_count": 6,
    "forensics_quarantined_count": 3,
    "cycle_index": 7,
    "active_cycle": {
      "correlation_id": "active_30m_observation_20260602T091845Z_cycle_7",
      "outputs": {
        "source_to_neuron": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_257dd99711bc4127a289c2dbace97b10",
          "blocked": false,
          "providers_checked": [
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
            "polymarket_activity_readonly",
            "ollama_local_model",
            "news_provider",
            "reddit_or_social_provider"
          ],
          "provider_status": {
            "polymarket_gamma": {
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
              "last_success_at": "2026-06-02T09:40:11.939648+00:00",
              "last_error_at": null,
              "latency_ms": 659,
              "details_json": {
                "event_count": 10,
                "sample_market_id": "2169995",
                "sample_token_available": true,
                "token_candidates": 34
              },
              "notes": "Gamma active events check succeeded."
            },
            "polymarket_clob_orderbook": {
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
              "last_success_at": "2026-06-02T09:40:12.296452+00:00",
              "last_error_at": null,
              "latency_ms": 352,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48757382.16,
                "last_trade_price_present": true
              },
              "notes": "CLOB /book read-only check succeeded."
            },
            "polymarket_clob_prices": {
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
              "last_success_at": "2026-06-02T09:40:12.296494+00:00",
              "last_error_at": null,
              "latency_ms": 352,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48757382.16,
                "last_trade_price_present": true
              },
              "notes": "Price truth derived from read-only CLOB book response."
            },
            "polymarket_clob_spreads": {
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
              "last_success_at": "2026-06-02T09:40:12.296530+00:00",
              "last_error_at": null,
              "latency_ms": 352,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48757382.16,
                "last_trade_price_present": true
              },
              "notes": "Spread and depth truth derived from read-only CLOB book response."
            },
            "polymarket_activity_readonly": {
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
              "last_success_at": "2026-06-02T09:40:12.519305+00:00",
              "last_error_at": null,
              "latency_ms": 221,
              "details_json": {
                "sample_count": 1
              },
              "notes": "Data API /trades read-only discovery check succeeded."
            },
            "ollama_local_model": {
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
              "last_success_at": "2026-06-02T09:40:12.588729+00:00",
              "last_error_at": null,
              "latency_ms": 68,
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
                  "http://host.docker.internal:11434/api/tags"
                ]
              },
              "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
            },
            "news_provider": {
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
            "reddit_or_social_provider": {
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
            },
            "ai_context_router": {
              "runtime_status": "ACTIVE",
              "selected_provider": "anthropic",
              "final_reason": "AI_CONTEXT_UPDATED",
              "secret_value_exposed": false
            }
          },
          "events_created": 7,
          "events_by_type": {
            "MARKET_REPRICING": 1,
            "NEWS_DETECTED": 2,
            "ORDERBOOK_REFRESHED": 1,
            "SPREAD_CHANGED": 1,
            "LIQUIDITY_CHANGED": 1,
            "AI_CONTEXT_UPDATED": 1
          },
          "sessions_updated": 21,
          "awareness_domains_updated": 120,
          "brain_opinions_created": 30,
          "coordinator_decisions_created": 6,
          "latest_items": [
            {
              "event_id": "neural_event_84cd7fe2aceb42b280859f6368497727",
              "event_type": "MARKET_REPRICING",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_gamma",
              "neuron": "Market Neuron",
              "source_table": "source_status",
              "source_record_id": "polymarket_gamma:source_to_neuron_257dd99711bc4127a289c2dbace97b10",
              "created_at": "2026-06-02T09:40:13.035370+00:00"
            },
            {
              "event_id": "neural_event_166150ddfdc943a387ab29a634c2600c",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "rss",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_3ff4e42c91744c2d8a7d40a12bcca86c",
              "created_at": "2026-06-02T09:40:14.281850+00:00"
            },
            {
              "event_id": "neural_event_8b14f6f3268d4a898818b42c21fc1d86",
              "event_type": "NEWS_DETECTED",
              "market_id": "598936",
              "candidate_id": null,
              "position_id": null,
              "provider": "newsapi",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_d6f217aa53d84f91943bf49ab58bd71c",
              "created_at": "2026-06-02T09:40:16.466416+00:00"
            },
            {
              "event_id": "neural_event_66f8db1f69764c569ae6afb69f88652d",
              "event_type": "ORDERBOOK_REFRESHED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Orderbook Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_e4a8af844e5c4458b5cd7fa7143bf98a",
              "created_at": "2026-06-02T09:40:17.042585+00:00"
            },
            {
              "event_id": "neural_event_81a3ef381ac64b25b75dff9a03d862ed",
              "event_type": "SPREAD_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_e4a8af844e5c4458b5cd7fa7143bf98a:SPREAD_CHANGED",
              "created_at": "2026-06-02T09:40:17.400407+00:00"
            },
            {
              "event_id": "neural_event_5f8ab50e37324f07b69c8f8746c49113",
              "event_type": "LIQUIDITY_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_e4a8af844e5c4458b5cd7fa7143bf98a:LIQUIDITY_CHANGED",
              "created_at": "2026-06-02T09:40:17.721191+00:00"
            },
            {
              "event_id": "neural_event_c3a0bf47cd674fada7fa541436a1162c",
              "event_type": "AI_CONTEXT_UPDATED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "anthropic",
              "neuron": "AI Context Brain",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_3074bc97f53ebc8518fe6432",
              "created_at": "2026-06-02T09:40:31.402135+00:00"
            }
          ],
          "errors": [],
          "missing_providers": [],
          "degraded_providers": [],
          "whale_status": "NO_WHALE_EVENT_FOUND",
          "secrets_exposed": false,
          "ai_context_router": {
            "mock_data": false,
            "status": "OK",
            "run_id": "source_to_neuron_257dd99711bc4127a289c2dbace97b10",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "providers_attempted": [
              {
                "provider": "ollama",
                "status": "FAILED",
                "reason": "OLLAMA_TIMEOUT",
                "attempts": [
                  {
                    "endpoint": "http://host.docker.internal:11434",
                    "model": "qwen3:4b",
                    "reason": "OLLAMA_TIMEOUT"
                  }
                ]
              },
              {
                "provider": "anthropic",
                "status": "OK",
                "reason": "COMPLETED",
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 2995,
                "response_hash": "829ed4e9c54c45769e1818d41fe3d43641792b2fe3784e2dc9770565bbb6c47e"
              }
            ],
            "event": {
              "id": 172,
              "event_id": "neural_event_c3a0bf47cd674fada7fa541436a1162c",
              "event_type": "AI_CONTEXT_UPDATED",
              "correlation_id": "source_to_neuron_257dd99711bc4127a289c2dbace97b10",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "source_component": "AI Context Brain",
              "source_type": "brain",
              "priority": 5,
              "payload_json": {
                "model": "claude-haiku-4-5-20251001",
                "status": "COMPLETED",
                "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input from: provider, news, orderbook, whale, PnL collectors. Will return factual context only. Trade creation, risk bypass, capital allocation, and state changes blocked at governance layer.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"trade_creation\": \"blocked\",\n    \"risk_bypass\": \"blocked\",\n    \"capital_allocation\": \"requires_coordinator\",\n    \"state_changes\": \"requires_governor\",\n    \"output_type\": \"context_only\"\n  },\n  \"ready_for\": [\n    \"provider_data\",\n    \"news_signals\",\n    \"orderbook_snapshots\",\n    \"whale_activity\",\n    \"pnl_metrics\"\n  ]\n}\n```\n\n**Awaiting source-backed evidence input.** Submit facts; I will contextualize without creating trades or bypassing governance.",
                "attempts": [
                  {
                    "reason": "OLLAMA_TIMEOUT",
                    "status": "FAILED",
                    "attempts": [
                      {
                        "model": "qwen3:4b",
                        "reason": "OLLAMA_TIMEOUT",
                        "endpoint": "http://host.docker.internal:11434"
                      }
                    ],
                    "provider": "ollama"
                  },
                  {
                    "model": "claude-haiku-4-5-20251001",
                    "reason": "COMPLETED",
                    "status": "OK",
                    "provider": "anthropic",
                    "latency_ms": 2995,
                    "response_hash": "829ed4e9c54c45769e1818d41fe3d43641792b2fe3784e2dc9770565bbb6c47e"
                  }
                ],
                "provider": "anthropic",
                "confidence": 0.5,
                "source_refs": [
                  {
                    "source_table": "ai_responses",
                    "source_record_id": "ai_resp_context_router_3074bc97f53ebc8518fe6432"
                  }
                ]
              },
              "created_at": "2026-06-02T09:40:31.402135+00:00",
              "consumed_count": 0,
              "status": "PUBLISHED",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_3074bc97f53ebc8518fe6432",
              "schema_version": 1,
              "metadata_json": {
                "router": "ai_context_fallback",
                "provider": "anthropic",
                "source_to_neuron": true
              }
            },
            "ai_request_id": "ai_req_context_router_3828f39a3538edbe8fce73ae",
            "ai_response_id": "ai_resp_context_router_3074bc97f53ebc8518fe6432",
            "latency_ms": 13083,
            "secrets_exposed": false
          },
          "safety_before": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10400,
            "exit_plans": 10400,
            "coordinator_decisions": 10696,
            "brain_outputs": 10732,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "safety_after": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10400,
            "exit_plans": 10400,
            "coordinator_decisions": 10696,
            "brain_outputs": 10732,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "trading_mutation_detected": false
        },
        "paper_execution": {
          "mock_data": false,
          "run_id": "paper_execution_f5d7bc56fb0144cea12c96a3d890b2fb",
          "cycle_id": "active_30m_observation_20260602T091845Z_cycle_7",
          "system_power": "ON",
          "started_at": "2026-06-02T09:40:39.367466+00:00",
          "finished_at": "2026-06-02T09:40:39.751526+00:00",
          "status": "NO_VALID_PAPER_INTENTS",
          "intents_checked": 3,
          "executable_intents": 0,
          "orders_created": 0,
          "fills_created": 0,
          "positions_created": 0,
          "blocked_intents": 3,
          "duplicate_skipped": 0,
          "block_reasons_json": {
            "INTENT_ALREADY_EXECUTED": 3,
            "MISSING_TRUSTED_ORDERBOOK": 3
          },
          "real_orders_delta": 0,
          "live_orders_delta": 0,
          "fills_v2_delta": 0,
          "positions_delta": 0,
          "error_message": null,
          "metadata_json": {
            "reason": "no executable paper intents"
          }
        },
        "paper_exits": {
          "mock_data": false,
          "run_id": "paper_exit_loop_87432b0551dd45aa889c8baa80511964",
          "system_power": "ON",
          "status": "NO_OPEN_PAPER_POSITIONS",
          "open_positions_checked": 0,
          "closed_positions_count": 0,
          "marked_positions_count": 0,
          "blocked_positions_count": 0,
          "no_exit_price_count": 0,
          "no_exit_condition_count": 0,
          "duplicate_close_skipped_count": 0,
          "orphan_positions_count": 0,
          "realized_pnl": 0,
          "unrealized_pnl": null,
          "paper_orders_delta": 0,
          "paper_positions_delta": 0,
          "real_orders_delta": 0,
          "fills_delta": 0,
          "live_orders_delta": 0,
          "started_at": "2026-06-02T09:40:39.863987+00:00",
          "finished_at": "2026-06-02T09:40:40.038850+00:00",
          "error_summary": null,
          "metadata": {
            "paper_orders": 9,
            "paper_positions": 9,
            "no_fake_pnl": true
          }
        }
      },
      "errors": []
    },
    "repeated_api_failures": 0,
    "repeated_cycle_failures": 0,
    "deltas": {
      "neural_events": 50,
      "mesh_sessions": 9,
      "shared_awareness": 9,
      "brain_opinions": 36,
      "mesh_coordinator_decisions": 9,
      "capital_evaluations": 9,
      "position_awareness": 0,
      "paper": {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "paper_position_closes": 0,
        "paper_trade_ledger": 0,
        "orders_v2": 0,
        "fills_v2": 0,
        "canonical_positions": 0,
        "real_orders_current": 0,
        "live_orders": 0
      },
      "events_by_type": {
        "AI_CONTEXT_UNAVAILABLE": 0,
        "AI_CONTEXT_UPDATED": 7,
        "LIQUIDITY_CHANGED": 7,
        "MARKET_REPRICING": 7,
        "NEWS_DETECTED": 14,
        "ORDERBOOK_REFRESHED": 7,
        "PNL_CHANGED": 0,
        "RISK_CHANGED": 0,
        "SPREAD_CHANGED": 7,
        "WHALE_DETECTED": 1
      }
    }
  },
  {
    "timestamp": "2026-06-02T09:44:27.678835+00:00",
    "system_power": "ON",
    "runtime_health": "HEALTHY",
    "endpoint_status": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/source-to-neuron-flow": "OK",
      "/dashboard/api/v2/ai-context-router": "OK",
      "/dashboard/api/v2/neural-bus": "OK",
      "/dashboard/api/v2/mesh-sessions": "OK",
      "/dashboard/api/v2/shared-awareness": "OK",
      "/dashboard/api/v2/multi-brain-consumption": "OK",
      "/dashboard/api/v2/mesh-coordinator": "OK",
      "/dashboard/api/v2/capital-brain": "OK",
      "/dashboard/api/v2/positions-awareness": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/trade-forensics": "OK",
      "/dashboard/api/v2/overnight/status": "OK",
      "/dashboard/api/v2/source-status": "OK"
    },
    "mock_data_endpoints": [],
    "secret_exposed": false,
    "source_health": "OK",
    "degraded_sources": [],
    "ai_router": {
      "latest_status": "OK",
      "selected_provider": "anthropic",
      "ollama_status": {
        "status": "FAILED",
        "reason": "OLLAMA_TIMEOUT",
        "last_run_id": "source_to_neuron_ad63611ab1164d1e86d044854e1c3e25"
      },
      "anthropic_status": {
        "status": "OK",
        "reason": "COMPLETED",
        "last_run_id": "source_to_neuron_ad63611ab1164d1e86d044854e1c3e25"
      },
      "openai_status": {
        "status": "FAILED",
        "reason": "OPENAI_QUOTA_EXCEEDED",
        "last_run_id": "post_env_ai_router_verification_20260602"
      },
      "success_count": 9,
      "unavailable_count": 2,
      "secrets_exposed": false
    },
    "events_by_type": {
      "NEWS_DETECTED": 22,
      "ORDERBOOK_REFRESHED": 18,
      "LIQUIDITY_CHANGED": 11,
      "MARKET_REPRICING": 11,
      "SPREAD_CHANGED": 11,
      "AI_CONTEXT_UPDATED": 9,
      "RISK_CHANGED": 4,
      "AI_CONTEXT_UNAVAILABLE": 2,
      "PNL_CHANGED": 2,
      "WHALE_DETECTED": 2
    },
    "neural_events": 92,
    "mesh_sessions": 35,
    "shared_awareness": 35,
    "brain_opinions": 113,
    "mesh_coordinator_decisions": 25,
    "mesh_conflicts_detected": 18,
    "source_brain_count_avg": 4.0357,
    "capital_evaluations": 23,
    "capital_decisions": {
      "CAPITAL_SUPPORT": 20,
      "CAPITAL_BLOCK": 2,
      "CAPITAL_RELEASE_REVIEW": 1
    },
    "position_awareness": 1,
    "position_reactions": {
      "PNL_RISING": 2,
      "CAPITAL_PRESSURE": 1,
      "PNL_FALLING": 1,
      "POSITION_AGING": 1
    },
    "paper": {
      "live_orders": 0,
      "live_enabled": false,
      "shadow_enabled": false,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "open_positions": 0,
      "closed_positions": 6,
      "active_positions_without_fills": 0,
      "paper_lineage": "OK",
      "capital_reconciliation": "OK",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "top_blockers": [
        {
          "blocker": "MISSING_TRUSTED_ORDERBOOK",
          "count": 2631
        },
        {
          "blocker": "INTENT_ALREADY_EXECUTED",
          "count": 1917
        }
      ]
    },
    "forensics_active_count": 6,
    "forensics_quarantined_count": 3,
    "cycle_index": 8,
    "active_cycle": {
      "correlation_id": "active_30m_observation_20260602T091845Z_cycle_8",
      "outputs": {
        "source_to_neuron": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_ad63611ab1164d1e86d044854e1c3e25",
          "blocked": false,
          "providers_checked": [
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
            "polymarket_activity_readonly",
            "ollama_local_model",
            "news_provider",
            "reddit_or_social_provider"
          ],
          "provider_status": {
            "polymarket_gamma": {
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
              "last_success_at": "2026-06-02T09:43:56.695562+00:00",
              "last_error_at": null,
              "latency_ms": 231,
              "details_json": {
                "event_count": 10,
                "sample_market_id": "2169995",
                "sample_token_available": true,
                "token_candidates": 34
              },
              "notes": "Gamma active events check succeeded."
            },
            "polymarket_clob_orderbook": {
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
              "last_success_at": "2026-06-02T09:43:56.995324+00:00",
              "last_error_at": null,
              "latency_ms": 298,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48770395.13,
                "last_trade_price_present": true
              },
              "notes": "CLOB /book read-only check succeeded."
            },
            "polymarket_clob_prices": {
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
              "last_success_at": "2026-06-02T09:43:56.995364+00:00",
              "last_error_at": null,
              "latency_ms": 298,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48770395.13,
                "last_trade_price_present": true
              },
              "notes": "Price truth derived from read-only CLOB book response."
            },
            "polymarket_clob_spreads": {
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
              "last_success_at": "2026-06-02T09:43:56.995369+00:00",
              "last_error_at": null,
              "latency_ms": 298,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48770395.13,
                "last_trade_price_present": true
              },
              "notes": "Spread and depth truth derived from read-only CLOB book response."
            },
            "polymarket_activity_readonly": {
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
              "last_success_at": "2026-06-02T09:43:57.066098+00:00",
              "last_error_at": null,
              "latency_ms": 70,
              "details_json": {
                "sample_count": 1
              },
              "notes": "Data API /trades read-only discovery check succeeded."
            },
            "ollama_local_model": {
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
              "last_success_at": "2026-06-02T09:43:57.095713+00:00",
              "last_error_at": null,
              "latency_ms": 29,
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
                  "http://host.docker.internal:11434/api/tags"
                ]
              },
              "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
            },
            "news_provider": {
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
            "reddit_or_social_provider": {
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
            },
            "ai_context_router": {
              "runtime_status": "ACTIVE",
              "selected_provider": "anthropic",
              "final_reason": "AI_CONTEXT_UPDATED",
              "secret_value_exposed": false
            }
          },
          "events_created": 7,
          "events_by_type": {
            "MARKET_REPRICING": 1,
            "NEWS_DETECTED": 2,
            "ORDERBOOK_REFRESHED": 1,
            "SPREAD_CHANGED": 1,
            "LIQUIDITY_CHANGED": 1,
            "AI_CONTEXT_UPDATED": 1
          },
          "sessions_updated": 21,
          "awareness_domains_updated": 122,
          "brain_opinions_created": 30,
          "coordinator_decisions_created": 6,
          "latest_items": [
            {
              "event_id": "neural_event_b8b90c8281594d3e90260bce8326b75c",
              "event_type": "MARKET_REPRICING",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_gamma",
              "neuron": "Market Neuron",
              "source_table": "source_status",
              "source_record_id": "polymarket_gamma:source_to_neuron_ad63611ab1164d1e86d044854e1c3e25",
              "created_at": "2026-06-02T09:43:57.339641+00:00"
            },
            {
              "event_id": "neural_event_022d6b44bef34f7fb2bc0f251697dbc7",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "rss",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_46303a9e9bc7459992aedc3146f5c435",
              "created_at": "2026-06-02T09:43:58.495159+00:00"
            },
            {
              "event_id": "neural_event_dad1587aeffa457cae994ba946eeb598",
              "event_type": "NEWS_DETECTED",
              "market_id": "598936",
              "candidate_id": null,
              "position_id": null,
              "provider": "newsapi",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_61d2a43ac6144c7f9d6f540288d68b80",
              "created_at": "2026-06-02T09:44:01.135473+00:00"
            },
            {
              "event_id": "neural_event_1e2245e2142845368d1c9b8946949c84",
              "event_type": "ORDERBOOK_REFRESHED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Orderbook Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_8977a8a04c5c4c0d9f9f4c20c766b1d2",
              "created_at": "2026-06-02T09:44:01.863203+00:00"
            },
            {
              "event_id": "neural_event_57d8ce1fc9054ae0b67fa0470f89571b",
              "event_type": "SPREAD_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_8977a8a04c5c4c0d9f9f4c20c766b1d2:SPREAD_CHANGED",
              "created_at": "2026-06-02T09:44:02.211106+00:00"
            },
            {
              "event_id": "neural_event_463578b444b1446c89be05d20dac2aec",
              "event_type": "LIQUIDITY_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_8977a8a04c5c4c0d9f9f4c20c766b1d2:LIQUIDITY_CHANGED",
              "created_at": "2026-06-02T09:44:02.557712+00:00"
            },
            {
              "event_id": "neural_event_fc2c49a9f6e440d58aa1631b079315a0",
              "event_type": "AI_CONTEXT_UPDATED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "anthropic",
              "neuron": "AI Context Brain",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_775a7843a9623441e1b1513f",
              "created_at": "2026-06-02T09:44:16.724223+00:00"
            }
          ],
          "errors": [],
          "missing_providers": [],
          "degraded_providers": [],
          "whale_status": "NO_WHALE_EVENT_FOUND",
          "secrets_exposed": false,
          "ai_context_router": {
            "mock_data": false,
            "status": "OK",
            "run_id": "source_to_neuron_ad63611ab1164d1e86d044854e1c3e25",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "providers_attempted": [
              {
                "provider": "ollama",
                "status": "FAILED",
                "reason": "OLLAMA_TIMEOUT",
                "attempts": [
                  {
                    "endpoint": "http://host.docker.internal:11434",
                    "model": "qwen3:4b",
                    "reason": "OLLAMA_TIMEOUT"
                  }
                ]
              },
              {
                "provider": "anthropic",
                "status": "OK",
                "reason": "COMPLETED",
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 3081,
                "response_hash": "c5dfa8ee9ae1ba09d53e94ad3cd1677e6cadff90dc3dc1f9a08947d009449fac"
              }
            ],
            "event": {
              "id": 200,
              "event_id": "neural_event_fc2c49a9f6e440d58aa1631b079315a0",
              "event_type": "AI_CONTEXT_UPDATED",
              "correlation_id": "source_to_neuron_ad63611ab1164d1e86d044854e1c3e25",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "source_component": "AI Context Brain",
              "source_type": "brain",
              "priority": 5,
              "payload_json": {
                "model": "claude-haiku-4-5-20251001",
                "status": "COMPLETED",
                "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input from: provider, news, orderbook, whale, PnL collectors. Will return contextual analysis only. Trade creation, risk bypass, capital allocation, and state changes blocked at governance layer.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"trade_creation\": \"blocked\",\n    \"risk_bypass\": \"blocked\",\n    \"capital_allocation\": \"blocked\",\n    \"state_modification\": \"blocked\",\n    \"output_scope\": \"evidence_context_only\"\n  },\n  \"ready_for\": [\n    \"provider_data\",\n    \"news_signals\",\n    \"orderbook_analysis\",\n    \"whale_activity\",\n    \"pnl_metrics\"\n  ]\n}\n```\n\n**Awaiting source-backed evidence input.** Submit collected data and I will return bounded contextual analysis without trade recommendations or governance bypass.",
                "attempts": [
                  {
                    "reason": "OLLAMA_TIMEOUT",
                    "status": "FAILED",
                    "attempts": [
                      {
                        "model": "qwen3:4b",
                        "reason": "OLLAMA_TIMEOUT",
                        "endpoint": "http://host.docker.internal:11434"
                      }
                    ],
                    "provider": "ollama"
                  },
                  {
                    "model": "claude-haiku-4-5-20251001",
                    "reason": "COMPLETED",
                    "status": "OK",
                    "provider": "anthropic",
                    "latency_ms": 3081,
                    "response_hash": "c5dfa8ee9ae1ba09d53e94ad3cd1677e6cadff90dc3dc1f9a08947d009449fac"
                  }
                ],
                "provider": "anthropic",
                "confidence": 0.5,
                "source_refs": [
                  {
                    "source_table": "ai_responses",
                    "source_record_id": "ai_resp_context_router_775a7843a9623441e1b1513f"
                  }
                ]
              },
              "created_at": "2026-06-02T09:44:16.724223+00:00",
              "consumed_count": 0,
              "status": "PUBLISHED",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_775a7843a9623441e1b1513f",
              "schema_version": 1,
              "metadata_json": {
                "router": "ai_context_fallback",
                "provider": "anthropic",
                "source_to_neuron": true
              }
            },
            "ai_request_id": "ai_req_context_router_01f02d432b8bb41d643a28b1",
            "ai_response_id": "ai_resp_context_router_775a7843a9623441e1b1513f",
            "latency_ms": 13590,
            "secrets_exposed": false
          },
          "safety_before": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10410,
            "exit_plans": 10410,
            "coordinator_decisions": 10706,
            "brain_outputs": 10742,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "safety_after": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10410,
            "exit_plans": 10410,
            "coordinator_decisions": 10706,
            "brain_outputs": 10742,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "trading_mutation_detected": false
        },
        "paper_execution": {
          "mock_data": false,
          "run_id": "paper_execution_fc01ac26b00749bbac58edd89059e8e6",
          "cycle_id": "active_30m_observation_20260602T091845Z_cycle_8",
          "system_power": "ON",
          "started_at": "2026-06-02T09:44:22.207759+00:00",
          "finished_at": "2026-06-02T09:44:22.303582+00:00",
          "status": "NO_VALID_PAPER_INTENTS",
          "intents_checked": 3,
          "executable_intents": 0,
          "orders_created": 0,
          "fills_created": 0,
          "positions_created": 0,
          "blocked_intents": 3,
          "duplicate_skipped": 0,
          "block_reasons_json": {
            "INTENT_ALREADY_EXECUTED": 3,
            "MISSING_TRUSTED_ORDERBOOK": 3
          },
          "real_orders_delta": 0,
          "live_orders_delta": 0,
          "fills_v2_delta": 0,
          "positions_delta": 0,
          "error_message": null,
          "metadata_json": {
            "reason": "no executable paper intents"
          }
        },
        "paper_exits": {
          "mock_data": false,
          "run_id": "paper_exit_loop_9566eeb4736a4cc3be69aba181faa177",
          "system_power": "ON",
          "status": "NO_OPEN_PAPER_POSITIONS",
          "open_positions_checked": 0,
          "closed_positions_count": 0,
          "marked_positions_count": 0,
          "blocked_positions_count": 0,
          "no_exit_price_count": 0,
          "no_exit_condition_count": 0,
          "duplicate_close_skipped_count": 0,
          "orphan_positions_count": 0,
          "realized_pnl": 0,
          "unrealized_pnl": null,
          "paper_orders_delta": 0,
          "paper_positions_delta": 0,
          "real_orders_delta": 0,
          "fills_delta": 0,
          "live_orders_delta": 0,
          "started_at": "2026-06-02T09:44:22.340589+00:00",
          "finished_at": "2026-06-02T09:44:22.421202+00:00",
          "error_summary": null,
          "metadata": {
            "paper_orders": 9,
            "paper_positions": 9,
            "no_fake_pnl": true
          }
        }
      },
      "errors": []
    },
    "repeated_api_failures": 0,
    "repeated_cycle_failures": 0,
    "deltas": {
      "neural_events": 57,
      "mesh_sessions": 10,
      "shared_awareness": 10,
      "brain_opinions": 40,
      "mesh_coordinator_decisions": 10,
      "capital_evaluations": 10,
      "position_awareness": 0,
      "paper": {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "paper_position_closes": 0,
        "paper_trade_ledger": 0,
        "orders_v2": 0,
        "fills_v2": 0,
        "canonical_positions": 0,
        "real_orders_current": 0,
        "live_orders": 0
      },
      "events_by_type": {
        "AI_CONTEXT_UNAVAILABLE": 0,
        "AI_CONTEXT_UPDATED": 8,
        "LIQUIDITY_CHANGED": 8,
        "MARKET_REPRICING": 8,
        "NEWS_DETECTED": 16,
        "ORDERBOOK_REFRESHED": 8,
        "PNL_CHANGED": 0,
        "RISK_CHANGED": 0,
        "SPREAD_CHANGED": 8,
        "WHALE_DETECTED": 1
      }
    }
  },
  {
    "timestamp": "2026-06-02T09:48:06.038025+00:00",
    "system_power": "ON",
    "runtime_health": "HEALTHY",
    "endpoint_status": {
      "/healthz": "OK",
      "/runtime/health": "OK",
      "/system/power": "OK",
      "/dashboard/api/v2/source-to-neuron-flow": "OK",
      "/dashboard/api/v2/ai-context-router": "OK",
      "/dashboard/api/v2/neural-bus": "OK",
      "/dashboard/api/v2/mesh-sessions": "OK",
      "/dashboard/api/v2/shared-awareness": "OK",
      "/dashboard/api/v2/multi-brain-consumption": "OK",
      "/dashboard/api/v2/mesh-coordinator": "OK",
      "/dashboard/api/v2/capital-brain": "OK",
      "/dashboard/api/v2/positions-awareness": "OK",
      "/dashboard/api/v2/paper": "OK",
      "/dashboard/api/v2/paper/trade-forensics": "OK",
      "/dashboard/api/v2/overnight/status": "OK",
      "/dashboard/api/v2/source-status": "OK"
    },
    "mock_data_endpoints": [],
    "secret_exposed": false,
    "source_health": "OK",
    "degraded_sources": [],
    "ai_router": {
      "latest_status": "OK",
      "selected_provider": "anthropic",
      "ollama_status": {
        "status": "FAILED",
        "reason": "OLLAMA_TIMEOUT",
        "last_run_id": "source_to_neuron_b22379cdb95c4cab940e970813996c7a"
      },
      "anthropic_status": {
        "status": "OK",
        "reason": "COMPLETED",
        "last_run_id": "source_to_neuron_b22379cdb95c4cab940e970813996c7a"
      },
      "openai_status": {
        "status": "FAILED",
        "reason": "OPENAI_QUOTA_EXCEEDED",
        "last_run_id": "post_env_ai_router_verification_20260602"
      },
      "success_count": 10,
      "unavailable_count": 2,
      "secrets_exposed": false
    },
    "events_by_type": {
      "NEWS_DETECTED": 24,
      "ORDERBOOK_REFRESHED": 19,
      "LIQUIDITY_CHANGED": 12,
      "MARKET_REPRICING": 12,
      "SPREAD_CHANGED": 12,
      "AI_CONTEXT_UPDATED": 10,
      "RISK_CHANGED": 4,
      "AI_CONTEXT_UNAVAILABLE": 2,
      "PNL_CHANGED": 2,
      "WHALE_DETECTED": 2
    },
    "neural_events": 99,
    "mesh_sessions": 36,
    "shared_awareness": 36,
    "brain_opinions": 117,
    "mesh_coordinator_decisions": 26,
    "mesh_conflicts_detected": 19,
    "source_brain_count_avg": 4.0345,
    "capital_evaluations": 24,
    "capital_decisions": {
      "CAPITAL_SUPPORT": 21,
      "CAPITAL_BLOCK": 2,
      "CAPITAL_RELEASE_REVIEW": 1
    },
    "position_awareness": 1,
    "position_reactions": {
      "PNL_RISING": 2,
      "CAPITAL_PRESSURE": 1,
      "PNL_FALLING": 1,
      "POSITION_AGING": 1
    },
    "paper": {
      "live_orders": 0,
      "live_enabled": false,
      "shadow_enabled": false,
      "real_orders_current": 1,
      "orders_v2": 1,
      "fills_v2": 1,
      "canonical_positions": 0,
      "paper_intents": 6,
      "paper_orders": 9,
      "paper_fills": 6,
      "paper_positions": 9,
      "paper_position_closes": 6,
      "paper_trade_ledger": 12,
      "open_positions": 0,
      "closed_positions": 6,
      "active_positions_without_fills": 0,
      "paper_lineage": "OK",
      "capital_reconciliation": "OK",
      "realized_pnl": 23.55,
      "unrealized_pnl": 0.0,
      "available_balance": 1000.0,
      "locked_balance": 0.0,
      "open_exposure": 0.0,
      "top_blockers": [
        {
          "blocker": "MISSING_TRUSTED_ORDERBOOK",
          "count": 2640
        },
        {
          "blocker": "INTENT_ALREADY_EXECUTED",
          "count": 1926
        }
      ]
    },
    "forensics_active_count": 6,
    "forensics_quarantined_count": 3,
    "cycle_index": 9,
    "active_cycle": {
      "correlation_id": "active_30m_observation_20260602T091845Z_cycle_9",
      "outputs": {
        "source_to_neuron": {
          "mock_data": false,
          "status": "OK",
          "run_id": "source_to_neuron_b22379cdb95c4cab940e970813996c7a",
          "blocked": false,
          "providers_checked": [
            "polymarket_gamma",
            "polymarket_clob_orderbook",
            "polymarket_clob_prices",
            "polymarket_clob_spreads",
            "polymarket_activity_readonly",
            "ollama_local_model",
            "news_provider",
            "reddit_or_social_provider"
          ],
          "provider_status": {
            "polymarket_gamma": {
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
              "last_success_at": "2026-06-02T09:47:28.913258+00:00",
              "last_error_at": null,
              "latency_ms": 941,
              "details_json": {
                "event_count": 10,
                "sample_market_id": "2169995",
                "sample_token_available": true,
                "token_candidates": 34
              },
              "notes": "Gamma active events check succeeded."
            },
            "polymarket_clob_orderbook": {
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
              "last_success_at": "2026-06-02T09:47:29.214342+00:00",
              "last_error_at": null,
              "latency_ms": 296,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48344659.16,
                "last_trade_price_present": true
              },
              "notes": "CLOB /book read-only check succeeded."
            },
            "polymarket_clob_prices": {
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
              "last_success_at": "2026-06-02T09:47:29.214388+00:00",
              "last_error_at": null,
              "latency_ms": 296,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48344659.16,
                "last_trade_price_present": true
              },
              "notes": "Price truth derived from read-only CLOB book response."
            },
            "polymarket_clob_spreads": {
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
              "last_success_at": "2026-06-02T09:47:29.214394+00:00",
              "last_error_at": null,
              "latency_ms": 296,
              "details_json": {
                "sample_market_id": "2169995",
                "sample_token_id": "25714007960293389110960044475283546872601238755063051359394740854408462452120",
                "attempted_tokens": 1,
                "best_bid": 0.008,
                "best_ask": 0.009,
                "spread": 0.001,
                "depth_1c": 48344659.16,
                "last_trade_price_present": true
              },
              "notes": "Spread and depth truth derived from read-only CLOB book response."
            },
            "polymarket_activity_readonly": {
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
              "last_success_at": "2026-06-02T09:47:29.576452+00:00",
              "last_error_at": null,
              "latency_ms": 361,
              "details_json": {
                "sample_count": 1
              },
              "notes": "Data API /trades read-only discovery check succeeded."
            },
            "ollama_local_model": {
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
              "last_success_at": "2026-06-02T09:47:29.690891+00:00",
              "last_error_at": null,
              "latency_ms": 112,
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
                  "http://host.docker.internal:11434/api/tags"
                ]
              },
              "notes": "Ollama tag check succeeded; model routing remains outside V2.21."
            },
            "news_provider": {
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
            "reddit_or_social_provider": {
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
            },
            "ai_context_router": {
              "runtime_status": "ACTIVE",
              "selected_provider": "anthropic",
              "final_reason": "AI_CONTEXT_UPDATED",
              "secret_value_exposed": false
            }
          },
          "events_created": 7,
          "events_by_type": {
            "MARKET_REPRICING": 1,
            "NEWS_DETECTED": 2,
            "ORDERBOOK_REFRESHED": 1,
            "SPREAD_CHANGED": 1,
            "LIQUIDITY_CHANGED": 1,
            "AI_CONTEXT_UPDATED": 1
          },
          "sessions_updated": 21,
          "awareness_domains_updated": 92,
          "brain_opinions_created": 25,
          "coordinator_decisions_created": 5,
          "latest_items": [
            {
              "event_id": "neural_event_40b919737a904043bed59ec46f1f647e",
              "event_type": "MARKET_REPRICING",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_gamma",
              "neuron": "Market Neuron",
              "source_table": "source_status",
              "source_record_id": "polymarket_gamma:source_to_neuron_b22379cdb95c4cab940e970813996c7a",
              "created_at": "2026-06-02T09:47:30.243328+00:00"
            },
            {
              "event_id": "neural_event_f85eec74c00f493997b8dcc59ed2ba61",
              "event_type": "NEWS_DETECTED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "rss",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_63c128c2b7b848fdb16c96c59199ce6c",
              "created_at": "2026-06-02T09:47:31.865952+00:00"
            },
            {
              "event_id": "neural_event_451fa9fa7a8642cba10aa47d65fafbce",
              "event_type": "NEWS_DETECTED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "newsapi",
              "neuron": "News Neuron",
              "source_table": "news_normalized_events",
              "source_record_id": "news_evt_bfc5b99d1d2c4cff9eabb753376685f5",
              "created_at": "2026-06-02T09:47:33.491875+00:00"
            },
            {
              "event_id": "neural_event_fb0c0a38367a4cd392c1e72327c688c8",
              "event_type": "ORDERBOOK_REFRESHED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Orderbook Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_b7bb8ef5f2534ef79fe3c48ec8058ba6",
              "created_at": "2026-06-02T09:47:34.046472+00:00"
            },
            {
              "event_id": "neural_event_9e0747ae0c4e47e3aa74976780908bf3",
              "event_type": "SPREAD_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_b7bb8ef5f2534ef79fe3c48ec8058ba6:SPREAD_CHANGED",
              "created_at": "2026-06-02T09:47:34.369284+00:00"
            },
            {
              "event_id": "neural_event_b808f0644320454a90709c410656ec71",
              "event_type": "LIQUIDITY_CHANGED",
              "market_id": "2169995",
              "candidate_id": null,
              "position_id": null,
              "provider": "polymarket_clob",
              "neuron": "Liquidity Neuron",
              "source_table": "orderbook_snapshots",
              "source_record_id": "ob_b7bb8ef5f2534ef79fe3c48ec8058ba6:LIQUIDITY_CHANGED",
              "created_at": "2026-06-02T09:47:34.730454+00:00"
            },
            {
              "event_id": "neural_event_66cf8063cff1404683df704059480cf2",
              "event_type": "AI_CONTEXT_UPDATED",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "provider": "anthropic",
              "neuron": "AI Context Brain",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_d1e79ca368790ed34df45c67",
              "created_at": "2026-06-02T09:47:48.378621+00:00"
            }
          ],
          "errors": [],
          "missing_providers": [],
          "degraded_providers": [],
          "whale_status": "NO_WHALE_EVENT_FOUND",
          "secrets_exposed": false,
          "ai_context_router": {
            "mock_data": false,
            "status": "OK",
            "run_id": "source_to_neuron_b22379cdb95c4cab940e970813996c7a",
            "selected_provider": "anthropic",
            "final_reason": "AI_CONTEXT_UPDATED",
            "providers_attempted": [
              {
                "provider": "ollama",
                "status": "FAILED",
                "reason": "OLLAMA_TIMEOUT",
                "attempts": [
                  {
                    "endpoint": "http://host.docker.internal:11434",
                    "model": "qwen3:4b",
                    "reason": "OLLAMA_TIMEOUT"
                  }
                ]
              },
              {
                "provider": "anthropic",
                "status": "OK",
                "reason": "COMPLETED",
                "model": "claude-haiku-4-5-20251001",
                "latency_ms": 3051,
                "response_hash": "71f1a2bac9d17208b74588f7ec04dcccccc8ae593bd9c59decf14dee688355cc"
              }
            ],
            "event": {
              "id": 230,
              "event_id": "neural_event_66cf8063cff1404683df704059480cf2",
              "event_type": "AI_CONTEXT_UPDATED",
              "correlation_id": "source_to_neuron_b22379cdb95c4cab940e970813996c7a",
              "market_id": null,
              "candidate_id": null,
              "position_id": null,
              "source_component": "AI Context Brain",
              "source_type": "brain",
              "priority": 5,
              "payload_json": {
                "model": "claude-haiku-4-5-20251001",
                "status": "COMPLETED",
                "summary": "```json\n{\n  \"status\": \"ready\",\n  \"summary\": \"POLYBOT AI Context Brain initialized. Awaiting source-backed evidence input. Capable of processing: provider data, news feeds, orderbook snapshots, whale activity, and PnL metrics. Output limited to context synthesis only. Trade creation, risk bypass, capital allocation, and state changes require downstream governance approval.\",\n  \"confidence\": 0.95,\n  \"constraints\": {\n    \"cannot_create\": [\"trades\", \"intents\", \"orders\", \"fills\", \"positions\", \"PnL modifications\"],\n    \"cannot_bypass\": [\"Risk\", \"Exit\", \"Capital\", \"Coordinator\", \"State Governor\"],\n    \"input_scope\": [\"provider\", \"news\", \"orderbook\", \"whale\", \"PnL\"],\n    \"output_scope\": [\"context\", \"evidence_synthesis\", \"confidence_scoring\"]\n  }\n}\n```\n\n**Ready for source-backed input.** Provide evidence payload with source attribution.",
                "attempts": [
                  {
                    "reason": "OLLAMA_TIMEOUT",
                    "status": "FAILED",
                    "attempts": [
                      {
                        "model": "qwen3:4b",
                        "reason": "OLLAMA_TIMEOUT",
                        "endpoint": "http://host.docker.internal:11434"
                      }
                    ],
                    "provider": "ollama"
                  },
                  {
                    "model": "claude-haiku-4-5-20251001",
                    "reason": "COMPLETED",
                    "status": "OK",
                    "provider": "anthropic",
                    "latency_ms": 3051,
                    "response_hash": "71f1a2bac9d17208b74588f7ec04dcccccc8ae593bd9c59decf14dee688355cc"
                  }
                ],
                "provider": "anthropic",
                "confidence": 0.5,
                "source_refs": [
                  {
                    "source_table": "ai_responses",
                    "source_record_id": "ai_resp_context_router_d1e79ca368790ed34df45c67"
                  }
                ]
              },
              "created_at": "2026-06-02T09:47:48.378621+00:00",
              "consumed_count": 0,
              "status": "PUBLISHED",
              "source_table": "ai_responses",
              "source_record_id": "ai_resp_context_router_d1e79ca368790ed34df45c67",
              "schema_version": 1,
              "metadata_json": {
                "router": "ai_context_fallback",
                "provider": "anthropic",
                "source_to_neuron": true
              }
            },
            "ai_request_id": "ai_req_context_router_219d089514b26d05acfeec58",
            "ai_response_id": "ai_resp_context_router_d1e79ca368790ed34df45c67",
            "latency_ms": 13151,
            "secrets_exposed": false
          },
          "safety_before": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10420,
            "exit_plans": 10420,
            "coordinator_decisions": 10716,
            "brain_outputs": 10752,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "safety_after": {
            "live_orders": 0,
            "paper_orders": 9,
            "paper_fills": 6,
            "paper_positions": 9,
            "paper_intents": 6,
            "paper_capital_ledger": 1,
            "risk_decisions": 10420,
            "exit_plans": 10420,
            "coordinator_decisions": 10716,
            "brain_outputs": 10752,
            "orders_v2": 1,
            "fills_v2": 1,
            "positions": 0,
            "paper_account_balances": {
              "current_balance": 1000.0,
              "available_balance": 1000.0,
              "locked_balance": 0.0,
              "open_exposure": 0.0
            }
          },
          "trading_mutation_detected": false
        },
        "paper_execution": {
          "mock_data": false,
          "run_id": "paper_execution_0b5ac945e0ed4b7d9572da2f5832bb4e",
          "cycle_id": "active_30m_observation_20260602T091845Z_cycle_9",
          "system_power": "ON",
          "started_at": "2026-06-02T09:47:53.195930+00:00",
          "finished_at": "2026-06-02T09:47:53.264865+00:00",
          "status": "NO_VALID_PAPER_INTENTS",
          "intents_checked": 3,
          "executable_intents": 0,
          "orders_created": 0,
          "fills_created": 0,
          "positions_created": 0,
          "blocked_intents": 3,
          "duplicate_skipped": 0,
          "block_reasons_json": {
            "INTENT_ALREADY_EXECUTED": 3,
            "MISSING_TRUSTED_ORDERBOOK": 3
          },
          "real_orders_delta": 0,
          "live_orders_delta": 0,
          "fills_v2_delta": 0,
          "positions_delta": 0,
          "error_message": null,
          "metadata_json": {
            "reason": "no executable paper intents"
          }
        },
        "paper_exits": {
          "mock_data": false,
          "run_id": "paper_exit_loop_e0c48028beb541b2a1359a9cea0fa5a2",
          "system_power": "ON",
          "status": "NO_OPEN_PAPER_POSITIONS",
          "open_positions_checked": 0,
          "closed_positions_count": 0,
          "marked_positions_count": 0,
          "blocked_positions_count": 0,
          "no_exit_price_count": 0,
          "no_exit_condition_count": 0,
          "duplicate_close_skipped_count": 0,
          "orphan_positions_count": 0,
          "realized_pnl": 0,
          "unrealized_pnl": null,
          "paper_orders_delta": 0,
          "paper_positions_delta": 0,
          "real_orders_delta": 0,
          "fills_delta": 0,
          "live_orders_delta": 0,
          "started_at": "2026-06-02T09:47:53.290683+00:00",
          "finished_at": "2026-06-02T09:47:53.341874+00:00",
          "error_summary": null,
          "metadata": {
            "paper_orders": 9,
            "paper_positions": 9,
            "no_fake_pnl": true
          }
        }
      },
      "errors": []
    },
    "repeated_api_failures": 0,
    "repeated_cycle_failures": 0,
    "deltas": {
      "neural_events": 64,
      "mesh_sessions": 11,
      "shared_awareness": 11,
      "brain_opinions": 44,
      "mesh_coordinator_decisions": 11,
      "capital_evaluations": 11,
      "position_awareness": 0,
      "paper": {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "paper_position_closes": 0,
        "paper_trade_ledger": 0,
        "orders_v2": 0,
        "fills_v2": 0,
        "canonical_positions": 0,
        "real_orders_current": 0,
        "live_orders": 0
      },
      "events_by_type": {
        "AI_CONTEXT_UNAVAILABLE": 0,
        "AI_CONTEXT_UPDATED": 9,
        "LIQUIDITY_CHANGED": 9,
        "MARKET_REPRICING": 9,
        "NEWS_DETECTED": 18,
        "ORDERBOOK_REFRESHED": 9,
        "PNL_CHANGED": 0,
        "RISK_CHANGED": 0,
        "SPREAD_CHANGED": 9,
        "WHALE_DETECTED": 1
      }
    }
  }
]
```
