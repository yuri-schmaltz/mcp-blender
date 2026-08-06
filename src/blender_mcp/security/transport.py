"""Transport-level hardening helpers shared by the MCP server and the addon.

These helpers are deliberately small and depend only on the standard library
so they can be imported in the Blender addon (which has a constrained Python
environment) as well as in the FastMCP server runtime.

Three concerns are covered:

1. ``safe_bind_host`` — refuse to bind a socket to a non-loopback address
   unless the operator explicitly opts in via the
   ``BLENDER_MCP_ALLOW_PUBLIC_BIND`` environment variable (or the matching
   CLI flag).

2. ``validate_token`` / ``matches_token`` — server-side check that the
   incoming command carries the configured shared secret in the
   ``X-BlenderMCP-Token`` header. The check is a constant-time comparison
   so the secret cannot be leaked via timing analysis. When no token is
   configured the helper is a no-op and returns True (so single-user
   loopback setups keep working).

3. ``enforce_payload_cap`` — protect Blender from runaway clients that
   send enormous JSON blobs. The default cap is 4 MiB and can be tuned
   via ``BLENDER_MCP_MAX_PAYLOAD_BYTES``.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import socket
from typing import Any

from ..constants import (
    DEFAULT_MAX_PAYLOAD_BYTES,
    LOOPBACK_HOSTS,
    MAX_PAYLOAD_ENV_VAR,
    PUBLIC_BIND_ENV_VAR,
    TOKEN_ENV_VAR,
    TOKEN_HEADER,
)

__all__ = [
    "safe_bind_host",
    "validate_token",
    "matches_token",
    "enforce_payload_cap",
    "PayloadTooLargeError",
    "TokenMismatchError",
]


class PayloadTooLargeError(Exception):
    """Raised when an incoming payload exceeds ``MAX_PAYLOAD_BYTES``."""


class TokenMismatchError(Exception):
    """Raised when an incoming command carries an invalid or missing token."""


def _env_flag(name: str, default: bool = False) -> bool:
    """Best-effort truthy parser for env-vars. ``"1"``, ``"true"``, ``"yes"``."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def safe_bind_host(host: str, *, allow_public: bool | None = None) -> str:
    """Return ``host`` if it is safe to bind, raise ``PermissionError`` otherwise.

    A host is considered safe when it is in :data:`LOOPBACK_HOSTS` (including
    the magic name ``localhost``) or when the operator has explicitly opted in
    via ``BLENDER_MCP_ALLOW_PUBLIC_BIND=1``.

    The check is intentionally permissive about the *form* of the host: any
    valid IPv4/IPv6 literal or DNS hostname is accepted, only the binding
    address is policed. ``0.0.0.0`` and ``::`` are treated as public
    (they bind to every interface).
    """

    if not host:
        raise PermissionError("empty bind host is not allowed")

    normalised = host.strip().lower()
    if normalised in LOOPBACK_HOSTS:
        return host

    # Wildcard addresses bind to all interfaces -> treat as public.
    if normalised in {"0.0.0.0", "::", "*"}:
        public = allow_public if allow_public is not None else _env_flag(PUBLIC_BIND_ENV_VAR)
        if not public:
            raise PermissionError(
                f"refusing to bind to {host!r}: public interfaces are disabled. "
                f"Set {PUBLIC_BIND_ENV_VAR}=1 if you really mean it."
            )
        return host

    # Try to interpret as an IP address for a more precise decision.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A DNS name we cannot resolve offline — fall back to the env flag.
        public = allow_public if allow_public is not None else _env_flag(PUBLIC_BIND_ENV_VAR)
        if not public:
            raise PermissionError(
                f"refusing to bind to {host!r}: non-loopback hosts require {PUBLIC_BIND_ENV_VAR}=1."
            )
        return host

    if ip.is_loopback:
        return host

    public = allow_public if allow_public is not None else _env_flag(PUBLIC_BIND_ENV_VAR)
    if not public:
        raise PermissionError(
            f"refusing to bind to {host!r}: non-loopback addresses require {PUBLIC_BIND_ENV_VAR}=1."
        )
    return host


def _configured_token() -> str:
    return os.environ.get(TOKEN_ENV_VAR, "").strip()


def matches_token(headers: dict[str, Any] | None) -> bool:
    """Return True if the headers carry the right token (or no token is set)."""

    expected = _configured_token()
    if not expected:
        return True
    if not headers:
        return False
    # Headers are case-insensitive; the addon sends exactly the canonical name
    # but defence in depth costs nothing here.
    candidate = None
    expected_header = TOKEN_HEADER.upper()
    for k, v in headers.items():
        if isinstance(k, str) and k.upper() == expected_header:
            candidate = v
            break
    if not isinstance(candidate, str):
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def validate_token(headers: dict[str, Any] | None) -> None:
    """Raise :class:`TokenMismatchError` when the token does not match."""

    if not matches_token(headers):
        raise TokenMismatchError("missing or invalid token")


def enforce_payload_cap(payload: bytes | bytearray | memoryview | str) -> None:
    """Raise :class:`PayloadTooLargeError` if the payload exceeds the cap."""

    if isinstance(payload, str):
        size = len(payload.encode("utf-8"))
    else:
        size = len(payload)
    limit_raw = os.environ.get(MAX_PAYLOAD_ENV_VAR)
    try:
        limit = int(limit_raw) if limit_raw else DEFAULT_MAX_PAYLOAD_BYTES
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_PAYLOAD_BYTES
    if size > limit:
        raise PayloadTooLargeError(
            f"payload of {size} bytes exceeds limit of {limit} bytes ({MAX_PAYLOAD_ENV_VAR})"
        )


def is_loopback_host(host: str) -> bool:
    """Best-effort loopback check used by validators in the rest of the project."""

    if not host:
        return False
    if host.strip().lower() in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resolve_loopback(host: str) -> str:
    """Convert ``localhost`` to ``127.0.0.1`` so the address is bindable."""

    if host.strip().lower() in {"localhost", ""}:
        return "127.0.0.1"
    return host


def can_resolve(host: str, port: int, timeout: float = 1.0) -> bool:
    """Quick TCP-connect sanity check used by --doctor."""

    try:
        with socket.create_connection((resolve_loopback(host), port), timeout=timeout):
            return True
    except OSError:
        return False
