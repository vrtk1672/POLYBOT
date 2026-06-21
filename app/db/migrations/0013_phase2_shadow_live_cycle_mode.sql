ALTER TABLE cycles
DROP CONSTRAINT IF EXISTS cycles_mode_check;

ALTER TABLE cycles
ADD CONSTRAINT cycles_mode_check
CHECK (
    mode IN (
        'SCAN_ONLY',
        'PAPER',
        'PAPER_SIGNAL',
        'PAPER_EXECUTION_AWARE',
        'SHADOW_LIVE',
        'LIVE_DRY_RUN',
        'LIVE_SUBMIT'
    )
);
