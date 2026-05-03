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
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
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
        if fan_capability is not None and fan_capability.can_write:
            self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
            self._attr_fan_modes = list(fan_capability.values)
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
        running = _is_running(self.state_value(self.state_path))
        mode = _hvac_mode_from_api(self.state_value(self.mode_path))
        self._attr_hvac_mode = mode if running and mode else (HVACMode.AUTO if running else HVACMode.OFF)
        self._attr_target_temperature = self.state_value(self.target_temperature_path)
        self._attr_current_temperature = self.state_value(self.current_temperature_path)
        self._attr_fan_mode = self.state_value(self.fan_mode_path)
        self._attr_swing_mode = _on_off_state(self.state_value(self.swing_path))

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
            self._update_attributes()
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._recompute_capability_controls()
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        if self.power_path and not _is_running(self.state_value(self.state_path)):
            await self.async_turn_on()
        if self.mode_path:
            value = _api_mode_from_hvac(self.capability(self.mode_path), hvac_mode)
            if await self.send_capability(self.mode_path, value):
                self._update_attributes()
                self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        self._recompute_capability_controls()
        if self.target_temperature_path is None or "temperature" not in kwargs:
            return
        if await self.send_capability(self.target_temperature_path, kwargs["temperature"]):
            self._update_attributes()
            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._recompute_capability_controls()
        if self.fan_mode_path and await self.send_capability(self.fan_mode_path, fan_mode):
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
