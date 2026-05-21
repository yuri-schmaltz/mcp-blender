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

Current context: {bpy.context.scene.name} in {bpy.data.filepath if bpy.data.filepath else 'unsaved file'}.
"""

def handle_chat_request_headless(prompt, provider, model, api_key, allow_code_execution, base_url=None, execution_callback=None):
    """
    Headless chat request handler. Safe to run in background threads.
    If execution_callback is provided, tool execution will be deferred to it.
    execution_callback should accept (tool_command) and return the result synchronously.
    """
    if litellm is None:
        return {"error": "litellm is not installed. Please run 'Check/Install Dependencies' in the panel."}

    if not prompt:
        return {"error": "Prompt is empty"}
        
    # Local providers usually don't need API keys, but litellm might require a dummy one
    if not api_key and provider in {'OLLAMA', 'CUSTOM'}:
        api_key = "sk-1234"
    elif not api_key:
        return {"error": "Missing API Key"}
        
    # Format model string for litellm
    if provider == 'OLLAMA':
        model = f"ollama/{model}"
    elif provider == 'CUSTOM':
        model = f"openai/{model}"

    messages = [
        {"role": "system", "content": _get_system_prompt()},
        {"role": "user", "content": prompt}
    ]

    # Convert our internal MCP tool schemas to OpenAI format for litellm
    tools_list = get_tools_list()
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
            final_message = second_response.choices[0].message.content
            return {"status": "success", "message": final_message}
        else:
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
    elif provider == 'CUSTOM':
        model = prefs.llm_model_custom if prefs.llm_model_custom_enum == 'MANUAL' else prefs.llm_model_custom_enum
    else:
        model = prefs.llm_model
    base_url = prefs.llm_base_url if provider in {'OLLAMA', 'CUSTOM'} else None

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
    elif provider == 'CUSTOM':
        model = prefs.llm_model_custom if prefs.llm_model_custom_enum == 'MANUAL' else prefs.llm_model_custom_enum
    else:
        model = prefs.llm_model
    base_url = prefs.llm_base_url if provider in {'OLLAMA', 'CUSTOM'} else None
    
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
                if hasattr(bpy.context, "window_manager") and bpy.context.window_manager.windows:
                    win = bpy.context.window_manager.windows[0]
                    override["window"] = win
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
