from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
import logging

from ...hub import ElectroluxHub
from ...appliance import Appliance
from ...capabilities import ApplianceInfo
from ...appliance_state import ApplianceState, ConnectionState
from ...entity import ElectroluxApplianceEntity

_LOGGER = logging.getLogger(__name__)


class CO2Sensor(ElectroluxApplianceEntity, SensorEntity):
    livestream_properties = frozenset({"ECO2", "CO2"})

    def __init__(self, hub: ElectroluxHub, appliance: Appliance, info: ApplianceInfo, appliance_state: ApplianceState):
        self.hub = hub
        self.appliance = appliance
        self.info = info
        self.capabilities = info.capabilities
        self.appliance_state = appliance_state

        self._attr_unique_id = f"electrolux_co2_{appliance.id}"
        self._attr_name = f"{appliance.name} CO2"
        
        self._attr_device_class = None
        self._attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
        
        self._attr_should_poll = False
        
        self._update_attributes()
    
    def _update_attributes(self):
        reported = self.appliance_state.properties.reported
        self._attr_native_value = reported.eco2
        
        co2_level = reported.eco2 if reported.eco2 else 400
        if co2_level > 1000:
            self._attr_extra_state_attributes = {"status": "high"}
        else:
            self._attr_extra_state_attributes = {"status": "normal"}

    @property
    def available(self) -> bool:
        return self.appliance_state.connectionState == ConnectionState.CONNECTED
