from __future__ import annotations

from typing import Any

from homeassistant.components.climate import HVACMode
from .appliance import ApplianceData
from .appliance_state import ConnectionState
from .capabilities import Capability, DeviceType
from .entity import ElectroluxApplianceEntity
from .hub import ElectroluxHub


CLIMATE_DEVICE_TYPES = {DeviceType.PORTABLE_AIR_CONDITIONER.value, "AC", "DAM_AC"}
FAN_DEVICE_TYPES = {DeviceType.AIR_PURIFIER.value, "AIR_PURIFIER", "AP", "DAM_AP"}

ON_VALUES = ("ON", "On", "on", "TRUE", "true", "ENABLED", "enabled")
OFF_VALUES = ("OFF", "Off", "off", "FALSE", "false", "DISABLED", "disabled")


class DynamicElectroluxEntity(ElectroluxApplianceEntity):
    def __init__(self, hub: ElectroluxHub, appliance_data: ApplianceData) -> None:
        self.hub = hub
        self.appliance_data = appliance_data
        self.appliance = appliance_data.appliance
        self.info = appliance_data.info
        self.appliance_state = appliance_data.state
        self._attr_should_poll = False

    @property
    def available(self) -> bool:
        return self.appliance_state.connectionState == ConnectionState.CONNECTED

    def capability(self, path: str | None) -> Capability | None:
        if path is None:
            return None
        return self.info.runtime_capabilities(self.appliance_state.properties.reported.raw).get(path)

    def state_value(self, path: str | None, default: Any = None) -> Any:
        if path is None:
            return default
        return self.appliance_state.get_reported(path, default)

    async def send_capability(self, path: str, value: Any) -> bool:
        success = await self.hub.send_capability_command(self.appliance.id, path, value)
        if success:
            self.appliance_state.set_reported(path, value)
        return success


def _main_entity_consumed_paths(appliance_data: ApplianceData) -> set[str]:
    runtime_capabilities = appliance_data.info.runtime_capabilities(appliance_data.state.properties.reported.raw)
    device_type = _device_type(appliance_data)
    if device_type in CLIMATE_DEVICE_TYPES:
        return {
            path
            for path in (
                _find_capability_path(appliance_data.info, runtime_capabilities, "executeCommand"),
                _find_capability_path(appliance_data.info, runtime_capabilities, "applianceState"),
                _find_capability_path(appliance_data.info, runtime_capabilities, "mode"),
                _find_capability_path(appliance_data.info, runtime_capabilities, "targetTemperatureC", "targetTemperature"),
                _find_capability_path(appliance_data.info, runtime_capabilities, "ambientTemperatureC", "Temp", "temperature"),
                _find_capability_path(appliance_data.info, runtime_capabilities, "fanSpeedSetting", "fanMode"),
                _find_capability_path(appliance_data.info, runtime_capabilities, "verticalSwing"),
            )
            if path is not None
        }
    if device_type in FAN_DEVICE_TYPES:
        return {
            path
            for path in (
                _find_capability_path(appliance_data.info, runtime_capabilities, "Workmode", "workmode"),
                _find_capability_path(appliance_data.info, runtime_capabilities, "Fanspeed", "fanSpeed"),
            )
            if path is not None
        }
    return set()


def _is_climate_appliance(appliance_data: ApplianceData) -> bool:
    return _device_type(appliance_data) in CLIMATE_DEVICE_TYPES


def _is_fan_appliance(appliance_data: ApplianceData) -> bool:
    return _device_type(appliance_data) in FAN_DEVICE_TYPES


def _device_type(appliance_data: ApplianceData) -> str:
    return appliance_data.info.appliance_info.device_type or appliance_data.appliance.type


def _find_capability_path(
    info: Any,
    runtime_capabilities: dict[str, Capability],
    *names: str,
) -> str | None:
    capability = info.find_capability(*names, runtime_capabilities=runtime_capabilities)
    return capability.path if capability else None


def _known_switch_unique_id(appliance_id: str, capability_path: str) -> str | None:
    mapping = {
        "Ionizer": "ionizer",
    }
    suffix = mapping.get(capability_path.rsplit(".", 1)[-1])
    return f"electrolux_{suffix}_{appliance_id}" if suffix else None


def _known_translation_key(capability_path: str) -> str | None:
    mapping = {
        "Ionizer": "ionizer",
        "SafetyLock": "safety_lock",
        "UILight": "ui_light",
    }
    return mapping.get(capability_path.rsplit(".", 1)[-1])


def _is_switch_capability(capability: Capability) -> bool:
    if capability.type == "boolean":
        return True
    normalized_values = {_normalize_value(value) for value in capability.values}
    return bool(normalized_values) and normalized_values <= {
        "ON",
        "OFF",
        "TRUE",
        "FALSE",
        "ENABLED",
        "DISABLED",
    }


def _is_running(value: Any) -> bool:
    return _normalize_value(value) in {"RUNNING", "ON", "TRUE", "ENABLED"}


def _is_on_value(value: Any) -> bool:
    return _normalize_value(value) in {"ON", "TRUE", "ENABLED"}


def _is_off_value(value: Any) -> bool:
    return value is None or _normalize_value(value) in {"OFF", "FALSE", "DISABLED", "POWEROFF", "POWER_OFF"}


def _hvac_mode_from_api(value: Any) -> HVACMode | None:
    mapping = {
        "AUTO": HVACMode.AUTO,
        "COOL": HVACMode.COOL,
        "HEAT": HVACMode.HEAT,
        "DRY": HVACMode.DRY,
        "FANONLY": HVACMode.FAN_ONLY,
        "FAN_ONLY": HVACMode.FAN_ONLY,
        "OFF": HVACMode.OFF,
    }
    return mapping.get(_normalize_value(value))


def _api_mode_from_hvac(capability: Capability | None, hvac_mode: HVACMode) -> str:
    preferred = {
        HVACMode.AUTO: ("AUTO", "auto"),
        HVACMode.COOL: ("COOL", "cool"),
        HVACMode.HEAT: ("HEAT", "heat"),
        HVACMode.DRY: ("DRY", "dry"),
        HVACMode.FAN_ONLY: ("FANONLY", "fanOnly", "fan_only"),
    }.get(hvac_mode, ("AUTO",))
    return _capability_value(capability, preferred, preferred[0])


def _capability_value(capability: Capability | None, candidates: tuple[str, ...], fallback: str) -> str:
    if capability:
        normalized_candidates = {_normalize_value(candidate) for candidate in candidates}
        for value in capability.values:
            if _normalize_value(value) in normalized_candidates:
                return value
    return fallback


def _on_off_options(capability: Capability) -> list[str]:
    if capability.values:
        return ["on" if _normalize_value(value) in {"ON", "TRUE", "ENABLED"} else "off" for value in capability.values]
    return ["off", "on"]


def _on_off_state(value: Any) -> str | None:
    if value is None:
        return None
    return "on" if _is_on_value(value) else "off"


def _percentage_from_speed(value: int, max_value: int) -> int:
    if max_value <= 0:
        return 0
    percentage = round((value / max_value) * 100)
    return max(1, percentage) if value > 0 else 0


def _safe_id(path: str) -> str:
    return path.replace(".", "_").replace("-", "_").lower()


def _display_name(path: str) -> str:
    leaf = path.rsplit(".", 1)[-1]
    label = ""
    for char in leaf.replace("_", " "):
        if label and char.isupper() and label[-1].islower():
            label += " "
        label += char
    return label.title()


def _normalize_value(value: Any) -> str:
    return str(value).strip().replace("_", "").replace(" ", "").upper()
