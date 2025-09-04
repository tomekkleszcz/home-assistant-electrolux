from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Optional

from homeassistant.components.climate.const import HVACMode


class ConnectionState(Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"

    @classmethod
    def from_string(cls, value: str) -> "Optional[ConnectionState]":
        try:
            return cls(value.upper()) if value else None
        except ValueError:
            return None


class Status(Enum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"

    @classmethod
    def from_string(cls, value: str) -> "Optional[Status]":
        try:
            return cls(value.upper()) if value else None
        except ValueError:
            return None


class ApplianceStateValue(Enum):
    RUNNING = "RUNNING"
    OFF = "OFF"

    @classmethod
    def from_string(cls, value: str) -> "Optional[ApplianceStateValue]":
        try:
            return cls(value.upper()) if value else None
        except ValueError:
            return None


class Toggle(Enum):
    ON = "ON"
    OFF = "OFF"

    @classmethod
    def from_string(cls, value: str) -> "Optional[Toggle]":
        try:
            return cls(value.upper()) if value else None
        except ValueError:
            return None


class TemperatureRepresentation(Enum):
    CELSIUS = "CELSIUS"

    @classmethod
    def from_string(cls, value: str) -> "Optional[TemperatureRepresentation]":
        try:
            return cls(value.upper()) if value else None
        except ValueError:
            return None


class Mode(Enum):
    AUTO = "AUTO"
    COOL = "COOL"
    HEAT = "HEAT"

    @classmethod
    def from_string(cls, value: str) -> "Optional[Mode]":
        try:
            return cls(value.upper()) if value else None
        except ValueError:
            return None

    @classmethod
    def from_hvac_mode(cls, hvac_mode: HVACMode) -> "Mode":
        mapping = {
            HVACMode.AUTO: Mode.AUTO,
            HVACMode.COOL: Mode.COOL,
            HVACMode.HEAT: Mode.HEAT
        }
        return mapping.get(hvac_mode, Mode.AUTO)

    def to_hvac_mode(self):
        mapping = {
            Mode.AUTO: HVACMode.AUTO,
            Mode.COOL: HVACMode.COOL,
            Mode.HEAT: HVACMode.HEAT
        }

        return mapping.get(self, HVACMode.OFF)


class FanSpeedSetting(Enum):
    AUTO = "AUTO"
    LOW = "LOW"
    MIDDLE = "MIDDLE"
    HIGH = "HIGH"

    @classmethod
    def from_string(cls, value: str) -> "Optional[FanSpeedSetting]":
        try:
            return cls(value.upper()) if value else None
        except ValueError:
            return None


class State(Enum):
    GOOD = "GOOD"

    @classmethod
    def from_string(cls, value: str) -> "Optional[State]":
        try:
            return cls(value.upper()) if value else None        
        except ValueError:
            return None


class Workmode(Enum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    POWER_OFF = "POWER_OFF"

    @classmethod
    def from_string(cls, value: str) -> "Optional[Workmode]":
        mapping = {
            "Manual": Workmode.MANUAL,
            "Auto": Workmode.AUTO,
            "PowerOff": Workmode.POWER_OFF
        }
        return mapping.get(value, None)


class FilterType(IntEnum):
    PARTICLE_FILTER_1 = 48
    PARTICLE_FILTER_2 = 49
    ODOR_FILTER = 192

    @classmethod
    def from_int(cls, value: int) -> "Optional[FilterType]":
        try:
            return cls(value) if value else None
        except ValueError:
            return None


@dataclass
class ReportedProperties:
    # Comfort 600
    appliance_state: Optional[ApplianceStateValue]
    temperature_representation: Optional[TemperatureRepresentation]
    sleep_mode: Optional[Toggle]
    target_temperature_c: Optional[float]
    ui_lock_mode: Optional[bool]
    mode: Optional[Mode]
    fan_speed_setting: Optional[FanSpeedSetting]
    vertical_swing: Optional[Toggle]        
    filter_state: Optional[State]
    ambient_temperature_c: Optional[float]

    # Air purifiers
    workmode: Optional[Workmode]
    fan_speed: Optional[int]
    filter_life_1: Optional[float]
    filter_type_1: Optional[FilterType]
    filter_life_2: Optional[float]
    filter_type_2: Optional[FilterType]

    # Well A7, Pure A9
    ionizer: Optional[bool]
    ui_light: Optional[bool]
    safety_lock: Optional[bool]
    pm_1: Optional[float]
    pm_2_5: Optional[float]
    pm_10: Optional[float]
    temperature: Optional[float]
    humidity: Optional[float]
    tvoc: Optional[float]

    # Well A7
    eco2: Optional[float]

    # Pure A9
    co2: Optional[float]

    # Extreme Home 500
    uv_state: Optional[Toggle]
    pm_2_5_approximate: Optional[float]


@dataclass
class Properties:
    reported: ReportedProperties


@dataclass
class ApplianceState:
    id: str
    connectionState: Optional[ConnectionState]
    status: Optional[Status]
    properties: Properties

