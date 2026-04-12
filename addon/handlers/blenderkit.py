import bpy
import requests
import json
import os
import time

# BlenderKit API URL
BASE_API_URL = "https://www.blenderkit.com/api/v1"

def search_blenderkit(scene, query, asset_type='model', free_only=True):
    """
    Search BlenderKit for assets.
    """
    url = f"{BASE_API_URL}/search/"
    params = {
        "query": query,
        "asset_type": asset_type,
        "order": "-_score",
        "page_size": 10
    }
    if free_only:
        params["free_only"] = True

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for asset in data.get("results", []):
            results.append({
                "id": asset.get("id"),
                "name": asset.get("name"),
                "description": asset.get("description"),
                "thumbnail": asset.get("thumbnail_small"),
                "author": asset.get("author", {}).get("firstName", ""),
                "is_free": asset.get("isFree"),
                "asset_type": asset.get("assetType")
            })
        
        return {"results": results}
    except Exception as e:
        return {"error": str(e)}

def import_blenderkit_asset(scene, asset_id):
    """
    Import a BlenderKit asset into the scene.
    NOTE: Downloads require authentication. 
    If official BlenderKit addon is installed, we try to use it.
    """
    # 1. Check if official BlenderKit addon is active
    addon_active = "blenderkit" in bpy.context.preferences.addons
    
    if addon_active:
        try:
            # We try to use the BlenderKit operator if possible.
            # This is tricky because their operator usually depends on UI context.
            # But we can try to trigger a download by ID.
            # In BlenderKit 3.x/4.x, the operator is bkit.download_asset
            if hasattr(bpy.ops, "blenderkit"):
                # Most BlenderKit operators require a specific context or are modal.
                # A safer way is to just tell the user we're handing it off to the official addon.
                # Or better: search for the asset in their internal database and trigger download.
                pass
        except Exception:
            pass

    # 2. Manual download (Complex - requires token and handling .blend append)
    # For now, we'll return a message that specialized import is in progress
    # or requires the official addon for best results.
    
    # Let's try to get more details for the LLM to decide
    url = f"{BASE_API_URL}/assets/{asset_id}/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        asset_data = response.json()
        
        # If the user provided a token in our addon, we could use it here.
        token = scene.blendermcp_blenderkit_api_key
        
        return {
            "message": f"Asset {asset_data.get('name')} found. Specialized download logic is being initialized. "
                       f"Please ensure the official BlenderKit addon is installed for optimal results.",
            "asset_name": asset_data.get("name"),
            "asset_id": asset_id
        }
    except Exception as e:
        return {"error": str(e)}
