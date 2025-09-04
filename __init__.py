from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import cast, TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .token import Token
from .hub import ElectroluxHub
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.FAN, Platform.SENSOR]

class ElectroluxConfigData(TypedDict):
    scan_interval: int

ElectroluxConfigEntry = ConfigEntry[ElectroluxConfigData]

async def async_setup_entry(hass: HomeAssistant, entry: ElectroluxConfigEntry) -> bool:
    store = Store(hass, version=1, key=DOMAIN)
    stored_data = await store.async_load()

    if stored_data and stored_data.get("api_key") and stored_data.get("access_token") and stored_data.get("refresh_token") and entry.data.get("api_key"):
        api_key: str = cast(str, entry.data.get("api_key"))
        access_token: str = stored_data.get("access_token")
        refresh_token: str = stored_data.get("refresh_token")
        token_expiration_date: datetime = datetime.fromisoformat(stored_data.get("token_expiration_date"))
        scan_interval: int = cast(int, entry.options.get("scan_interval", entry.data.get("scan_interval", 120)))

        token: Token = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expiration_date": token_expiration_date
        }

        hub = ElectroluxHub(
            hass=hass,
            api_key=api_key,
            token=token,
            scan_interval=scan_interval
        )

        try:
            await hub.discover_appliances()

            # Store the timer so it can be cancelled later
            timer = async_track_time_interval(hass, hub.poll_appliances, timedelta(seconds=scan_interval))

            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][entry.entry_id] = {
                "hub": hub,
                "timer": timer
            }
        except Exception as e:
            # If setup fails, close the API session
            await hub.close()
            raise e

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ElectroluxConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_update_options(hass: HomeAssistant, entry: ElectroluxConfigEntry) -> None:
    """Update options and reload entry."""
    await async_reload_entry(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ElectroluxConfigEntry) -> bool:
    # Cancel the timer and close API session before unloading platforms
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        entry_data = hass.data[DOMAIN][entry.entry_id]
        if isinstance(entry_data, dict):
            if "timer" in entry_data:
                entry_data["timer"]()  # Cancel the timer
            if "hub" in entry_data:
                await entry_data["hub"].close()  # Close API session
    
    ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return ok


