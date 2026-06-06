import os
import shutil

# Bootstrap to find addon package
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from addon.utils import helpers


class TestClientDetection(unittest.TestCase):
    def setUp(self):
        # Reset any cached states if necessary
        pass

    @patch("shutil.which")
    @patch("os.path.isfile")
    def test_ollama_detection_by_binary(self, mock_isfile, mock_which):
        # Scenario: ollama found in PATH
        mock_which.return_value = "/usr/bin/ollama"
        mock_isfile.return_value = True

        self.assertTrue(helpers._is_ollama_installed())

        # Scenario: ollama NOT in PATH but in local bin
        mock_which.return_value = None
        mock_isfile.side_effect = lambda p: p.endswith("ollama")

        self.assertTrue(helpers._is_ollama_installed())

    @patch("platform.system")
    @patch("os.path.isdir")
    def test_claude_detection_linux(self, mock_isdir, mock_system):
        mock_system.return_value = "Linux"
        mock_isdir.side_effect = lambda p: ".config/Claude" in p

        self.assertTrue(helpers._is_claude_installed())

    @patch("platform.system")
    @patch("os.path.isdir")
    def test_cursor_detection_linux(self, mock_isdir, mock_system):
        mock_system.return_value = "Linux"
        mock_isdir.side_effect = lambda p: ".config/Cursor" in p

        self.assertTrue(helpers._is_cursor_installed())

    @patch("shutil.which")
    @patch("os.path.isdir")
    @patch("platform.system")
    def test_lm_studio_detection_linux(self, mock_system, mock_isdir, mock_which):
        mock_system.return_value = "Linux"
        mock_which.return_value = None
        mock_isdir.side_effect = lambda p: ".cache/lm-studio" in p

        self.assertTrue(helpers._is_lm_studio_installed())

    @patch("platform.system")
    @patch("os.path.isdir")
    def test_cherry_studio_detection_linux(self, mock_isdir, mock_system):
        mock_system.return_value = "Linux"
        mock_isdir.side_effect = lambda p: ".cherrystudio" in p

        self.assertTrue(helpers._is_cherry_studio_installed())

    @patch("addon.utils.helpers._is_ollama_installed")
    @patch("addon.utils.helpers._is_claude_installed")
    @patch("addon.utils.helpers._is_cursor_installed")
    @patch("addon.utils.helpers._is_lm_studio_installed")
    @patch("addon.utils.helpers._is_cherry_studio_installed")
    def test_detect_installed_clients_priority(
        self, mock_cherry, mock_lms, mock_cursor, mock_claude, mock_ollama
    ):
        # Scenario: All detected
        mock_ollama.return_value = True
        mock_claude.return_value = True
        mock_cursor.return_value = True
        mock_lms.return_value = True
        mock_cherry.return_value = True

        results = helpers.detect_installed_clients()

        # Ollama should be first
        self.assertEqual(results[0][0], "ollama")
        self.assertEqual(len(results), 5)

    @patch("addon.utils.helpers._is_ollama_installed")
    @patch("addon.utils.helpers._is_claude_installed")
    @patch("addon.utils.helpers._is_cursor_installed")
    @patch("addon.utils.helpers._is_lm_studio_installed")
    @patch("addon.utils.helpers._is_cherry_studio_installed")
    def test_detect_nothing_fallback(
        self, mock_cherry, mock_lms, mock_cursor, mock_claude, mock_ollama
    ):
        # Scenario: None detected
        mock_ollama.return_value = False
        mock_claude.return_value = False
        mock_cursor.return_value = False
        mock_lms.return_value = False
        mock_cherry.return_value = False

        results = helpers.detect_installed_clients()

        # Should return full list (fallback)
        self.assertEqual(len(results), 5)


if __name__ == "__main__":
    unittest.main()
