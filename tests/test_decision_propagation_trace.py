from __future__ import annotations

import app.control_center.decision_propagation_trace as trace_module
from app.control_center.decision_propagation_trace import DecisionPropagationTraceService


def test_decision_propagation_trace_reports_same_cycle_context(monkeypatch) -> None:
    monkeypatch.setattr(trace_module, "SourceRefreshStatusService", lambda connection_factory=None: _SourceRefresh())
    monkeypatch.setattr(trace_module, "SourceBackedEdgeControlService", lambda connection_factory=None: _Edge())
    monkeypatch.setattr(trace_module, "PaperActionabilityService", lambda connection_factory=None: _Actionability())

    payload = DecisionPropagationTraceService(connection_factory=None).get_trace()

    assert payload["propagation_state"] == "ACTIVE"
    assert payload["source_refresh_cycle_id"] == "cycle-1"
    assert payload["counts"]["cycle_consistent"] == 1
    assert payload["traces"][0]["edge_thesis_id"] == "edge-1"
    assert payload["traces"][0]["risk_evidence_id"] == "risk-1"
    assert payload["traces"][0]["propagation_breakpoint"] is None


class _SourceRefresh:
    def get_status(self):
        return {
            "source_refresh_orchestrator_state": "ACTIVE",
            "latest_source_refresh_cycle_id": "cycle-1",
            "propagation_state": "ACTIVE",
            "propagation_breakpoint": None,
        }


class _Edge:
    def list_edges(self, *, limit=20, candidate_id=None, market_id=None):
        return {
            "items": [
                {
                    "candidate_id": "candidate-1",
                    "market_id": "market-1",
                    "side": "YES",
                    "token_id": "token-1",
                    "source_refresh_cycle_id": "cycle-1",
                    "propagation_context": {"source_refresh_cycle_id": "cycle-1"},
                    "edge_thesis_id": "edge-1",
                    "risk_evidence_id": "risk-1",
                    "edge_state": "EDGE_WATCH",
                    "risk_decision": "RISK_REVIEW",
                    "risk_blocker_subtype": "RISK_REVIEW_EDGE_WEAK",
                }
            ]
        }


class _Actionability:
    def list_actionability(self, *, limit=20, candidate_id=None):
        return {
            "items": [
                {
                    "candidate_id": "candidate-1",
                    "candidate_paper_actionability_state": "BLOCKED_BY_RISK",
                    "decision_cycle_consistent": True,
                    "propagation_breakpoint": None,
                }
            ]
        }
