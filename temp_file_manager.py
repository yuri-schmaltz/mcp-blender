"""Temporary file management utilities for safer cleanup."""
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
        # Register cleanup on exit
        atexit.register(self.cleanup_all)
    
    def register_file(self, filepath: str) -> str:
        """Register a temporary file for cleanup.
        
        Args:
            filepath: Path to the temporary file
            
        Returns:
            The same filepath for convenience
        """
        self._temp_files.add(filepath)
        logger.debug(f"Registered temp file: {filepath}")
        return filepath
    
    def register_dir(self, dirpath: str) -> str:
        """Register a temporary directory for cleanup.
        
        Args:
            dirpath: Path to the temporary directory
            
        Returns:
            The same dirpath for convenience
        """
        self._temp_dirs.add(dirpath)
        logger.debug(f"Registered temp dir: {dirpath}")
        return dirpath
    
    def cleanup_file(self, filepath: str, silent: bool = True) -> bool:
        """Clean up a specific temporary file.
        
        Args:
            filepath: Path to the file to clean up
            silent: If True, suppress errors
            
        Returns:
            True if cleanup succeeded, False otherwise
        """
        try:
            if os.path.exists(filepath):
                os.unlink(filepath)
                logger.debug(f"Cleaned up temp file: {filepath}")
            self._temp_files.discard(filepath)
            return True
        except Exception as e:
            if not silent:
                logger.error(f"Failed to cleanup file {filepath}: {e}")
            return False
    
    def cleanup_dir(self, dirpath: str, silent: bool = True) -> bool:
        """Clean up a specific temporary directory.
        
        Args:
            dirpath: Path to the directory to clean up
            silent: If True, suppress errors
            
        Returns:
            True if cleanup succeeded, False otherwise
        """
        try:
            if os.path.exists(dirpath):
                shutil.rmtree(dirpath)
                logger.debug(f"Cleaned up temp dir: {dirpath}")
            self._temp_dirs.discard(dirpath)
            return True
        except Exception as e:
            if not silent:
                logger.error(f"Failed to cleanup directory {dirpath}: {e}")
            return False
    
    def cleanup_all(self) -> None:
        """Clean up all registered temporary files and directories."""
        # Clean up files first
        for filepath in list(self._temp_files):
            self.cleanup_file(filepath, silent=True)
        
        # Then clean up directories
        for dirpath in list(self._temp_dirs):
            self.cleanup_dir(dirpath, silent=True)
        
        logger.debug("Cleaned up all temp files and directories")


# Global registry instance
_registry = TempFileRegistry()


@contextmanager
def managed_temp_file(suffix="", prefix="tmp", dir=None, delete=True):
    """Context manager for temporary files with guaranteed cleanup.
    
    Args:
        suffix: Suffix for the temp file (e.g., ".png")
        prefix: Prefix for the temp file
        dir: Directory to create the file in
        delete: Whether to delete the file on exit
        
    Yields:
        Path to the temporary file
        
    Example:
        with managed_temp_file(suffix=".png") as tmp_path:
            # Use tmp_path
            pass
        # File is automatically cleaned up
    """
    tmp_file = tempfile.NamedTemporaryFile(
        suffix=suffix, prefix=prefix, dir=dir, delete=False
    )
    tmp_path = tmp_file.name
    tmp_file.close()
    
    if delete:
        _registry.register_file(tmp_path)
    
    try:
        yield tmp_path
    finally:
        if delete:
            _registry.cleanup_file(tmp_path)


@contextmanager
def managed_temp_dir(suffix="", prefix="tmp", dir=None, delete=True):
    """Context manager for temporary directories with guaranteed cleanup.
    
    Args:
        suffix: Suffix for the temp directory
        prefix: Prefix for the temp directory
        dir: Parent directory to create the temp dir in
        delete: Whether to delete the directory on exit
        
    Yields:
        Path to the temporary directory
        
    Example:
        with managed_temp_dir() as tmp_dir:
            # Use tmp_dir
            pass
        # Directory is automatically cleaned up
    """
    tmp_dir = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
    
    if delete:
        _registry.register_dir(tmp_dir)
    
    try:
        yield tmp_dir
    finally:
        if delete:
            _registry.cleanup_dir(tmp_dir)


def create_managed_temp_file(suffix="", prefix="tmp", dir=None) -> str:
    """Create a temporary file that will be cleaned up on exit.
    
    Args:
        suffix: Suffix for the temp file (e.g., ".png")
        prefix: Prefix for the temp file
        dir: Directory to create the file in
        
    Returns:
        Path to the temporary file
        
    Note:
        File will be automatically cleaned up on program exit or via cleanup_all()
    """
    tmp_file = tempfile.NamedTemporaryFile(
        suffix=suffix, prefix=prefix, dir=dir, delete=False
    )
    tmp_path = tmp_file.name
    tmp_file.close()
    return _registry.register_file(tmp_path)


def create_managed_temp_dir(suffix="", prefix="tmp", dir=None) -> str:
    """Create a temporary directory that will be cleaned up on exit.
    
    Args:
        suffix: Suffix for the temp directory
        prefix: Prefix for the temp directory
        dir: Parent directory to create the temp dir in
        
    Returns:
        Path to the temporary directory
        
    Note:
        Directory will be automatically cleaned up on program exit or via cleanup_all()
    """
    tmp_dir = tempfile.mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
    return _registry.register_dir(tmp_dir)


def cleanup_all():
    """Manually trigger cleanup of all managed temporary files and directories."""
    _registry.cleanup_all()
