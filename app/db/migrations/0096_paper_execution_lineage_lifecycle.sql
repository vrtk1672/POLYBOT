ALTER TABLE paper_intents
    DROP CONSTRAINT IF EXISTS paper_intents_intent_status_check;

ALTER TABLE paper_intents
    ADD CONSTRAINT paper_intents_intent_status_check
        CHECK (
            intent_status IN (
                'CREATED',
                'READY',
                'EXECUTING',
                'EXECUTED',
                'POSITION_OPENED',
                'CLOSED',
                'BLOCKED',
                'CANCELLED',
                'ERROR',
                'EXPIRED'
            )
        );

ALTER TABLE paper_intents
    ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS execution_block_reason TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_paper_intents_executed_at
    ON paper_intents (executed_at DESC)
    WHERE executed_at IS NOT NULL;
