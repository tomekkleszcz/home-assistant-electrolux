from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import cast, TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from .token import Token
from .hub import ElectroluxHub
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_EMAIL,
    CONF_API_KEY,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_EXPIRATION_DATE,
    CONF_USE_LIVESTREAM_UPDATES,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .jwt_utils import get_token_expiration

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.FAN,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

class ElectroluxConfigData(TypedDict):
    scan_interval: int
    use_livestream_updates: bool

ElectroluxConfigEntry = ConfigEntry[ElectroluxConfigData]


def _parse_token_expiration(value: datetime | str | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ElectroluxConfigEntry) -> bool:
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    store = Store(hass, version=1, key=DOMAIN)
    stored_data = await store.async_load() or {}

    api_key: str | None = cast(str | None, entry.data.get(CONF_API_KEY) or stored_data.get(CONF_API_KEY))
    access_token: str | None = cast(
        str | None,
        stored_data.get(CONF_ACCESS_TOKEN) or entry.data.get(CONF_ACCESS_TOKEN),
    )
    refresh_token: str | None = cast(
        str | None,
        stored_data.get(CONF_REFRESH_TOKEN) or entry.data.get(CONF_REFRESH_TOKEN),
    )

    if not api_key or not access_token or not refresh_token:
        _LOGGER.error("Cannot set up Electrolux Home because credentials are incomplete")
        return False

    token_expiration_date = _parse_token_expiration(
        cast(datetime | str | None, stored_data.get(CONF_TOKEN_EXPIRATION_DATE) or entry.data.get(CONF_TOKEN_EXPIRATION_DATE))
    )
    if token_expiration_date is None:
        token_expiration_date = get_token_expiration(access_token)

    scan_interval: int = max(
        MIN_SCAN_INTERVAL,
        cast(int, entry.options.get("scan_interval", entry.data.get("scan_interval", 120))),
    )
    use_livestream_updates = cast(
        bool,
        entry.options.get(
            CONF_USE_LIVESTREAM_UPDATES,
            entry.data.get(CONF_USE_LIVESTREAM_UPDATES, True),
        ),
    )

    token: Token = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expiration_date": token_expiration_date
    }

    hub = ElectroluxHub(
        hass=hass,
        api_key=api_key,
        token=token,
        scan_interval=scan_interval,
        use_livestream_updates=use_livestream_updates,
    )

    timer = None
    try:
        account_email = cast(str | None, entry.data.get(CONF_ACCOUNT_EMAIL)) or await hub.api.get_account_email()
        if account_email and entry.title != account_email:
            hass.config_entries.async_update_entry(
                entry,
                title=account_email,
                data={**entry.data, CONF_ACCOUNT_EMAIL: account_email},
            )

        await hub.discover_appliances()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "hub": hub,
            "timer": timer
        }
        await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

        async def close_hub_at_stop(_) -> None:
            await hub.close()

        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, close_hub_at_stop))

        if use_livestream_updates:
            async def start_livestream_after_started(_: HomeAssistant) -> None:
                hub.start_livestream()

            entry.async_on_unload(async_at_started(hass, start_livestream_after_started))
        else:
            timer = async_track_time_interval(hass, hub.poll_appliances, timedelta(seconds=scan_interval))
            hass.data[DOMAIN][entry.entry_id]["timer"] = timer
    except Exception:
        if timer is not None:
            timer()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        await hub.close()
        raise

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ElectroluxConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_update_options(hass: HomeAssistant, entry: ElectroluxConfigEntry) -> None:
    """Update options and reload entry."""
    await async_reload_entry(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ElectroluxConfigEntry) -> bool:
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if not ok:
        return False

    if isinstance(entry_data, dict):
        timer = entry_data.get("timer")
        if callable(timer):
            timer()

        hub = entry_data.get("hub")
        if hub is not None:
            await hub.close()

    if DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return True
