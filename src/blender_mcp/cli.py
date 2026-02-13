"""Command-line entrypoint for Blender MCP."""

from __future__ import annotations

import argparse
import json
import os

from blender_mcp.logging_config import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_HANDLER,
    DEFAULT_LOG_LEVEL,
    configure_logging,
)
from blender_mcp.server import DEFAULT_HOST, DEFAULT_PORT


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Blender MCP server")
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
    return parser


def _client_config_snippet(client: str, host: str, port: int) -> str:
    args = ["run", "blender-mcp", "--host", host, "--port", str(port)]
    payload = {"mcpServers": {"blender": {"command": "uv", "args": args}}}
    if client == "ollama":
        return (
            "Use this in an MCP-capable Ollama client (Continue/Open WebUI/etc):\n"
            + json.dumps(payload, indent=2)
        )
    return json.dumps(payload, indent=2)


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

    # Import lazily so logging is configured before server module side effects
    from blender_mcp import server

    server.main(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
