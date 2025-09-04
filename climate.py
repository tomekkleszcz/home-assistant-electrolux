from .const import DOMAIN

async def async_setup_entry(hass, config_entry, async_add_entities):
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    hub = entry_data["hub"]
    
    if hub is None:
        return

    entities = []
    for appliance in hub.get_discovered_appliances():
        if appliance.type != "Azul":
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