from datetime import datetime
from typing import Optional, TypedDict

class Token(TypedDict):
    access_token: str
    refresh_token: str
    token_expiration_date: datetime