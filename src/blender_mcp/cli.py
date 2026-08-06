"""Command-line entrypoint for Blender MCP."""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sys

from blender_mcp.logging_config import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_HANDLER,
    DEFAULT_LOG_LEVEL,
    configure_logging,
)
from blender_mcp.server import DEFAULT_HOST, DEFAULT_PORT


def _resolve_version() -> str:
    """Look up the installed package version; fall back to a hard-coded string."""
    try:
        from importlib import metadata as _md

        return _md.version("blender-mcp")
    except Exception:
        return "0.0.0+local"


__version__ = _resolve_version()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blender-mcp",
        description=f"Run the Blender MCP server (v{__version__})",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"blender-mcp {__version__}",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("BLENDER_HOST", DEFAULT_HOST),
        help="Blender addon host (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("BLENDER_PORT", DEFAULT_PORT)),
        help="Blender addon port (default: %(default)s)",
    )
    parser.add_argument(
        "--allow-public-bind",
        action="store_true",
        help=(
            "Allow the MCP server to connect to a non-loopback host. Refused by default for safety."
        ),
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("BLENDER_MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL),
        help="Logging level (default: %(default)s)",
    )
    parser.add_argument(
        "--log-format",
        default=os.getenv("BLENDER_MCP_LOG_FORMAT", DEFAULT_LOG_FORMAT),
        help="Logging format string",
    )
    parser.add_argument(
        "--log-handler",
        default=os.getenv("BLENDER_MCP_LOG_HANDLER", DEFAULT_LOG_HANDLER),
        help="Logging handler (console or file)",
    )
    parser.add_argument(
        "--print-client-config",
        choices=["claude", "cursor", "ollama", "lm_studio"],
        help="Print MCP stdio config snippet for a client and exit",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run connectivity diagnostics and exit",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate environment configuration and exit",
    )
    return parser


def _client_config_snippet(client: str, host: str, port: int) -> str:
    args = ["run", "blender-mcp", "--host", host, "--port", str(port)]
    payload = {"mcpServers": {"blender": {"command": "uv", "args": args}}}
    if client == "ollama":
        return "Use this in an MCP-capable Ollama client (Continue/Open WebUI/etc):\n" + json.dumps(
            payload, indent=2
        )
    return json.dumps(payload, indent=2)


def _format_kv(label: str, value: str, status: str = "info") -> str:
    status_to_symbol = {
        "ok": "[OK]    ",
        "warn": "[WARN]  ",
        "fail": "[FAIL]  ",
        "info": "[INFO]  ",
    }
    prefix = status_to_symbol.get(status, "[INFO]  ")
    return f"{prefix}{label}: {value}"


def _safe_bind_host(host: str, allow_public: bool) -> str:
    """Resolve to a bindable loopback address unless the operator opted in."""

    # Local import — the security module pulls stdlib only.
    from blender_mcp.security.transport import safe_bind_host

    return safe_bind_host(host, allow_public=allow_public)


def _run_doctor(host: str, port: int, allow_public: bool = False) -> int:
    print(f"[doctor] blender-mcp {__version__} diagnostics")
    print(f"[doctor] target socket: {host}:{port}")

    failed = False

    if not (1 <= int(port) <= 65535):
        print(_format_kv("port", f"{port} out of range (1-65535)", "fail"))
        failed = True
    else:
        print(_format_kv("port", str(port), "ok"))

    try:
        bind_target = _safe_bind_host(host, allow_public)
        print(_format_kv("host", f"{bind_target} (bind allowed)", "ok"))
    except PermissionError as exc:
        print(_format_kv("host", str(exc), "fail"))
        print(
            "[doctor] Hint: pass --allow-public-bind, or set "
            "BLENDER_MCP_ALLOW_PUBLIC_BIND=1, if you really want this."
        )
        failed = True
        bind_target = host

    try:
        with socket.create_connection((bind_target, port), timeout=2):
            print(_format_kv("tcp-connect", f"connected to {bind_target}:{port}", "ok"))
    except OSError as exc:
        print(_format_kv("tcp-connect", str(exc), "fail"))
        print(
            "[doctor] Hint: open Blender and click 'Connect to MCP server' in the "
            "BlenderMCP sidebar."
        )
        failed = True

    print()
    print("[doctor] system info:")
    print(_format_kv("python", sys.version.split()[0], "info"))
    print(_format_kv("platform", platform.platform(), "info"))
    print(_format_kv("cwd", os.getcwd(), "info"))

    token_set = bool(os.environ.get("BLENDER_MCP_TOKEN", "").strip())
    print(
        _format_kv(
            "token",
            "enabled" if token_set else "disabled (BLENDER_MCP_TOKEN not set)",
            "ok" if token_set else "warn",
        )
    )

    if failed:
        print()
        print("[doctor] FAIL: at least one check did not pass")
        return 1
    print()
    print("[doctor] OK: basic diagnostics passed")
    return 0


def _run_check_config() -> int:
    """Validate env-vars (host/port/token/payload-cap) and exit."""

    print(f"[check-config] blender-mcp {__version__}")
    failed = False

    host = os.environ.get("BLENDER_HOST", "localhost")
    try:
        port = int(os.environ.get("BLENDER_PORT", "9876"))
        if not (1 <= port <= 65535):
            raise ValueError("port out of range")
    except ValueError as exc:
        print(_format_kv("BLENDER_PORT", str(exc), "fail"))
        failed = True
    else:
        print(_format_kv("BLENDER_PORT", str(port), "ok"))

    try:
        _safe_bind_host(host, allow_public=False)
        print(_format_kv("BLENDER_HOST", f"{host} (loopback)", "ok"))
    except PermissionError as exc:
        # Non-loopback bindings are not failures per se, but worth flagging.
        print(_format_kv("BLENDER_HOST", str(exc), "warn"))

    cap = os.environ.get("BLENDER_MCP_MAX_PAYLOAD_BYTES", "")
    if cap:
        try:
            v = int(cap)
            if v <= 0:
                raise ValueError("must be > 0")
            print(_format_kv("BLENDER_MCP_MAX_PAYLOAD_BYTES", f"{v} bytes", "ok"))
        except ValueError as exc:
            print(
                _format_kv(
                    "BLENDER_MCP_MAX_PAYLOAD_BYTES",
                    f"invalid: {exc}",
                    "fail",
                )
            )
            failed = True
    else:
        print(
            _format_kv(
                "BLENDER_MCP_MAX_PAYLOAD_BYTES",
                "unset (using default 4 MiB)",
                "info",
            )
        )

    token = os.environ.get("BLENDER_MCP_TOKEN", "").strip()
    if token:
        if len(token) < 16:
            print(
                _format_kv(
                    "BLENDER_MCP_TOKEN",
                    f"set ({len(token)} chars) — consider 32+ chars",
                    "warn",
                )
            )
        else:
            print(_format_kv("BLENDER_MCP_TOKEN", "set", "ok"))
    else:
        print(
            _format_kv(
                "BLENDER_MCP_TOKEN",
                "unset (single-user loopback mode)",
                "info",
            )
        )

    if failed:
        print()
        print("[check-config] FAIL: invalid configuration")
        return 1
    print()
    print("[check-config] OK: configuration is valid")
    return 0


def main(argv: list[str] | None = None) -> None:
    """Entry point for the blender-mcp package."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    configure_logging(
        level=args.log_level, log_format=args.log_format, handler_type=args.log_handler
    )

    if args.print_client_config:
        print(_client_config_snippet(args.print_client_config, args.host, args.port))
        return
    if args.check_config:
        raise SystemExit(_run_check_config())
    if args.doctor:
        raise SystemExit(_run_doctor(args.host, args.port, allow_public=args.allow_public_bind))

    # Import lazily so logging is configured before server module side effects
    from blender_mcp import server

    # Defence in depth: refuse to even start the server pointing at a
    # non-loopback host unless the operator asked for it.
    try:
        _safe_bind_host(args.host, allow_public=args.allow_public_bind)
    except PermissionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)

    server.main(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
