from app.learning.memory_update_coordinator import MemoryUpdateCoordinator


def test_memory_update_skipped_on_low_confidence():
    decision = MemoryUpdateCoordinator().evaluate(confidence=0.4, evidence_exists=True)
    assert decision.update_memory is False


def test_memory_update_allowed_on_sufficient_confidence():
    decision = MemoryUpdateCoordinator().evaluate(confidence=0.8, evidence_exists=True)
    assert decision.update_memory is True
