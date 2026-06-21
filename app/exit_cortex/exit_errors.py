from __future__ import annotations


class ExitCortexBlocked(RuntimeError):
    """Raised when an exit action is blocked by V2.16 safety rules."""

