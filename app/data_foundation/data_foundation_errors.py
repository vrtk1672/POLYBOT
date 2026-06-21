from __future__ import annotations


class DataFoundationError(Exception):
    """Base error for V2.2 data foundation failures."""


class DataCompletenessError(DataFoundationError):
    """Raised when completeness cannot be computed safely."""
