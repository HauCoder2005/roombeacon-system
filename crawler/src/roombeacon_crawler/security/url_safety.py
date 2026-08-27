"""Fail-closed validation for outbound HTTP destinations."""

from __future__ import annotations

from enum import Enum
import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlparse


class UnsafeURLReason(str, Enum):
    """Machine-readable reasons for rejecting an outbound destination."""
    INVALID_URL = "INVALID_URL"
    UNSUPPORTED_SCHEME = "UNSUPPORTED_SCHEME"
    BLOCKED_HOST = "BLOCKED_HOST"
    DNS_RESOLUTION_FAILED = "DNS_RESOLUTION_FAILED"
    NON_PUBLIC_ADDRESS = "NON_PUBLIC_ADDRESS"


class URLSafetyError(ValueError):
    """An outbound URL cannot be proven to target a public HTTP endpoint."""

    def __init__(self, reason: UnsafeURLReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


Resolver = Callable[[str, int], Iterable[str]]


def resolve_host_addresses(hostname: str, port: int) -> set[str]:
    """Resolve all IPv4/IPv6 addresses for a hostname without making an HTTP request."""
    records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return {record[4][0] for record in records}


def validate_public_http_url(url: str, resolver: Resolver = resolve_host_addresses) -> None:
    """Require an HTTP(S) URL whose every resolved address is globally routable."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise URLSafetyError(UnsafeURLReason.INVALID_URL) from None

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise URLSafetyError(UnsafeURLReason.UNSUPPORTED_SCHEME)
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise URLSafetyError(UnsafeURLReason.INVALID_URL)

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise URLSafetyError(UnsafeURLReason.BLOCKED_HOST)

    destination_port = port or (443 if scheme == "https" else 80)
    try:
        literal = ipaddress.ip_address(hostname)
        addresses = {str(literal)}
    except ValueError:
        try:
            addresses = set(resolver(hostname, destination_port))
        except (OSError, socket.gaierror):
            raise URLSafetyError(UnsafeURLReason.DNS_RESOLUTION_FAILED) from None

    if not addresses:
        raise URLSafetyError(UnsafeURLReason.DNS_RESOLUTION_FAILED)

    try:
        parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
    except ValueError:
        raise URLSafetyError(UnsafeURLReason.DNS_RESOLUTION_FAILED) from None

    # is_global rejects loopback, RFC1918/ULA, link-local, multicast,
    # reserved, unspecified and other non-public special-use ranges.
    if any(not address.is_global for address in parsed_addresses):
        raise URLSafetyError(UnsafeURLReason.NON_PUBLIC_ADDRESS)
