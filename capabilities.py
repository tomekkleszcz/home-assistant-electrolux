from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Union

from dataclasses import asdict


class DeviceType(Enum):
    PORTABLE_AIR_CONDITIONER = "PORTABLE_AIR_CONDITIONER"
    AIR_PURIFIER = "AIR_PURIFIER"

    @classmethod
    def from_string(cls, value: str) -> "DeviceType":
        return DeviceType[value.upper()]

@dataclass
class ApplianceInfoValue:
    serial_number: str
    pnc: str
    brand: str
    device_type: DeviceType
    model: str
    variant: str
    color: str

class Access(Enum):
    READ = "READ"
    WRITE = "WRITE"
    READ_WRITE = "READ_WRITE"

    @classmethod
    def from_string(cls, value: str) -> "Access":
        match value:
            case "read":
                return Access.READ
            case "write":
                return Access.WRITE
            case _:
                return Access.READ

@dataclass
class StringCapability:
    access: Access
    values: list[str]

@dataclass
class IntegerCapability:
    access: Access
    max: Optional[int]
    min: Optional[int]
    step: int

@dataclass
class TemperatureCapability:
    access: Access
    max: float
    min: float
    step: float

Capability = Union[StringCapability, IntegerCapability, TemperatureCapability]

Capabilities = Dict[str, Capability]

@dataclass
class ApplianceInfo:
    appliance_info: ApplianceInfoValue
    capabilities: Capabilities

def capabilities_from_json(json: Any) -> ApplianceInfo:
    json_capabilities = json["capabilities"]
    capabilities: Dict[str, Capability] = {}

    for name, json_capability in json_capabilities.items():
        if name == "networkInterface":
            continue

        match json_capability["type"]:
            case "string":
                values: list[str] = []
                for value in json_capability["values"].items():
                    values.append(value)

                capabilities[name] = StringCapability(
                    access = Access.from_string(json_capability["access"]),
                    values = values
                )
            case "int":
                capabilities[name] = IntegerCapability(
                    access = Access.from_string(json_capability["access"]),
                    max = json_capability["max"] if "max" in json_capability else None,
                    min = json_capability["min"] if "min" in json_capability else None,
                    step = json_capability["step"]
                )
            case "temperature":
                capabilities[name] = TemperatureCapability(
                    access = Access.from_string(json_capability["access"]),
                    max = json_capability["max"],
                    min = json_capability["min"],
                    step = json_capability["step"]
                )

    appliance_info = ApplianceInfo(
        appliance_info = ApplianceInfoValue(
            serial_number = json["applianceInfo"]["serialNumber"],
            pnc = json["applianceInfo"]["pnc"],
            brand = json["applianceInfo"]["brand"],
            device_type = DeviceType.from_string(json["applianceInfo"]["deviceType"]),
            model = json["applianceInfo"]["model"],
            variant = json["applianceInfo"]["variant"],
            color = json["applianceInfo"]["colour"]
        ),
        capabilities = capabilities
    )

    return appliance_info