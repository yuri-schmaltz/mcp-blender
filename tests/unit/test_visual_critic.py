import base64
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add repository root to path for addon imports
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import pytest

from addon.handlers.visual_critic import analyze_viewport_visuals


class MockPrefs:
    def __init__(self, provider="OLLAMA", base_url="http://127.0.0.1:11434", api_key=""):
        self.llm_provider = provider
        self.llm_base_url = base_url
        self.llm_api_key = api_key


def test_analyze_viewport_visuals_success(tmp_path):
    # Mock screenshot function to write a dummy file
    def mock_get_screenshot(scene, max_size, filepath, format):
        return {
            "success": True,
            "width": 800,
            "height": 600,
            "image_base64": base64.b64encode(b"dummy image data").decode("utf-8"),
        }

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = json.dumps(
        {"response": "The viewport shows a 3D scene with a blue cube."}
    ).encode("utf-8")

    with (
        patch(
            "addon.handlers.visual_critic.get_viewport_screenshot", side_effect=mock_get_screenshot
        ),
        patch("addon.handlers.visual_critic.get_prefs", return_value=MockPrefs()),
        patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen,
    ):
        res = analyze_viewport_visuals(None, prompt="What is here?", model="moondream")
        assert res["status"] == "success"
        assert res["analysis"] == "The viewport shows a 3D scene with a blue cube."
        assert res["model_used"] == "moondream"

        # Verify urlopen details
        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://127.0.0.1:11434/api/generate"

        # Verify request body contains encoded dummy data
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["model"] == "moondream"
        assert payload["prompt"] == "What is here?"
        assert payload["images"][0] == base64.b64encode(b"dummy image data").decode("utf-8")


def test_analyze_viewport_visuals_model_not_found(tmp_path):
    def mock_get_screenshot(scene, max_size, filepath, format):
        return {
            "success": True,
            "image_base64": base64.b64encode(b"dummy image data").decode("utf-8"),
        }

    # Mock HTTPError 404
    error_response = MagicMock()
    error_response.read.return_value = b"model 'moondream' not found"
    http_error = urllib.error.HTTPError(
        "http://127.0.0.1:11434/api/generate", 404, "Not Found", {}, error_response
    )

    # Mock tags response for installed models listing
    mock_tags_response = MagicMock()
    mock_tags_response.__enter__.return_value = mock_tags_response
    mock_tags_response.read.return_value = json.dumps({"models": [{"name": "qwen3.5:9b"}]}).encode(
        "utf-8"
    )

    with (
        patch(
            "addon.handlers.visual_critic.get_viewport_screenshot", side_effect=mock_get_screenshot
        ),
        patch("addon.handlers.visual_critic.get_prefs", return_value=MockPrefs()),
        patch("urllib.request.urlopen", side_effect=[http_error, mock_tags_response]),
    ):
        res = analyze_viewport_visuals(None, prompt="What is here?", model="moondream")
        assert "error" in res
        assert "Ollama vision model 'moondream' not found" in res["error"]
        assert "qwen3.5:9b" in res["error"]
