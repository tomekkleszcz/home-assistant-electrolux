from __future__ import annotations
from typing import Any, cast
from homeassistant.components.fan import FanEntity, FanEntityFeature
import logging

from ...hub import ElectroluxHub
from ...appliance import Appliance
from ...capabilities import ApplianceInfo, IntegerCapability
from ...appliance_state import ApplianceState, ConnectionState, Workmode
from ...entity import ElectroluxApplianceEntity

_LOGGER = logging.getLogger(__name__)


class Fan(ElectroluxApplianceEntity, FanEntity):
    livestream_properties = frozenset({"Workmode", "Fanspeed"})

    def __init__(self, hub: ElectroluxHub, appliance: Appliance, info: ApplianceInfo, appliance_state: ApplianceState):
        self.hub = hub
        self.appliance = appliance
        self.info = info
        self.capabilities = info.capabilities
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
        self._last_active_workmode = (
            appliance_state.properties.reported.workmode
            if appliance_state.properties.reported.workmode in (Workmode.AUTO, Workmode.MANUAL)
            else Workmode.AUTO
        )
        
        self._update_attributes()

    def _update_attributes(self):
        reported = self.appliance_state.properties.reported

        fan_speed_cap = cast(IntegerCapability, self.capabilities["Fanspeed"])

        # Set speed_count first so we can use it in percentage calculation
        self._attr_speed_count = fan_speed_cap.max if fan_speed_cap.max else 5
        
        if reported.workmode == Workmode.AUTO:
            self._last_active_workmode = Workmode.AUTO
            self._attr_preset_mode = "Smart"
            self._attr_percentage = None
        elif reported.workmode == Workmode.MANUAL:
            self._last_active_workmode = Workmode.MANUAL
            self._attr_preset_mode = "Manual"
            self._attr_percentage = cast(int, (reported.fan_speed / self._attr_speed_count) * 100) if reported.fan_speed else 0
        else:
            self._attr_preset_mode = self._preset_mode_from_workmode(self._last_active_workmode)
            self._attr_percentage = 0

    def _preset_mode_from_workmode(self, workmode: Workmode) -> str:
        return "Smart" if workmode == Workmode.AUTO else "Manual"

    def _command_value_from_workmode(self, workmode: Workmode) -> str:
        if workmode == Workmode.AUTO:
            return "Auto"
        if workmode == Workmode.MANUAL:
            return "Manual"
        return "PowerOff"

    def _fan_speed_from_percentage(self, percentage: int) -> int:
        fan_speed_cap = cast(IntegerCapability, self.capabilities["Fanspeed"])
        max_speed = fan_speed_cap.max or 5
        min_speed = fan_speed_cap.min or 1
        computed = int((percentage / 100) * max_speed)
        return max(min_speed, min(max_speed, computed))

    @property
    def available(self) -> bool:
        return self.appliance_state.connectionState == ConnectionState.CONNECTED

    @property
    def is_on(self) -> bool:
        return (
            self.appliance_state.connectionState == ConnectionState.CONNECTED and
            self.appliance_state.properties.reported.workmode != Workmode.POWER_OFF
        )

    async def async_turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any) -> None:
        target_workmode = self._last_active_workmode
        if preset_mode == "Smart":
            target_workmode = Workmode.AUTO
        elif preset_mode == "Manual" or percentage is not None:
            target_workmode = Workmode.MANUAL

        body: dict[str, Any] = {
            "Workmode": self._command_value_from_workmode(target_workmode)
        }
        if percentage is not None:
            body["Fanspeed"] = self._fan_speed_from_percentage(percentage)

        success = await self.hub.send_command(self.appliance.id, body)
        if not success:
            return

        self.appliance_state.properties.reported.workmode = target_workmode
        if "Fanspeed" in body:
            self.appliance_state.properties.reported.fan_speed = body["Fanspeed"]
        self._update_attributes()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        current_workmode = self.appliance_state.properties.reported.workmode
        if current_workmode in (Workmode.AUTO, Workmode.MANUAL):
            self._last_active_workmode = current_workmode

        body = {
            "Workmode": "PowerOff"
        }
        success = await self.hub.send_command(self.appliance.id, body)
        if not success:
            return

        self.appliance_state.properties.reported.workmode = Workmode.POWER_OFF
        self._update_attributes()
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        if self.appliance_state.properties.reported.workmode != Workmode.MANUAL:
            self._attr_percentage = 0
            self.async_write_ha_state()
            return

        fan_speed = self._fan_speed_from_percentage(percentage)

        body = {
            "Fanspeed": fan_speed
        }
        success = await self.hub.send_command(self.appliance.id, body)
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
            
        body = {
            "Workmode": workmode
        }
        success = await self.hub.send_command(self.appliance.id, body)
        if not success:
            return
        
        self.appliance_state.properties.reported.workmode = Workmode.AUTO if preset_mode == "Smart" else Workmode.MANUAL
        self._last_active_workmode = self.appliance_state.properties.reported.workmode
        self._attr_preset_mode = preset_mode
        
        if preset_mode == "Smart":
            self._attr_percentage = None
        else:
            self._attr_percentage = cast(int, (self.appliance_state.properties.reported.fan_speed / self._attr_speed_count) * 100) if self.appliance_state.properties.reported.fan_speed else 0

        self.async_write_ha_state()
