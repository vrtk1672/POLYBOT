ALTER TABLE shadow_orders
    DROP CONSTRAINT IF EXISTS shadow_orders_status_check;

ALTER TABLE shadow_orders
    ADD CONSTRAINT shadow_orders_status_check CHECK (
        status IN (
            'CREATED',
            'BLOCKED',
            'WOULD_SUBMIT',
            'WOULD_REJECT',
            'BLOCKED_BY_RISK',
            'BLOCKED_BY_CONFIG',
            'INVALID_REQUEST',
            'SHADOW_ONLY'
        )
    );
