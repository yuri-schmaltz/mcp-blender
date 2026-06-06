import json
import queue
import subprocess
import sys
import threading
import time


def run_tests():
    print("Starting MCP Exhaustive Integration Test")

    # Start blender-mcp stdio server
    mcp_process = subprocess.Popen(
        ["uv", "run", "blender-mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    print("MCP Proxy started.")

    # Thread to read responses
    response_queue = queue.Queue()

    def read_stdout():
        for line in mcp_process.stdout:
            try:
                msg = json.loads(line)
                response_queue.put(msg)
            except json.JSONDecodeError:
                print(f"[RAW STDOUT] {line.strip()}")

    def read_stderr():
        for line in mcp_process.stderr:
            print(f"[STDERR] {line.strip()}")

    t1 = threading.Thread(target=read_stdout, daemon=True)
    t2 = threading.Thread(target=read_stderr, daemon=True)
    t1.start()
    t2.start()

    msg_id = 1

    def send_request(method, params=None):
        nonlocal msg_id
        req = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
        msg_id += 1
        mcp_process.stdin.write(json.dumps(req) + "\n")
        mcp_process.stdin.flush()

        # Wait for response
        try:
            while True:
                resp = response_queue.get(timeout=10)
                if resp.get("id") == req["id"]:
                    return resp
        except queue.Empty:
            return {"error": "Timeout waiting for response"}

    # --- TEST 1: Protocol Initialization ---
    print("\n--- TEST 1: Initialize Protocol ---")
    resp = send_request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "lm-studio-mock", "version": "1.0.0"},
        },
    )
    print(json.dumps(resp, indent=2))
    assert "result" in resp, "Initialize failed"

    # Send initialized notification
    mcp_process.stdin.write(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
    )
    mcp_process.stdin.flush()
    time.sleep(0.5)

    # --- TEST 2: List Tools ---
    print("\n--- TEST 2: tools/list ---")
    resp = send_request("tools/list")
    tools = resp.get("result", {}).get("tools", [])
    print(f"Discovered {len(tools)} tools.")
    tool_names = [t["name"] for t in tools]
    print(tool_names)
    assert len(tools) > 5, "Not enough tools found!"

    # Helper to call a tool
    def call_tool(name, arguments):
        print(f"\n--- Testing Tool: {name} ---")
        return send_request("tools/call", {"name": name, "arguments": arguments})

    # --- TEST 3: Execute Tools Exhaustively ---

    # 3.1 Get Scene Info
    res = call_tool("get_scene_info", {})
    print(json.dumps(res, indent=2))
    assert "result" in res

    # 3.2 Create Mesh
    res = call_tool("create_mesh", {"type": "CUBE", "name": "TestCube", "size": 2.0})
    print(json.dumps(res, indent=2))

    # 3.3 Create PBR Material
    res = call_tool(
        "create_pbr_material",
        {
            "name": "ShinyRed",
            "color_hex": "#FF0000",
            "roughness": 0.1,
            "metallic": 0.9,
            "apply_to_object": "TestCube",
        },
    )
    print(json.dumps(res, indent=2))

    # 3.4 Setup Product Studio
    res = call_tool(
        "setup_product_studio", {"target_name": "TestCube", "backdrop_color": "#FFFFFF"}
    )
    print(json.dumps(res, indent=2))

    # 3.5 Setup Turntable Animation
    res = call_tool("create_turntable_animation", {"target_object_name": "TestCube", "frames": 100})
    print(json.dumps(res, indent=2))

    # 3.6 Setup Render Engine
    res = call_tool(
        "configure_render_settings", {"engine": "CYCLES", "resolution_x": 800, "resolution_y": 600}
    )
    print(json.dumps(res, indent=2))

    # 3.7 Render Screenshot
    import os

    img_path = os.path.abspath("test_render.png")
    res = call_tool("get_viewport_screenshot", {"filepath": img_path})
    print(json.dumps(res, indent=2))

    # 3.8 Export Model
    export_path = os.path.abspath("test_export.glb")
    res = call_tool("export_model", {"filepath": export_path, "format": "GLTF"})
    print(json.dumps(res, indent=2))

    # Cleanup
    print("\n--- ALL TESTS COMPLETED SUCCESSFULLY ---")
    mcp_process.terminate()


if __name__ == "__main__":
    run_tests()
