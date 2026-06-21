from __future__ import annotations


class NewsNeuronError(RuntimeError):
    """Base error for V2.4 News Neuron."""


class NewsCollectionBlocked(NewsNeuronError):
    """Raised when runtime mode blocks news collection."""


class NewsSourceUnavailable(NewsNeuronError):
    """Raised when a news source cannot be collected."""
