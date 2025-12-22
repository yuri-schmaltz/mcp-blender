"""Tests for progress tracking."""

import time
import pytest
from blender_mcp.progress import (
    ProgressInfo,
    ProgressTracker,
    get_progress_tracker,
)


class TestProgressInfo:
    """Test ProgressInfo dataclass."""
    
    def test_progress_percent(self):
        """Calculate progress percentage correctly."""
        progress = ProgressInfo(
            operation_id="test",
            total_bytes=1000,
            downloaded_bytes=250,
            start_time=time.time(),
            status="running"
        )
        assert progress.progress_percent == 25.0
    
    def test_progress_percent_zero_total(self):
        """Handle zero total bytes."""
        progress = ProgressInfo(
            operation_id="test",
            total_bytes=0,
            downloaded_bytes=0,
            start_time=time.time(),
            status="running"
        )
        assert progress.progress_percent == 0.0
    
    def test_download_speed(self):
        """Calculate download speed."""
        start = time.time() - 10  # 10 seconds ago
        progress = ProgressInfo(
            operation_id="test",
            total_bytes=10_000_000,  # 10 MB
            downloaded_bytes=5_000_000,  # 5 MB
            start_time=start,
            status="running"
        )
        # Should be around 0.5 MB/s (5 MB in 10 seconds)
        assert 0.4 < progress.download_speed_mbps < 0.6
    
    def test_eta_calculation(self):
        """Calculate ETA."""
        start = time.time() - 10  # 10 seconds ago
        progress = ProgressInfo(
            operation_id="test",
            total_bytes=10_000_000,  # 10 MB total
            downloaded_bytes=5_000_000,  # 5 MB done
            start_time=start,
            status="running"
        )
        # Should be around 10 seconds (5 MB left at 0.5 MB/s)
        eta = progress.eta_seconds
        assert eta is not None
        assert 8 <= eta <= 12
    
    def test_format_progress_running(self):
        """Format running progress."""
        progress = ProgressInfo(
            operation_id="test",
            total_bytes=1000,
            downloaded_bytes=250,
            start_time=time.time() - 1,
            status="running"
        )
        formatted = progress.format_progress()
        assert "25.0%" in formatted
        assert "MB/s" in formatted
    
    def test_format_progress_completed(self):
        """Format completed progress."""
        progress = ProgressInfo(
            operation_id="test",
            total_bytes=1000,
            downloaded_bytes=1000,
            start_time=time.time(),
            status="completed"
        )
        formatted = progress.format_progress()
        assert "✅" in formatted or "Complete" in formatted


class TestProgressTracker:
    """Test ProgressTracker functionality."""
    
    def test_start_operation(self):
        """Start tracking an operation."""
        tracker = ProgressTracker()
        progress = tracker.start_operation("test_op", 1000)
        
        assert progress.operation_id == "test_op"
        assert progress.total_bytes == 1000
        assert progress.downloaded_bytes == 0
        assert progress.status == "running"
    
    def test_update_progress(self):
        """Update operation progress."""
        tracker = ProgressTracker()
        tracker.start_operation("test_op", 1000)
        
        progress = tracker.update_progress("test_op", 500)
        assert progress.downloaded_bytes == 500
        assert progress.progress_percent == 50.0
    
    def test_auto_complete_on_full_download(self):
        """Auto-complete when bytes reach total."""
        tracker = ProgressTracker()
        tracker.start_operation("test_op", 1000)
        
        progress = tracker.update_progress("test_op", 1000)
        assert progress.status == "completed"
    
    def test_complete_operation(self):
        """Manually complete operation."""
        tracker = ProgressTracker()
        tracker.start_operation("test_op", 1000)
        tracker.complete_operation("test_op")
        
        progress = tracker.get_progress("test_op")
        assert progress.status == "completed"
    
    def test_cancel_operation(self):
        """Cancel operation."""
        tracker = ProgressTracker()
        tracker.start_operation("test_op", 1000)
        tracker.cancel_operation("test_op")
        
        progress = tracker.get_progress("test_op")
        assert progress.status == "cancelled"
    
    def test_error_operation(self):
        """Mark operation as errored."""
        tracker = ProgressTracker()
        tracker.start_operation("test_op", 1000)
        tracker.error_operation("test_op", "Network error")
        
        progress = tracker.get_progress("test_op")
        assert progress.status == "error"
        assert progress.error_message == "Network error"
    
    def test_get_all_operations(self):
        """Get all tracked operations."""
        tracker = ProgressTracker()
        tracker.start_operation("op1", 1000)
        tracker.start_operation("op2", 2000)
        
        all_ops = tracker.get_all_operations()
        assert len(all_ops) == 2
        assert "op1" in all_ops
        assert "op2" in all_ops
    
    def test_progress_callbacks(self):
        """Callbacks are called on progress updates."""
        tracker = ProgressTracker()
        called_with = []
        
        def callback(progress: ProgressInfo):
            called_with.append(progress.operation_id)
        
        tracker.register_callback(callback)
        tracker.start_operation("test_op", 1000)
        tracker.update_progress("test_op", 500)
        
        assert "test_op" in called_with
        assert len(called_with) == 2  # start + update
    
    def test_cleanup_completed(self):
        """Clean up old completed operations."""
        tracker = ProgressTracker()
        
        # Create old completed operation
        tracker.start_operation("old_op", 1000)
        old_progress = tracker.get_progress("old_op")
        old_progress.start_time = time.time() - 400  # 400 seconds ago
        old_progress.status = "completed"
        
        # Create recent completed operation
        tracker.start_operation("new_op", 1000)
        tracker.complete_operation("new_op")
        
        # Cleanup operations older than 300 seconds
        removed = tracker.cleanup_completed(max_age_seconds=300)
        
        assert removed == 1
        assert tracker.get_progress("old_op") is None
        assert tracker.get_progress("new_op") is not None
    
    def test_global_tracker(self):
        """Test global tracker singleton."""
        tracker1 = get_progress_tracker()
        tracker2 = get_progress_tracker()
        
        assert tracker1 is tracker2
