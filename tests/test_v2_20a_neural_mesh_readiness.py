from __future__ import annotations

from app.tools.v2_20a_neural_mesh_audit import (
    ai_model_readiness,
    build_audit,
    edge_matrix,
    node_matrix,
)


def test_node_matrix_treats_polybot_as_mesh_not_single_pipeline() -> None:
    matrix = node_matrix()
    names = {row["node_name"] for row in matrix}

    assert "Runtime / State Governor" in names
    assert "Event Bus" in names
    assert "Opportunity Cortex" in names
    assert "Execution Cortex" in names
    assert "Feedback / Learning Loop" in names
    assert len(matrix) >= 20


def test_edge_matrix_contains_safety_and_learning_edges() -> None:
    edges = edge_matrix()
    labels = {(row["from_node"], row["to_node"]) for row in edges}

    assert ("Risk Gate", "Execution Cortex") in labels
    assert ("Execution Cortex", "Exit Cortex") in labels
    assert ("No-Trade Intelligence", "Feedback / Learning Loop") in labels
    assert ("Safety-Sensitive Paths", "Runtime / State Governor") in labels


def test_ai_model_readiness_lists_expected_local_models() -> None:
    report = ai_model_readiness()

    assert "qwen3:8b" in report["expected_models"]
    assert "qwen3:14b" in report["expected_models"]
    assert "deepseek-r1:14b" in report["expected_models"]
    assert "fallback_behavior" in report


def test_build_audit_returns_required_sections() -> None:
    audit = build_audit()

    assert audit["audit_id"] == "v2_20a_neural_mesh_readiness"
    assert audit["node_matrix"]
    assert audit["edge_matrix"]
    assert audit["ai_model_readiness"]
    assert audit["data_source_readiness"]
    assert audit["runtime_readiness"]
    assert audit["blockers"]
    assert audit["fix_plan"]
