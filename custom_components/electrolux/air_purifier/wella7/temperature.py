from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTemperature
import logging

from ...hub import ElectroluxHub
from ...appliance import Appliance
from ...capabilities import ApplianceInfo
from ...appliance_state import ApplianceState, ConnectionState
from ...entity import ElectroluxApplianceEntity

_LOGGER = logging.getLogger(__name__)


class TemperatureSensor(ElectroluxApplianceEntity, SensorEntity):
    livestream_properties = frozenset({"Temp"})

    def __init__(self, hub: ElectroluxHub, appliance: Appliance, info: ApplianceInfo, appliance_state: ApplianceState):
        self.hub = hub
        self.appliance = appliance
        self.info = info
        self.capabilities = info.capabilities
        self.appliance_state = appliance_state

        self._attr_unique_id = f"electrolux_temperature_{appliance.id}"
        self._attr_name = f"{appliance.name} Temperature"
        
        self._attr_device_class = None
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        
        self._attr_should_poll = False
        
        self._update_attributes()

    def _update_attributes(self):
        reported = self.appliance_state.properties.reported
        self._attr_native_value = reported.temperature

    @property
    def available(self) -> bool:
        return self.appliance_state.connectionState == ConnectionState.CONNECTED
