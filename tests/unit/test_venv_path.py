import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Bootstrap to find addon package
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from addon.utils import helpers


class TestVenvPathExtension(unittest.TestCase):
    def setUp(self):
        self.original_sys_path = list(sys.path)

    def tearDown(self):
        sys.path = self.original_sys_path

    @patch("addon.utils.helpers.os.path.exists")
    @patch("addon.utils.helpers.os.listdir")
    def test_extend_sys_path_unix(self, mock_listdir, mock_exists):
        # We mock exists to return True for venv, lib, and lib/python3.10/site-packages
        # and False for Windows paths
        def exists_side_effect(path):
            if "Lib" in path:
                return False
            return True

        mock_exists.side_effect = exists_side_effect
        mock_listdir.return_value = ["python3.10"]

        # Call the extension function
        helpers.extend_sys_path_with_venv()

        # Check if the path was added to sys.path
        added_path = any("python3.10" in p and "site-packages" in p for p in sys.path)
        self.assertTrue(added_path)

    @patch("addon.utils.helpers.os.path.exists")
    def test_extend_sys_path_windows(self, mock_exists):
        # We mock exists to return True for Windows path and False for unix-like lib path
        def exists_side_effect(path):
            if "lib" in path:
                return False
            return True

        mock_exists.side_effect = exists_side_effect

        helpers.extend_sys_path_with_venv()

        added_path = any("Lib" in p and "site-packages" in p for p in sys.path)
        self.assertTrue(added_path)


if __name__ == "__main__":
    unittest.main()
