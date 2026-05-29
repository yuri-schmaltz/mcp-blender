import sys
import os
import site

# ROOT path
ROOT = '/home/yurix/Documentos/mcp-blender'
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure user site-packages are in sys.path (critical for flatpak sandbox)
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.append(user_site)

import bpy
import time
import threading
import json
import urllib.request
import logging

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout)

# Monkeypatch litellm.completion to remove tools parameter (prevents 9B model confusion)
try:
    import litellm
    old_completion = litellm.completion
    def completion_without_tools(*args, **kwargs):
        if "tools" in kwargs:
            print("MONKEYPATCH: Stripping tools from litellm request for local LLM stability")
            kwargs.pop("tools")
        return old_completion(*args, **kwargs)
    litellm.completion = completion_without_tools
except Exception as e:
    print(f"Failed to monkeypatch litellm: {e}")

# Import components
from addon.server import BlenderMCPServer
import addon.core.router as router
import addon.handlers as handlers
from addon.webui_server import BlenderMCPWebUIServer
from addon.handlers.llm_handler import handle_chat_request_headless

# Load handlers
handlers.load_all_handlers()

# Monkeypatch timers for background mode (queue-based thread bridge)
print("--- MONKEYPATCHING TIMERS FOR THREAD SAFETY ---")
import queue
import concurrent.futures

main_queue = queue.Queue()

def custom_register(func, first_interval=0.0):
    main_queue.put(func)
    return None

bpy.app.timers.register = custom_register

# Monkeypatch _get_system_prompt in llm_handler to guide Ollama correctly
import addon.handlers.llm_handler as llm_handler
def mock_get_system_prompt():
    return (
        "You are a Blender assistant. Write Python code in a ```python block. "
        "IMPORTANT: bpy.ops.mesh.primitive_cylinder_add() returns {'FINISHED'}, NOT the object. "
        "To access or rename the newly created object, use the active object, e.g.:\n"
        "bpy.ops.mesh.primitive_cylinder_add(radius=1.0, depth=4.0, location=(0,0,0))\n"
        "cylinder = bpy.context.active_object\n"
        "cylinder.name = 'Cylinder'"
    )
llm_handler._get_system_prompt = mock_get_system_prompt

# Thread-safe execution callback that runs commands on the main thread
def safe_execute_command(tool_command):
    future = concurrent.futures.Future()
    def _run():
        try:
            res = router.execute_command(tool_command)
            future.set_result(res)
        except Exception as e:
            future.set_result({"status": "error", "message": str(e)})
    main_queue.put(_run)
    return future.result()

class IntegratedServer(BlenderMCPServer):
    def __init__(self, port):
        super().__init__(host="0.0.0.0", port=port)
        self.command_executor = safe_execute_command

# Initialize and start MCP socket server
bpy.types.blendermcp_server = IntegratedServer(9876)
bpy.types.blendermcp_server.start()
print("--- BLENDER MCP SOCKET SERVER LISTENING ON 9876 ---")

# Initialize and start WebUI server
bpy.types.blendermcp_webui_server = BlenderMCPWebUIServer(port=8080)
bpy.types.blendermcp_webui_server.start()
print("--- BLENDER MCP WEBUI SERVER LISTENING ON 8080 ---")

# Configure preferences for Ollama
addon_name = "bl_ext.user_default.mcp_blender"
if addon_name not in bpy.context.preferences.addons:
    for name in bpy.context.preferences.addons.keys():
        if "mcp_blender" in name:
            addon_name = name
            break

# Monkeypatch resolve_addon_package to return the correct registered extension name
import addon.utils.helpers as helpers
helpers.resolve_addon_package = lambda *args, **kwargs: addon_name

print(f"Resolving preferences for addon: {addon_name}")
prefs = bpy.context.preferences.addons[addon_name].preferences

# Clear scene objects safely without resetting factory settings
for obj in list(bpy.context.scene.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

test_success = True
test_error_message = ""

def run_tests():
    global test_success, test_error_message
    time.sleep(3) # Wait for servers and port forwarder to spin up
    
    print("Setting active LLM preferences...")
    prefs.llm_provider = 'OLLAMA'
    prefs.llm_base_url = 'http://127.0.0.1:11434'
    
    # Try to set model directly now that connection is active
    try:
        prefs.llm_model_ollama = 'qwen3.5:9b'
    except Exception as ex:
        print(f"Could not set enum directly, setting MANUAL: {ex}")
        prefs.llm_model_ollama = 'MANUAL'
        prefs.llm_model_custom = 'qwen3.5:9b'
        
    prefs.allow_code_execution = True

    print("\n=============================================")
    print("STARTING INTEGRATION TESTS WITH OLLAMA (DIRECT CALLS)")
    print("=============================================\n")
    
    # Debug print preferences to see what is resolved
    from addon.handlers.llm_handler import get_prefs
    resolved_prefs = get_prefs()
    print("DEBUG ACTIVE PREFS:")
    if resolved_prefs:
        print(f"  provider: {resolved_prefs.llm_provider}")
        print(f"  base_url: {resolved_prefs.llm_base_url}")
        print(f"  model_ollama: {resolved_prefs.llm_model_ollama}")
        print(f"  model_custom: {resolved_prefs.llm_model_custom}")
        print(f"  allow_code: {resolved_prefs.allow_code_execution}")
    else:
        print("  Failed to resolve preferences inside handler context!")

    try:
        # Test 1: GET /api/scene (should be empty initially)
        print("Test 1: Getting initial scene via WebUI API...")
        req = urllib.request.Request("http://127.0.0.1:8080/api/scene")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            print(f"Initial scene response: {json.dumps(data, indent=2)}")
            assert data["status"] == "success"
            assert len(data["objects"]) == 0
            print("-> Test 1 PASSED!\n")

        # Test 2: Direct call to handler to add a cylinder using qwen3.5:9b
        print("Test 2: Direct request to add a cylinder...")
        res = handle_chat_request_headless(
            prompt="Write a Python script that creates a cylinder mesh named 'Cylinder' with radius 1.0, height 4.0 at location (0, 0, 0) inside a ```python block.",
            provider="OLLAMA",
            model="qwen3.5:9b",
            api_key="sk-1234",
            allow_code_execution=True,
            base_url="http://127.0.0.1:11434",
            execution_callback=safe_execute_command
        )
        print(f"Direct cylinder call response: {json.dumps(res, indent=2)}")
        assert res.get("status") in ("success", "info")
        
        # Verify the cylinder was actually added to the scene in Blender
        assert "Cylinder" in bpy.context.scene.objects, "Cylinder object was not created in Blender!"
        print("-> Test 2 PASSED!\n")

        # Test 3: Direct call to generate a washer
        print("Test 3: Direct request to generate an M5 washer...")
        # Since fasteners is a python module in the addon, we can instruct the LLM to call the generate_fastener function
        res = handle_chat_request_headless(
            prompt="Write a Python script that generates an M5 washer at location (0, 0, 2) in the active scene using the addon.handlers.fasteners module: 'from addon.handlers.fasteners import generate_fastener; generate_fastener(bpy.context.scene, type=\"WASHER\", size=\"M3\")'. Put it inside a ```python block.",
            provider="OLLAMA",
            model="qwen3.5:9b",
            api_key="sk-1234",
            allow_code_execution=True,
            base_url="http://127.0.0.1:11434",
            execution_callback=safe_execute_command
        )
        print(f"Direct washer call response: {json.dumps(res, indent=2)}")
        assert res.get("status") in ("success", "info")
        
        # Verify washer was added
        object_names = [obj.name for obj in bpy.context.scene.objects]
        print(f"Current objects: {object_names}")
        assert any("Washer" in name or "washer" in name.lower() for name in object_names), "Washer object was not created in Blender!"
        print("-> Test 3 PASSED!\n")

        # Test 4: Direct call to analyze structural properties
        print("Test 4: Direct request to analyze structural properties of the Cylinder...")
        res = handle_chat_request_headless(
            prompt="Write a Python script that runs the structural analysis on the object named 'Cylinder': 'from addon.handlers.structural_analyzer import analyze_structural_properties; print(analyze_structural_properties(bpy.context.scene, \"Cylinder\", \"PLA\"))'. Put it inside a ```python block.",
            provider="OLLAMA",
            model="qwen3.5:9b",
            api_key="sk-1234",
            allow_code_execution=True,
            base_url="http://127.0.0.1:11434",
            execution_callback=safe_execute_command
        )
        print(f"Direct structural analysis response: {json.dumps(res, indent=2)}")
        assert res.get("status") in ("success", "info")
        print("-> Test 4 PASSED!\n")

        # Test 5: GET /api/scene WebUI API (should show the generated objects)
        print("Test 5: Verifying scene elements via WebUI API...")
        req = urllib.request.Request("http://127.0.0.1:8080/api/scene")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            print(f"Final scene response: {json.dumps(data, indent=2)}")
            assert data["status"] == "success"
            web_object_names = [obj["name"] for obj in data["objects"]]
            print(f"Objects returned by WebUI API: {web_object_names}")
            assert any("Cylinder" in name for name in web_object_names), "Cylinder not found in WebUI API response"
            assert any("Washer" in name or "washer" in name.lower() for name in web_object_names), "Washer not found in WebUI API response"
            print("-> Test 5 PASSED!\n")

        print("=============================================")
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=============================================\n")

    except Exception as e:
        import traceback
        test_success = False
        test_error_message = f"Test failure: {str(e)}\n{traceback.format_exc()}"
        print("\n=============================================")
        print("TEST RUN FAILED!")
        print(test_error_message)
        print("=============================================\n")
        
    finally:
        # Shut down servers
        print("Stopping servers...")
        try:
            bpy.types.blendermcp_server.stop()
            bpy.types.blendermcp_webui_server.stop()
        except:
            pass
        
        # Delay to let threads exit
        time.sleep(1)
        
        # Quit Blender
        print("Exiting Blender...")
        bpy.ops.wm.quit_blender()

# Run the test client in a background thread so it doesn't block the main thread timers
test_thread = threading.Thread(target=run_tests)
test_thread.daemon = True
test_thread.start()

# Keep Blender main thread alive until tests are completed and process main_queue items
try:
    while test_thread.is_alive():
        while not main_queue.empty():
            func = main_queue.get_nowait()
            try:
                func()
            except Exception as e:
                print(f"Error executing main thread queue item: {e}")
        time.sleep(0.05)
except KeyboardInterrupt:
    pass
