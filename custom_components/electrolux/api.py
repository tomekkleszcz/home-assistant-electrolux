import asyncio
import aiohttp
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any, Optional, Protocol

from .capabilities import ApplianceInfo, capabilities_from_json

from .appliance_state import ApplianceState, ApplianceStateValue, ConnectionState, FanSpeedSetting, FilterType, Mode, Properties, ReportedProperties, State, Status, TemperatureRepresentation, Toggle, Workmode

from .appliance import Appliance
from .const import API_HOST
from .token import Token


_LOGGER = logging.getLogger(__name__)


class TokenRefreshCallback(Protocol):
    async def __call__(self, token: Token) -> None:
        pass


class ElectroluxAPI:
    def __init__(
        self, 
        api_key: str, 
        token: Token,
        on_token_refresh: TokenRefreshCallback
    ):
        self.api_key = api_key
        self.token = token
        self.on_token_refresh = on_token_refresh
        
        self.connector = aiohttp.TCPConnector(keepalive_timeout=30, limit=100)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)

        headers = {
            "Accept": "application/json",
            "Accept-Charset": "utf-8",
            "x-api-key": self.api_key
        }

        self.session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=timeout,
            headers=headers
        )
    

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        if hasattr(self, 'connector') and self.connector and not self.connector.closed:
            await self.connector.close()


    def _auth_interceptor(self, url: str, headers: dict[str, str]) -> dict[str, str]:
        if "/api/v1/token/refresh" in url:
            # Add Content-Type for token refresh
            headers["Content-Type"] = "application/json"
            return headers
        
        if self.token and self.token["access_token"]:
            headers["Authorization"] = f"Bearer {self.token['access_token']}"

        return headers


    async def _ensure_access_token(self) -> None:
        if not self.token or not self.token["token_expiration_date"]:
            return

        if datetime.now() < self.token["token_expiration_date"]:
            return

        _LOGGER.info("Access token expired, refreshing...")
        if not await self.refresh_access_token():
            raise Exception("Failed to refresh access token")


    async def _request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        if url != "/api/v1/token/refresh":
            await self._ensure_access_token()
        
        url = f"{API_HOST}{url}"

        headers = kwargs.get("headers", {})
        headers = self._auth_interceptor(url, headers)

        kwargs['headers'] = headers
        
        async with self.session.request(method, url, **kwargs) as response:
            response.raise_for_status()
            
            body = await response.text()
            response._body = body.encode()
            return response
    

    async def refresh_access_token(self) -> bool:
        try:
            response = await self._request("POST", "/api/v1/token/refresh", json={"refreshToken": self.token["refresh_token"]})
            
            data = await response.json()
            token: Token = {
                "access_token": data["accessToken"],
                "refresh_token": data["refreshToken"],
                "token_expiration_date": datetime.now() + timedelta(seconds=data["expiresIn"])
            }

            self.token = token
            
            await self.on_token_refresh(token)

            return True
        except Exception as e:
            _LOGGER.error(f"Failed to refresh access token: {e}")
            return False


    async def get_appliances(self) -> Optional[list[Appliance]]:
        try:
            _LOGGER.info("Making API request to get appliances...")
            response = await self._request("GET", "/api/v1/appliances")
            data = await response.json()
            _LOGGER.info(f"API response: {data}")

            appliances: list[Appliance] = []
            for item in data:
                appliance = Appliance(
                    id=item["applianceId"],
                    name=item["applianceName"],
                    type=item["applianceType"],
                    created=datetime.fromisoformat(item["created"].replace('Z', '+00:00'))
                )
                appliances.append(appliance)
            
            _LOGGER.info(f"Parsed {len(appliances)} appliances from API response")
            return appliances
        except Exception as e:
            _LOGGER.error(f"Failed to get appliances: {e}")
            return None

    async def get_account_email(self, *, raise_on_error: bool = False) -> Optional[str]:
        try:
            response = await self._request("GET", "/api/v1/users/current/email")
            data = await response.json()
            return data.get("email")
        except aiohttp.ClientResponseError as e:
            if raise_on_error:
                raise
            _LOGGER.error(f"Failed to get account email: {e}")
            return None
        except Exception as e:
            if raise_on_error:
                raise
            _LOGGER.error(f"Failed to get account email: {e}")
            return None

    async def get_livestream_configuration(self) -> Optional[dict[str, Any]]:
        try:
            response = await self._request("GET", "/api/v1/configurations/livestream")
            data = await response.json()
            if not isinstance(data, dict) or not isinstance(data.get("url"), str):
                _LOGGER.error(f"Unexpected livestream configuration response: {data}")
                return None
            return data
        except Exception as e:
            _LOGGER.error(f"Failed to get livestream configuration: {e}")
            return None

    async def stream_livestream_events(self, livestream_url: str) -> AsyncIterator[dict[str, Any]]:
        await self._ensure_access_token()

        headers = {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {self.token['access_token']}",
            "x-api-key": self.api_key,
        }
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
        connect_started_at = asyncio.get_running_loop().time()
        _LOGGER.debug("Opening Electrolux livestream SSE endpoint")

        try:
            async with aiohttp.ClientSession() as websession:
                async with websession.get(livestream_url, timeout=timeout, headers=headers) as response:
                    response.raise_for_status()
                    connect_elapsed = asyncio.get_running_loop().time() - connect_started_at
                    _LOGGER.debug("Connected to Electrolux livestream SSE endpoint after %.2fs", connect_elapsed)

                    while True:
                        event_type = None
                        data_lines: list[str] = []

                        while True:
                            if response.closed:
                                raise ConnectionError("SSE response stream closed unexpectedly")

                            line = await asyncio.wait_for(response.content.readline(), timeout=120)
                            if not line:
                                raise ConnectionError("SSE connection closed by server")

                            line_str = line.decode().strip()
                            if line_str == "":
                                break
                            if line_str.startswith(":"):
                                continue
                            if line_str.startswith("event:"):
                                event_type = line_str.removeprefix("event:").strip()
                            elif line_str.startswith("data:"):
                                data_lines.append(line_str.removeprefix("data:").strip())

                        if event_type == "ping" or not data_lines:
                            continue

                        try:
                            event = json.loads("\n".join(data_lines))
                        except json.JSONDecodeError:
                            _LOGGER.debug("Ignoring invalid livestream event payload: %s", data_lines)
                            continue

                        if isinstance(event, dict):
                            _LOGGER.debug(
                                "Received Electrolux livestream event type=%s payload=%s",
                                event_type or "message",
                                event,
                            )
                            yield event
        finally:
            _LOGGER.debug("Closing Electrolux livestream SSE endpoint")

    async def get_appliance_info(self, appliance_id: str) -> Optional[ApplianceInfo]:
        try:
            response = await self._request("GET", f"/api/v1/appliances/{appliance_id}/info")
            data = await response.json()

            return capabilities_from_json(data)
        except Exception as e:
            _LOGGER.error(f"Failed to get appliance capabilities: {e}")
            return None

    async def get_appliance_state(self, appliance_id: str) -> Optional[ApplianceState]:
        try:
            response = await self._request("GET", f"/api/v1/appliances/{appliance_id}/state")
            data = await response.json()

            reported = data.get("properties", {}).get("reported", {})

            return ApplianceState(
                id=data["applianceId"],
                connectionState=ConnectionState.from_string(data["connectionState"]),
                status=Status.from_string(data["status"]),
                properties=Properties(
                    reported=ReportedProperties(
                        appliance_state=ApplianceStateValue.from_string(reported.get("applianceState")),
                        temperature_representation=TemperatureRepresentation.from_string(reported.get("temperatureRepresentation")),
                        sleep_mode=Toggle.from_string(reported.get("sleepMode")),
                        target_temperature_c=reported.get("targetTemperatureC"),
                        ui_lock_mode=reported.get("uiLockMode"),
                        mode=Mode.from_string(reported.get("mode")),
                        fan_speed_setting=FanSpeedSetting.from_string(reported.get("fanSpeedSetting")),
                        vertical_swing=Toggle.from_string(reported.get("verticalSwing")),
                        filter_state=State.from_string(reported.get("filterState")),
                        ambient_temperature_c=reported.get("ambientTemperatureC"),

                        workmode=Workmode.from_string(reported.get("Workmode")),
                        fan_speed=reported.get("Fanspeed"),
                        filter_life_1=reported.get("FilterLife_1"),
                        filter_type_1=FilterType.from_int(reported.get("FilterType_1")),
                        filter_life_2=reported.get("FilterLife_2"),
                        filter_type_2=FilterType.from_int(reported.get("FilterType_2")),

                        ionizer=reported.get("Ionizer"),
                        ui_light=reported.get("UILight"),
                        safety_lock=reported.get("SafetyLock"),
                        pm_1=reported.get("PM1"),
                        pm_2_5=reported.get("PM2_5"),
                        pm_10=reported.get("PM10"),
                        temperature=reported.get("Temp"),
                        humidity=reported.get("Humidity"),
                        tvoc=reported.get("TVOC"),
                        
                        eco2=reported.get("ECO2"),
                        
                        co2=reported.get("CO2"),

                        uv_state=Toggle.from_string(reported.get("UVState")),
                        pm_2_5_approximate=reported.get("PM2_5_Approximate"),
                    )
                )
            )
        except Exception as e:
            _LOGGER.error(f"Failed to get appliance state: {e}")
            return None
        

    async def send_command(self, appliance_id: str, body: dict[str, Any]) -> bool:
        try:
            await self._request("PUT", f"/api/v1/appliances/{appliance_id}/command", json=body)
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to send command: {e}")
            return False
