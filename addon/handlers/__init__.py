"""API handlers for external services."""
import os
import importlib
import logging

logger = logging.getLogger("BlenderMCP.Handlers")

def load_all_handlers():
    """Dynamically loads all handler modules to register their @mcp_command decorators."""
    handlers_dir = os.path.dirname(__file__)
    for filename in os.listdir(handlers_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = filename[:-3]
            try:
                importlib.import_module(f".{module_name}", package=__name__)
            except Exception as e:
                logger.error(f"Failed to load handler {module_name}: {e}")

load_all_handlers()
