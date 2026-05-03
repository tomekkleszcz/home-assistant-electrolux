from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature

from .appliance import ApplianceData
from .capabilities import set_state_value
from .dynamic_helpers import (
    OFF_VALUES,
    DynamicElectroluxEntity,
    _capability_value,
    _find_capability_path,
    _is_fan_appliance,
    _is_off_value,
    _is_on_value,
    _percentage_from_speed,
)
from .hub import ElectroluxHub


def fan_entities(hub: ElectroluxHub) -> list[FanEntity]:
    return [
        entity
        for appliance_data in hub.get_discovered_appliance_data()
        if _is_fan_appliance(appliance_data)
        for entity in [DynamicFan(hub, appliance_data)]
        if entity.is_supported
    ]


class DynamicFan(DynamicElectroluxEntity, FanEntity):
    def __init__(self, hub: ElectroluxHub, appliance_data: ApplianceData) -> None:
        super().__init__(hub, appliance_data)
        self._attr_unique_id = f"electrolux_fan_{self.appliance.id}"
        self._attr_name = self.appliance.name

        runtime_capabilities = self.info.runtime_capabilities(self.appliance_state.properties.reported.raw)
        self.workmode_path = _find_capability_path(self.info, runtime_capabilities, "Workmode", "workmode")
        self.fan_speed_path = _find_capability_path(self.info, runtime_capabilities, "Fanspeed", "fanSpeed")
        self.safety_lock_path = _find_capability_path(self.info, runtime_capabilities, "SafetyLock", "safetyLock")
        self.consumed_paths = {
            path
            for path in (self.workmode_path, self.fan_speed_path)
            if path is not None
        }
        self.livestream_properties = frozenset(self.consumed_paths)
        self.is_supported = self.workmode_path is not None or self.fan_speed_path is not None

        self._update_supported_features()
        self._last_active_mode = self._first_active_mode()
        self._update_attributes()

    def _first_active_mode(self) -> str:
        capability = self.capability(self.workmode_path)
        if capability:
            for value in capability.values:
                if not _is_off_value(value):
                    return value
        return "Auto"

    def _update_attributes(self) -> None:
        self._update_supported_features()
        workmode = self.state_value(self.workmode_path)
        if workmode and not _is_off_value(workmode):
            self._last_active_mode = workmode
        self._attr_preset_mode = self._last_active_mode if self.workmode_path else None
        speed_value = self.state_value(self.fan_speed_path)
        speed_capability = self.capability(self.fan_speed_path)
        if speed_value is None or speed_capability is None or speed_capability.disabled:
            self._attr_percentage = None
        else:
            min_speed = int(speed_capability.min or 0)
            max_speed = int(speed_capability.max or 100)
            speed_value = int(speed_value)
            if speed_value > 0 and min_speed > 0:
                speed_value = max(speed_value, min_speed)
            self._attr_speed_count = max_speed
            self._attr_percentage = _percentage_from_speed(speed_value, max_speed)

    def _update_supported_features(self) -> None:
        speed_capability = self.capability(self.fan_speed_path)
        workmode_capability = self.capability(self.workmode_path)
        can_speed_write = speed_capability is not None and speed_capability.can_write
        can_workmode_write = workmode_capability is not None and workmode_capability.can_write

        supported_features = FanEntityFeature(0)
        if can_speed_write or can_workmode_write:
            supported_features |= FanEntityFeature.TURN_ON
        if can_workmode_write or (can_speed_write and self._fan_speed_off_value() is not None):
            supported_features |= FanEntityFeature.TURN_OFF

        if speed_capability is not None:
            self._attr_speed_count = int(speed_capability.max or 100)
            if can_speed_write:
                supported_features |= FanEntityFeature.SET_SPEED

        if can_workmode_write and workmode_capability.values:
            supported_features |= FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = [
                value for value in workmode_capability.values if not _is_off_value(value)
            ]
        else:
            self._attr_preset_modes = None

        self._attr_supported_features = supported_features

    @property
    def percentage(self) -> int | None:
        return self._attr_percentage

    @property
    def speed_count(self) -> int:
        return self._attr_speed_count

    @property
    def supported_features(self) -> FanEntityFeature:
        return self._attr_supported_features

    @property
    def preset_mode(self) -> str | None:
        return self._attr_preset_mode

    @property
    def preset_modes(self) -> list[str] | None:
        return self._attr_preset_modes

    @property
    def is_on(self) -> bool:
        if not self.available:
            return False
        if self.workmode_path is not None:
            workmode = self.state_value(self.workmode_path)
            return not _is_off_value(workmode)
        return self._current_fan_speed() > 0

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        success = True
        sent_command = False
        workmode_capability = self.capability(self.workmode_path)
        speed_capability = self.capability(self.fan_speed_path)
        can_workmode_write = workmode_capability is not None and workmode_capability.can_write
        can_speed_write = speed_capability is not None and speed_capability.can_write
        if percentage is None and not can_workmode_write and can_speed_write:
            percentage = self._attr_percentage or 100
        if self.workmode_path and can_workmode_write:
            workmode = self._workmode_for_speed(preset_mode) if percentage is not None else preset_mode or self._last_active_mode
            success = await self.send_capability(self.workmode_path, workmode)
            sent_command = True
        if success and percentage is not None and self.fan_speed_path and can_speed_write:
            success = await self.send_capability(self.fan_speed_path, self._fan_speed_from_percentage(percentage))
            sent_command = True
        if success and sent_command:
            self._update_attributes()
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        workmode_capability = self.capability(self.workmode_path)
        if self.workmode_path is None or workmode_capability is None or not workmode_capability.can_write:
            if self.fan_speed_path is None:
                return
            speed_capability = self.capability(self.fan_speed_path)
            if speed_capability is None or not speed_capability.can_write:
                return
            off_value = self._fan_speed_off_value()
            if off_value is None:
                return
            if await self.send_capability(self.fan_speed_path, off_value):
                self._update_attributes()
                self.async_write_ha_state()
            return
        current = self.state_value(self.workmode_path)
        if current and not _is_off_value(current):
            self._last_active_mode = current
        value = _capability_value(workmode_capability, (*OFF_VALUES, "PowerOff", "POWER_OFF"), "PowerOff")
        if await self.send_capability(self.workmode_path, value):
            await self._async_turn_off_safety_lock()
            self._update_attributes()
            self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        speed_capability = self.capability(self.fan_speed_path)
        if self.fan_speed_path is None or speed_capability is None or not speed_capability.can_write:
            self._update_attributes()
            self.async_write_ha_state()
            return
        if percentage <= 0:
            await self.async_turn_off()
            return
        if await self.send_capability(self.fan_speed_path, self._fan_speed_from_percentage(percentage)):
            self._update_attributes()
            self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if self.workmode_path and await self.send_capability(self.workmode_path, preset_mode):
            self._last_active_mode = preset_mode
            self._update_attributes()
            self.async_write_ha_state()

    def _current_fan_speed(self) -> int:
        value = self.state_value(self.fan_speed_path, 0)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _fan_speed_off_value(self) -> int | None:
        capability = self.capability(self.fan_speed_path)
        if capability is None:
            return 0
        min_speed = int(capability.min or 0)
        return min_speed if min_speed <= 0 else None

    def _fan_speed_from_percentage(self, percentage: int) -> int:
        capability = self.capability(self.fan_speed_path)
        if capability is None:
            return percentage
        min_speed = int(capability.min or 0)
        max_speed = int(capability.max or 100)
        step = max(int(capability.step or 1), 1)
        min_percentage = _percentage_from_speed(min_speed, max_speed) if min_speed > 0 else 0
        percentage = max(percentage, min_percentage)
        computed = round(max_speed * (percentage / 100))
        max_steps = max((max_speed - min_speed) // step, 0)
        snapped_steps = int(((computed - min_speed) / step) + 0.5)
        snapped_steps = min(max(snapped_steps, 0), max_steps)
        return min_speed + (snapped_steps * step)

    def _workmode_for_speed(self, preset_mode: str | None) -> str:
        for value in (preset_mode, self._last_active_mode, *self._writable_workmode_values()):
            if value and self._fan_speed_can_write_for_workmode(value):
                return value
        return preset_mode or self._last_active_mode

    def _writable_workmode_values(self) -> tuple[str, ...]:
        capability = self.capability(self.workmode_path)
        if capability is None:
            return ()
        return tuple(value for value in capability.values if not _is_off_value(value))

    def _fan_speed_can_write_for_workmode(self, workmode: str) -> bool:
        if self.workmode_path is None or self.fan_speed_path is None:
            return False
        reported = deepcopy(self.appliance_state.properties.reported.raw)
        set_state_value(reported, self.workmode_path, workmode)
        capability = self.info.runtime_capabilities(reported).get(self.fan_speed_path)
        return capability is not None and capability.can_write

    async def _async_turn_off_safety_lock(self) -> None:
        if not self.safety_lock_path or not _is_on_value(self.state_value(self.safety_lock_path)):
            return

        capability = self.capability(self.safety_lock_path)
        if capability is None or not capability.can_write:
            return

        value: bool | str = False if capability.type == "boolean" else _capability_value(capability, OFF_VALUES, "OFF")
        if await self.send_capability(self.safety_lock_path, value):
            await self.hub._update_entities_for_appliance(
                self.appliance.id,
                self.appliance_state,
                call_async_update=False,
                changed_property=self.safety_lock_path,
            )
