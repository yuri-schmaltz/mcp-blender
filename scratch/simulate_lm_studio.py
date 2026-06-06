import json
import subprocess


def call_tool(tool_name, params=None):
    # Handshake sequence
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "TestClient", "version": "1.0"},
        },
    }

    initialized_notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}

    tool_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": params or {}},
    }

    cmd = ["uv", "run", "blender-mcp"]
    process = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    try:
        # Send init
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()

        # Read init response
        while True:
            line = process.stdout.readline()
            if not line:
                break
            if '"id":1' in line:
                break

        # Send initialized
        process.stdin.write(json.dumps(initialized_notification) + "\n")
        process.stdin.flush()

        # Send tool call
        process.stdin.write(json.dumps(tool_request) + "\n")
        process.stdin.flush()

        # Read tool response
        while True:
            line = process.stdout.readline()
            if not line:
                break
            if '"id":2' in line:
                return line
    finally:
        process.terminate()
    return None


print("--- TESTING: get_scene_info ---")
out = call_tool("get_scene_info")
print("OUT:", out)

print("\n--- TESTING: add_primitive (Cube) ---")
out = call_tool("add_primitive", {"type": "CUBE", "location": [1, 2, 3]})
print("OUT:", out)

print("\n--- TESTING: get_viewport_screenshot ---")
out = call_tool("get_viewport_screenshot", {"max_size": 200})
if out:
    print("OUT (first 100):", out[:100])
else:
    print("OUT: None")
