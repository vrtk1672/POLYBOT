from __future__ import annotations


class NeuralEventBusError(RuntimeError):
    pass


class NeuralPublishBlocked(NeuralEventBusError):
    pass


class NeuralDeliveryBlocked(NeuralEventBusError):
    pass
