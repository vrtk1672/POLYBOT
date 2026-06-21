from __future__ import annotations


class RuntimeStateError(RuntimeError):
    """Base exception for runtime state failures."""


class RuntimeStateUnavailable(RuntimeStateError):
    """Raised when runtime state cannot be loaded safely."""


class RuntimePermissionDenied(RuntimeStateError):
    """Raised when the current mode blocks a runtime action."""


class RuntimeModeTransitionDenied(RuntimeStateError):
    """Raised when a mode transition is not legal."""
