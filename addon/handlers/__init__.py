"""API handlers for external services and core functionality."""

import os
import pkgutil
import importlib

# Auto-discovery: import all modules in this package to ensure @mcp_tool decorators are executed
__all__ = []

package_dir = os.path.dirname(__file__)
for _, module_name, _ in pkgutil.iter_modules([package_dir]):
    if not module_name.startswith('_'):
        try:
            importlib.import_module(f".{module_name}", package=__name__)
            __all__.append(module_name)
        except Exception as e:
            print(f"BlenderMCP Auto-discovery error loading handler '{module_name}': {e}")
