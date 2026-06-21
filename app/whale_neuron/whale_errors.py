from __future__ import annotations


class WhaleNeuronError(RuntimeError):
    pass


class WhaleScanBlocked(WhaleNeuronError):
    pass


class WhaleCollectionBlocked(WhaleNeuronError):
    pass
