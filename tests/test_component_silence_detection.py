from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_dialogue import BrainDialogueService

from brain_dialogue_fixtures import prepare_brain_dialogue


def test_silent_component_detection_does_not_trust_decorative_service_health(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO service_health (service_name, service_type, status, updated_at)
            VALUES ('risk_gate_governor', 'risk', 'RUNNING', now())
            ON CONFLICT (service_name) DO UPDATE SET status='RUNNING', updated_at=now()
            """
        )

    life = BrainDialogueService().get_system_life()
    components = {component["component"]: component for component in life["components"]}

    assert components["Risk Gate"]["wired"] is True
    assert components["Risk Gate"]["active"] is False
    assert components["Risk Gate"]["last_source_record_at"] is None


def test_component_becomes_active_only_after_real_source_record_and_dialogue(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO brain_mesh_activation_runs (
                run_id, cycle_id, system_power, status, evidence_created,
                brain_outputs_created, coordinator_decisions_created
            )
            VALUES ('brain-silence-run', 'brain-silence-cycle', 'ON', 'OK', 1, 1, 1)
            """
        )

    BrainDialogueService().materialize_recent(limit_per_source=10)
    life = BrainDialogueService().get_system_life()
    components = {component["component"]: component for component in life["components"]}

    assert components["Brain Mesh Activation"]["active"] is True
    assert components["Brain Mesh Activation"]["last_source_record_at"] is not None
