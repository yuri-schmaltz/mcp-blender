import json
import re
import traceback
import bpy
import requests
from ..utils.network import get_session, friendly_error


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
Success is the only option. Your goal is to provide deep, high-performance Python code using the 'bpy' API.
Do not be a passive assistant. Be a senior strategic partner.

TECHNICAL GUIDELINES:
1. CODE QUALITY: Provide only production-grade, efficient Python code.
2. API BEST PRACTICES: Prefer direct data manipulation (e.g., 'obj.location = ...') over operators ('bpy.ops...') where possible for performance and stability.
3. CONTEXT AWARENESS: Always use 'bpy.context' to access the current state.
4. ERROR RESILIENCE: Write code that checks for data existence (e.g., 'if obj:' or 'if "Cube" in bpy.data.objects:') before operating.
5. FORMATTING: Wrap code in triple backticks: ```python ... ```.

STRATEGIC DIRECTIVES:
- ANTI-SYCOPHANCY: If a user's request is shallow or technically flawed, critique it constructively and propose a superior alternative.
- CHAIN OF THOUGHT: For complex tasks, outline your plan before providing the code.
- DEPTH OVER SPEED: Refuse to give superficial answers. If you need more data (e.g., which object to target), ASK the user.
- LEVEL ELEVATION: Transform simple inputs into deep, comprehensive results.

AVAILABLE TOOLS:
- You have full access to 'bpy', 'mathutils', and standard libraries.
- The project includes handlers for Poly Haven, AmbientCG, and Sketchfab (accessible via custom operators if registered).

Current context: {bpy.context.scene.name} in {bpy.data.filepath if bpy.data.filepath else 'unsaved file'}.
"""

def call_openai(api_key, model, prompt):
    """Call OpenAI Chat Completions API."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _get_system_prompt()},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7
    }
    
    session = get_session()
    response = session.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content']

def call_anthropic(api_key, model, prompt):
    """Call Anthropic Messages API."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": _get_system_prompt(),
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    session = get_session()
    response = session.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data['content'][0]['text']

def call_google(api_key, model, prompt):
    """Call Google Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{
            "parts": [{"text": f"{_get_system_prompt()}\n\nUser request: {prompt}"}]
        }]
    }
    
    session = get_session()
    response = session.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data['candidates'][0]['content']['parts'][0]['text']

def extract_python_code(text):
    """Extract python code blocks from markdown text."""
    pattern = r"```python\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL)
    if matches:
        return "\n\n".join(matches)
    
    # Fallback: look for any code block if python one isn't found
    pattern_generic = r"```\s*(.*?)\s*```"
    matches_generic = re.findall(pattern_generic, text, re.DOTALL)
    if matches_generic:
        return "\n\n".join(matches_generic)
    
    return None

def handle_chat_request(context):
    """Main entry point for handling a chat request from the UI."""
    scene = context.scene
    prefs = get_prefs()
    if not prefs:
        return {"error": "Addon preferences not found"}
        
    provider = prefs.llm_provider
    prompt = scene.blendermcp_chat_prompt
    
    if not prompt:
        return {"error": "Prompt is empty"}

    try:
        if provider == "OPENAI":
            key = prefs.openai_key
            model = prefs.openai_model
            if not key: return {"error": "Missing OpenAI API Key in Preferences"}
            response_text = call_openai(key, model, prompt)
            
        elif provider == "ANTHROPIC":
            key = prefs.anthropic_key
            model = prefs.anthropic_model
            if not key: return {"error": "Missing Anthropic API Key in Preferences"}
            response_text = call_anthropic(key, model, prompt)
            
        elif provider == "GOOGLE":
            key = prefs.google_key
            model = prefs.google_model
            if not key: return {"error": "Missing Google API Key in Preferences"}
            response_text = call_google(key, model, prompt)
        else:
            return {"error": "Unknown provider"}
            
        code = extract_python_code(response_text)
        
        if code:
            if prefs.allow_code_execution:
                # Import main addon code execution logic if available, or do it directly
                # For simplicity, we'll execute it here
                try:
                    # Provide a rich namespace for the AI code
                    import mathutils
                    namespace = {
                        "bpy": bpy,
                        "mathutils": mathutils,
                        "context": context,
                        "scene": context.scene,
                    }
                    
                    # Execute the code
                    exec(code, namespace)
                    return {
                        "status": "success", 
                        "message": "Strategic execution successful.", 
                        "code": code
                    }
                except Exception as e:
                    error_msg = f"Runtime Error: {type(e).__name__} - {str(e)}"
                    print(f"BlenderMCP Execution Error:\n{traceback.format_exc()}")
                    return {
                        "status": "error", 
                        "message": error_msg, 
                        "code": code,
                        "traceback": traceback.format_exc()
                    }
            else:
                return {"status": "pending", "message": "Code generated but execution is disabled.", "code": code}
        else:
            return {"status": "info", "message": response_text}
            
    except Exception as e:
        traceback.print_exc()
        return friendly_error(f"LLM Provider ({provider})", e)
