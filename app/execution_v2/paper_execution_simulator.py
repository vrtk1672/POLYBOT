from __future__ import annotations

from app.execution_v2.contracts import PaperExecutionResult, OrderContract
from app.execution_v2.execution_quality import ExecutionQualityScorer
from app.execution_v2.fill_simulator import FillSimulator
from app.execution_v2.partial_fill_handler import PartialFillHandler


class PaperExecutionSimulator:
    def __init__(self) -> None:
        self.fill_simulator = FillSimulator()
        self.partial_handler = PartialFillHandler()
        self.quality = ExecutionQualityScorer()

    def simulate(self, contract: OrderContract) -> tuple[PaperExecutionResult, object]:
        fill = self.fill_simulator.simulate(contract)
        state = self.partial_handler.apply(order_id=contract.order_id, requested_size=contract.size, fills=[fill])
        quality = self.quality.score(
            order_id=contract.order_id,
            market_id=contract.market_id,
            expected_price=contract.price,
            expected_slippage_bps=fill.slippage_bps,
            expected_fill_probability=fill.fill_probability,
            requested_size=contract.size,
            fills=[fill],
        )
        return PaperExecutionResult(order_id=contract.order_id, order_status=state.order_status, fills=[fill], filled_size=state.filled_size, remaining_size=state.remaining_size, avg_fill_price=state.avg_fill_price, slippage_bps=fill.slippage_bps, fees_usd=fill.fee_usd, quality_score=quality.execution_quality_score), quality

