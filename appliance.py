from dataclasses import dataclass
from datetime import datetime


@dataclass
class Appliance:
    id: str
    name: str
    type: str
    created: datetime