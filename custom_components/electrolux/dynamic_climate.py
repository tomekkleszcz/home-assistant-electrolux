from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature

from .appliance import ApplianceData
from .capabilities import Capability
from .dynamic_helpers import (
    OFF_VALUES,
    ON_VALUES,
    DynamicElectroluxEntity,
    _api_mode_from_hvac,
    _capability_value,
    _find_capability_path,
    _hvac_mode_from_api,
    _is_climate_appliance,
    _is_running,
    _on_off_options,
    _on_off_state,
)
from .hub import ElectroluxHub


FAN_MODE_STATE_KEYS = {
    "AUTO": "auto",
    "LOW": "low",
    "MIDDLE": "middle",
    "HIGH": "high",
}


def climate_entities(hub: ElectroluxHub) -> list[ClimateEntity]:
    return [
        entity
        for appliance_data in hub.get_discovered_appliance_data()
        if _is_climate_appliance(appliance_data)
        for entity in [DynamicClimate(hub, appliance_data)]
        if entity.is_supported
    ]


class DynamicClimate(DynamicElectroluxEntity, ClimateEntity):
    def __init__(self, hub: ElectroluxHub, appliance_data: ApplianceData) -> None:
        super().__init__(hub, appliance_data)
        self._attr_unique_id = f"electrolux_climate_{self.appliance.id}"
        self._attr_name = self.appliance.name
        self._attr_translation_key = "climate"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._last_writable_fan_mode: str | None = None
        self._prefer_last_writable_fan_mode = False
        self._update_attributes()

    def _recompute_capability_controls(self) -> None:
        runtime_capabilities = self.info.runtime_capabilities(self.appliance_state.properties.reported.raw)
        self.power_path = _find_capability_path(self.info, runtime_capabilities, "executeCommand")
        self.state_path = _find_capability_path(self.info, runtime_capabilities, "applianceState")
        self.mode_path = _find_capability_path(self.info, runtime_capabilities, "mode")
        self.target_temperature_path = _find_capability_path(
            self.info,
            runtime_capabilities,
            "targetTemperatureC",
            "targetTemperature",
        )
        self.current_temperature_path = _find_capability_path(
            self.info,
            runtime_capabilities,
            "ambientTemperatureC",
            "Temp",
            "temperature",
        )
        self.fan_mode_path = _find_capability_path(self.info, runtime_capabilities, "fanSpeedSetting", "fanMode")
        self.fan_speed_state_path = _find_capability_path(self.info, runtime_capabilities, "fanSpeedState")
        self.swing_path = _find_capability_path(self.info, runtime_capabilities, "verticalSwing")

        self.consumed_paths = {
            path
            for path in (
                self.power_path,
                self.state_path,
                self.mode_path,
                self.target_temperature_path,
                self.current_temperature_path,
                self.fan_mode_path,
                self.fan_speed_state_path,
                self.swing_path,
            )
            if path is not None
        }
        self.livestream_properties = frozenset(self.consumed_paths)
        self.is_supported = self.target_temperature_path is not None or self.mode_path is not None or self.power_path is not None

        self._attr_supported_features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        target_capability = runtime_capabilities.get(self.target_temperature_path) if self.target_temperature_path else None
        if target_capability is not None:
            if target_capability.can_write:
                self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
            self._set_or_clear_attr("_attr_min_temp", target_capability.min)
            self._set_or_clear_attr("_attr_max_temp", target_capability.max)
            self._set_or_clear_attr("_attr_target_temperature_step", target_capability.step)
        else:
            self._set_or_clear_attr("_attr_min_temp", None)
            self._set_or_clear_attr("_attr_max_temp", None)
            self._set_or_clear_attr("_attr_target_temperature_step", None)

        fan_capability = runtime_capabilities.get(self.fan_mode_path) if self.fan_mode_path else None
        if fan_capability is not None and fan_capability.can_read and fan_capability.values:
            self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
            if fan_capability.can_write:
                self._attr_fan_modes = [_fan_mode_state_key(value) for value in fan_capability.values]
            else:
                fan_mode = self._fan_mode_from_state(fan_capability)
                self._attr_fan_modes = [fan_mode] if fan_mode else [_fan_mode_state_key(fan_capability.values[0])]
        else:
            self._attr_fan_modes = None

        swing_capability = runtime_capabilities.get(self.swing_path) if self.swing_path else None
        if swing_capability is not None and swing_capability.can_write:
            self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
            self._attr_swing_modes = _on_off_options(swing_capability)
        else:
            self._attr_swing_modes = None

        self._attr_hvac_modes = self._hvac_modes(runtime_capabilities)

    def _set_or_clear_attr(self, attr: str, value: Any) -> None:
        if value is None:
            if hasattr(self, attr):
                delattr(self, attr)
            return
        setattr(self, attr, value)

    def _hvac_modes(self, runtime_capabilities: dict[str, Capability]) -> list[HVACMode]:
        modes = [HVACMode.OFF]
        if self.mode_path is None:
            modes.append(HVACMode.AUTO)
            return modes
        for value in runtime_capabilities[self.mode_path].values:
            hvac_mode = _hvac_mode_from_api(value)
            if hvac_mode and hvac_mode not in modes:
                modes.append(hvac_mode)
        if len(modes) == 1:
            modes.append(HVACMode.AUTO)
        return modes

    def _update_attributes(self) -> None:
        self._recompute_capability_controls()
        mode = _hvac_mode_from_api(self.state_value(self.mode_path))
        running = (
            _is_running(self.state_value(self.state_path))
            if self.state_path is not None
            else mode not in (None, HVACMode.OFF)
        )
        self._attr_hvac_mode = mode if running and mode else (HVACMode.AUTO if running else HVACMode.OFF)
        self._attr_target_temperature = self.state_value(self.target_temperature_path)
        self._attr_current_temperature = self.state_value(self.current_temperature_path)
        self._remember_writable_fan_mode()
        self._attr_fan_mode = self._fan_mode_from_state()
        self._attr_swing_mode = _on_off_state(self.state_value(self.swing_path))
        if self._attr_hvac_mode == HVACMode.OFF:
            self._clear_off_controls()

    def _clear_off_controls(self) -> None:
        self._attr_supported_features &= ~(
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE
        )
        self._attr_fan_modes = None
        self._attr_swing_modes = None
        self._attr_target_temperature = None
        self._attr_fan_mode = None
        self._attr_swing_mode = None

    def _set_local_running_state(self, running: bool) -> None:
        if self.state_path is not None:
            self.appliance_state.set_reported(self.state_path, "RUNNING" if running else "OFF")

    def _fan_mode_from_state(self, capability: Capability | None = None) -> str | None:
        capability = capability or self.capability(self.fan_mode_path)
        if capability is None:
            value = self.state_value(self.fan_mode_path)
            return _fan_mode_state_key(str(value)) if value is not None else None

        if (
            capability.can_write
            and self._prefer_last_writable_fan_mode
            and _fan_mode_capability_value(capability, self._last_writable_fan_mode) is not None
        ):
            return self._last_writable_fan_mode

        paths = (
            (self.fan_mode_path, self.fan_speed_state_path)
            if capability.can_write
            else (self.fan_speed_state_path, self.fan_mode_path)
        )
        for path in paths:
            capability_value = _fan_mode_capability_value(capability, self.state_value(path))
            if capability_value is not None:
                return _fan_mode_state_key(capability_value)

        if capability.values:
            return _fan_mode_state_key(capability.values[0])

        return None

    def _remember_writable_fan_mode(self) -> None:
        if self._prefer_last_writable_fan_mode:
            return

        capability = self.capability(self.fan_mode_path)
        if capability is None or not capability.can_write:
            return

        capability_value = _fan_mode_capability_value(capability, self.state_value(self.fan_mode_path))
        if capability_value is not None:
            self._last_writable_fan_mode = _fan_mode_state_key(capability_value)

    def _handle_appliance_state_update(self, changed_property: str | None) -> None:
        if changed_property is None or changed_property == self.fan_mode_path:
            self._prefer_last_writable_fan_mode = False

    async def async_turn_on(self) -> None:
        self._recompute_capability_controls()
        if self.power_path:
            value = _capability_value(self.capability(self.power_path), ON_VALUES, "ON")
            success = await self.send_capability(self.power_path, value)
        elif self.state_path:
            success = await self.send_capability(self.state_path, "RUNNING")
        else:
            success = False
        if success:
            self._set_local_running_state(True)
            self._update_attributes()
            self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        self._recompute_capability_controls()
        if self.power_path:
            value = _capability_value(self.capability(self.power_path), OFF_VALUES, "OFF")
            success = await self.send_capability(self.power_path, value)
        elif self.state_path:
            success = await self.send_capability(self.state_path, "OFF")
        else:
            success = False
        if success:
            self._set_local_running_state(False)
            self._update_attributes()
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._recompute_capability_controls()
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        previous_fan_capability = self.capability(self.fan_mode_path)
        previous_fan_writable = bool(previous_fan_capability and previous_fan_capability.can_write)
        previous_writable_fan_mode = self._last_writable_fan_mode
        if not _is_running(self.state_value(self.state_path)):
            await self.async_turn_on()
            self._recompute_capability_controls()
        if self.mode_path:
            value = _api_mode_from_hvac(self.capability(self.mode_path), hvac_mode)
            if await self.send_capability(self.mode_path, value):
                self._recompute_capability_controls()
                await self._align_fan_mode_after_hvac_mode_change(
                    previous_fan_writable,
                    previous_writable_fan_mode,
                )
                self._update_attributes()
                self.async_write_ha_state()

    async def _align_fan_mode_after_hvac_mode_change(
        self,
        previous_fan_writable: bool,
        previous_writable_fan_mode: str | None,
    ) -> None:
        capability = self.capability(self.fan_mode_path)
        if self.fan_mode_path is None or capability is None or not capability.can_write or not capability.values:
            return

        current_value = _fan_mode_capability_value(capability, self.state_value(self.fan_mode_path))
        if current_value is None:
            value = capability.values[0]
            if await self.send_capability(self.fan_mode_path, value):
                self._last_writable_fan_mode = _fan_mode_state_key(value)
                self._prefer_last_writable_fan_mode = False
            return

        if (
            previous_writable_fan_mode
            and not previous_fan_writable
            and _fan_mode_capability_value(capability, previous_writable_fan_mode) is not None
        ):
            self._prefer_last_writable_fan_mode = True

    async def async_set_temperature(self, **kwargs: Any) -> None:
        self._recompute_capability_controls()
        if self.target_temperature_path is None or "temperature" not in kwargs:
            return
        if await self.send_capability(self.target_temperature_path, kwargs["temperature"]):
            self._update_attributes()
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._recompute_capability_controls()
        capability = self.capability(self.fan_mode_path)
        if self.fan_mode_path is None or capability is None or not capability.can_write:
            return
        value = _capability_value(capability, (fan_mode,), fan_mode)
        if await self.send_capability(self.fan_mode_path, value):
            self._last_writable_fan_mode = _fan_mode_state_key(value)
            self._prefer_last_writable_fan_mode = False
            self._update_attributes()
            self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        self._recompute_capability_controls()
        if self.swing_path is None:
            return
        value = _capability_value(self.capability(self.swing_path), ON_VALUES if swing_mode == "on" else OFF_VALUES, swing_mode)
        if await self.send_capability(self.swing_path, value):
            self._update_attributes()
            self.async_write_ha_state()


def _fan_mode_state_key(value: str) -> str:
    return FAN_MODE_STATE_KEYS.get(value.upper(), value)


def _fan_mode_capability_value(capability: Capability, value: Any) -> str | None:
    if value is None:
        return None

    normalized_value = str(value).strip().replace("_", "").replace(" ", "").upper()
    for capability_value in capability.values:
        if capability_value.strip().replace("_", "").replace(" ", "").upper() == normalized_value:
            return capability_value
    return None
