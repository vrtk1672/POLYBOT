from __future__ import annotations

import inspect

from app.ingestion.market_service import MarketService


def test_neuron_intelligence_runs_after_trusted_orderbook_before_downstream_recompute() -> None:
    source = inspect.getsource(MarketService.refresh)

    trusted_index = source.index("self._trusted_orderbook.resolve")
    neuron_index = source.index("self._neuron_intelligence.run_pack")
    downstream_index = source.index("self._downstream_recompute.run_recompute")

    assert trusted_index < neuron_index < downstream_index
