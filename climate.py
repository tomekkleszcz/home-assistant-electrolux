import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    hub = entry_data["hub"]
    
    if hub is None:
        _LOGGER.warning("Hub is None, skipping climate platform setup")
        return

    discovered_appliances = hub.get_discovered_appliances()
    if not discovered_appliances:
        _LOGGER.warning("No appliances discovered, skipping climate platform setup")
        return

    _LOGGER.info(f"Setting up climate platform with {len(discovered_appliances)} appliances")
    entities = []
    for appliance in discovered_appliances:
        _LOGGER.info(f"Processing appliance: {appliance.name} (Type: {appliance.type})")
        if appliance.type != "Azul":
            _LOGGER.info(f"Skipping appliance {appliance.name} - type {appliance.type} is not Azul")
            continue

        state = await hub.api.get_appliance_state(appliance.id)
        if not state:
            continue

        info = await hub.api.get_appliance_info(appliance.id)
        if not info:
            continue

        from .air_conditioner.comfort600.climate import Climate
        entities.append(Climate(hub, appliance, info.capabilities, state))

    hub.add_entities(entities)
    async_add_entities(entities)