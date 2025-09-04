from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.entity import cached_property
import logging

from ...hub import ElectroluxHub
from ...appliance import Appliance
from ...capabilities import Capabilities
from ...appliance_state import ApplianceState, ConnectionState

_LOGGER = logging.getLogger(__name__)


class HumiditySensor(SensorEntity):
    def __init__(self, hub: ElectroluxHub, appliance: Appliance, capabilities: Capabilities, appliance_state: ApplianceState):
        self.hub = hub
        self.appliance = appliance
        self.capabilities = capabilities
        self.appliance_state = appliance_state

        self._attr_unique_id = f"electrolux_humidity_{appliance.id}"
        self._attr_name = f"{appliance.name} Humidity"
        
        self._attr_device_class = None
        self._attr_native_unit_of_measurement = PERCENTAGE
        
        self._attr_should_poll = False
        
        self._update_attributes()

    @property
    def appliance_id(self) -> str:
        return self.appliance.id

    def _update_attributes(self):
        reported = self.appliance_state.properties.reported
        self._attr_native_value = reported.humidity

    @cached_property
    def available(self) -> bool:
        return self.appliance_state.connectionState == ConnectionState.CONNECTED
