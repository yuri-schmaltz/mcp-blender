"""Transport hardening helpers for the Blender addon side.

Sister module of ``src/blender_mcp/security/transport.py``. The two are kept
in sync intentionally — the addon runs inside Blender's own Python
interpreter with a constrained module layout, so we ship a compact copy of
the safety helpers here instead of trying to share code across the
``addon/`` and ``src/`` trees.

If you change the public API in one place, mirror it in the other.
"""

from __future__ import annotations

import hmac
import ipaddress
import os

# These names mirror blender_mcp.constants on the MCP server side. We
# duplicate them so the addon doesn't need to import from src/.
DEFAULT_MAX_PAYLOAD_BYTES = 4 * 1024 * 1024  # 4 MiB
MAX_PAYLOAD_ENV_VAR = "BLENDER_MCP_MAX_PAYLOAD_BYTES"
TOKEN_ENV_VAR = "BLENDER_MCP_TOKEN"
TOKEN_HEADER = "X-BlenderMCP-Token"
PUBLIC_BIND_ENV_VAR = "BLENDER_MCP_ALLOW_PUBLIC_BIND"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class PayloadTooLargeError(Exception):
    """Raised when the incoming command exceeds ``BLENDER_MCP_MAX_PAYLOAD_BYTES``."""


class TokenMismatchError(Exception):
    """Raised when the incoming command carries an invalid or missing token."""


def enforce_payload_cap(payload) -> None:
    """Raise :class:`PayloadTooLargeError` when the payload is too big.

    Accepts bytes / str / dict / list. Containers are sized as the UTF-8
    length of their ``json.dumps`` output (i.e. what we'd send on the wire).
    """

    if isinstance(payload, str):
        size = len(payload.encode("utf-8"))
    elif isinstance(payload, (bytes, bytearray, memoryview)):
        size = len(payload)
    else:
        import json as _json

        size = len(_json.dumps(payload).encode("utf-8"))
    raw = os.environ.get(MAX_PAYLOAD_ENV_VAR)
    try:
        limit = int(raw) if raw else DEFAULT_MAX_PAYLOAD_BYTES
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_PAYLOAD_BYTES
    if size > limit:
        raise PayloadTooLargeError(
            f"payload of {size} bytes exceeds limit of {limit} bytes "
            f"({MAX_PAYLOAD_ENV_VAR})"
        )


def _configured_token() -> str:
    return os.environ.get(TOKEN_ENV_VAR, "").strip()


def matches_token(headers) -> bool:
    """Return True if the headers carry the configured token (or none is set)."""

    expected = _configured_token()
    if not expected:
        return True
    if not headers:
        return False
    candidate = None
    expected_header = TOKEN_HEADER.upper()
    for k, v in headers.items():
        if isinstance(k, str) and k.upper() == expected_header:
            candidate = v
            break
    if not isinstance(candidate, str):
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def validate_token(headers) -> None:
    """Raise :class:`TokenMismatchError` when the token does not match."""

    if not matches_token(headers):
        raise TokenMismatchError("missing or invalid X-BlenderMCP-Token")


def is_loopback_host(host: str) -> bool:
    if not host:
        return False
    if host.strip().lower() in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def safe_bind_host(host: str) -> str:
    """Refuse non-loopback binds unless ``BLENDER_MCP_ALLOW_PUBLIC_BIND=1``."""

    if not host:
        raise PermissionError("empty bind host is not allowed")

    if host.strip().lower() in LOOPBACK_HOSTS:
        return host
    if host.strip() in {"0.0.0.0", "::", "*"}:
        public = os.environ.get(PUBLIC_BIND_ENV_VAR, "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not public:
            raise PermissionError(
                f"refusing to bind to {host!r}: public interfaces are disabled. "
                f"Set {PUBLIC_BIND_ENV_VAR}=1 if you really mean it."
            )
        return host

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        public = os.environ.get(PUBLIC_BIND_ENV_VAR, "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not public:
            raise PermissionError(
                f"refusing to bind to {host!r}: non-loopback hosts require "
                f"{PUBLIC_BIND_ENV_VAR}=1."
            )
        return host

    if ip.is_loopback:
        return host

    public = os.environ.get(PUBLIC_BIND_ENV_VAR, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not public:
        raise PermissionError(
            f"refusing to bind to {host!r}: non-loopback addresses require "
            f"{PUBLIC_BIND_ENV_VAR}=1."
        )
    return host
