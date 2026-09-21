"""Derive a client identity without trusting spoofable forwarding headers."""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Iterable

from starlette.requests import Request

# Cloudflare publishes these ranges at https://www.cloudflare.com/ips/.
# Keep this list versioned and override it with CLOUDFLARE_TRUSTED_CIDRS when
# the deployment requires a narrower or newer set.
_CLOUDFLARE_CIDRS = (
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "172.64.0.0/13",
    "131.0.72.0/22",
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
)


def client_identity(request: Request) -> str:
    """Return the direct peer, or a validated CF-Connecting-IP behind Cloudflare."""
    peer = request.client.host if request.client else "unknown"
    peer_ip = _parse_ip(peer)
    if peer_ip is None or not _is_trusted_cloudflare(peer_ip):
        return peer

    forwarded = request.headers.get("CF-Connecting-IP")
    forwarded_ip = _parse_ip(forwarded)
    if forwarded_ip is not None and forwarded_ip.is_global:
        return str(forwarded_ip)
    return peer


def _parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted_cloudflare(peer: ipaddress._BaseAddress) -> bool:
    return any(peer in network for network in _trusted_networks())


def _trusted_networks() -> tuple[ipaddress._BaseNetwork, ...]:
    configured = os.getenv("CLOUDFLARE_TRUSTED_CIDRS")
    values: Iterable[str] = configured.split(",") if configured else _CLOUDFLARE_CIDRS
    networks = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value.strip(), strict=False))
        except ValueError as exc:
            raise RuntimeError(f"Invalid CLOUDFLARE_TRUSTED_CIDRS entry: {value}") from exc
    return tuple(networks)
