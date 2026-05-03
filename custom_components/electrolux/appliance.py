from dataclasses import dataclass
from datetime import datetime

from .appliance_state import ApplianceState
from .capabilities import ApplianceInfo


@dataclass
class Appliance:
    id: str
    name: str
    type: str
    created: datetime


@dataclass
class ApplianceData:
    appliance: Appliance
    info: ApplianceInfo
    state: ApplianceState

    @property
    def is_dam(self) -> bool:
        return (
            self.appliance.id.startswith("1:")
            or self.appliance.type.upper().startswith("DAM_")
            or self.info.data_model_version is not None
            or self.state.data_model_version is not None
        )
