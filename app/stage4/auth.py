"""
Authentication helpers for Stage 4 live execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eth_account import Account
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

from app.stage4.config import Stage4Settings


@dataclass(slots=True)
class AuthValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def resolve_signer_address(settings: Stage4Settings) -> str | None:
    if not settings.poly_private_key:
        return None
    return str(Account.from_key(settings.poly_private_key).address)


def resolve_signature_type(settings: Stage4Settings) -> int:
    if "poly_signature_type" in settings.model_fields_set:
        return settings.poly_signature_type

    signer_address = resolve_signer_address(settings)
    if signer_address and settings.poly_funder and signer_address.lower() == settings.poly_funder.lower():
        return 0
    return settings.poly_signature_type


def credential_source(settings: Stage4Settings) -> str:
    return "env" if settings.has_l2_credentials else "derived"


def describe_auth_context(settings: Stage4Settings) -> dict[str, str | int | None]:
    return {
        "host": settings.poly_clob_host,
        "chain_id": settings.poly_chain_id,
        "signer_address": resolve_signer_address(settings),
        "funder_address": settings.poly_funder,
        "signature_type": resolve_signature_type(settings),
        "credential_source": credential_source(settings),
    }


def validate_stage4_credentials(settings: Stage4Settings) -> AuthValidation:
    errors: list[str] = []
    warnings: list[str] = []

    if not settings.poly_private_key:
        errors.append("POLY_PRIVATE_KEY is missing")
    if not settings.poly_funder:
        errors.append("POLY_FUNDER is missing")
    if settings.poly_signature_type not in {0, 1, 2}:
        errors.append("POLY_SIGNATURE_TYPE must be 0, 1, or 2")
    if settings.has_l2_credentials and not settings.has_l1_credentials:
        errors.append("L2 API credentials require POLY_PRIVATE_KEY and POLY_FUNDER to be usable")
    if not settings.has_l2_credentials:
        warnings.append("L2 API credentials are not configured; the client will try create_or_derive_api_creds()")

    return AuthValidation(ok=not errors, errors=errors, warnings=warnings)


def build_api_creds(settings: Stage4Settings) -> ApiCreds | None:
    if not settings.has_l2_credentials:
        return None
    return ApiCreds(
        api_key=str(settings.poly_api_key),
        api_secret=str(settings.poly_api_secret),
        api_passphrase=str(settings.poly_api_passphrase),
    )


def build_clob_client(
    settings: Stage4Settings,
    *,
    require_l2: bool,
) -> ClobClient:
    validation = validate_stage4_credentials(settings)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))

    client = ClobClient(
        settings.poly_clob_host,
        chain_id=settings.poly_chain_id,
        key=settings.poly_private_key,
        creds=build_api_creds(settings),
        signature_type=resolve_signature_type(settings),
        funder=settings.poly_funder,
    )
    if require_l2:
        creds = build_api_creds(settings) or client.create_or_derive_api_creds()
        client.set_api_creds(creds)
    return client
