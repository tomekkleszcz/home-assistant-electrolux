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
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_EMAIL,
    CONF_API_KEY,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRATION_DATE,
    CONF_USE_LIVESTREAM_UPDATES,
    DOMAIN,
)
from .token import Token
from .hub import ElectroluxHub
from .jwt_utils import get_token_expiration


_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
        vol.Required(CONF_USE_LIVESTREAM_UPDATES, default=True): bool,
    }
)

STEP_POLLING_OPTIONS_DATA_SCHEMA = vol.Schema(
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
        scan_interval=data.get(CONF_SCAN_INTERVAL, 120),
        use_livestream_updates=data.get(CONF_USE_LIVESTREAM_UPDATES, True),
    )

    try:
        account_email = await hub.api.get_account_email(raise_on_error=True)
        if not account_email:
            raise InvalidCredentials
    except InvalidCredentials:
        raise
    except Exception as err:
        raise CannotConnect from err
    finally:
        await hub.close()

    return {
        "title": account_email,
        CONF_ACCOUNT_EMAIL: account_email,
        "token_expiration": token_expiration
    }

class ConfigFlow(HassConfigFlow, domain=DOMAIN):
    _pending_entry_data: dict[str, Any]
    _pending_entry_options: dict[str, Any]
    _pending_entry_title: str

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
                    CONF_TOKEN_EXPIRATION_DATE: info["token_expiration"].isoformat() if info["token_expiration"] else None,
                    CONF_ACCOUNT_EMAIL: info[CONF_ACCOUNT_EMAIL]
                }
                options = {
                    CONF_USE_LIVESTREAM_UPDATES: user_input[CONF_USE_LIVESTREAM_UPDATES],
                    CONF_SCAN_INTERVAL: 120,
                }
                if not user_input[CONF_USE_LIVESTREAM_UPDATES]:
                    self._pending_entry_data = data
                    self._pending_entry_options = options
                    self._pending_entry_title = info["title"]
                    return await self.async_step_polling()

                return self.async_create_entry(title=info["title"], data=data, options=options)

        return self.async_show_form(
            step_id="user", 
            data_schema=STEP_USER_DATA_SCHEMA, 
            errors=errors,
            description_placeholders={
                "docs_url": "https://developer.electrolux.one"
            }
        )

    async def async_step_polling(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._pending_entry_title,
                data=self._pending_entry_data,
                options={
                    **self._pending_entry_options,
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                },
            )

        return self.async_show_form(
            step_id="polling",
            data_schema=STEP_POLLING_OPTIONS_DATA_SCHEMA,
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ElectroluxOptionsFlow()

class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

class InvalidCredentials(HomeAssistantError):
    """Error to indicate there is invalid auth."""
