import json
import traceback
import bpy

try:
    import litellm
except ImportError:
    litellm = None

from ..utils.network import friendly_error
from ..tool_schemas import get_tools_list
from ..core.router import execute_command


def get_prefs():
    """Access global addon preferences safely."""
    from ..utils.helpers import get_addon_prefs
    return get_addon_prefs(__package__)


def _get_system_prompt():
    """Returns a high-level expert system prompt for the AI assistant."""
    bl_ver = f"{bpy.app.version[0]}.{bpy.app.version[1]}"
    scene = getattr(bpy.context, "scene", None)
    scene_name = scene.name if scene else "No active scene"
    filepath = bpy.data.filepath if bpy.data.filepath else "unsaved file"
    return f"""You are BlenderMCP, a Senior Strategic AI Partner for Blender 3D (v{bl_ver}).
You represent the pinnacle of technical excellence and strategic thinking.

CORE MISSION:
Success is the only option. Your goal is to provide deep, high-performance Python code and use tools to manipulate Blender.
Do not be a passive assistant. Be a senior strategic partner.

TECHNICAL GUIDELINES:
1. CODE QUALITY: Provide only production-grade, efficient Python code.
2. API BEST PRACTICES: Prefer direct data manipulation over operators where possible.
3. CONTEXT AWARENESS: Always use 'bpy.context' to access the current state.
4. ERROR RESILIENCE: Write code that checks for data existence before operating.
5. TOOLS: You have access to tools. Always prefer using specific tools over executing raw python code when a specific tool is available.
If no tool fits, you can use the execute_code tool.

Current context: {scene_name} in {filepath}.
"""

def handle_chat_request_headless(prompt, provider, model, api_key, allow_code_execution, base_url=None, execution_callback=None):
    """
    Headless chat request handler. Safe to run in background threads.
    If execution_callback is provided, tool execution will be deferred to it.
    execution_callback should accept (tool_command) and return the result synchronously.
    """
    global litellm
    if litellm is None:
        try:
            from ..utils.helpers import extend_sys_path_with_venv
            extend_sys_path_with_venv()
            import litellm
        except ImportError:
            litellm = None

    if litellm is None:
        return {"error": "litellm is not installed. Please run 'Check/Install Dependencies' in the panel."}

    if not prompt:
        return {"error": "Prompt is empty"}
        
    # Local providers usually don't need API keys, but litellm might require a dummy one
    if not api_key:
        api_key = "sk-1234"
        
    # Format model string for litellm
    if provider == 'OLLAMA':
        model = f"ollama/{model}"
    else:
        model = f"openai/{model}"

    messages = [
        {"role": "system", "content": _get_system_prompt()},
        {"role": "user", "content": prompt}
    ]

    # Convert our internal MCP tool schemas to OpenAI format for litellm
    tools_list = get_tools_list()
    
    # Filter tools based on mcp_tool_profile preference to optimize context size and speed
    prefs = get_prefs()
    profile = getattr(prefs, "mcp_tool_profile", "ALL")
    
    if profile != "ALL":
        essential_tools = {
            "get_scene_info",
            "get_active_object",
            "set_active_object",
            "get_object_info",
            "transform_object",
            "delete_object",
            "add_primitive",
            "analyze_viewport_visuals",
            "execute_code",
            "get_operator_help",
            "list_blender_operators",
            "list_tools"
        }
        
        allowed_tools = set(essential_tools)
        
        if profile == "MODELING":
            allowed_tools.update({
                "add_modifier", "apply_modifier", "apply_all_modifiers", 
                "add_array_modifier", "add_mirror_modifier", "add_screw_modifier", 
                "add_curve_modifier", "apply_boolean_operation", "align_objects", 
                "distribute_objects", "duplicate_object", "parent_objects", 
                "join_objects", "set_exact_dimensions", "snap_objects_by_proximity", 
                "separate_loose_parts", "separate_by_material", "extrude_faces", 
                "inset_faces", "bevel_edges", "subdivide_mesh", "smooth_mesh", 
                "spin_mesh", "shade_smooth", "recalculate_normals", "merge_vertices", 
                "fill_hole", "decimate_mesh", "remesh_voxel", "smart_uv_project", 
                "mark_sharp_by_angle", "text_to_mesh", "create_collection", "move_to_collection"
            })
        elif profile == "MATERIALS":
            allowed_tools.update({
                "create_pbr_material", "set_texture", "download_polyhaven_asset", 
                "download_ambientcg_material", "download_sketchfab_model", 
                "search_polyhaven_assets", "search_ambientcg_materials", 
                "search_sketchfab_models", "setup_camera", 
                "setup_product_studio", "configure_render_settings", "render_catalog_angles", 
                "animate_rotation", "create_turntable_animation"
            })
        elif profile == "PHYSICS":
            allowed_tools.update({
                "mark_as_functional_part", "list_functional_parts"
            })
        elif profile == "PRINTING":
            allowed_tools.update({
                "check_mesh_integrity", "auto_repair_mesh", "resolve_self_intersections", 
                "apply_print_thickness", "assign_print_color", "generate_print_report", 
                "export_for_printing", "export_model"
            })
            
        tools_list = [t for t in tools_list if t["name"] in allowed_tools]
        print(f"BlenderMCP Embedded Chat: Filtered tools count down to {len(tools_list)} for profile {profile}")

    litellm_tools = []
    for t in tools_list:
        litellm_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["inputSchema"]
            }
        })

    kwargs = {
        "model": model,
        "api_key": api_key,
        "messages": messages,
        "tools": litellm_tools,
        "temperature": 0.7,
    }
    if base_url:
        kwargs["base_url"] = base_url

    try:
        # Initial call
        response = litellm.completion(**kwargs)

        response_message = response.choices[0].message
        
        # Check if the model wants to call tools
        if response_message.tool_calls:
            messages.append(response_message)
            
            # Execute each tool call
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                print(f"BlenderMCP AI: Executing Tool -> {function_name}({function_args})")
                
                tool_command = {
                    "type": function_name,
                    "params": function_args
                }
                
                if function_name == "execute_code" and not allow_code_execution:
                    result_content = "Error: Code execution is disabled in preferences."
                else:
                    if execution_callback:
                        # Defer execution to callback (e.g. main thread dispatcher)
                        try:
                            tool_result = execution_callback(tool_command)
                        except Exception as e:
                            tool_result = {"status": "error", "message": str(e)}
                    else:
                        # Execute directly (unsafe from background thread)
                        tool_result = execute_command(tool_command)
                        
                    if tool_result.get("status") == "error":
                        result_content = f"Error: {tool_result.get('message')}"
                    else:
                        result_content = str(tool_result.get("result", "Success"))
                
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": result_content,
                })

            # Call LLM again with the tool responses
            kwargs.pop("temperature", None) # litellm might prefer default here
            kwargs["messages"] = messages
            second_response = litellm.completion(**kwargs)
            final_message_obj = second_response.choices[0].message
            if getattr(final_message_obj, "refusal", None):
                return {"status": "error", "message": f"Request refused: {final_message_obj.refusal}"}
            final_message = final_message_obj.content
            return {"status": "success", "message": final_message}
        else:
            if getattr(response_message, "refusal", None):
                return {"status": "error", "message": f"Request refused: {response_message.refusal}"}
            content = response_message.content
            import re
            pattern = r"```python\s*(.*?)\s*```"
            matches = re.findall(pattern, content, re.DOTALL)
            
            if matches and allow_code_execution:
                code = "\n\n".join(matches)
                tool_command = {"type": "execute_code", "params": {"code": code}}
                if execution_callback:
                    execution_callback(tool_command)
                else:
                    execute_command(tool_command)
                return {"status": "success", "message": "Python code extracted and executed.\n" + content}
                
            return {"status": "info", "message": content}

    except Exception as e:
        traceback.print_exc()
        return friendly_error(f"LLM Provider ({provider})", e)


def handle_chat_request(context):
    """Main entry point for handling a chat request from the Blender UI."""
    scene = context.scene
    prefs = get_prefs()
    if not prefs:
        return {"error": "Addon preferences not found"}

    provider = prefs.llm_provider
    if provider == 'OLLAMA':
        model = prefs.llm_model_custom if prefs.llm_model_ollama == 'MANUAL' else prefs.llm_model_ollama
    else:
        model = prefs.llm_model_custom if prefs.llm_model_custom_enum == 'MANUAL' else prefs.llm_model_custom_enum
    base_url = prefs.llm_base_url

    return handle_chat_request_headless(
        prompt=scene.blendermcp_chat_prompt,
        provider=provider,
        model=model,
        api_key=prefs.llm_api_key,
        allow_code_execution=prefs.allow_code_execution,
        base_url=base_url,
        execution_callback=None  # Use direct execution since we are in the main thread
    )


import threading
import concurrent.futures

def handle_chat_request_async(context, on_complete_callback):
    """
    Run chat request in a background thread to prevent UI freezing.
    Updates status and logs results safely back on the main thread via timers.
    """
    scene = context.scene
    prefs = get_prefs()
    if not prefs:
        on_complete_callback({"error": "Addon preferences not found"})
        return

    provider = prefs.llm_provider
    if provider == 'OLLAMA':
        model = prefs.llm_model_custom if prefs.llm_model_ollama == 'MANUAL' else prefs.llm_model_ollama
    else:
        model = prefs.llm_model_custom if prefs.llm_model_custom_enum == 'MANUAL' else prefs.llm_model_custom_enum
    base_url = prefs.llm_base_url
    
    prompt = scene.blendermcp_chat_prompt
    api_key = prefs.llm_api_key
    allow_code_execution = prefs.allow_code_execution

    # Safe execute command callback for the background thread to talk to Blender main thread
    def safe_execute_command(tool_command):
        future = concurrent.futures.Future()
        
        def _run_in_main():
            try:
                from ..core.router import execute_command
                override = {}
                wm = getattr(bpy.context, "window_manager", None)
                if wm is not None and hasattr(wm, "windows") and wm.windows:
                    windows = list(wm.windows)
                    if windows:
                        win = windows[0]
                        override["window"] = win
                        if hasattr(win, "screen") and win.screen:
                            override["screen"] = win.screen
                            for area in win.screen.areas:
                                if area.type == 'VIEW_3D':
                                    override["area"] = area
                                    for region in area.regions:
                                        if region.type == 'WINDOW':
                                            override["region"] = region
                                            break
                                    break
                with bpy.context.temp_override(**override):
                    res = execute_command(tool_command)
                future.set_result(res)
            except Exception as e:
                future.set_exception(e)
            return None
            
        bpy.app.timers.register(_run_in_main)
        return future.result(timeout=120)

    def thread_target():
        try:
            result = handle_chat_request_headless(
                prompt=prompt,
                provider=provider,
                model=model,
                api_key=api_key,
                allow_code_execution=allow_code_execution,
                base_url=base_url,
                execution_callback=safe_execute_command
            )
        except Exception as e:
            result = {"error": str(e)}
            
        # Schedule the completion callback to run in Blender's main thread
        def run_callback_in_main():
            on_complete_callback(result)
            return None
            
        bpy.app.timers.register(run_callback_in_main)

    thread = threading.Thread(target=thread_target, name="blender-mcp-chat-thread")
    thread.daemon = True
    thread.start()
