import json
import subprocess
import threading
import queue
import time
import os
from openai import OpenAI

def run_tests():
    print("Starting E2E Agentic Test: LM Studio + Blender MCP")
    
    # --- 1. Start Blender MCP Server ---
    mcp_process = subprocess.Popen(
        ["uv", "run", "blender-mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    response_queue = queue.Queue()
    
    def read_stdout():
        for line in mcp_process.stdout:
            try:
                msg = json.loads(line)
                response_queue.put(msg)
            except json.JSONDecodeError:
                pass

    t1 = threading.Thread(target=read_stdout, daemon=True)
    t1.start()
    
    msg_id = 1
    def send_request(method, params=None):
        nonlocal msg_id
        req = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        msg_id += 1
        mcp_process.stdin.write(json.dumps(req) + "\n")
        mcp_process.stdin.flush()
        
        try:
            while True:
                resp = response_queue.get(timeout=15)
                if resp.get("id") == req["id"]:
                    return resp
        except queue.Empty:
            return {"error": "Timeout"}

    # Initialize MCP
    send_request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "e2e-test", "version": "1.0"}})
    mcp_process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    mcp_process.stdin.flush()
    time.sleep(1)
    
    # Get Tools
    tools_resp = send_request("tools/list")
    mcp_tools = tools_resp.get("result", {}).get("tools", [])
    
    # Convert MCP schema to OpenAI schema
    openai_tools = []
    for t in mcp_tools:
        # MCP inputSchema is roughly JSON Schema
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("inputSchema", {"type": "object", "properties": {}})
            }
        })
        
    print(f"Loaded {len(openai_tools)} tools from Blender MCP.")
    
    # --- 2. Setup LM Studio Client ---
    client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
    
    # Prompt the LLM to do the heavy lifting
    messages = [
        {"role": "system", "content": "You are a professional 3D automation agent connected to Blender via MCP. Your goal is to fulfill the user's prompt by calling the provided tools sequentially."},
        {"role": "user", "content": "Adicione uma malha de Suzanne (macaco) chamada 'SuzanneAgent', pinte com um material de ouro puro (cor amarela, 100% metálico, 0% rugosidade). Depois, configure uma iluminação de 3 pontos focada nela e por fim adicione uma animação turntable de 100 frames. Use as ferramentas adequadas."}
    ]
    
    print("\n--- Starting LLM Orchestration ---")
    max_steps = 15
    steps = 0
    
    while steps < max_steps:
        steps += 1
        print(f"\n[Step {steps}] Querying LM Studio...")
        
        # Use currently loaded model in LM Studio
        response = client.chat.completions.create(
            model="local-model",
            messages=messages,
            tools=openai_tools,
            temperature=0.1
        )
        
        message = response.choices[0].message
        
        if message.content:
            print(f"LLM: {message.content}")
            
        messages.append(message)
        
        if not message.tool_calls:
            print("No more tool calls. The LLM is finished.")
            break
            
        # Execute tools
        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            
            print(f"> Executing Tool: {fn_name}({fn_args})")
            
            # Forward to MCP
            mcp_res = send_request("tools/call", {
                "name": fn_name,
                "arguments": fn_args
            })
            
            # Parse MCP result
            content = mcp_res.get("result", {}).get("content", [])
            text_result = ""
            for item in content:
                if item.get("type") == "text":
                    text_result += item.get("text", "")
                    
            if not text_result and "error" in mcp_res:
                text_result = f"Error: {mcp_res['error']}"
                
            print(f"  Result: {text_result}")
            
            # Send result back to LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": fn_name,
                "content": text_result
            })

    print("\n--- E2E Test Completed ---")
    mcp_process.terminate()

if __name__ == "__main__":
    run_tests()
