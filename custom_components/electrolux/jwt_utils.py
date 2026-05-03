"""JWT utilities for Electrolux Home integration."""

import base64
import json
import logging
from datetime import datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)


def decode_jwt_token(token: str) -> dict[str, Any] | None:
    """Decode JWT token and return payload."""
    try:
        # JWT has 3 parts separated by dots: header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        # Decode payload (second part)
        payload = parts[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        _LOGGER.warning(f"Failed to decode JWT token: {e}")
        return None


def get_token_expiration(access_token: str) -> datetime | None:
    """Get token expiration date from JWT token."""
    payload = decode_jwt_token(access_token)
    if payload and 'exp' in payload:
        # JWT exp is in seconds since epoch
        return datetime.fromtimestamp(payload['exp'])
    return None
