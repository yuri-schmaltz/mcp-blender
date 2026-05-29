import http.server
import json
import threading
import os
import concurrent.futures
import traceback
import logging

import bpy

logger = logging.getLogger("BlenderMCP.WebUI")

class WebUIHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            html_path = os.path.join(os.path.dirname(__file__), "ui", "web", "index.html")
            try:
                with open(html_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.wfile.write(content.encode('utf-8'))
            except Exception as e:
                self.wfile.write(f"Error loading HTML: {e}".encode('utf-8'))
        elif self.path == '/api/scene':
            try:
                import concurrent.futures
                future = concurrent.futures.Future()
                
                def _run_in_main():
                    try:
                        import bpy
                        
                        scene_data = {
                            "status": "success",
                            "objects": []
                        }
                        
                        for obj in bpy.context.scene.objects:
                            obj_data = {
                                "name": obj.name,
                                "type": obj.type,
                                "location": [obj.location.x, obj.location.y, obj.location.z],
                                "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
                                "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
                                "dimensions": [obj.dimensions.x, obj.dimensions.y, obj.dimensions.z] if hasattr(obj, "dimensions") else [1, 1, 1]
                            }
                            
                            shape_guess = "cube"
                            name_lower = obj.name.lower()
                            if "sphere" in name_lower or (obj.type == 'MESH' and hasattr(obj.data, "vertices") and len(obj.data.vertices) == 482):
                                shape_guess = "sphere"
                            elif "cylinder" in name_lower or "screw" in name_lower or "bolt" in name_lower or "shaft" in name_lower or "pocket" in name_lower or "hole" in name_lower:
                                shape_guess = "cylinder"
                            elif "cone" in name_lower:
                                shape_guess = "cone"
                            elif "torus" in name_lower or "bearing" in name_lower or "nut" in name_lower or "washer" in name_lower:
                                shape_guess = "torus"
                            elif "light" in name_lower or obj.type == 'LIGHT':
                                shape_guess = "light"
                                obj_data["light_type"] = obj.data.type if hasattr(obj, "data") else "POINT"
                            elif obj.type == 'CAMERA':
                                shape_guess = "camera"
                                
                            obj_data["shape_guess"] = shape_guess
                            scene_data["objects"].append(obj_data)
                            
                        future.set_result(scene_data)
                    except Exception as e:
                        future.set_exception(e)
                    return None
                
                bpy.app.timers.register(_run_in_main)
                scene_info = future.result(timeout=5.0)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(scene_info).encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/api/stream':
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'keep-alive')
                self.end_headers()
                
                logger.info("WebUI client connected to SSE live stream")
                
                last_version = -1
                while True:
                    future = concurrent.futures.Future()
                    def _fetch():
                        try:
                            objs = []
                            for obj in bpy.context.scene.objects:
                                # Safe property checks
                                type_str = getattr(obj, "type", "MESH")
                                loc = getattr(obj, "location", None)
                                rot = getattr(obj, "rotation_euler", None)
                                scl = getattr(obj, "scale", None)
                                dim = getattr(obj, "dimensions", None)
                                
                                objs.append({
                                    "name": obj.name,
                                    "type": type_str,
                                    "location": [loc.x, loc.y, loc.z] if loc else [0,0,0],
                                    "rotation": [rot.x, rot.y, rot.z] if rot else [0,0,0],
                                    "scale": [scl.x, scl.y, scl.z] if scl else [1,1,1],
                                    "dimensions": [dim.x, dim.y, dim.z] if dim else [1, 1, 1],
                                    "shape_guess": "cube"
                                })
                            # Resolve shape guesses
                            for obj_data in objs:
                                name_lower = obj_data["name"].lower()
                                shape_guess = "cube"
                                if "sphere" in name_lower:
                                    shape_guess = "sphere"
                                elif "cylinder" in name_lower or "screw" in name_lower or "bolt" in name_lower or "shaft" in name_lower or "pocket" in name_lower or "hole" in name_lower:
                                    shape_guess = "cylinder"
                                elif "cone" in name_lower:
                                    shape_guess = "cone"
                                elif "torus" in name_lower or "bearing" in name_lower or "nut" in name_lower or "washer" in name_lower:
                                    shape_guess = "torus"
                                obj_data["shape_guess"] = shape_guess
                            future.set_result(objs)
                        except Exception as e:
                            future.set_exception(e)
                        return None
                        
                    bpy.app.timers.register(_fetch)
                    try:
                        objs = future.result(timeout=1.0)
                        objs_str = json.dumps(objs)
                        import hashlib
                        h = hashlib.md5(objs_str.encode('utf-8')).hexdigest()
                        if h != last_version:
                            last_version = h
                            payload = {"status": "success", "objects": objs}
                            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode('utf-8'))
                            self.wfile.flush()
                    except (concurrent.futures.TimeoutError, TimeoutError) as e:
                        logger.warning(f"SSE viewport stream tick timed out (Blender main thread busy): {e}")
                        import time
                        time.sleep(0.1)
                        continue
                    except Exception as e:
                        # Client disconnected or other network error
                        logger.info(f"SSE viewport stream connection closed: {e}")
                        break
                        
                    import time
                    time.sleep(0.1) # 10Hz limit
            except Exception as e:
                logger.error(f"SSE general failure: {e}")
        else:
            self.send_error(404, "File not found")

    def do_POST(self):
        if self.path == '/api/chat':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                prompt = data.get('prompt', '')
                
                # Fetch preferences from the main thread safely?
                # Actually, reading properties in Blender from a background thread is
                # theoretically unsafe, but often works for simple reads. 
                # For ultimate safety, we should fetch prefs via a future, but simple reads are usually fine.
                # Let's read them dynamically.
                from .handlers.llm_handler import get_prefs, handle_chat_request_headless
                prefs = get_prefs()
                if not prefs:
                    raise Exception("Preferences not found")
                
                provider = prefs.llm_provider
                if provider == 'OLLAMA':
                    model = prefs.llm_model_custom if prefs.llm_model_ollama == 'MANUAL' else prefs.llm_model_ollama
                elif provider == 'CUSTOM':
                    model = prefs.llm_model_custom if prefs.llm_model_custom_enum == 'MANUAL' else prefs.llm_model_custom_enum
                else:
                    model = prefs.llm_model
                base_url = prefs.llm_base_url if provider in {'OLLAMA', 'CUSTOM'} else None
                api_key = prefs.llm_api_key
                allow_code_execution = prefs.allow_code_execution
                
                print(f"WEBUI SERVER API CALL: provider={provider}, model={model}, base_url={base_url}, allow_code={allow_code_execution}")
                
                # Local models often don't need an API key, but check for cloud ones
                if not api_key and provider not in {'OLLAMA', 'CUSTOM'}:
                    raise Exception("API Key not configured in Blender Addon Preferences.")
                
                # Define thread-safe execution callback
                def safe_execute_command(tool_command):
                    future = concurrent.futures.Future()
                    
                    def _run_in_main():
                        try:
                            from .core.router import execute_command
                            # Inject override context if possible, or just let it use default
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
                        return None # Do not reschedule
                        
                    bpy.app.timers.register(_run_in_main)
                    return future.result(timeout=120)

                # Process the chat request (blocks this background thread, but not Blender)
                result = handle_chat_request_headless(
                    prompt=prompt,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    allow_code_execution=allow_code_execution,
                    base_url=base_url,
                    execution_callback=safe_execute_command
                )
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))
                
            except Exception as e:
                logger.error(f"WebUI POST Error: {traceback.format_exc()}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        else:
            self.send_error(404, "Endpoint not found")

    def log_message(self, format, *args):
        # Suppress default HTTP logging to avoid spamming Blender console
        pass


class BlenderMCPWebUIServer:
    def __init__(self, port=8080):
        self.port = port
        self.server = None
        self.server_thread = None

    def start(self):
        if self.server:
            logger.warning("WebUI Server is already running")
            return
            
        try:
            self.server = http.server.ThreadingHTTPServer(('', self.port), WebUIHandler)
            self.server_thread = threading.Thread(target=self.server.serve_forever, name="blender-mcp-webui")
            self.server_thread.daemon = True
            self.server_thread.start()
            logger.info(f"WebUI Server started on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start WebUI Server: {e}")
            self.stop()

    def stop(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception as e:
                logger.error(f"Error closing WebUI Server: {e}")
            self.server = None
            
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)
            self.server_thread = None
        logger.info("WebUI Server stopped")
