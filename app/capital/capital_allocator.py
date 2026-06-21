from __future__ import annotations

from app.capital.allocation_policy import AllocationPolicy
from app.capital.contracts import CapitalAllocationDecision, CapitalAllocationRequest, CapitalState, EngineBudget


class CapitalAllocatorV2:
    def __init__(self, *, policy: AllocationPolicy | None = None) -> None:
        self.policy = policy or AllocationPolicy()

    def allocate(
        self,
        request: CapitalAllocationRequest,
        state: CapitalState,
        budgets: list[EngineBudget],
    ) -> CapitalAllocationDecision:
        return self.policy.decide(request, state, budgets)

