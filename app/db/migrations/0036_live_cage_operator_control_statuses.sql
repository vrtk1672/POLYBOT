ALTER TABLE operator_control_actions
    DROP CONSTRAINT IF EXISTS operator_control_actions_status_class_check;

ALTER TABLE operator_control_actions
    ADD CONSTRAINT operator_control_actions_status_class_check
    CHECK (status_class IN ('PLACEHOLDER', 'REJECTED', 'ACTIVE_GUARD', 'RELEASED_GUARD'));
