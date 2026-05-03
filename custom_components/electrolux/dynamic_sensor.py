from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory

from .appliance import ApplianceData
from .capabilities import Capability
from .dynamic_helpers import (
    DynamicElectroluxEntity,
    _display_name,
    _main_entity_consumed_paths,
    _safe_id,
)
from .hub import ElectroluxHub


def sensor_entities(hub: ElectroluxHub) -> list[SensorEntity]:
    entities: list[SensorEntity] = []
    for appliance_data in hub.get_discovered_appliance_data():
        consumed = _main_entity_consumed_paths(appliance_data)
        runtime_capabilities = appliance_data.info.runtime_capabilities(appliance_data.state.properties.reported.raw)
        added_paths: set[str] = set()
        added_sensor_ids: set[str] = set()
        for capability in runtime_capabilities.values():
            if capability.path in consumed or not capability.can_read or capability.can_write:
                continue
            metadata = _sensor_metadata(capability)
            diagnostic = metadata is None
            entities.append(DynamicSensor(hub, appliance_data, capability.path, metadata, diagnostic))
            added_paths.add(capability.path)
            added_sensor_ids.add(_sensor_unique_id(appliance_data.appliance.id, capability.path))
        for path in _reported_sensor_paths(appliance_data, runtime_capabilities, consumed | added_paths):
            sensor_id = _sensor_unique_id(appliance_data.appliance.id, path)
            if sensor_id in added_sensor_ids:
                continue
            metadata = _sensor_metadata_for_path(path)
            entities.append(DynamicSensor(hub, appliance_data, path, metadata, diagnostic=False))
            added_sensor_ids.add(sensor_id)
    return entities


class DynamicSensor(DynamicElectroluxEntity, SensorEntity):
    def __init__(
        self,
        hub: ElectroluxHub,
        appliance_data: ApplianceData,
        capability_path: str,
        metadata: dict[str, Any] | None,
        diagnostic: bool,
    ) -> None:
        super().__init__(hub, appliance_data)
        self.capability_path = capability_path
        self.livestream_properties = frozenset({capability_path})
        self._attr_unique_id = _known_sensor_unique_id(self.appliance.id, capability_path) or (
            f"electrolux_sensor_{self.appliance.id}_{_safe_id(capability_path)}"
        )
        if metadata and (translation_key := metadata.get("translation_key")):
            self._attr_has_entity_name = True
            self._attr_translation_key = translation_key
        else:
            self._attr_name = f"{self.appliance.name} {metadata['name'] if metadata else _display_name(capability_path)}"
        self._attr_entity_registry_enabled_default = not diagnostic
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if metadata:
            self._attr_device_class = metadata.get("device_class")
            self._attr_native_unit_of_measurement = metadata.get("unit")
        self._update_attributes()

    def _update_attributes(self) -> None:
        self._attr_native_value = self.state_value(self.capability_path)

    @property
    def available(self) -> bool:
        capability = self.capability(self.capability_path)
        if capability is not None:
            return super().available and capability.can_read
        return super().available and self.state_value(self.capability_path) is not None


def _sensor_metadata(capability: Capability) -> dict[str, Any] | None:
    return _sensor_metadata_for_path(capability.name)


def _sensor_metadata_for_path(path: str) -> dict[str, Any] | None:
    leaf = path.rsplit(".", 1)[-1]
    mapping = {
        "PM1": {"name": "PM1", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER},
        "PM2_5": {
            "name": "PM2.5",
            "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            "device_class": SensorDeviceClass.PM25,
        },
        "PM2_5_Approximate": {
            "name": "PM2.5 Approximate",
            "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
            "device_class": SensorDeviceClass.PM25,
        },
        "PM10": {"name": "PM10", "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER},
        "TVOC": {"name": "TVOC", "translation_key": "tvoc", "unit": CONCENTRATION_PARTS_PER_MILLION},
        "tvoc": {"name": "TVOC", "translation_key": "tvoc", "unit": CONCENTRATION_PARTS_PER_MILLION},
        "CO2": {"name": "CO2", "translation_key": "co2", "unit": CONCENTRATION_PARTS_PER_MILLION, "device_class": SensorDeviceClass.CO2},
        "co2": {"name": "CO2", "translation_key": "co2", "unit": CONCENTRATION_PARTS_PER_MILLION, "device_class": SensorDeviceClass.CO2},
        "ECO2": {"name": "ECO2", "translation_key": "eco2", "unit": CONCENTRATION_PARTS_PER_MILLION, "device_class": SensorDeviceClass.CO2},
        "eCO2": {"name": "ECO2", "translation_key": "eco2", "unit": CONCENTRATION_PARTS_PER_MILLION, "device_class": SensorDeviceClass.CO2},
        "eco2": {"name": "ECO2", "translation_key": "eco2", "unit": CONCENTRATION_PARTS_PER_MILLION, "device_class": SensorDeviceClass.CO2},
        "Humidity": {"name": "Humidity", "translation_key": "humidity", "unit": PERCENTAGE, "device_class": SensorDeviceClass.HUMIDITY},
        "humidity": {"name": "Humidity", "translation_key": "humidity", "unit": PERCENTAGE, "device_class": SensorDeviceClass.HUMIDITY},
        "relativeHumidity": {"name": "Humidity", "translation_key": "humidity", "unit": PERCENTAGE, "device_class": SensorDeviceClass.HUMIDITY},
        "Temp": {"name": "Temperature", "translation_key": "temperature", "unit": UnitOfTemperature.CELSIUS, "device_class": SensorDeviceClass.TEMPERATURE},
        "ambientTemperatureC": {"name": "Ambient Temperature", "translation_key": "temperature", "unit": UnitOfTemperature.CELSIUS, "device_class": SensorDeviceClass.TEMPERATURE},
        "temperature": {"name": "Temperature", "translation_key": "temperature", "unit": UnitOfTemperature.CELSIUS, "device_class": SensorDeviceClass.TEMPERATURE},
        "FilterLife_1": {"name": "Filter Life 1", "unit": PERCENTAGE},
        "FilterLife_2": {"name": "Filter Life 2", "unit": PERCENTAGE},
        "filterState": {"name": "Filter State"},
        "FilterState": {"name": "Filter State"},
    }
    return mapping.get(leaf)


def _known_sensor_unique_id(appliance_id: str, capability_path: str) -> str | None:
    mapping = {
        "CO2": "co2",
        "co2": "co2",
        "ECO2": "eco2",
        "eCO2": "eco2",
        "eco2": "eco2",
        "Humidity": "humidity",
        "humidity": "humidity",
        "relativeHumidity": "humidity",
        "PM1": "pm1",
        "PM2_5": "pm25",
        "PM10": "pm10",
        "Temp": "temperature",
        "ambientTemperatureC": "temperature",
        "temperature": "temperature",
        "TVOC": "tvoc",
        "tvoc": "tvoc",
    }
    suffix = mapping.get(capability_path.rsplit(".", 1)[-1])
    return f"electrolux_{suffix}_{appliance_id}" if suffix else None


def _sensor_unique_id(appliance_id: str, capability_path: str) -> str:
    return _known_sensor_unique_id(appliance_id, capability_path) or (
        f"electrolux_sensor_{appliance_id}_{_safe_id(capability_path)}"
    )


def _reported_sensor_paths(
    appliance_data: ApplianceData,
    runtime_capabilities: dict[str, Capability],
    consumed: set[str],
) -> list[str]:
    reported = appliance_data.state.properties.reported.raw
    paths: list[str] = []
    for path, value in _flatten_reported_paths(reported):
        if path in consumed or path in runtime_capabilities or value is None:
            continue
        if _sensor_metadata_for_path(path) is not None:
            paths.append(path)
    return paths


def _flatten_reported_paths(value: Any, parent_path: str | None = None) -> list[tuple[str, Any]]:
    if not isinstance(value, dict):
        return []
    paths: list[tuple[str, Any]] = []
    for key, child in value.items():
        if not isinstance(key, str):
            continue
        path = f"{parent_path}.{key}" if parent_path else key
        if isinstance(child, dict):
            paths.extend(_flatten_reported_paths(child, path))
        elif not isinstance(child, list):
            paths.append((path, child))
    return paths
