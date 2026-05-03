from homeassistant.helpers.entity import DeviceInfo

from .appliance import Appliance
from .capabilities import ApplianceInfo
from .const import DOMAIN


def device_info_for_appliance(appliance: Appliance, info: ApplianceInfo) -> DeviceInfo:
    appliance_info = info.appliance_info

    return DeviceInfo(
        identifiers={(DOMAIN, appliance.id)},
        manufacturer=appliance_info.brand,
        model=appliance_info.model,
        model_id=appliance_info.pnc,
        name=appliance.name,
        serial_number=appliance_info.serial_number,
    )
