from app.exit_cortex.exit_event_manager import ExitEventManager


def test_exit_event_manager_maps_trigger_events():
    assert ExitEventManager().event_type_for_trigger("STOP_LOSS") == "EXIT_STOP_LOSS_TRIGGERED"
    assert ExitEventManager().event_type_for_trigger("UNKNOWN") == "EXIT_TRIGGER_DETECTED"

