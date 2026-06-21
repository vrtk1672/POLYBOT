from app.services.proactive_seed_mesh_adapter import ProactiveSeedDataOnlyMeshAdapter
from app.services.proactive_seed_mesh_inquiry import ProactiveSeedMeshInquiryService


def test_adapter_diagnostics_surface_is_safe_when_database_unavailable():
    diagnostics = ProactiveSeedDataOnlyMeshAdapter(connection_factory=type("Factory", (), {"enabled": False})()).diagnostics()

    assert diagnostics["status"] == "DATABASE_UNAVAILABLE"
    assert diagnostics["adapter_available"] is False


def test_empty_seed_fields_include_adapter_metadata():
    fields = ProactiveSeedMeshInquiryService(connection_factory=type("Factory", (), {"enabled": False})()).fields_for_seed(proactive_candidate_seed_id=None)

    assert fields["seed_mesh_adapter_payload_id"] is None
    assert fields["seed_mesh_adapter_result_state"] is None
    assert fields["mesh_inquiry_request_count"] == 0
