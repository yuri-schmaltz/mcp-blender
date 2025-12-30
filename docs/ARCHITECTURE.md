# BlenderMCP Architecture

> **Decisões arquiteturais e convenções mínimas estão documentadas em [ADR-0001-estrutura-modular.md](ADR-0001-estrutura-modular.md). Consulte para padrões de modularização, logging, UI e testes. Atualize sempre que houver mudanças relevantes.**

## Overview

BlenderMCP is a Model Context Protocol (MCP) server that enables AI assistants to control Blender 3D through a socket-based communication layer. The system consists of two main components:

1. **Blender Addon** (`addon.py`) - Runs inside Blender, listens on a TCP socket
2. **MCP Server** (`src/blender_mcp/`) - FastMCP-based server that communicates with the addon

## System Architecture

```
┌──────────────────┐         MCP Protocol          ┌─────────────────┐
│   AI Assistant   │◄──────────────────────────────►│   MCP Server    │
│  (Claude, etc)   │     (stdio/SSE transport)     │  (FastMCP)      │
└──────────────────┘                                └────────┬────────┘
                                                             │
                                                    TCP Socket (9876)
                                                             │
                                                    ┌────────▼────────┐
                                                    │  Blender Addon  │
                                                    │   (addon.py)    │
                                                    └────────┬────────┘
                                                             │
                                                    ┌────────▼────────┐
                                                    │  Blender API    │
                                                    │      (bpy)      │
                                                    └─────────────────┘
```

## Components

### 1. Blender Addon (`addon.py`)

**Purpose**: Socket server running inside Blender that executes commands.

**Key Classes**:
- `BlenderMCPServer`: Main server class with socket management
  - `_server_loop()`: Accepts connections in background thread
  - `_handle_client()`: Processes commands from MCP server
  - `execute_command()`: Dispatches to specific handlers

**Command Handlers**:
- Scene operations: `get_scene_info()`, `get_object_info()`, `get_viewport_screenshot()`
- Code execution: `execute_code()` (sandboxed via MCP server)
- Poly Haven: `download_polyhaven_asset()`, `set_texture()`
- Hyper3D: `create_rodin_job()`, `poll_rodin_job_status()`, `import_generated_asset()`
- Sketchfab: `search_sketchfab_models()`, `download_sketchfab_model()`

**Communication Protocol**:
```python
# Request format
{
    "type": "command_name",
    "params": { ...command_parameters... }
}

# Response format
{
    "status": "success"|"error",
    "result": { ...command_result... } | None,
    "message": "error message" | None
}
```

### 2. MCP Server (`src/blender_mcp/`)

**Purpose**: MCP protocol adapter that translates MCP tool calls to Blender commands.

#### Module Structure

```
src/blender_mcp/
├── server.py           # FastMCP server & tool implementations
├── cli.py              # Command-line entry point
├── gui.py              # PySide6 configuration GUI
├── logging_config.py   # Logging setup
├── constants.py        # Centralized constants
├── security/
│   ├── sandbox.py      # Sandboxed code execution
│   └── __init__.py
├── shared/
│   ├── validators.py   # Input validation utilities
│   ├── retry.py        # Retry with exponential backoff
│   └── __init__.py
└── temp_file_manager.py # Temporary file cleanup (future use)
```

#### Key Modules

**`server.py`** (1142 lines):
- `BlenderConnection`: Socket connection wrapper with retry logic
- MCP tool implementations decorated with `@mcp.tool()`
- Connection management and error handling

**`security/sandbox.py`**:
- `RateLimiter`: Global rate limiting for code execution
- `create_safe_namespace()`: Creates restricted Python environment
- `validate_code()`: Checks code against forbidden patterns
- `execute_code_safe()`: Executes with timeout (platform-aware for Windows)

**`shared/validators.py`**:
- `validate_port()`, `validate_api_key()`, `validate_asset_id()`
- `validate_filename()`, `validate_filepath()`, `validate_resolution()`
- Consistent ValidationError exceptions

**`shared/retry.py`**:
- `retry_with_backoff()`: Generic retry decorator
- `retry_on_network_error()`: Network-specific retry with transient error detection
- Exponential backoff with configurable max delay

## Data Flow

### 1. Tool Invocation Flow

```
1. AI calls MCP tool (e.g., get_scene_info)
   ↓
2. FastMCP routes to server.py function
   ↓
3. Input validation (validators.py)
   ↓
4. BlenderConnection.send_command()
   │  - JSON serialization
   │  - Socket send
   │  - Retry on failure
   ↓
5. Blender addon receives command
   │  - JSON deserialization
   │  - Handler lookup
   │  - Execute in main thread (bpy.app.timers)
   ↓
6. Result returned to MCP server
   ↓
7. JSON formatted for AI assistant
```

### 2. Code Execution Flow (Sandboxed)

```
1. AI calls execute_blender_code(code)
   ↓
2. server.py validates and rate-limits
   ↓
3. sandbox.py: validate_code(code)
   │  - Check for forbidden imports
   │  - Check for file system access
   │  - Check for network access
   ↓
4. sandbox.py: create_safe_namespace()
   │  - Limited builtins
   │  - No __import__, eval, exec
   │  - Only allowed modules
   ↓
5. sandbox.py: execute_code_safe()
   │  - Platform-aware timeout (signal/threading)
   │  - Capture stdout
   │  - Return result or error
   ↓
6. Result sent to Blender addon
   │  - Addon executes in Blender context
   │  - Full bpy access (addon is trusted)
   ↓
7. Result returned to AI
```

### 3. Asset Download Flow

```
1. AI calls download_polyhaven_asset(id, type, resolution)
   ↓
2. Validation: asset_id, asset_type, resolution
   ↓
3. MCP server sends command to addon
   ↓
4. Addon fetches from PolyHaven API
   │  - GET /files/{asset_id}
   │  - Download binary data
   │  - Create temp file
   ↓
5. Import into Blender (type-specific):
   │  - HDRI: Load as environment texture
   │  - Texture: Create material with PBR maps  
   │  - Model: Import GLTF/FBX/OBJ
   ↓
6. Cleanup temp files (finally block)
   ↓
7. Return success with imported object names
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BLENDER_HOST` | `localhost` | Addon socket host |
| `BLENDER_PORT` | `9876` | Addon socket port |
| `BLENDER_SOCKET_TIMEOUT` | `10` | Socket timeout (seconds) |
| `BLENDER_CONNECT_ATTEMPTS` | `3` | Connection retry attempts |
| `BLENDER_COMMAND_ATTEMPTS` | `3` | Command retry attempts |
| `BLENDER_RETRY_BACKOFF` | `0.5` | Retry delay (seconds) |
| `BLENDER_MCP_LOG_LEVEL` | `INFO` | Logging level |
| `BLENDER_MCP_LOG_FORMAT` | `text` | Log format (text/json) |
| `BLENDER_MCP_LOG_HANDLER` | `console` | Log output (console/file) |
| `BLENDER_MCP_LOG_FILE` | `blender_mcp.log` | Log file path |
| `BLENDER_MCP_ENV_FILE` | - | Path to .env file for GUI |

### Connection Lifecycle

1. **Startup**: MCP server started by AI client (stdio transport)
2. **Connection**: `BlenderConnection` created on first tool call
3. **Lazy connect**: Socket connection established on demand
4. **Retry logic**: Automatic reconnection on failures
5. **Cleanup**: Connection closed on server shutdown

## Security Model

### Sandboxing

**MCP Server Side** (Limited):
- Rate limiting (10 requests/60s)
- Code validation (forbidden patterns)
- Limited namespace (no eval, exec, __import__)
- Timeout enforcement (5s default)

**Addon Side** (Trusted):
- Full bpy access (runs in Blender process)
- File system access (downloads, screenshots)
- Network access (API calls)

> **Note**: The addon is TRUSTED code. Sandboxing in MCP server is defense-in-depth
> but the addon executes whatever code it receives. Only use BlenderMCP with
> trusted AI assistants.

### Input Validation

All user inputs validated before processing:
- **Port numbers**: 1024-65535 range
- **API keys**: Minimum length, no placeholders
- **Asset IDs**: Alphanumeric + underscore/hyphen only
- **File paths**: No parent directory references (`../`)
- **Resolutions**: Whitelisted values only

## Error Handling

### Retry Strategy

**Network Errors** (transient):
- Automatic retry with exponential backoff
- Max 3 attempts by default
- Retryable: `TimeoutError`, `ConnectionError`, HTTP 5xx

**Validation Errors** (permanent):
- Immediate failure, no retry
- Clear error messages with field details
- Type: `ValidationError`

**Blender Errors**:
- Captured and returned in response
- Stack trace logged on server side
- User sees concise error message

### Cleanup Guarantees

**Temporary Files**:
- All temp files use `try-finally` blocks
- Cleanup on both success and error paths
- Warning logged if cleanup fails (non-fatal)

**Network Connections**:
- Socket closed in context managers
- Automatic reconnection on next request
- Stale connections detected and recycled

## Performance Considerations

### Bottlenecks

1. **Socket latency**: ~10-50ms per command (local)
2. **Blender main thread**: Commands queued via `bpy.app.timers`
3. **Large assets**: Downloads can take seconds to minutes
4. **Complex scenes**: `get_scene_info()` limited to 10 objects

### Optimizations

- **Connection pooling**: Reuse socket connections  
- **Lazy initialization**: Connect only when needed
- **Asset limits**: Restrict result set sizes (20 for PolyHaven)
- **Minimal serialization**: Only essential data in responses
- **Concurrent requests**: Multiple tools can run in parallel (MCP layer)

## Testing Strategy

### Unit Tests
```
tests/unit/
├── test_validators.py      # Input validation
├── test_sandbox.py          # Code execution sandbox
├── test_windows_timeout.py  # Platform-specific timeout
└── test_retry.py            # Retry logic (future)
```

### Integration Tests
```
tests/
├── test_server.py           # MCP server tools
│   ├── Mock Blender connection
│   ├── Tool invocation tests
│   └── Error handling tests
└── integration/
    └── mock_blender_server.py  # Development mock
```

### Manual Testing

Use the mock server for development without Blender:
```bash
python -m tests.integration.mock_blender_server
# In another terminal:
uvx blender-mcp
```

## Future Improvements

### Architecture
- [ ] Refactor `addon.py` into modules (1878 lines → 200-300 each)
- [ ] Plugin system for external tool integrations
- [ ] Event streaming for progress updates
- [ ] Websocket upgrade for bidirectional communication

### Features
- [ ] Batch operations (multiple commands in one request)
- [ ] File upload/download via base64 encoding
- [ ] Render job management
- [ ] Animation timeline control

### Observability
- [ ] Structured logging (JSON format)
- [ ] Metrics collection (request counts, latency)
- [ ] Health check endpoint
- [ ] Distributed tracing (OpenTelemetry)

## Development Workflow

### Prerequisites
- Python 3.10+
- uv package manager
- Blender 3.0+ (for integration testing)

### Setup
```bash
# Clone repository
git clone https://github.com/modelcontextprotocol/blender-mcp
cd blender-mcp

# Install dependencies
uv sync

# Run tests
uv run pytest

# Install in development mode
uv pip install -e .
```

### Adding a New Tool

1. **Define tool in `server.py`**:
```python
@mcp.tool()
def my_new_tool(ctx: Context, param: str) -> str:
    """Tool description."""
    # Validate inputs
    from blender_mcp.shared.validators import validate_asset_id
    param = validate_asset_id(param)
    
    # Send command to Blender
    blender = get_blender_connection()
    result = blender.send_command("my_command", {"param": param})
    return json.dumps(result)
```

2. **Add handler in `addon.py`**:
```python
def my_command(self, param):
    """Execute the command."""
    # Use bpy API
    obj = bpy.data.objects.get(param)
    return {"found": obj is not None}
```

3. **Register in handlers dict**:
```python
handlers = {
    "my_command": self.my_command,
    # ... existing handlers
}
```

4. **Write tests**:
```python
def test_my_new_tool():
    # Mock Blender connection
    # Call tool
    # Assert result
```

## References

- [MCP Protocol Specification](https://modelcontextprotocol.io/docs)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Blender Python API](https://docs.blender.org/api/current/)
- [PolyHaven API](https://github.com/Poly-Haven/Public-API)
