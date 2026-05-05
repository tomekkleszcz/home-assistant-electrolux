import logging

from .const import DOMAIN
from .dynamic import climate_entities

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    hub = entry_data["hub"]
    if hub is None:
        _LOGGER.warning("Hub is None, skipping climate platform setup")
        return

    entities = climate_entities(hub)
    hub.add_entities(entities)
    async_add_entities(entities)
