from __future__ import annotations
from typing import Any, cast
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.helpers.entity import cached_property
import logging

from ...hub import ElectroluxHub
from ...appliance import Appliance
from ...capabilities import Capabilities, IntegerCapability
from ...appliance_state import ApplianceState, ConnectionState, Workmode

_LOGGER = logging.getLogger(__name__)


class Fan(FanEntity):
    def __init__(self, hub: ElectroluxHub, appliance: Appliance, capabilities: Capabilities, appliance_state: ApplianceState):
        self.hub = hub
        self.appliance = appliance
        self.capabilities = capabilities
        self.appliance_state = appliance_state

        self._attr_unique_id = f"electrolux_fan_{appliance.id}"
        self._attr_name = appliance.name
        
        self._attr_supported_features = (
            FanEntityFeature.TURN_ON |
            FanEntityFeature.TURN_OFF |
            FanEntityFeature.SET_SPEED |
            FanEntityFeature.PRESET_MODE
        )

        self._attr_preset_modes = ["Smart", "Manual"]
        
        self._attr_should_poll = False
        
        self._update_attributes()

    @property
    def appliance_id(self) -> str:
        return self.appliance.id

    def _update_attributes(self):
        reported = self.appliance_state.properties.reported

        fan_speed_cap = cast(IntegerCapability, self.capabilities["Fanspeed"])

        # Set speed_count first so we can use it in percentage calculation
        self._attr_speed_count = fan_speed_cap.max if fan_speed_cap.max else 5
        
        if reported.workmode == Workmode.AUTO:
            self._attr_preset_mode = "Smart"
            self._attr_percentage = None
        else:
            self._attr_preset_mode = "Manual"
            self._attr_percentage = cast(int, (reported.fan_speed / self._attr_speed_count) * 100) if reported.fan_speed else 0

    @cached_property
    def available(self) -> bool:
        return self.appliance_state.connectionState == ConnectionState.CONNECTED

    @property
    def is_on(self) -> bool:
        return (
            self.appliance_state.connectionState == ConnectionState.CONNECTED and
            self.appliance_state.properties.reported.workmode != Workmode.POWER_OFF
        )

    async def async_turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any) -> None:
        success = await self.hub.api.send_command(self.appliance.id, {
            "Workmode": "Auto"
        })
        if not success:
            return

        self.appliance_state.properties.reported.workmode = Workmode.AUTO
        self._attr_preset_mode = "Auto"
        self.async_write_ha_state()
        pass

    async def async_turn_off(self, **kwargs: Any) -> None:
        success = await self.hub.api.send_command(self.appliance.id, {
            "Workmode": "PowerOff"
        })
        if not success:
            return

        self.appliance_state.properties.reported.workmode = Workmode.POWER_OFF
        self.async_write_ha_state()
        pass

    async def async_set_percentage(self, percentage: int) -> None:
        if self.appliance_state.properties.reported.workmode != Workmode.MANUAL:
            self._attr_percentage = 0
            self.async_write_ha_state()
            return

        fan_speed_cap = cast(IntegerCapability, self.capabilities["Fanspeed"])
        fan_speed = int((percentage / 100) * fan_speed_cap.max) if fan_speed_cap.max else 5

        success = await self.hub.api.send_command(self.appliance.id, {
            "Fanspeed": fan_speed
        })
        if not success:
            return
        
        self.appliance_state.properties.reported.fan_speed = fan_speed
        self._attr_percentage = percentage
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == "Smart":
            workmode = "Auto"
        else:
            workmode = "Manual"
            
        success = await self.hub.api.send_command(self.appliance.id, {
            "Workmode": workmode
        })
        if not success:
            return
        
        self.appliance_state.properties.reported.workmode = Workmode.AUTO if preset_mode == "Smart" else Workmode.MANUAL
        self._attr_preset_mode = preset_mode
        
        if preset_mode == "Smart":
            self._attr_percentage = None
        else:
            self._attr_percentage = cast(int, (self.appliance_state.properties.reported.fan_speed / self._attr_speed_count) * 100) if self.appliance_state.properties.reported.fan_speed else 0

        self.async_write_ha_state()
