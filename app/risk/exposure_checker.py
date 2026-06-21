from __future__ import annotations


class ExposureChecker:
    def check(self, *, open_exposure_usd: float, proposed_size_usd: float, max_total_exposure_usd: float) -> tuple[bool, str | None]:
        if max(open_exposure_usd, 0.0) + max(proposed_size_usd, 0.0) > max(max_total_exposure_usd, 0.0):
            return False, "max_total_exposure_breach"
        return True, None

    def check_open_positions(self, *, open_positions_count: int, max_open_positions: int) -> tuple[bool, str | None]:
        if int(open_positions_count or 0) >= int(max_open_positions or 0):
            return False, "max_open_positions_breach"
        return True, None

