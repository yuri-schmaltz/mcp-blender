"""Sketchfab API handler for searching and downloading 3D models."""

import os
import shutil
import tempfile
import traceback
import zipfile
from contextlib import suppress

import bpy

from ..utils.network import robust_get

# Try to get progress tracker
PROGRESS_AVAILABLE = False
def get_progress_tracker():
    return None

try:
    from ...src.blender_mcp.progress import get_progress_tracker as _get_tracker
    get_progress_tracker = _get_tracker
    PROGRESS_AVAILABLE = True
except ImportError:
    pass


def get_sketchfab_status(scene):
    """Get the current status of Sketchfab integration"""
    enabled = scene.blendermcp_use_sketchfab
    api_key = scene.blendermcp_sketchfab_api_key

    if api_key:
        try:
            headers = {"Authorization": f"Token {api_key}"}
            response = robust_get(
                "https://api.sketchfab.com/v3/me",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 200:
                user_data = response.json()
                username = user_data.get("username", "Unknown user")
                return {
                    "enabled": True,
                    "message": f"Sketchfab integration is enabled and ready to use. Logged in as: {username}",
                }
            else:
                return {
                    "enabled": False,
                    "message": f"Sketchfab API key seems invalid. Status code: {response.status_code}",
                }
        except Exception as e:
            return {"enabled": False, "message": f"Error testing Sketchfab API key: {str(e)}"}

    if enabled and not api_key:
        return {
            "enabled": False,
            "message": """Sketchfab integration is currently enabled, but API key is not given. To enable it:
                        1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                        2. Keep the 'Use Sketchfab' checkbox checked
                        3. Enter your Sketchfab API Key
                        4. Restart the connection to your LLM client""",
        }
    else:
        return {
            "enabled": False,
            "message": """Sketchfab integration is currently disabled. To enable it:
                        1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                        2. Check the 'Use assets from Sketchfab' checkbox
                        3. Enter your Sketchfab API Key
                        4. Restart the connection to your LLM client""",
        }


def search_sketchfab_models(scene, query, categories=None, count=20, downloadable=True):
    """Search for models on Sketchfab"""
    try:
        api_key = scene.blendermcp_sketchfab_api_key
        if not api_key:
            return {"error": "Sketchfab API key is not configured"}

        params = {
            "type": "models",
            "q": query,
            "count": count,
            "downloadable": downloadable,
            "archives_flavours": False,
        }

        if categories:
            params["categories"] = categories

        headers = {"Authorization": f"Token {api_key}"}
        response = robust_get(
            "https://api.sketchfab.com/v3/search",
            headers=headers,
            params=params,
            timeout=30,
        )

        if response.status_code == 401:
            return {"error": "Authentication failed (401). Check your API key."}

        if response.status_code != 200:
            return {"error": f"API request failed with status code {response.status_code}"}

        return response.json()

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}


def download_sketchfab_model(scene, uid):
    """Download and import a model from Sketchfab"""
    try:
        api_key = scene.blendermcp_sketchfab_api_key
        if not api_key:
            return {"error": "Sketchfab API key is not configured"}

        headers = {"Authorization": f"Token {api_key}"}
        download_endpoint = f"https://api.sketchfab.com/v3/models/{uid}/download"

        response = robust_get(download_endpoint, headers=headers, timeout=30)

        if response.status_code == 401:
            return {"error": "Authentication failed (401). Check your API key."}

        if response.status_code != 200:
            return {"error": f"Download request failed with status code {response.status_code}"}

        data = response.json()
        gltf_data = data.get("gltf")
        if not gltf_data or not gltf_data.get("url"):
            return {"error": "No glTF download URL available for this model."}

        download_url = gltf_data.get("url")
        operation_id = f"sketchfab_{uid}"

        model_response = robust_get(download_url, timeout=60, stream=True)
        if model_response.status_code != 200:
            return {"error": f"Model download failed: {model_response.status_code}"}

        temp_dir = tempfile.mkdtemp()
        zip_file_path = os.path.join(temp_dir, f"{uid}.zip")

        total_size = int(model_response.headers.get("content-length", 0))
        downloaded = 0

        tracker = get_progress_tracker()
        if tracker:
            tracker.start_operation(operation_id, total_size)

        with open(zip_file_path, "wb") as f:
            for chunk in model_response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if tracker:
                        tracker.update_progress(operation_id, downloaded)

        if tracker:
            tracker.complete_operation(operation_id)

        # Extract and import
        with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
            for file_info in zip_ref.infolist():
                file_path = file_info.filename
                target_path = os.path.join(temp_dir, os.path.normpath(file_path))
                abs_temp_dir = os.path.abspath(temp_dir)
                abs_target_path = os.path.abspath(target_path)

                if not abs_target_path.startswith(abs_temp_dir) or ".." in file_path:
                    with suppress(Exception):
                        shutil.rmtree(temp_dir)
                    return {"error": "Security issue: Zip contains path traversal attempt"}

            zip_ref.extractall(temp_dir)

        gltf_files = [f for f in os.listdir(temp_dir) if f.endswith(".gltf") or f.endswith(".glb")]
        if not gltf_files:
            with suppress(Exception):
                shutil.rmtree(temp_dir)
            return {"error": "No glTF file found in the downloaded model"}

        main_file = os.path.join(temp_dir, gltf_files[0])
        bpy.ops.import_scene.gltf(filepath=main_file)
        
        # Pack all textures to ensure they persist after temp dir deletion
        bpy.ops.file.pack_all()
        
        imported_objects = [obj.name for obj in bpy.context.selected_objects]

        with suppress(Exception):
            shutil.rmtree(temp_dir)

        return {
            "success": True,
            "message": "Model imported successfully",
            "imported_objects": imported_objects,
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": f"Failed to download model: {str(e)}"}
