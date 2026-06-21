from __future__ import annotations

from dataclasses import dataclass

from app.db.connection import DatabaseConnectionFactory
from app.services.alerts import TelegramDeliveryService
from app.services.operator_control import OperatorControlService
from app.services.query.operator_dashboard_query_service import OperatorDashboardQueryService


@dataclass(slots=True)
class TelegramCommandResponse:
    command: str
    supported: bool
    response_text: str
    sent: bool = False
    control_action_id: str | None = None


class TelegramCommandService:
    def __init__(
        self,
        connection_factory: DatabaseConnectionFactory | None = None,
    ) -> None:
        factory = connection_factory or DatabaseConnectionFactory()
        self._dashboard = OperatorDashboardQueryService(factory)
        self._controls = OperatorControlService(factory)
        self._delivery = TelegramDeliveryService()

    def handle_command(
        self,
        command_text: str,
        *,
        requested_by: str | None = None,
    ) -> TelegramCommandResponse:
        command = (command_text or "").strip().split()[0].lower()
        if command == "/status":
            health = self._dashboard.get_system_health()
            ranking = self._dashboard.get_ranking_overview(limit=3)
            response = (
                f"DB: {'OK' if health['db_connected'] else 'DOWN'}\n"
                f"Pending eligible intents: {health['pending_eligible_command_intents']}\n"
                f"Top candidates: {len(ranking['top_ranked'])}\n"
                f"Warnings: {len(health['warnings'])}"
            )
            return TelegramCommandResponse(command=command, supported=True, response_text=response)
        if command == "/health":
            health = self._dashboard.get_system_health()
            cycle_status = health["last_cycle"]["status"] if health["last_cycle"] else "none"
            response = (
                f"Health: {'OK' if health['db_connected'] else 'DEGRADED'}\n"
                f"Last cycle: {cycle_status}\n"
                f"Critical alerts (24h): {health['critical_alert_count_24h']}\n"
                f"Warnings: {', '.join(health['warnings']) if health['warnings'] else 'none'}"
            )
            return TelegramCommandResponse(command=command, supported=True, response_text=response)
        if command == "/top":
            ranking = self._dashboard.get_ranking_overview(limit=5)
            items = ranking["top_ranked"]
            if not items:
                return TelegramCommandResponse(command=command, supported=True, response_text="No persisted ranking candidates are available yet.")
            lines = ["Top ranked opportunities:"]
            for item in items:
                lines.append(
                    f"{item['rank_position']}. {item['market_id']} {item['gate_decision_class']} score={item['total_rank_score']}"
                )
            return TelegramCommandResponse(command=command, supported=True, response_text="\n".join(lines))
        if command == "/positions":
            positions = self._dashboard.get_positions_orders(limit=5)
            total = len(positions["live_positions"]) + len(positions["paper_positions"]) + len(positions["shadow_positions"])
            if total == 0:
                return TelegramCommandResponse(command=command, supported=True, response_text="No open persisted positions are available.")
            response = (
                f"Open positions\n"
                f"Live: {len(positions['live_positions'])}\n"
                f"Paper: {len(positions['paper_positions'])}\n"
                f"Shadow: {len(positions['shadow_positions'])}"
            )
            return TelegramCommandResponse(command=command, supported=True, response_text=response)
        if command == "/orders":
            orders = self._dashboard.get_positions_orders(limit=5)
            total = len(orders["live_orders"]) + len(orders["paper_orders"]) + len(orders["shadow_orders"])
            if total == 0:
                return TelegramCommandResponse(command=command, supported=True, response_text="No persisted orders are available.")
            response = (
                f"Orders\n"
                f"Live: {len(orders['live_orders'])}\n"
                f"Paper: {len(orders['paper_orders'])}\n"
                f"Shadow: {len(orders['shadow_orders'])}"
            )
            return TelegramCommandResponse(command=command, supported=True, response_text=response)
        if command == "/pnl":
            pnl = self._dashboard.get_pnl_snapshot()
            response = (
                f"PnL snapshot\n"
                f"Live: unrealized={pnl['live']['unrealized']} realized={pnl['live']['realized']}\n"
                f"Paper: unrealized={pnl['paper']['unrealized']} realized={pnl['paper']['realized']}\n"
                f"Shadow: unrealized={pnl['shadow']['unrealized']} realized={pnl['shadow']['realized']}"
            )
            return TelegramCommandResponse(command=command, supported=True, response_text=response)
        if command == "/whales":
            whales = self._dashboard.get_intelligence_panels(limit=3)["whales"]
            if not whales:
                return TelegramCommandResponse(command=command, supported=True, response_text="No persisted whale intelligence is available yet.")
            lines = ["Whale signals:"]
            for item in whales:
                lines.append(f"{item['market_id']} presence={item['whale_presence_score']} reversal_risk={item['whale_reversal_risk']}")
            return TelegramCommandResponse(command=command, supported=True, response_text="\n".join(lines))
        if command == "/news":
            news = self._dashboard.get_intelligence_panels(limit=3)["news"]
            if not news:
                return TelegramCommandResponse(command=command, supported=True, response_text="No persisted external news is available yet.")
            lines = ["Recent news:"]
            for item in news:
                lines.append(f"- {item['normalized_title']}")
            return TelegramCommandResponse(command=command, supported=True, response_text="\n".join(lines))
        if command in {"/kill", "/resume"}:
            result = self._controls.request_live_cage_action(
                action_class=command.replace("/", "").upper(),
                requested_via="TELEGRAM",
                requested_by=requested_by,
                command_text=command_text,
            )
            return TelegramCommandResponse(
                command=command,
                supported=True,
                response_text=result.message,
                control_action_id=result.action_id,
            )
        if command == "/pause":
            result = self._controls.request_cooldown_action(
                requested_via="TELEGRAM",
                requested_by=requested_by,
                command_text=command_text,
            )
            return TelegramCommandResponse(
                command=command,
                supported=True,
                response_text=result.message,
                control_action_id=result.action_id,
            )
        return TelegramCommandResponse(
            command=command or command_text.strip() or "<empty>",
            supported=False,
            response_text="Command not supported yet by the current Telegram foundation.",
        )

    def handle_update(self, update: dict[str, object], *, send_reply: bool = False) -> TelegramCommandResponse:
        message = dict(update.get("message") or {})
        chat = dict(message.get("chat") or {})
        from_user = dict(message.get("from") or {})
        text = str(message.get("text") or "")
        response = self.handle_command(text, requested_by=str(from_user.get("username") or from_user.get("id") or "telegram"))
        if send_reply and chat.get("id") is not None:
            self._delivery.send_message(chat_id=str(chat["id"]), text=response.response_text)
            response.sent = True
        return response
