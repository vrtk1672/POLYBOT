from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4


_current_correlation_id: ContextVar[str | None] = ContextVar("polybot_correlation_id", default=None)


def new_correlation_id() -> str:
    return f"corr_{uuid4().hex}"


def get_current_correlation_id() -> str | None:
    return _current_correlation_id.get()


@contextmanager
def with_correlation_id(correlation_id: str):
    token = _current_correlation_id.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _current_correlation_id.reset(token)


def derive_child_correlation(parent_envelope) -> str:
    return getattr(parent_envelope, "correlation_id", None) or new_correlation_id()
