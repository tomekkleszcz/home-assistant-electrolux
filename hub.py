from datetime import datetime
import logging
from homeassistant.const import CONF_SCAN_INTERVAL
from .const import CONF_ACCESS_TOKEN, CONF_API_KEY, CONF_REFRESH_TOKEN, CONF_TOKEN_EXPIRATION_DATE, DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from .api import ElectroluxAPI
from typing import Optional, Any
from .token import Token
from .api import Appliance, ApplianceState


_LOGGER = logging.getLogger(__name__)


class ElectroluxHub:
    def __init__(self, hass: HomeAssistant, api_key: str, token: Token, scan_interval: Optional[int]) -> None:
        self.hass = hass
        self.api_key = api_key
        self.token = token
        self.scan_interval = scan_interval
        self.entities = []
        
        self.api = ElectroluxAPI(
            api_key=api_key,
            token=token,
            on_token_refresh=self.on_token_refresh
        )

    async def on_token_refresh(self, token: Token):
        store = Store(self.hass, version=1, key=DOMAIN)
        await store.async_save({
            CONF_API_KEY: self.api_key,
            CONF_ACCESS_TOKEN: token["access_token"],
            CONF_REFRESH_TOKEN: token["refresh_token"],
            CONF_TOKEN_EXPIRATION_DATE: token["token_expiration_date"],
            CONF_SCAN_INTERVAL: self.scan_interval
        })

    async def validate_credentials(self) -> bool:
        return await self.api.get_appliances() is not []

    async def poll_appliances(self, _: datetime):
        _LOGGER.info("Polling appliances")

        try:
            if not self.discovered_appliances:
                return

            for appliance in self.discovered_appliances:
                state = await self.api.get_appliance_state(appliance.id)
                if not state:
                    continue

                for entity in self.entities:
                    if not hasattr(entity, 'appliance_id'):
                        continue

                    if entity.appliance_id != appliance.id:
                        continue
                
                    try:
                        if hasattr(entity, 'appliance_state'):
                            entity.appliance_state = state
                            
                        if hasattr(entity, '_update_attributes'):
                            entity._update_attributes()
                            
                        if hasattr(entity, 'async_update'):
                            await entity.async_update()
                            
                        if hasattr(entity, 'async_write_ha_state'):
                            entity.async_write_ha_state()
                            
                        _LOGGER.debug(f"Updated entity state for {entity.entity_id}")
                    except Exception as e:
                        _LOGGER.error(f"Failed to update entity {entity.entity_id}: {e}")
        except Exception as e:
            _LOGGER.error(f"Error during periodic update: {e}")

    def get_discovered_appliances(self) -> list[Appliance] | None:
        return self.discovered_appliances

    async def discover_appliances(self):
        try:
            self.discovered_appliances = await self.api.get_appliances()
            if not self.discovered_appliances:
                return []

            return self.discovered_appliances
        except Exception as e:
            _LOGGER.error(f"Failed to discover appliances: {e}")
            return []
    
    def add_entities(self, entities: list[Any]):
        self.entities.extend(entities)

    async def close(self):
        """Close the API session."""
        if hasattr(self, 'api') and self.api:
            await self.api.close()
