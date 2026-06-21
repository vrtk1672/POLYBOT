"""
Execution client wrapper around the official py-clob-client.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    AssetType,
    BalanceAllowanceParams,
    OpenOrderParams,
    OrderArgs,
    OrderType,
    PartialCreateOrderOptions,
)
from py_clob_client.exceptions import PolyApiException

from app.stage4.auth import build_clob_client, describe_auth_context, validate_stage4_credentials
from app.stage4.config import Stage4Settings
from app.stage4.order_builder import LiveOrderIntent

USDC_DECIMALS = 6
USDC_SCALE = Decimal("1000000")


def normalize_usdc_balance(raw_balance: str | int | float | Decimal | None) -> float:
    if raw_balance in (None, ""):
        return 0.0
    normalized = Decimal(str(raw_balance)) / USDC_SCALE
    return float(normalized)


@dataclass(slots=True)
class AuthSelfCheckResult:
    ok: bool
    summary: str
    details: dict[str, Any]


@dataclass(slots=True)
class LiveSubmissionError(RuntimeError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class Stage4ExecutionClient:
    def __init__(self, settings: Stage4Settings) -> None:
        self.settings = settings

    def build_public_client(self) -> ClobClient:
        return ClobClient(self.settings.poly_clob_host)

    def build_authenticated_client(self) -> ClobClient:
        return build_clob_client(self.settings, require_l2=True)

    def auth_self_check(self) -> AuthSelfCheckResult:
        validation = validate_stage4_credentials(self.settings)
        details: dict[str, Any] = {**describe_auth_context(self.settings), "warnings": validation.warnings}
        if not validation.ok:
            details["errors"] = validation.errors
            return AuthSelfCheckResult(
                ok=False,
                summary="Stage 4 auth config is incomplete",
                details=details,
            )

        public_client = self.build_public_client()
        details["server_time"] = public_client.get_server_time()

        auth_client = self.build_authenticated_client()
        details["api_keys"] = auth_client.get_api_keys()
        collateral = auth_client.get_balance_allowance(
            BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        details["collateral_balance_allowance"] = collateral
        details["collateral_balance_usd"] = normalize_usdc_balance(collateral.get("balance"))
        details["open_orders"] = auth_client.get_orders(OpenOrderParams())
        return AuthSelfCheckResult(
            ok=True,
            summary="Authenticated Stage 4 connectivity verified",
            details=details,
        )

    def get_order_book_summary(self, token_id: str) -> Any:
        return self.build_public_client().get_order_book(token_id)

    def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, Any]:
        client = self.build_authenticated_client()
        collateral = dict(
            client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
        )
        collateral["balance_usd"] = normalize_usdc_balance(collateral.get("balance"))
        response = {
            "collateral": collateral
        }
        if token_id:
            response["conditional"] = client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
            )
        return response

    def get_open_orders(self) -> list[dict[str, Any]]:
        client = self.build_authenticated_client()
        return client.get_orders(OpenOrderParams())

    def auth_context(self) -> dict[str, Any]:
        return describe_auth_context(self.settings)

    def _create_signed_order_with_client(self, client: ClobClient, intent: LiveOrderIntent) -> Any:
        return client.create_order(
            OrderArgs(
                token_id=intent.token_id,
                price=intent.price,
                size=intent.size,
                side=intent.side,
            ),
            PartialCreateOrderOptions(
                tick_size=intent.tick_size,
                neg_risk=intent.neg_risk,
            ),
        )

    def create_signed_order(self, intent: LiveOrderIntent) -> Any:
        client = self.build_authenticated_client()
        return self._create_signed_order_with_client(client, intent)

    def submit_order(
        self,
        intent: LiveOrderIntent,
        *,
        order_type: str = OrderType.GTC,
        post_only: bool = False,
    ) -> dict[str, Any]:
        client = self.build_authenticated_client()
        signed_order = self._create_signed_order_with_client(client, intent)
        try:
            response = client.post_order(signed_order, order_type, post_only=post_only)
        except PolyApiException as exc:
            details = {
                "error_type": type(exc).__name__,
                "status_code": exc.status_code,
                "error_body": exc.error_msg,
                "auth_context": self.auth_context(),
                "order_summary": {
                    "market_id": intent.market_id,
                    "token_id": intent.token_id,
                    "side": intent.side,
                    "action": intent.action,
                    "price": intent.price,
                    "size": intent.size,
                    "notional_usd": intent.notional_usd,
                    "tick_size": intent.tick_size,
                    "neg_risk": intent.neg_risk,
                },
            }
            raise LiveSubmissionError(
                message=f"PolyApiException status={exc.status_code} body={exc.error_msg}",
                details=details,
            ) from exc
        return {
            "intent": asdict(intent),
            "order_type": order_type,
            "post_only": post_only,
            "response": response,
        }

    def get_order_status(self, order_id: str) -> dict[str, Any]:
        client = self.build_authenticated_client()
        return client.get_order(order_id)
