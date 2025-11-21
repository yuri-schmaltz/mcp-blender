"""Command-line entrypoint for Blender MCP."""

from blender_mcp.logging_config import configure_logging


def main() -> None:
    """Entry point for the blender-mcp package."""
    configure_logging()

    # Import lazily so logging is configured before server module side effects
    from blender_mcp import server

    server.main()


if __name__ == "__main__":
    main()
