from __future__ import annotations
from typing import Any
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import cached_property
import logging

from ...hub import ElectroluxHub
from ...appliance import Appliance
from ...capabilities import Capabilities
from ...appliance_state import ApplianceState, ConnectionState

_LOGGER = logging.getLogger(__name__)


class IonizerSwitch(SwitchEntity):
    def __init__(self, hub: ElectroluxHub, appliance: Appliance, capabilities: Capabilities, appliance_state: ApplianceState):
        self.hub = hub
        self.appliance = appliance
        self.capabilities = capabilities
        self.appliance_state = appliance_state

        self._attr_unique_id = f"electrolux_ionizer_{appliance.id}"
        self._attr_name = f"{appliance.name} Ionizer"

        self._attr_should_poll = False
        
        self._update_attributes()

    @property
    def appliance_id(self) -> str:
        return self.appliance.id

    def _update_attributes(self):
        reported = self.appliance_state.properties.reported
        self._attr_is_on = reported.ionizer if reported.ionizer else False

    @cached_property
    def available(self) -> bool:
        return self.appliance_state.connectionState == ConnectionState.CONNECTED

    async def async_turn_on(self, **kwargs: Any) -> None:
        success = await self.hub.api.send_command(self.appliance.id, {
            "Ionizer": True
        })
        if not success:
            return
        
        self.appliance_state.properties.reported.ionizer = True
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        success = await self.hub.api.send_command(self.appliance.id, {
            "Ionizer": False
        })
        if not success:
            return
        
        self.appliance_state.properties.reported.ionizer = False
        self._attr_is_on = False
        self.async_write_ha_state()
