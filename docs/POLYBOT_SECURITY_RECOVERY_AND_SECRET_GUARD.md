# POLYBOT Security Recovery And Secret Guard

Date: 2026-06-02

## Purpose

This phase closes the prior credential exposure governance issue by adding a
safe configuration audit path and a dashboard endpoint that never returns raw
secret values.

## Guardrails Added

- `app/security/redaction.py` centralizes `mask_secret`, `redact_secrets`, and
  `contains_secret_like_value`.
- `app/security/env_audit.py` performs safe env inspection and returns
  present/missing status, duplicate keys, compose passthrough key names, and
  redaction status.
- `scripts/safe_env_audit.py` and `scripts/safe_env_audit.ps1` are the operator
  entrypoints for safe env inspection.
- `GET /dashboard/api/v2/security/secrets` returns mock-free security status
  without secret values.

## Forbidden Normal Debugging Commands

- Raw `docker compose config`
- Raw `.env` output
- Raw `printenv`
- Direct provider response dumps without redaction

Use `scripts/safe_env_audit.py --json --no-masked-values` instead.

## Current Governance Status

Status: `ROTATION_REQUIRED`.

No new raw secrets were printed in this phase. Prior compose-resolved output may
have exposed credentials, so the operator must rotate affected keys or explicitly
accept governance risk as `YELLOW/ACCEPTED_RISK`.

