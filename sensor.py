from .const import DOMAIN

async def async_setup_entry(hass, config_entry, async_add_entities):
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    hub = entry_data["hub"]

    entities = []
    for appliance in hub.get_discovered_appliances():
        if appliance.type != "WELLA7":
            continue

        state = await hub.api.get_appliance_state(appliance.id)
        if not state:
            continue

        info = await hub.api.get_appliance_info(appliance.id)
        if not info:
            continue

        from .air_purifier.wella7 import (
            PM1Sensor,
            PM25Sensor,
            PM10Sensor,
            TVOCSensor,
            HumiditySensor,
            TemperatureSensor,
            CO2Sensor
        )
        entities.append(PM1Sensor(hub, appliance, info.capabilities, state))
        entities.append(PM25Sensor(hub, appliance, info.capabilities, state))
        entities.append(PM10Sensor(hub, appliance, info.capabilities, state))
        entities.append(TVOCSensor(hub, appliance, info.capabilities, state))
        entities.append(HumiditySensor(hub, appliance, info.capabilities, state))
        entities.append(TemperatureSensor(hub, appliance, info.capabilities, state))
        entities.append(CO2Sensor(hub, appliance, info.capabilities, state))

    hub.add_entities(entities)
    async_add_entities(entities)