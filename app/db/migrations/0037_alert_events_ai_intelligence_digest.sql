ALTER TABLE alert_events
    DROP CONSTRAINT IF EXISTS alert_events_event_class_check;

ALTER TABLE alert_events
    ADD CONSTRAINT alert_events_event_class_check CHECK (
        event_class IN (
            'CANDIDATE_SELECTED',
            'INVALIDATION_WARNING',
            'FEED_FAILURE',
            'SERVICE_CRASH',
            'RISK_OVERLOAD',
            'CRITICAL_HEALTH_DEGRADATION',
            'AI_INTELLIGENCE_DIGEST'
        )
    );
