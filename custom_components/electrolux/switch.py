from .const import DOMAIN
from .dynamic import switch_entities


async def async_setup_entry(hass, config_entry, async_add_entities):
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    hub = entry_data["hub"]
    if hub is None:
        return

    entities = switch_entities(hub)
    hub.add_entities(entities)
    async_add_entities(entities)
