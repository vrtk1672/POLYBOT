from __future__ import annotations

from enum import StrEnum


class SystemPower(StrEnum):
    ON = "ON"
    OFF = "OFF"


def parse_system_power(value: SystemPower | str) -> SystemPower:
    if isinstance(value, SystemPower):
        return value
    return SystemPower(str(value).strip().upper())
