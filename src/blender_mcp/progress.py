"""Progress tracking for long-running operations (MP-02).

This module provides progress tracking infrastructure for downloads
and other long-running operations in the Blender addon.
"""

import time
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class ProgressInfo:
    """Progress information for an operation."""
    
    operation_id: str
    total_bytes: int
    downloaded_bytes: int
    start_time: float
    status: str  # 'running', 'completed', 'cancelled', 'error'
    error_message: Optional[str] = None
    
    @property
    def progress_percent(self) -> float:
        """Get progress as percentage (0-100)."""
        if self.total_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.total_bytes) * 100
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time
    
    @property
    def download_speed_mbps(self) -> float:
        """Get download speed in MB/s."""
        if self.elapsed_time == 0:
            return 0.0
        mb_downloaded = self.downloaded_bytes / (1024 * 1024)
        return mb_downloaded / self.elapsed_time
    
    @property
    def eta_seconds(self) -> Optional[int]:
        """Get estimated time remaining in seconds."""
        if self.downloaded_bytes == 0 or self.download_speed_mbps == 0:
            return None
        
        remaining_bytes = self.total_bytes - self.downloaded_bytes
        remaining_mb = remaining_bytes / (1024 * 1024)
        return int(remaining_mb / self.download_speed_mbps)
    
    def format_progress(self) -> str:
        """Format progress as human-readable string."""
        percent = self.progress_percent
        speed = self.download_speed_mbps
        
        if self.status == 'completed':
            return f"✅ Complete ({percent:.1f}%)"
        elif self.status == 'cancelled':
            return f"🚫 Cancelled ({percent:.1f}%)"
        elif self.status == 'error':
            return f"❌ Error: {self.error_message}"
        
        # Running status
        eta = self.eta_seconds
        eta_str = f", ETA: {eta}s" if eta else ""
        return f"⏳ {percent:.1f}% @ {speed:.2f} MB/s{eta_str}"


class ProgressTracker:
    """Track progress of multiple operations.
    
    This is used by the Blender addon to track download progress
    and can be queried by the MCP server to show progress to users.
    """
    
    def __init__(self):
        self._operations: dict[str, ProgressInfo] = {}
        self._callbacks: list[Callable[[ProgressInfo], None]] = []
    
    def start_operation(
        self,
        operation_id: str,
        total_bytes: int
    ) -> ProgressInfo:
        """Start tracking a new operation.
        
        Args:
            operation_id: Unique identifier for the operation
            total_bytes: Total size in bytes
            
        Returns:
            ProgressInfo object for this operation
        """
        progress = ProgressInfo(
            operation_id=operation_id,
            total_bytes=total_bytes,
            downloaded_bytes=0,
            start_time=time.time(),
            status='running'
        )
        self._operations[operation_id] = progress
        self._notify_callbacks(progress)
        return progress
    
    def update_progress(
        self,
        operation_id: str,
        downloaded_bytes: int
    ) -> ProgressInfo:
        """Update progress for an operation.
        
        Args:
            operation_id: Operation to update
            downloaded_bytes: New byte count
            
        Returns:
            Updated ProgressInfo
        """
        if operation_id not in self._operations:
            raise ValueError(f"Unknown operation: {operation_id}")
        
        progress = self._operations[operation_id]
        progress.downloaded_bytes = downloaded_bytes
        
        # Auto-complete when done
        if downloaded_bytes >= progress.total_bytes:
            progress.status = 'completed'
        
        self._notify_callbacks(progress)
        return progress
    
    def complete_operation(self, operation_id: str) -> None:
        """Mark operation as completed."""
        if operation_id in self._operations:
            self._operations[operation_id].status = 'completed'
            self._notify_callbacks(self._operations[operation_id])
    
    def cancel_operation(self, operation_id: str) -> None:
        """Mark operation as cancelled."""
        if operation_id in self._operations:
            self._operations[operation_id].status = 'cancelled'
            self._notify_callbacks(self._operations[operation_id])
    
    def error_operation(
        self,
        operation_id: str,
        error_message: str
    ) -> None:
        """Mark operation as errored."""
        if operation_id in self._operations:
            progress = self._operations[operation_id]
            progress.status = 'error'
            progress.error_message = error_message
            self._notify_callbacks(progress)
    
    def get_progress(self, operation_id: str) -> Optional[ProgressInfo]:
        """Get progress for an operation."""
        return self._operations.get(operation_id)
    
    def get_all_operations(self) -> dict[str, ProgressInfo]:
        """Get all tracked operations."""
        return self._operations.copy()
    
    def register_callback(
        self,
        callback: Callable[[ProgressInfo], None]
    ) -> None:
        """Register callback for progress updates.
        
        Callback will be called whenever progress is updated.
        """
        self._callbacks.append(callback)
    
    def _notify_callbacks(self, progress: ProgressInfo) -> None:
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(progress)
            except Exception as e:
                print(f"Error in progress callback: {e}")
    
    def cleanup_completed(self, max_age_seconds: int = 300) -> int:
        """Remove completed operations older than max_age.
        
        Args:
            max_age_seconds: Remove operations completed this long ago
            
        Returns:
            Number of operations removed
        """
        now = time.time()
        to_remove = []
        
        for op_id, progress in self._operations.items():
            if progress.status in ('completed', 'cancelled', 'error'):
                if now - progress.start_time > max_age_seconds:
                    to_remove.append(op_id)
        
        for op_id in to_remove:
            del self._operations[op_id]
        
        return len(to_remove)


# Global progress tracker instance
_global_tracker: Optional[ProgressTracker] = None


def get_progress_tracker() -> ProgressTracker:
    """Get global progress tracker instance."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = ProgressTracker()
    return _global_tracker
