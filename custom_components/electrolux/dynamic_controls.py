from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import UnitOfTemperature

from .appliance import ApplianceData
from .dynamic_helpers import (
    OFF_VALUES,
    ON_VALUES,
    DynamicElectroluxEntity,
    _capability_value,
    _display_name,
    _is_on_value,
    _is_switch_capability,
    _known_switch_unique_id,
    _known_translation_key,
    _main_entity_consumed_paths,
    _safe_id,
)
from .hub import ElectroluxHub


def switch_entities(hub: ElectroluxHub) -> list[SwitchEntity]:
    entities: list[SwitchEntity] = []
    for appliance_data in hub.get_discovered_appliance_data():
        consumed = _main_entity_consumed_paths(appliance_data)
        for capability in appliance_data.info.capabilities.values():
            if capability.path in consumed or not capability.access.can_write:
                continue
            if _is_switch_capability(capability):
                entities.append(DynamicSwitch(hub, appliance_data, capability.path))
    return entities


def select_entities(hub: ElectroluxHub) -> list[SelectEntity]:
    entities: list[SelectEntity] = []
    for appliance_data in hub.get_discovered_appliance_data():
        consumed = _main_entity_consumed_paths(appliance_data)
        for capability in appliance_data.info.capabilities.values():
            if capability.path in consumed or not capability.access.can_write or _is_switch_capability(capability):
                continue
            if capability.type == "string" and capability.values:
                entities.append(DynamicSelect(hub, appliance_data, capability.path))
    return entities


def number_entities(hub: ElectroluxHub) -> list[NumberEntity]:
    entities: list[NumberEntity] = []
    for appliance_data in hub.get_discovered_appliance_data():
        consumed = _main_entity_consumed_paths(appliance_data)
        for capability in appliance_data.info.capabilities.values():
            if capability.path in consumed or not capability.access.can_write:
                continue
            if capability.is_numeric:
                entities.append(DynamicNumber(hub, appliance_data, capability.path))
    return entities


class DynamicSwitch(DynamicElectroluxEntity, SwitchEntity):
    def __init__(self, hub: ElectroluxHub, appliance_data: ApplianceData, capability_path: str) -> None:
        super().__init__(hub, appliance_data)
        self.capability_path = capability_path
        self.livestream_properties = frozenset({capability_path})
        self._attr_unique_id = _known_switch_unique_id(self.appliance.id, capability_path) or (
            f"electrolux_switch_{self.appliance.id}_{_safe_id(capability_path)}"
        )
        if translation_key := _known_translation_key(capability_path):
            self._attr_has_entity_name = True
            self._attr_translation_key = translation_key
        else:
            self._attr_name = f"{self.appliance.name} {_display_name(capability_path)}"
        self._update_attributes()

    @property
    def available(self) -> bool:
        capability = self.capability(self.capability_path)
        return super().available and capability is not None and capability.can_write

    def _update_attributes(self) -> None:
        value = self.state_value(self.capability_path)
        self._attr_is_on = bool(value) if isinstance(value, bool) else _is_on_value(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        capability = self.capability(self.capability_path)
        if capability is None:
            return
        value = True if capability.type == "boolean" else _capability_value(capability, ON_VALUES, "ON")
        if await self.send_capability(self.capability_path, value):
            self._update_attributes()
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        capability = self.capability(self.capability_path)
        if capability is None:
            return
        value = False if capability.type == "boolean" else _capability_value(capability, OFF_VALUES, "OFF")
        if await self.send_capability(self.capability_path, value):
            self._update_attributes()
            self.async_write_ha_state()


class DynamicSelect(DynamicElectroluxEntity, SelectEntity):
    def __init__(self, hub: ElectroluxHub, appliance_data: ApplianceData, capability_path: str) -> None:
        super().__init__(hub, appliance_data)
        self.capability_path = capability_path
        self.livestream_properties = frozenset({capability_path})
        self._attr_unique_id = f"electrolux_select_{self.appliance.id}_{_safe_id(capability_path)}"
        self._attr_name = f"{self.appliance.name} {_display_name(capability_path)}"
        self._update_attributes()

    @property
    def available(self) -> bool:
        capability = self.capability(self.capability_path)
        return super().available and capability is not None and capability.can_write

    def _update_attributes(self) -> None:
        capability = self.capability(self.capability_path)
        self._attr_options = list(capability.values) if capability else []
        self._attr_current_option = self.state_value(self.capability_path)

    async def async_select_option(self, option: str) -> None:
        if await self.send_capability(self.capability_path, option):
            self._update_attributes()
            self.async_write_ha_state()


class DynamicNumber(DynamicElectroluxEntity, NumberEntity):
    def __init__(self, hub: ElectroluxHub, appliance_data: ApplianceData, capability_path: str) -> None:
        super().__init__(hub, appliance_data)
        self.capability_path = capability_path
        self.livestream_properties = frozenset({capability_path})
        self._attr_unique_id = f"electrolux_number_{self.appliance.id}_{_safe_id(capability_path)}"
        self._attr_name = f"{self.appliance.name} {_display_name(capability_path)}"
        capability = self.capability(capability_path)
        if capability and capability.type == "temperature":
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._update_attributes()

    @property
    def available(self) -> bool:
        capability = self.capability(self.capability_path)
        return super().available and capability is not None and capability.can_write

    def _update_attributes(self) -> None:
        capability = self.capability(self.capability_path)
        if capability:
            if capability.min is not None:
                self._attr_native_min_value = capability.min
            if capability.max is not None:
                self._attr_native_max_value = capability.max
            if capability.step is not None:
                self._attr_native_step = capability.step
        self._attr_native_value = self.state_value(self.capability_path)

    async def async_set_native_value(self, value: float) -> None:
        if await self.send_capability(self.capability_path, value):
            self._update_attributes()
            self.async_write_ha_state()
