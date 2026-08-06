"""Poly Haven API handler for downloading HDRIs, textures, and models."""

import os
import shutil
import tempfile
import traceback
import zipfile

import bpy

from ..core.router import mcp_command
from ..utils.cache import get_asset_cache
from ..utils.circuit_breaker import (
    CircuitBreakerError,
    get_circuit_breaker,
)
from ..utils.constants import REQ_HEADERS
from ..utils.network import log_asset_download, robust_get


# One breaker for all Poly Haven calls — shared across search/download/resolve.
_POLYHAVEN_BREAKER = get_circuit_breaker("polyhaven")

# Try to get progress tracker
PROGRESS_AVAILABLE = False


def get_progress_tracker():
    return None


try:
    # This assumes the progress module is available in the expected location
    from ...src.blender_mcp.progress import get_progress_tracker as _get_tracker

    get_progress_tracker = _get_tracker
    PROGRESS_AVAILABLE = True
except ImportError:
    pass


def get_prefs():
    """Access global addon preferences safely."""
    from ..utils.helpers import get_addon_prefs

    return get_addon_prefs(__package__)


@mcp_command(name="get_polyhaven_status", read_only=True)
def get_polyhaven_status(scene):
    """Get the current status of PolyHaven integration"""
    prefs = get_prefs()
    enabled = prefs.use_polyhaven if prefs else False
    if enabled:
        return {
            "enabled": True,
            "message": "PolyHaven integration is enabled and ready to use.",
        }
    else:
        return {
            "enabled": False,
            "message": """PolyHaven integration is currently disabled. To enable it:
                        1. Go to Edit > Preferences > Add-ons
                        2. Find Blender MCP and expand it
                        3. Check 'Use Poly Haven' in the Integrations section
                        4. Restart the connection to your LLM client""",
        }


@mcp_command(name="get_polyhaven_categories", read_only=True)
def get_polyhaven_categories(asset_type="hdris"):
    """Get available categories from Poly Haven"""
    try:
        url = f"https://api.polyhaven.com/categories/{asset_type}"
        response = robust_get(url, headers=REQ_HEADERS)
        if response.status_code == 200:
            return response.json()
        return {"error": f"API returned status {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}


@mcp_command(name="search_polyhaven_assets", read_only=True)
def search_polyhaven_assets(query, asset_type="hdris"):
    """Search Poly Haven assets"""
    try:
        url = "https://api.polyhaven.com/assets"
        params = {"t": asset_type}
        response = robust_get(
            url, params=params, headers=REQ_HEADERS, circuit_breaker=_POLYHAVEN_BREAKER
        )
        if response.status_code == 200:
            all_assets = response.json()
            results = {}
            query = query.lower()
            for asset_id, info in all_assets.items():
                if query in asset_id.lower() or any(
                    query in tag.lower() for tag in info.get("tags", [])
                ):
                    results[asset_id] = info
                if len(results) >= 20:  # Limit results
                    break
            return results
        return {"error": f"API returned status {response.status_code}"}
    except CircuitBreakerError as e:
        return {"error": f"Poly Haven temporarily unavailable: {e}"}
    except Exception as e:
        return {"error": str(e)}


def resolve_polyhaven_resolution(asset_id, asset_type, requested_res="4k"):
    """Verify if a resolution is available for an asset, fallback if not."""
    try:
        res_url = f"https://api.polyhaven.com/files/{asset_id}"
        response = robust_get(res_url, headers=REQ_HEADERS, circuit_breaker=_POLYHAVEN_BREAKER)
        if response.status_code != 200:
            return requested_res

        data = response.json()
        available = []

        if asset_type == "hdris":
            available = list(data.get("hdri", {}).keys())
        elif asset_type == "textures":
            # For textures, check 'diffuse' or 'all'
            available = list(data.get("all", {}).keys())
        elif asset_type == "models":
            available = list(data.get("downloadable", {}).keys())

        if requested_res in available:
            return requested_res

        # Fallback logic
        res_order = ["1k", "2k", "4k", "8k", "16k"]
        if requested_res not in res_order:
            return available[0] if available else requested_res

        current_idx = res_order.index(requested_res)
        # Try lower resolutions first
        for i in range(current_idx - 1, -1, -1):
            if res_order[i] in available:
                return res_order[i]
        # Then try higher
        for i in range(current_idx + 1, len(res_order)):
            if res_order[i] in available:
                return res_order[i]

        return available[0] if available else requested_res
    except Exception:
        return requested_res


@mcp_command(name="download_polyhaven_asset", read_only=False)
def download_polyhaven_asset(scene, asset_id, asset_type="hdris", resolution="4k"):
    """Download and set up a Poly Haven asset"""
    prefs = get_prefs()
    if not (prefs and prefs.use_polyhaven):
        return {"error": "PolyHaven integration is disabled in Blender settings."}

    resolution = resolve_polyhaven_resolution(asset_id, asset_type, resolution)
    cache = get_asset_cache()
    cached_path = cache.get(asset_id, asset_type, resolution)

    if cached_path:
        print(f"Using cached asset for {asset_id}")
        local_path = cached_path
    else:
        # Download logic
        try:
            if asset_type == "hdris":
                download_url = (
                    f"https://api.polyhaven.com/files/{asset_id}?file={asset_id}_{resolution}.exr"
                )
            elif asset_type == "textures":
                download_url = f"https://api.polyhaven.com/files/{asset_id}?file={asset_id}_{resolution}_png.zip"
            elif asset_type == "models":
                download_url = (
                    f"https://api.polyhaven.com/files/{asset_id}?file={asset_id}_{resolution}.zip"
                )
            else:
                return {"error": f"Unsupported asset type: {asset_type}"}

            response = robust_get(
                download_url,
                headers=REQ_HEADERS,
                stream=True,
                circuit_breaker=_POLYHAVEN_BREAKER,
            )
            if response.status_code != 200:
                # Try fallback for format (sometimes it's .hdr instead of .exr)
                if asset_type == "hdris":
                    alt_url = f"https://api.polyhaven.com/files/{asset_id}?file={asset_id}_{resolution}.hdr"
                    response = robust_get(alt_url, headers=REQ_HEADERS, stream=True)
                    if response.status_code != 200:
                        return {"error": f"Failed to download asset: {response.status_code}"}
                else:
                    return {"error": f"Failed to download asset: {response.status_code}"}

            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=".exr" if asset_type == "hdris" else ".zip"
            )
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            operation_id = f"polyhaven_{asset_id}_{resolution}"
            tracker = get_progress_tracker()
            if tracker:
                tracker.start_operation(operation_id, total_size)

            with open(temp_file.name, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if tracker:
                            tracker.update_progress(operation_id, downloaded)

            if tracker:
                tracker.complete_operation(operation_id)

            local_path = cache.put(asset_id, asset_type, temp_file.name, resolution)
            os.unlink(temp_file.name)

            log_asset_download("polyhaven", asset_id, asset_type, resolution)

        except Exception as e:
            return {"error": f"Download failed: {str(e)}"}

    # Import/Setup in Blender
    try:
        if asset_type == "hdris":
            # Set up world HDRI
            if not bpy.context.scene.world:
                bpy.context.scene.world = bpy.data.worlds.new("World")

            world = bpy.context.scene.world
            world.use_nodes = True
            nodes = world.node_tree.nodes
            links = world.node_tree.links

            nodes.clear()
            node_output = nodes.new(type="ShaderNodeOutputWorld")
            node_background = nodes.new(type="ShaderNodeBackground")
            node_env = nodes.new(type="ShaderNodeTexEnvironment")

            try:
                img = bpy.data.images.load(local_path)
                img.pack()
                node_env.image = img
            except Exception as e:
                return {"error": f"Failed to load image into Blender: {str(e)}"}

            links.new(node_env.outputs["Color"], node_background.inputs["Color"])
            links.new(node_background.outputs["Background"], node_output.inputs["Surface"])

            return {"success": True, "message": f"HDRI {asset_id} applied to world background."}

        elif asset_type == "textures":
            # Textures setup (requires set_texture logic which will be moved to material_tools)
            # For now, we'll need to call the set_texture logic.
            # In the final refactor, addon.py will coordinate this.
            # But let's keep the core extraction logic here.
            return {
                "success": True,
                "message": f"Texture {asset_id} downloaded to {local_path}. Extraction and application pending setup_texture call.",
                "path": local_path,
            }

        elif asset_type == "models":
            # Unzip and import
            temp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(local_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find gltf/glb files
            gltf_files = []
            for root, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith(".gltf") or file.endswith(".glb"):
                        gltf_files.append(os.path.join(root, file))

            if not gltf_files:
                return {"error": "No importable model file found in the ZIP."}

            bpy.ops.import_scene.gltf(filepath=gltf_files[0])
            shutil.rmtree(temp_dir)
            return {"success": True, "message": f"Model {asset_id} imported successfully."}

    except Exception as e:
        traceback.print_exc()
        return {"error": f"Blender setup failed: {str(e)}"}

    return {"error": "Unknown error"}
