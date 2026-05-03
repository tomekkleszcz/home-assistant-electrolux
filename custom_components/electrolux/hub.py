import asyncio
from contextlib import suppress
from datetime import datetime
import logging
from homeassistant.const import CONF_SCAN_INTERVAL
from .const import CONF_ACCESS_TOKEN, CONF_API_KEY, CONF_REFRESH_TOKEN, CONF_TOKEN_EXPIRATION_DATE, DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from .api import ElectroluxAPI
from typing import Optional, Any
from .appliance_state import ApplianceState, ConnectionState, update_reported_property
from .capabilities import Capability, command_body_for_capability
from .token import Token
from .appliance import Appliance, ApplianceData


_LOGGER = logging.getLogger(__name__)


class ElectroluxHub:
    _COMMAND_ONLY_PROPERTIES = frozenset({"executeCommand"})
    _COMMAND_HISTORY_LIMIT = 50

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        token: Token,
        scan_interval: Optional[int],
        use_livestream_updates: bool = True,
    ) -> None:
        self.hass = hass
        self.api_key = api_key
        self.token = token
        self.scan_interval = scan_interval
        self._use_livestream_updates = use_livestream_updates
        self.entities = []
        self.discovered_appliances: list[Appliance] = []
        self.discovered_appliance_data: dict[str, ApplianceData] = {}
        self._livestream_task: asyncio.Task[None] | None = None
        self._livestream_supported_properties_loaded = False
        self._livestream_supported_properties_by_appliance: dict[str, set[str]] = {}
        self._livestream_command_history: dict[tuple[str, str], list[Any]] = {}
        self._closed = False
        
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
            CONF_TOKEN_EXPIRATION_DATE: token["token_expiration_date"].isoformat() if token["token_expiration_date"] else None,
            CONF_SCAN_INTERVAL: self.scan_interval
        })

    async def validate_credentials(self, *, raise_on_error: bool = False) -> bool:
        return bool(await self.api.get_account_email(raise_on_error=raise_on_error))

    async def send_command(
        self,
        appliance_id: str,
        body: dict[str, Any],
        *,
        expected_livestream: dict[str, Any] | None = None,
    ) -> bool:
        success = await self.api.send_command(appliance_id, body)
        if success and self._use_livestream_updates:
            livestream_body = {
                property_name: value
                for property_name, value in body.items()
                if (
                    property_name not in self._COMMAND_ONLY_PROPERTIES
                    and self._can_receive_livestream_property(appliance_id, property_name)
                )
            }
            if livestream_body:
                self.register_livestream_command_echo_filter(appliance_id, livestream_body)
            if filtered_expected_livestream := self._filter_livestream_echo_body(appliance_id, expected_livestream):
                self.register_livestream_command_echo_filter(appliance_id, filtered_expected_livestream)
        return success

    async def send_capability_command(
        self,
        appliance_id: str,
        capability_path: str,
        value: Any,
        *,
        expected_livestream: dict[str, Any] | None = None,
    ) -> bool:
        appliance_data = self.discovered_appliance_data.get(appliance_id)
        if appliance_data is None:
            _LOGGER.debug("Ignoring command for unknown appliance %s capability %s", appliance_id, capability_path)
            return False

        runtime_capability = self.runtime_capability(appliance_id, capability_path)
        if runtime_capability is None or not runtime_capability.can_write:
            _LOGGER.debug(
                "Ignoring command for unavailable capability %s on appliance %s",
                capability_path,
                appliance_id,
            )
            return False
        if not self._is_capability_value_allowed(runtime_capability, value):
            _LOGGER.debug(
                "Ignoring command for capability %s on appliance %s because value is outside capabilities: %s",
                capability_path,
                appliance_id,
                value,
            )
            return False

        body = command_body_for_capability(runtime_capability, value, is_dam=appliance_data.is_dam)
        success = await self.send_command(appliance_id, body, expected_livestream=expected_livestream)
        if success:
            appliance_data.state.set_reported(capability_path, value)
        return success

    def _is_capability_value_allowed(self, capability: Capability, value: Any) -> bool:
        if capability.values:
            normalized_values = {self._normalize_capability_value(allowed) for allowed in capability.values}
            return self._normalize_capability_value(value) in normalized_values

        if capability.is_numeric:
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                return False
            if capability.min is not None and numeric_value < float(capability.min):
                return False
            if capability.max is not None and numeric_value > float(capability.max):
                return False
            if capability.step not in (None, 0) and capability.min is not None:
                offset = (numeric_value - float(capability.min)) / float(capability.step)
                if abs(offset - round(offset)) > 1e-6:
                    return False
        return True

    def _normalize_capability_value(self, value: Any) -> str:
        return str(value).strip().replace("_", "").replace(" ", "").upper()

    def runtime_capability(self, appliance_id: str, capability_path: str) -> Capability | None:
        appliance_data = self.discovered_appliance_data.get(appliance_id)
        if appliance_data is None:
            return None
        runtime_capabilities = appliance_data.info.runtime_capabilities(appliance_data.state.properties.reported.raw)
        return runtime_capabilities.get(capability_path)

    def _filter_livestream_echo_body(
        self,
        appliance_id: str,
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not body:
            return {}

        return {
            property_name: value
            for property_name, value in body.items()
            if self._can_receive_livestream_property(appliance_id, property_name)
        }

    def _can_receive_livestream_property(self, appliance_id: str, property_name: str) -> bool:
        if not self._livestream_supported_properties_loaded:
            return True

        supported_properties = self._livestream_supported_properties_by_appliance.get(appliance_id)
        return supported_properties is not None and property_name in supported_properties

    def register_livestream_command_echo_filter(self, appliance_id: str, body: dict[str, Any]) -> None:
        for property_name, value in body.items():
            history_key = (appliance_id, property_name)
            history = self._livestream_command_history.setdefault(history_key, [])
            history.append(self._normalize_livestream_value(property_name, value))
            if len(history) > self._COMMAND_HISTORY_LIMIT:
                del history[:-self._COMMAND_HISTORY_LIMIT]
            _LOGGER.debug(
                "Registered livestream command history for appliance %s: %s=%s",
                appliance_id,
                property_name,
                value,
            )

    def _should_ignore_livestream_event(self, appliance_id: str, property_name: str, value: Any) -> bool:
        history_key = (appliance_id, property_name)
        history = self._livestream_command_history.get(history_key)
        if not history:
            return False

        normalized_value = self._normalize_livestream_value(property_name, value)
        if normalized_value not in history:
            return False

        history.remove(normalized_value)
        if not history:
            self._livestream_command_history.pop(history_key, None)
        _LOGGER.debug(
            "Ignoring livestream echo for appliance %s: %s=%s",
            appliance_id,
            property_name,
            value,
        )
        return True

    def _normalize_livestream_value(self, property_name: str, value: Any) -> Any:
        if property_name == "Workmode":
            return str(value).strip().upper().replace("_", "").replace(" ", "") if value is not None else None
        return value

    def _set_livestream_supported_properties(self, supported_properties: dict[str, set[str]]) -> None:
        self._livestream_supported_properties_by_appliance = supported_properties
        self._livestream_supported_properties_loaded = True
        for appliance_id, property_name in list(self._livestream_command_history):
            if not self._can_receive_livestream_property(appliance_id, property_name):
                self._livestream_command_history.pop((appliance_id, property_name), None)

    async def _update_entities_for_appliance(
        self,
        appliance_id: str,
        state: ApplianceState,
        *,
        call_async_update: bool,
        changed_property: str | None = None,
    ) -> None:
        for entity in self.entities:
            if not hasattr(entity, 'appliance_id'):
                continue

            if entity.appliance_id != appliance_id:
                continue

            if not self._entity_handles_livestream_property(entity, changed_property):
                continue

            try:
                if hasattr(entity, 'appliance_state'):
                    entity.appliance_state = state
                if hasattr(entity, 'appliance_data') and entity.appliance_id in self.discovered_appliance_data:
                    entity.appliance_data = self.discovered_appliance_data[entity.appliance_id]

                if hasattr(entity, '_update_attributes'):
                    entity._update_attributes()

                if call_async_update and hasattr(entity, 'async_update'):
                    await entity.async_update()

                if hasattr(entity, 'async_write_ha_state'):
                    entity.async_write_ha_state()

                is_on = getattr(entity, "is_on", None)
                _LOGGER.debug(
                    "Updated entity state for %s from appliance %s; is_on=%s",
                    entity.entity_id,
                    appliance_id,
                    is_on,
                )
            except Exception as e:
                _LOGGER.error(f"Failed to update entity {entity.entity_id}: {e}")

    def _entity_handles_livestream_property(self, entity: Any, changed_property: str | None) -> bool:
        if changed_property is None or changed_property == "connectionState":
            return True

        livestream_properties = getattr(entity, "livestream_properties", None)
        if livestream_properties is None or changed_property in livestream_properties:
            return True
        changed_leaf = changed_property.rsplit(".", 1)[-1]
        return any(prop.rsplit(".", 1)[-1] == changed_leaf for prop in livestream_properties)

    async def poll_appliances(self, _: datetime):
        _LOGGER.info("Polling appliances")

        try:
            if not self.discovered_appliance_data:
                return

            for appliance_data in self.discovered_appliance_data.values():
                state = await self.api.get_appliance_state(appliance_data.appliance.id)
                if not state:
                    continue

                appliance_data.state = state
                await self._update_entities_for_appliance(appliance_data.appliance.id, state, call_async_update=True)
        except Exception as e:
            _LOGGER.error(f"Error during periodic update: {e}")

    def start_livestream(self) -> None:
        if self._closed:
            return

        if self._livestream_task is not None and not self._livestream_task.done():
            return

        self._livestream_task = self.hass.async_create_background_task(
            self._livestream_loop(),
            "electrolux_livestream",
        )

    async def _livestream_loop(self) -> None:
        while not self._closed:
            try:
                configuration = await self.api.get_livestream_configuration()
                if not configuration:
                    raise ConnectionError("Livestream configuration is unavailable")

                livestream_url = configuration["url"]
                supported_properties = self._livestream_supported_properties(configuration)
                self._set_livestream_supported_properties(supported_properties)
                _LOGGER.info("Starting Electrolux livestream updates")
                _LOGGER.debug(
                    "Electrolux livestream supported properties by appliance: %s",
                    supported_properties,
                )

                async for event in self.api.stream_livestream_events(livestream_url):
                    await self._handle_livestream_event(event, supported_properties)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOGGER.warning(f"Livestream disconnected, reconnecting in 10 seconds: {e}")
                await asyncio.sleep(10)

    def _livestream_supported_properties(self, configuration: dict[str, Any]) -> dict[str, set[str]]:
        supported_properties: dict[str, set[str]] = {}
        for appliance in configuration.get("appliances", []):
            appliance_id = appliance.get("applianceId")
            properties = appliance.get("properties", [])
            if isinstance(appliance_id, str) and isinstance(properties, list):
                supported_properties[appliance_id] = {prop for prop in properties if isinstance(prop, str)}
        return supported_properties

    async def _handle_livestream_event(self, event: dict[str, Any], supported_properties: dict[str, set[str]]) -> None:
        _LOGGER.debug("Handling Electrolux livestream event: %s", event)

        appliance_id = event.get("applianceId")
        property_name = event.get("property")
        value = event.get("value")
        if not isinstance(appliance_id, str) or not isinstance(property_name, str):
            _LOGGER.debug(f"Ignoring livestream event with unexpected shape: {event}")
            return

        if appliance_id in supported_properties and property_name not in supported_properties[appliance_id]:
            _LOGGER.debug(
                "Ignoring livestream event for non-whitelisted property %s on appliance %s; value=%s",
                property_name,
                appliance_id,
                value,
            )
            return

        if self._should_ignore_livestream_event(appliance_id, property_name, value):
            return

        state = self._get_entity_appliance_state(appliance_id)
        if state is None:
            _LOGGER.debug(
                "Ignoring livestream event for appliance without entities: %s property=%s value=%s",
                appliance_id,
                property_name,
                value,
            )
            return

        if property_name == "connectionState":
            previous_connection_state = state.connectionState
            state.connectionState = ConnectionState.from_string(value)
            _LOGGER.debug(
                "Applied livestream event for appliance %s: %s=%s; connection_state %s -> %s",
                appliance_id,
                property_name,
                value,
                previous_connection_state,
                state.connectionState,
            )
            await self._update_entities_for_appliance(
                appliance_id,
                state,
                call_async_update=False,
                changed_property=property_name,
            )
            return

        property_path = self._resolve_property_path(appliance_id, property_name)
        reported = state.properties.reported
        previous_value = reported.get(property_path)

        if not update_reported_property(reported, property_path, value):
            _LOGGER.debug(
                "Ignoring livestream event for unknown property %s on appliance %s; value=%s",
                property_name,
                appliance_id,
                value,
            )
            return

        if appliance_data := self.discovered_appliance_data.get(appliance_id):
            appliance_data.state = state

        _LOGGER.debug(
            "Applied livestream event for appliance %s: %s %s -> %s",
            appliance_id,
            property_path,
            previous_value,
            value,
        )

        await self._update_entities_for_appliance(
            appliance_id,
            state,
            call_async_update=False,
            changed_property=property_path,
        )

    def _resolve_property_path(self, appliance_id: str, property_name: str) -> str:
        appliance_data = self.discovered_appliance_data.get(appliance_id)
        if appliance_data is None:
            return property_name
        if property_name in appliance_data.info.capabilities:
            return property_name
        exact_name_matches = [
            capability.path
            for capability in appliance_data.info.capabilities.values()
            if capability.name == property_name
        ]
        if len(exact_name_matches) == 1:
            return exact_name_matches[0]
        leaf_matches = [
            capability.path
            for capability in appliance_data.info.capabilities.values()
            if capability.path.rsplit(".", 1)[-1] == property_name
        ]
        return leaf_matches[0] if len(leaf_matches) == 1 else property_name

    def _get_entity_appliance_state(self, appliance_id: str) -> ApplianceState | None:
        for entity in self.entities:
            if not hasattr(entity, 'appliance_id') or entity.appliance_id != appliance_id:
                continue
            if hasattr(entity, 'appliance_state'):
                return entity.appliance_state
        return None

    def get_discovered_appliances(self) -> list[Appliance]:
        return self.discovered_appliances

    def get_discovered_appliance_data(self) -> list[ApplianceData]:
        return list(self.discovered_appliance_data.values())

    async def discover_appliances(self):
        try:
            _LOGGER.info("Starting appliance discovery...")
            appliances = await self.api.get_appliances() or []
            self.discovered_appliances = appliances
            self.discovered_appliance_data = {}
            if not appliances:
                _LOGGER.warning("No appliances discovered")
                return []

            _LOGGER.info(f"Discovered {len(appliances)} appliances:")
            for appliance in appliances:
                _LOGGER.info(f"  - {appliance.name} (ID: {appliance.id}, Type: {appliance.type})")
                info = await self.api.get_appliance_info(appliance.id)
                state = await self.api.get_appliance_state(appliance.id)
                if info is None or state is None:
                    _LOGGER.warning("Skipping appliance %s because info or state is unavailable", appliance.id)
                    continue
                self.discovered_appliance_data[appliance.id] = ApplianceData(
                    appliance=appliance,
                    info=info,
                    state=state,
                )

            return appliances
        except Exception as e:
            _LOGGER.error(f"Failed to discover appliances: {e}")
            self.discovered_appliances = []
            self.discovered_appliance_data = {}
            return []
    
    def add_entities(self, entities: list[Any]):
        self.entities.extend(entities)

    async def close(self):
        """Close the API session."""
        if self._closed:
            return

        self._closed = True
        _LOGGER.debug("Closing Electrolux hub")

        if self._livestream_task is not None:
            _LOGGER.debug("Cancelling Electrolux livestream task")
            self._livestream_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._livestream_task
            self._livestream_task = None
            _LOGGER.debug("Electrolux livestream task cancelled")

        if hasattr(self, 'api') and self.api:
            await self.api.close()
