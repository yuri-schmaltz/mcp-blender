# Contributing to BlenderMCP

Thanks for helping improve BlenderMCP! This guide covers local setup, ways to iterate without a running Blender UI, and how to run checks before sending changes.

## Local setup

1. Install **Python 3.10+** and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**.
2. Clone the repository and install dependencies into a virtual environment:
   ```bash
   git clone https://github.com/yourusername/blender-mcp.git
   cd blender-mcp
   uv sync
   ```
3. Start the MCP server from the project root (Blender must already be running with the addon enabled):
   ```bash
   uv run blender-mcp
   ```
4. Use `BLENDER_HOST` and `BLENDER_PORT` to point at the Blender addon socket if you’re not using the defaults (`localhost:9876`).

## Developing without a running Blender UI

Need to exercise the MCP server without launching Blender? You can mock the addon socket with a tiny stub server that echoes expected JSON responses:

```bash
python - <<'PY'
import json, socket
HOST, PORT = 'localhost', 9876
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(1)
    print(f"Mock Blender listening on {HOST}:{PORT}")
    conn, _ = s.accept()
    with conn:
        while data := conn.recv(8192):
            cmd = json.loads(data.decode())
            conn.sendall(json.dumps({"status": "success", "result": {"echo": cmd}}).encode())
PY
```

This lets you:
- Validate MCP client/tool wiring and error handling.
- Iterate on request/response schemas without touching Blender APIs.
- Reproduce timeout/reconnect scenarios by stopping and restarting the stub.

When you’re ready to use real Blender features, start Blender, enable `addon.py`, and click **Connect to LLM client** in the sidebar.

## Testing and quality checks

- Run project tests (once they exist) with:
  ```bash
  uv run python -m pytest
  ```
- If you add new tools or networking behavior, also validate the end-to-end flow by starting the MCP server (`uv run blender-mcp`) and issuing a few representative tool calls from your MCP client (LM Studio, Cursor, Continue, etc.).
- Keep diagrams and README sections up to date when changing protocols, environment variables, or addon UI options.

Thanks for contributing!
