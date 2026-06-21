import math


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def log_scale(value: float | int | None, floor: float, ceiling: float) -> float:
    if value is None or value <= 0 or floor <= 0 or ceiling <= floor:
        return 0.0
    normalized = (math.log10(value) - math.log10(floor)) / (math.log10(ceiling) - math.log10(floor))
    return clamp(normalized, 0.0, 1.0)

