from datetime import datetime
from typing import Optional, TypedDict

class Token(TypedDict):
    access_token: Optional[str]
    refresh_token: str
    token_expiration_date: Optional[datetime]