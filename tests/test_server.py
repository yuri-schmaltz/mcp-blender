import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class _DummyFastMCP:
    def __init__(self, *_, **__):
        pass

    def tool(self, *_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    def prompt(self, *_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    def run(self):
        return None


class _DummyContext:
    pass


class _DummyImage:
    def __init__(self, data=None, format=None):
        self.data = data
        self.format = format


fastmcp_module = types.ModuleType("mcp.server.fastmcp")
fastmcp_module.FastMCP = _DummyFastMCP
fastmcp_module.Context = _DummyContext
fastmcp_module.Image = _DummyImage

sys.modules["mcp"] = types.ModuleType("mcp")
sys.modules["mcp.server"] = types.ModuleType("mcp.server")
sys.modules["mcp.server.fastmcp"] = fastmcp_module
sys.modules["mcp.server"].fastmcp = fastmcp_module

from blender_mcp import server


class ScreenshotSafetyTests(unittest.TestCase):
    def test_prepare_temp_file_path_requires_existing_dir(self):
        missing_dir = Path(tempfile.gettempdir()) / "nonexistent_subdir_for_tests"
        with mock.patch("tempfile.gettempdir", return_value=str(missing_dir)):
            with self.assertRaises(FileNotFoundError):
                server._prepare_temp_file_path()

    def test_get_viewport_screenshot_cleans_up_on_failure(self):
        temp_path = Path(tempfile.gettempdir()) / "blender_screenshot_test.png"
        cleanup_spy = mock.Mock()

        with mock.patch.object(server, "_prepare_temp_file_path", return_value=temp_path), \
            mock.patch.object(server, "_read_file_with_retry", side_effect=FileNotFoundError("missing")), \
            mock.patch.object(server, "_cleanup_file", cleanup_spy), \
            mock.patch.object(server, "get_blender_connection"):

            with self.assertRaises(Exception):
                server.get_viewport_screenshot(mock.Mock())

        cleanup_spy.assert_called_once_with(temp_path)


class AssetPathValidationTests(unittest.TestCase):
    def test_generate_model_rejects_relative_paths(self):
        response = server.generate_hyper3d_model_via_images(
            mock.Mock(),
            input_image_paths=["relative/path/to/image.png"],
            input_image_urls=None,
        )
        self.assertIn("absolute path", response)


if __name__ == "__main__":
    unittest.main()
