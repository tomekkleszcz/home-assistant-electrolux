from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any, cast
from ...capabilities import Capabilities, TemperatureCapability
from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import cached_property
import logging

from ...hub import ElectroluxHub
from ...appliance import Appliance
from ...appliance_state import ApplianceState, ApplianceStateValue, ConnectionState, Mode, Toggle

_LOGGER = logging.getLogger(__name__)

class Climate(ClimateEntity):
    last_turn_off_time: datetime | None = None

    def __init__(self, hub: ElectroluxHub, appliance: Appliance, capabilities: Capabilities, appliance_state: ApplianceState):
        self.hub = hub
        self.appliance = appliance
        self.capabilities = capabilities
        self.appliance_state = appliance_state

        self._attr_unique_id = f"electrolux.{appliance.id}"
        self._attr_name = appliance.name
        
        self._attr_supported_features = (
            ClimateEntityFeature.TURN_ON | 
            ClimateEntityFeature.TURN_OFF | 
            ClimateEntityFeature.TARGET_TEMPERATURE | 
            ClimateEntityFeature.PRESET_MODE | 
            ClimateEntityFeature.SWING_MODE
        )

        self._attr_hvac_modes = [HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]
        
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = cast(TemperatureCapability, self.capabilities["targetTemperatureC"]).min
        self._attr_max_temp = cast(TemperatureCapability, self.capabilities["targetTemperatureC"]).max
        self._attr_target_temperature_step = cast(TemperatureCapability, self.capabilities["targetTemperatureC"]).step

        self._attr_preset_modes = ["Unlocked", "Locked"]

        if "verticalSwing" in self.capabilities:
            self._attr_swing_modes = ["off", "on"]
        else:
            self._attr_swing_modes = None
        
        self._attr_should_poll = False
        
        self._update_attributes()

    @property
    def appliance_id(self) -> str:
        return self.appliance.id

    def _update_attributes(self):
        reported = self.appliance_state.properties.reported
        
        if reported.mode and reported.appliance_state == ApplianceStateValue.RUNNING:
            self._attr_hvac_mode = reported.mode.to_hvac_mode()
        else:
            self._attr_hvac_mode = HVACMode.OFF

        self._attr_target_temperature = reported.target_temperature_c
        self._attr_current_temperature = reported.ambient_temperature_c
        
        if reported.ui_lock_mode:
            self._attr_preset_mode = "Locked"
        else:
            self._attr_preset_mode = "Unlocked"
        
        if reported.vertical_swing == Toggle.OFF:
            self._attr_swing_mode = "off"
        else:
            self._attr_swing_mode = "on"

    @cached_property
    def available(self) -> bool:
        return self.appliance_state.connectionState == ConnectionState.CONNECTED

    @property
    def is_on(self) -> bool:
        return (
            self.appliance_state.connectionState == ConnectionState.CONNECTED and
            self.appliance_state.properties.reported.appliance_state == ApplianceStateValue.RUNNING
        )

    async def async_turn_on(self) -> None:
        success = await self.hub.api.send_command(self.appliance.id, {
            "executeCommand": "ON"
        })
        if not success:
            self.async_write_ha_state()
            return

        self.appliance_state.properties.reported.appliance_state = ApplianceStateValue.RUNNING

        self._attr_hvac_mode = self.appliance_state.properties.reported.mode.to_hvac_mode() if self.appliance_state.properties.reported.mode else HVACMode.AUTO

        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        if self.appliance_state.properties.reported.appliance_state == ApplianceStateValue.OFF:
            self.last_turn_off_time = datetime.now()
            return

        success = await self.hub.api.send_command(self.appliance.id, {
            "executeCommand": "OFF"
        })
        if not success:
            self.async_write_ha_state()
            return

        self.last_turn_off_time = datetime.now()
        
        self.appliance_state.properties.reported.appliance_state = ApplianceStateValue.OFF

        self._attr_hvac_mode = HVACMode.OFF

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return

        match hvac_mode:
            case HVACMode.COOL:
                mode = "COOL"
            case HVACMode.HEAT:
                mode = "HEAT"
            case _:
                mode = "AUTO"

        success = await self.hub.api.send_command(self.appliance.id, {
            "executeCommand": "ON",
            "mode": mode
        })
        if not success:
            return
        
        self.appliance_state.properties.reported.appliance_state = ApplianceStateValue.RUNNING
        self.appliance_state.properties.reported.mode = Mode.from_hvac_mode(hvac_mode)
        
        self._attr_hvac_mode = hvac_mode
        
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if self.last_turn_off_time and datetime.now() - self.last_turn_off_time < timedelta(seconds=1):
            self.async_write_ha_state()
            return

        success = await self.hub.api.send_command(self.appliance.id, {
            "targetTemperatureC": kwargs["temperature"]
        })
        if not success:
            return
        
        self.appliance_state.properties.reported.appliance_state = ApplianceStateValue.RUNNING
        self.appliance_state.properties.reported.target_temperature_c = kwargs["temperature"]
        
        self._attr_hvac_mode = self.appliance_state.properties.reported.mode.to_hvac_mode() if self.appliance_state.properties.reported.mode else HVACMode.AUTO
        self._attr_target_temperature = kwargs["temperature"]
        
        self.async_write_ha_state()
        pass

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if self.appliance_state.properties.reported.appliance_state == ApplianceStateValue.OFF:
            self.async_write_ha_state()
            return

        locked = preset_mode == "Locked"

        success = await self.hub.api.send_command(self.appliance.id, {
            "uiLockMode": locked
        })
        if not success:
            return
        
        self.appliance_state.properties.reported.ui_lock_mode = locked

        self._attr_preset_mode = preset_mode
            
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if self.appliance_state.properties.reported.appliance_state == ApplianceStateValue.OFF:
            self.async_write_ha_state()
            return

        enabled = swing_mode == "on"

        success = await self.hub.api.send_command(self.appliance.id, {
            "verticalSwing": "ON" if enabled else "OFF"
        })
        if not success:
            return
        
        self.appliance_state.properties.reported.vertical_swing = Toggle.ON if enabled else Toggle.OFF

        self._attr_swing_mode = swing_mode

        self.async_write_ha_state()

