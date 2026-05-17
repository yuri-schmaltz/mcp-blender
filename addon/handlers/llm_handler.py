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

def handle_chat_request(context):
    """Main entry point for handling a chat request from the UI."""
    scene = context.scene
    prefs = get_prefs()
    if not prefs:
        return {"error": "Addon preferences not found"}

    if litellm is None:
        return {"error": "litellm is not installed. Please run 'Check/Install Dependencies' in the panel."}

    prompt = scene.blendermcp_chat_prompt
    if not prompt:
        return {"error": "Prompt is empty"}

    provider = prefs.llm_provider
    api_key = prefs.llm_api_key
    model = prefs.llm_model

    if not api_key:
        return {"error": "Missing API Key in Preferences"}

    # litellm expects standard model names. If the user specifies just "gpt-4o", it works.
    # If the provider is Google or Anthropic, litellm might need prefixing or the specific model name.
    # Litellm generally handles 'gpt-4o', 'claude-3-5-sonnet-20240620', 'gemini/gemini-1.5-pro'
    # We will pass what the user wrote directly to litellm.
    if provider == 'ANTHROPIC' and not model.startswith('claude'):
        model = "claude-3-5-sonnet-20240620"
    if provider == 'GOOGLE' and not model.startswith('gemini'):
        model = "gemini/gemini-1.5-pro"

    # Set up messages
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

    try:
        # Initial call
        response = litellm.completion(
            model=model,
            api_key=api_key,
            messages=messages,
            tools=litellm_tools,
            temperature=0.7,
        )

        response_message = response.choices[0].message
        
        # Check if the model wants to call tools
        if response_message.tool_calls:
            messages.append(response_message)
            
            # Execute each tool call
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                print(f"BlenderMCP Client: Executing Tool -> {function_name}({function_args})")
                
                # Use our router to execute the tool
                # Execute_command expects {"type": "tool_name", "params": {...}}
                tool_command = {
                    "type": function_name,
                    "params": function_args
                }
                
                # Check for code execution safety
                if function_name == "execute_code" and not prefs.allow_code_execution:
                    result_content = "Error: Code execution is disabled in preferences."
                else:
                    tool_result = execute_command(tool_command)
                    if tool_result.get("status") == "error":
                        result_content = f"Error: {tool_result.get('message')}"
                    else:
                        result_content = str(tool_result.get("result", "Success"))
                
                # Append tool response
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": result_content,
                })

            # Call LLM again with the tool responses
            second_response = litellm.completion(
                model=model,
                api_key=api_key,
                messages=messages,
                tools=litellm_tools,
            )
            final_message = second_response.choices[0].message.content
            return {"status": "success", "message": "Tools executed successfully. " + (final_message[:50] if final_message else "")}
        else:
            # No tool calls, just a text response
            # Check if there is python code in the text as a fallback
            content = response_message.content
            import re
            pattern = r"```python\s*(.*?)\s*```"
            matches = re.findall(pattern, content, re.DOTALL)
            
            if matches and prefs.allow_code_execution:
                code = "\n\n".join(matches)
                tool_command = {
                    "type": "execute_code",
                    "params": {"code": code}
                }
                execute_command(tool_command)
                return {"status": "success", "message": "Python code extracted and executed."}
                
            return {"status": "info", "message": "Response received. No actions taken."}

    except Exception as e:
        traceback.print_exc()
        return friendly_error(f"LLM Provider ({provider})", e)
