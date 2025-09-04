from typing import Any
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import vol
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow, ConfigEntry



def get_options_schema(config_entry: ConfigEntry) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=config_entry.options.get(CONF_SCAN_INTERVAL, 120),
            ): int,
        }
    )

class ElectroluxOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            result = self.async_create_entry(data=user_input)
            
            async def reload_after_save():
                await self.hass.async_add_executor_job(lambda: None)
                from . import async_update_options
                await async_update_options(self.hass, self.config_entry)
            
            self.hass.async_create_task(reload_after_save())
            
            return result
        
        return self.async_show_form(
            step_id="init",
            data_schema=get_options_schema(self.config_entry),
        )