"""Standardized MCP and JSON-RPC Exceptions for BlenderMCP."""

class MCPError(Exception):
    """Base exception for all MCP related errors adhering to JSON-RPC 2.0 specs."""
    def __init__(self, code: int, message: str, data: dict = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}

    def to_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "data": self.data
        }

class ParseError(MCPError):
    def __init__(self, message="Parse error", data=None):
        super().__init__(-32700, message, data)

class InvalidRequestError(MCPError):
    def __init__(self, message="Invalid Request", data=None):
        super().__init__(-32600, message, data)

class MethodNotFoundError(MCPError):
    def __init__(self, message="Method not found", data=None):
        super().__init__(-32601, message, data)

class InvalidParamsError(MCPError):
    def __init__(self, message="Invalid params", data=None):
        super().__init__(-32602, message, data)

class InternalError(MCPError):
    def __init__(self, message="Internal error", data=None):
        super().__init__(-32603, message, data)

class MCPPermissionError(MCPError):
    """Custom MCP Error for when security/sandbox policies block execution."""
    def __init__(self, message="Permission denied", data=None):
        super().__init__(-32001, message, data)
