"""API-key authentication. Keys are compared as SHA-256 digests in constant time."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Request


API_KEY_HEADER = "X-API-Key"
MAX_KEY_LENGTH = 256


class UnauthorizedError(Exception):
    """Missing or invalid API key (deliberately indistinguishable)."""


class ApiKeyVerifier:
    def __init__(self, sha256_hex_digests: tuple[str, ...]) -> None:
        self._digests = tuple(bytes.fromhex(h) for h in sha256_hex_digests)

    def verify(self, presented: str | None) -> bool:
        if not presented or len(presented) > MAX_KEY_LENGTH:
            return False
        digest = hashlib.sha256(presented.encode("utf-8")).digest()
        matched = False
        for expected in self._digests:  # no early exit: same work for every key
            matched |= hmac.compare_digest(digest, expected)
        return matched


def require_api_key(request: Request) -> None:
    if not request.app.state.settings.auth_enabled:
        return
    if not request.app.state.api_key_verifier.verify(request.headers.get(API_KEY_HEADER)):
        raise UnauthorizedError()
