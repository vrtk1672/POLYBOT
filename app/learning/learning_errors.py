class LearningError(Exception):
    """Base error for V2.19 learning services."""


class LearningValidationError(LearningError):
    """Raised when a learning request is missing required evidence."""

