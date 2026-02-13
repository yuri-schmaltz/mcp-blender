# Utilitário de gerenciamento de arquivos temporários
# Movido de temp_file_manager.py para utils/temp_file_manager.py

import atexit
import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TempFileRegistry:
    """Registry to track temporary files and directories for cleanup."""

    def __init__(self):
        self._temp_files = set()
        self._temp_dirs = set()
        atexit.register(self.cleanup_all)

    def register_file(self, filepath: str) -> str:
        self._temp_files.add(filepath)
        logger.debug(f"Registered temp file: {filepath}")
        return filepath

    def register_dir(self, dirpath: str) -> str:
        self._temp_dirs.add(dirpath)
        logger.debug(f"Registered temp dir: {dirpath}")
        return dirpath

    def cleanup_all(self):
        for f in list(self._temp_files):
            try:
                os.remove(f)
                logger.info(f"Removed temp file: {f}")
            except Exception as e:
                logger.warning(f"Failed to remove temp file {f}: {e}")
        for d in list(self._temp_dirs):
            try:
                shutil.rmtree(d)
                logger.info(f"Removed temp dir: {d}")
            except Exception as e:
                logger.warning(f"Failed to remove temp dir {d}: {e}")


@contextmanager
def temp_file(suffix: str = "", prefix: str = "tmp", dir: Optional[str] = None):
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
    os.close(fd)
    try:
        yield path
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


@contextmanager
def temp_dir(suffix: str = "", prefix: str = "tmp", dir: Optional[str] = None):
    path = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
    try:
        yield path
    finally:
        try:
            shutil.rmtree(path)
        except Exception:
            pass
