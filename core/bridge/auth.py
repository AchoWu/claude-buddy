"""
Bridge Auth — JWT token generation and validation.
"""

import time
import hmac
import hashlib
import json
import base64
import secrets
from typing import Optional


class BridgeAuth:
    """
    Simple JWT-like authentication for Bridge connections.
    Uses HMAC-SHA256 with a per-session secret.
    """

    def __init__(self, secret: str | None = None, token_ttl: int = 86400):
        self._secret = secret or secrets.token_hex(32)
        self._token_ttl = token_ttl  # default: 24 hours
        self._trusted_devices: dict[str, float] = {}  # device_id → trust_expiry

    @property
    def secret(self) -> str:
        return self._secret

    def generate_token(self, device_id: str = "default") -> str:
        """Generate a signed token for a client connection."""
        payload = {
            "device": device_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + self._token_ttl,
        }
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode().rstrip("=")

        sig = hmac.new(
            self._secret.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()[:32]

        return f"{payload_b64}.{sig}"

    def validate_token(self, token: str) -> dict | None:
        """
        Validate a token. Returns payload dict if valid, None if invalid.
        """
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None

            payload_b64, sig = parts

            # Verify signature
            expected_sig = hmac.new(
                self._secret.encode(), payload_b64.encode(), hashlib.sha256
            ).hexdigest()[:32]

            if not hmac.compare_digest(sig, expected_sig):
                return None

            # Decode payload
            padding = 4 - len(payload_b64) % 4
            payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))

            # Check expiry
            if payload.get("exp", 0) < time.time():
                return None

            return payload
        except Exception:
            return None

    def is_trusted_device(self, device_id: str) -> bool:
        """Check if a device is in the trusted cache."""
        expiry = self._trusted_devices.get(device_id, 0)
        if expiry > time.time():
            return True
        self._trusted_devices.pop(device_id, None)
        return False

    def trust_device(self, device_id: str, duration: int = 604800):
        """Cache a device as trusted (default: 7 days)."""
        self._trusted_devices[device_id] = time.time() + duration
