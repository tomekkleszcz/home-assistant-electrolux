from __future__ import annotations
import logging
from typing import Any
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow as HassConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.config_entries import ConfigEntry
from .options_flow import ElectroluxOptionsFlow
from .const import DOMAIN, CONF_API_KEY, CONF_REFRESH_TOKEN, CONF_ACCESS_TOKEN, CONF_TOKEN_EXPIRATION_DATE
from .token import Token
from .hub import ElectroluxHub
from .jwt_utils import get_token_expiration


_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
        vol.Required(CONF_SCAN_INTERVAL, default=120): int,
    }
)

STEP_OPTIONS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=120): int,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    # Extract token expiration from JWT
    token_expiration = get_token_expiration(data[CONF_ACCESS_TOKEN])
    
    token: Token = {
        "access_token": data[CONF_ACCESS_TOKEN],
        "refresh_token": data[CONF_REFRESH_TOKEN],
        "token_expiration_date": token_expiration
    }

    hub = ElectroluxHub(
        hass=hass,
        api_key=data[CONF_API_KEY],
        token=token,
        scan_interval=data[CONF_SCAN_INTERVAL]
    )

    if not await hub.validate_credentials():
        raise InvalidCredentials

    return {
        "title": "Electrolux Home",
        CONF_SCAN_INTERVAL: data[CONF_SCAN_INTERVAL],
        "token_expiration": token_expiration
    }

class ConfigFlow(HassConfigFlow, domain=DOMAIN):
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidCredentials:
                errors["base"] = "invalid_credentials"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Separate data and options
                data = {
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    CONF_ACCESS_TOKEN: user_input[CONF_ACCESS_TOKEN],
                    CONF_REFRESH_TOKEN: user_input[CONF_REFRESH_TOKEN],
                    CONF_TOKEN_EXPIRATION_DATE: info["token_expiration"].isoformat()
                }
                options = {
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]
                }
                return self.async_create_entry(title=info["title"], data=data, options=options)

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "docs_url": "https://developer.electrolux.one"
            }
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ElectroluxOptionsFlow()

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidCredentials(HomeAssistantError):
    """Error to indicate there is invalid auth."""
