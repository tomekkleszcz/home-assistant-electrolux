from homeassistant.helpers.entity import DeviceInfo

from .appliance import Appliance
from .capabilities import ApplianceInfo
from .device import device_info_for_appliance


class ElectroluxApplianceEntity:
    appliance: Appliance
    info: ApplianceInfo

    @property
    def appliance_id(self) -> str:
        return self.appliance.id

    @property
    def device_info(self) -> DeviceInfo:
        return device_info_for_appliance(self.appliance, self.info)
