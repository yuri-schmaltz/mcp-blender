import base64
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch


def _add_src_to_path():
    """Ensure the repository's src directory is importable."""
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in os.sys.path:
        os.sys.path.insert(0, str(src_path))


_add_src_to_path()


def _mock_mcp_dependencies():
    """Provide lightweight stand-ins for the mcp package to enable imports."""
    if "mcp" in sys.modules:
        return

    class _DummyFastMCP:
        def __init__(self, *_, **__):
            pass

        def resource(self, *_, **__):
            def decorator(func):
                return func

            return decorator

        def tool(self, *_, **__):
            def decorator(func):
                return func

            return decorator

        def prompt(self, *_, **__):
            def decorator(func):
                return func

            return decorator

    mcp_module = types.ModuleType("mcp")
    mcp_server_module = types.ModuleType("mcp.server")
    mcp_server_fastmcp_module = types.ModuleType("mcp.server.fastmcp")

    mcp_server_fastmcp_module.FastMCP = _DummyFastMCP
    mcp_server_fastmcp_module.Context = MagicMock()
    mcp_server_fastmcp_module.Image = MagicMock()

    mcp_server_module.fastmcp = mcp_server_fastmcp_module
    mcp_module.server = mcp_server_module

    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = mcp_server_module
    sys.modules["mcp.server.fastmcp"] = mcp_server_fastmcp_module


_mock_mcp_dependencies()

from blender_mcp import server  # noqa: E402  # isort: skip


class GenerateHyper3DModelViaImagesTests(TestCase):
    def test_file_paths_validation_fails(self):
        result = server.generate_hyper3d_model_via_images(
            ctx=None,
            input_image_paths=["/nonexistent/path.png"],
        )

        self.assertEqual(result, "Error: not all image paths are valid!")

    def test_urls_validation_fails(self):
        result = server.generate_hyper3d_model_via_images(
            ctx=None,
            input_image_urls=["not-a-valid-url"],
        )

        self.assertEqual(result, "Error: not all image URLs are valid!")

    def test_generates_model_from_file_paths(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"image-bytes")
            image_path = tmp.name

        expected_b64 = base64.b64encode(b"image-bytes").decode("ascii")
        mock_blender = MagicMock()
        mock_blender.send_command.return_value = {
            "submit_time": True,
            "uuid": "task-123",
            "jobs": {"subscription_key": "sub-456"},
        }

        try:
            with patch(
                "blender_mcp.server.get_blender_connection",
                return_value=mock_blender,
            ):
                result = server.generate_hyper3d_model_via_images(
                    ctx=None,
                    input_image_paths=[image_path],
                )
        finally:
            os.unlink(image_path)

        payload = json.loads(result)
        self.assertEqual(payload["task_uuid"], "task-123")
        mock_blender.send_command.assert_called_once()
        sent_params = mock_blender.send_command.call_args[0][1]
        self.assertEqual(sent_params["images"], [(".png", expected_b64)])

    def test_generates_model_from_urls(self):
        mock_blender = MagicMock()
        mock_blender.send_command.return_value = {
            "submit_time": True,
            "uuid": "task-789",
            "jobs": {"subscription_key": "sub-987"},
        }
        urls = ["https://example.com/img.png"]

        with patch(
            "blender_mcp.server.get_blender_connection",
            return_value=mock_blender,
        ):
            result = server.generate_hyper3d_model_via_images(
                ctx=None,
                input_image_urls=urls,
            )

        payload = json.loads(result)
        self.assertEqual(payload["task_uuid"], "task-789")
        mock_blender.send_command.assert_called_once()
        sent_params = mock_blender.send_command.call_args[0][1]
        self.assertEqual(sent_params["images"], urls)
