from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_SCAN_INTERVAL

from .const import CONF_USE_LIVESTREAM_UPDATES


def _use_livestream_updates_default(config_entry: ConfigEntry) -> bool:
    return config_entry.options.get(
        CONF_USE_LIVESTREAM_UPDATES,
        config_entry.data.get(CONF_USE_LIVESTREAM_UPDATES, True),
    )


def _scan_interval_default(config_entry: ConfigEntry) -> int:
    return config_entry.options.get(
        CONF_SCAN_INTERVAL,
        config_entry.data.get(CONF_SCAN_INTERVAL, 120),
    )


def get_options_schema(config_entry: ConfigEntry, use_livestream_updates: bool | None = None) -> vol.Schema:
    if use_livestream_updates is None:
        use_livestream_updates = _use_livestream_updates_default(config_entry)

    schema = {
        vol.Required(
            CONF_USE_LIVESTREAM_UPDATES,
            default=use_livestream_updates,
        ): bool,
    }
    if not use_livestream_updates:
        schema[
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=_scan_interval_default(config_entry),
            )
        ] = int

    return vol.Schema(schema)


def options_from_user_input(config_entry: ConfigEntry, user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_USE_LIVESTREAM_UPDATES: user_input[CONF_USE_LIVESTREAM_UPDATES],
        CONF_SCAN_INTERVAL: user_input.get(
            CONF_SCAN_INTERVAL,
            _scan_interval_default(config_entry),
        ),
    }


class ElectroluxOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            use_livestream_updates = user_input[CONF_USE_LIVESTREAM_UPDATES]
            if not use_livestream_updates and CONF_SCAN_INTERVAL not in user_input:
                return self.async_show_form(
                    step_id="init",
                    data_schema=get_options_schema(self.config_entry, use_livestream_updates=False),
                )

            return self.async_create_entry(data=options_from_user_input(self.config_entry, user_input))

        return self.async_show_form(
            step_id="init",
            data_schema=get_options_schema(self.config_entry),
        )
