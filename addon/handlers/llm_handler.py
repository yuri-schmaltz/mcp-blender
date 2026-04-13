import json
import re
import traceback
import bpy
import requests
from addon.utils.network import get_session, friendly_error


def _get_system_prompt():
    """Returns the system prompt that explains the AI's capabilities in Blender."""
    return """You are BlenderMCP, an AI assistant for Blender 3D. 
Your goal is to help users by generating Python code that uses the 'bpy' API to perform tasks.

Guidelines:
1. Provide only valid Blender Python code.
2. Use 'bpy' to interact with the scene.
3. If the user asks for something complex, break it down into steps.
4. Wrap your code in triple backticks with 'python' language identifier: ```python ... ```
5. Be concise and precise.
6. The user may have enabled 'Allow Remote Code Execution', so you can assume your code will be run.
7. You have access to the full Blender API.
8. Current scene information can be accessed via 'bpy.context.scene'.
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
    provider = scene.blendermcp_llm_provider
    prompt = scene.blendermcp_chat_prompt
    
    if not prompt:
        return {"error": "Prompt is empty"}
    
    try:
        if provider == "OPENAI":
            key = scene.blendermcp_openai_key
            model = scene.blendermcp_openai_model
            if not key: return {"error": "Missing OpenAI API Key"}
            response_text = call_openai(key, model, prompt)
            
        elif provider == "ANTHROPIC":
            key = scene.blendermcp_anthropic_key
            model = scene.blendermcp_anthropic_model
            if not key: return {"error": "Missing Anthropic API Key"}
            response_text = call_anthropic(key, model, prompt)
            
        elif provider == "GOOGLE":
            key = scene.blendermcp_google_key
            model = scene.blendermcp_google_model
            if not key: return {"error": "Missing Google API Key"}
            response_text = call_google(key, model, prompt)
        else:
            return {"error": "Unknown provider"}
            
        code = extract_python_code(response_text)
        
        if code:
            if scene.blendermcp_allow_code_execution:
                # Import main addon code execution logic if available, or do it directly
                # For simplicity, we'll execute it here
                try:
                    namespace = {"bpy": bpy}
                    exec(code, namespace)
                    return {"status": "success", "message": "Code executed successfully", "code": code}
                except Exception as e:
                    return {"status": "error", "message": f"Execution error: {str(e)}", "code": code}
            else:
                return {"status": "pending", "message": "Code generated but execution is disabled.", "code": code}
        else:
            return {"status": "info", "message": response_text}
            
    except Exception as e:
        traceback.print_exc()
        return friendly_error(f"LLM Provider ({provider})", e)
