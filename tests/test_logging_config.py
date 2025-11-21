import logging
import os
import tempfile
import unittest

from blender_mcp.logging_config import configure_logging
from blender_mcp.server import tool_error


class ConfigureLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root_logger = logging.getLogger()
        self.original_handlers = list(self.root_logger.handlers)
        self.original_level = self.root_logger.level
        self.temp_log = tempfile.NamedTemporaryFile(delete=False)
        self.temp_log.close()

    def tearDown(self) -> None:
        for handler in list(self.root_logger.handlers):
            self.root_logger.removeHandler(handler)
            handler.close()
        for handler in self.original_handlers:
            self.root_logger.addHandler(handler)
        self.root_logger.setLevel(self.original_level)
        os.unlink(self.temp_log.name)

    def test_configure_logging_uses_environment(self) -> None:
        os.environ["BLENDER_MCP_LOG_LEVEL"] = "DEBUG"
        os.environ["BLENDER_MCP_LOG_FORMAT"] = "%(levelname)s:%(message)s"
        os.environ["BLENDER_MCP_LOG_HANDLER"] = "file"
        os.environ["BLENDER_MCP_LOG_FILE"] = self.temp_log.name

        configure_logging()

        self.assertEqual(self.root_logger.level, logging.DEBUG)
        self.assertTrue(self.root_logger.handlers)
        handler = self.root_logger.handlers[0]
        self.assertIsInstance(handler, logging.FileHandler)
        self.assertEqual(handler.formatter._fmt, "%(levelname)s:%(message)s")

        # Clean up environment overrides
        os.environ.pop("BLENDER_MCP_LOG_LEVEL")
        os.environ.pop("BLENDER_MCP_LOG_FORMAT")
        os.environ.pop("BLENDER_MCP_LOG_HANDLER")
        os.environ.pop("BLENDER_MCP_LOG_FILE")


class ToolErrorTests(unittest.TestCase):
    def test_tool_error_shapes_payload(self) -> None:
        payload = tool_error("Something broke", data={"step": "connect"})
        self.assertIn("error", payload)
        self.assertEqual(payload["error"]["message"], "Something broke")
        self.assertEqual(payload["error"]["code"], "runtime_error")
        self.assertEqual(payload["error"]["data"], {"step": "connect"})


if __name__ == "__main__":
    unittest.main()
