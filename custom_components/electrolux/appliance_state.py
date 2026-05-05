from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .capabilities import get_state_value, set_state_value


class ConnectionState(Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"

    @classmethod
    def from_string(cls, value: str | None) -> "ConnectionState | None":
        try:
            return cls(value.upper()) if value else None
        except ValueError:
            return None


class Status(Enum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"

    @classmethod
    def from_string(cls, value: str | None) -> "Status | None":
        try:
            return cls(value.upper()) if value else None
        except ValueError:
            return None


@dataclass
class ReportedProperties:
    raw: dict[str, Any]

    def get(self, path: str, default: Any = None) -> Any:
        value = get_state_value(self.raw, path)
        return default if value is None else value

    def set(self, path: str, value: Any) -> None:
        set_state_value(self.raw, path, value)


@dataclass
class Properties:
    reported: ReportedProperties


@dataclass
class ApplianceState:
    id: str
    connectionState: ConnectionState | None
    status: Status | None
    properties: Properties
    data_model_version: str | None = None
    raw: dict[str, Any] | None = None

    def get_reported(self, path: str, default: Any = None) -> Any:
        return self.properties.reported.get(path, default)

    def set_reported(self, path: str, value: Any) -> None:
        self.properties.reported.set(path, value)


def update_reported_property(reported: ReportedProperties, property_name: str, value: Any) -> bool:
    reported.set(property_name, value)
    return True
