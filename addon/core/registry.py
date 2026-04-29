"""Central Registry for MCP tools and handlers in BlenderMCP."""

from typing import Callable, Dict, Optional

class MCPRegistry:
    """Registry pattern implementation for decoupling MCP handlers from the core server."""
    
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, dict] = {}

    def register(self, name: str, schema: Optional[dict] = None):
        """Decorator to register a function as an MCP tool."""
        def decorator(func: Callable):
            self._tools[name] = func
            if schema:
                self._schemas[name] = schema
            return func
        return decorator

    def get_tool(self, name: str) -> Optional[Callable]:
        """Retrieve a registered tool by its name."""
        return self._tools.get(name)

    def get_all_tools(self) -> Dict[str, Callable]:
        """Return a copy of all registered tools."""
        return self._tools.copy()

    def get_all_schemas(self) -> list:
        """Return formatted schemas for MCP compliance."""
        return [
            {"name": name, **schema} 
            for name, schema in self._schemas.items()
        ]

# Global instance of the registry
mcp_registry = MCPRegistry()

# Alias for ease of use
mcp_tool = mcp_registry.register
