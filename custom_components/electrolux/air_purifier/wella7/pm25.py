from __future__ import annotations
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
import logging

from ...hub import ElectroluxHub
from ...appliance import Appliance
from ...capabilities import ApplianceInfo
from ...appliance_state import ApplianceState, ConnectionState
from ...entity import ElectroluxApplianceEntity

_LOGGER = logging.getLogger(__name__)


class PM25Sensor(ElectroluxApplianceEntity, SensorEntity):
    livestream_properties = frozenset({"PM2_5", "PM2_5_Approximate"})

    def __init__(self, hub: ElectroluxHub, appliance: Appliance, info: ApplianceInfo, appliance_state: ApplianceState):
        self.hub = hub
        self.appliance = appliance
        self.info = info
        self.capabilities = info.capabilities
        self.appliance_state = appliance_state

        self._attr_unique_id = f"electrolux_pm25_{appliance.id}"
        self._attr_name = f"{appliance.name} PM2.5"
        
        self._attr_device_class = SensorDeviceClass.PM25
        self._attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
        
        self._attr_should_poll = False
        
        self._update_attributes()

    def _update_attributes(self):
        reported = self.appliance_state.properties.reported
        self._attr_native_value = reported.pm_2_5

    @property
    def available(self) -> bool:
        return self.appliance_state.connectionState == ConnectionState.CONNECTED
