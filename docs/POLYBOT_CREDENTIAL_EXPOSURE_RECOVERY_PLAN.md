# POLYBOT Credential Exposure Recovery Plan

Date: 2026-06-02

## Exposure Summary

A prior raw compose configuration inspection may have exposed resolved
credential values in command output. This report intentionally contains no raw
secret values.

## Rotate At Minimum

- `ANTHROPIC_API_KEY`
- `POLYMARKET_CLOB_API_KEY`
- `POLYMARKET_CLOB_SECRET`
- `POLYMARKET_CLOB_PASSPHRASE`
- `NEWS_API_KEY` if it appeared in the raw compose output
- `OPENAI_API_KEY` if it appeared in the raw compose output

## Operator Actions

1. Revoke/rotate the listed provider credentials in their provider consoles.
2. Update the real `.env` manually with the new values.
3. Restart the API container.
4. Run `python scripts/safe_env_audit.py --json --no-masked-values`.
5. Confirm `GET /dashboard/api/v2/security/secrets` returns
   `raw_values_returned=false`.

If the operator chooses not to rotate, mark the phase
`YELLOW/ACCEPTED_RISK`, not `GREEN`.

## Prevention

- Do not run raw `docker compose config` during normal debugging.
- Do not print `.env`.
- Do not paste provider error bodies before redaction.
- Use the safe env audit script and dashboard security endpoint.

