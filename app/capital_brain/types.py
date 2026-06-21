from __future__ import annotations

from enum import StrEnum


class CapitalDecision(StrEnum):
    SUPPORT = "CAPITAL_SUPPORT"
    WATCH = "CAPITAL_WATCH"
    BLOCK = "CAPITAL_BLOCK"
    RELEASE_REVIEW = "CAPITAL_RELEASE_REVIEW"
    INSUFFICIENT_DATA = "CAPITAL_INSUFFICIENT_DATA"
