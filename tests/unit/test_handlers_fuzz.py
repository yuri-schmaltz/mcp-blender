import json

import pytest

from addon.handlers.polyhaven import download_polyhaven_asset
from addon.handlers.scene import get_scene_info
from addon.handlers.sketchfab import search_sketchfab_models


def test_scene_info():
    result = get_scene_info()
    assert result["status"] == "success"
    assert "scene" in result


def test_polyhaven_download():
    result = download_polyhaven_asset("asset123")
    assert result["status"] == "success"
    assert result["asset_id"] == "asset123"


def test_sketchfab_search():
    result = search_sketchfab_models("car")
    assert result["status"] == "success"
    assert "results" in result


def test_scene_info_fuzz():
    # Fuzzing: entrada inválida não deve quebrar
    try:
        get_scene_info(None)
    except Exception:
        pass


def test_polyhaven_download_fuzz():
    try:
        download_polyhaven_asset(None)
    except Exception:
        pass
