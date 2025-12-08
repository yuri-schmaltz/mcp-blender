"""Unit tests for validators module."""

import pytest
import sys
from pathlib import Path
import tempfile

# Add src to path
repo_root = Path(__file__).resolve().parents[2]
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from blender_mcp.shared import (
    ValidationError,
    validate_port,
    validate_api_key,
    validate_asset_id,
    secure_filename,
    validate_file_path,
    validate_resolution,
    validate_host,
)


class TestPortValidation:
    """Test port number validation."""
    
    def test_valid_port(self):
        """Should accept valid port numbers."""
        assert validate_port(9876) == 9876
        assert validate_port("9876") == 9876
        assert validate_port(1024) == 1024
        assert validate_port(65535) == 65535
    
    def test_reject_privileged_ports(self):
        """Should reject ports below 1024."""
        with pytest.raises(ValidationError, match="1024-65535"):
            validate_port(80)
        
        with pytest.raises(ValidationError, match="1024-65535"):
            validate_port(443)
    
    def test_reject_out_of_range(self):
        """Should reject ports out of valid range."""
        with pytest.raises(ValidationError):
            validate_port(0)
        
        with pytest.raises(ValidationError):
            validate_port(70000)
    
    def test_reject_invalid_types(self):
        """Should reject non-numeric ports."""
        with pytest.raises(ValidationError):
            validate_port("invalid")
        
        with pytest.raises(ValidationError):
            validate_port(None)


class TestAPIKeyValidation:
    """Test API key validation."""
    
    def test_valid_key(self):
        """Should accept valid API keys."""
        key = "abc123xyz789"
        assert validate_api_key(key) == key
    
    def test_reject_short_key(self):
        """Should reject keys below minimum length."""
        with pytest.raises(ValidationError, match="too short"):
            validate_api_key("short")
    
    def test_reject_empty_key(self):
        """Should reject empty keys."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_api_key("")
    
    def test_reject_placeholder_keys(self):
        """Should reject obvious placeholder keys."""
        with pytest.raises(ValidationError, match="placeholder"):
            validate_api_key("test_key_123")
        
        with pytest.raises(ValidationError, match="placeholder"):
            validate_api_key("dummy_api_key")
    
    def test_custom_min_length(self):
        """Should respect custom minimum length."""
        with pytest.raises(ValidationError):
            validate_api_key("12345", min_length=20)


class TestAssetIDValidation:
    """Test asset ID validation."""
    
    def test_valid_asset_ids(self):
        """Should accept valid asset IDs."""
        assert validate_asset_id("abandoned_factory") == "abandoned_factory"
        assert validate_asset_id("goegap-road") == "goegap-road"
        assert validate_asset_id("asset_123") == "asset_123"
    
    def test_reject_invalid_characters(self):
        """Should reject IDs with special characters."""
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_asset_id("asset/path")
        
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_asset_id("asset name")
    
    def test_reject_empty(self):
        """Should reject empty asset IDs."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_asset_id("")
    
    def test_reject_too_long(self):
        """Should reject overly long asset IDs."""
        long_id = "a" * 150
        with pytest.raises(ValidationError, match="too long"):
            validate_asset_id(long_id)


class TestSecureFilename:
    """Test filename sanitization."""
    
    def test_simple_filename(self):
        """Should return basename for simple filenames."""
        assert secure_filename("file.txt") == "file.txt"
        assert secure_filename("model.gltf") == "model.gltf"
    
    def test_remove_path_components(self):
        """Should remove directory components."""
        assert secure_filename("/path/to/file.txt") == "file.txt"
        assert secure_filename("../../../etc/passwd") == "passwd"
    
    def test_reject_hidden_files(self):
        """Should reject hidden files."""
        with pytest.raises(ValidationError, match="Hidden files"):
            secure_filename(".hidden")
    
    def test_reject_parent_refs(self):
        """Should reject parent directory references."""
        with pytest.raises(ValidationError, match="Parent directory"):
            secure_filename("file..txt")
    
    def test_reject_null_bytes(self):
        """Should reject null bytes."""
        with pytest.raises(ValidationError, match="Null bytes"):
            secure_filename("file\x00.txt")


class TestFilePathValidation:
    """Test file path validation."""
    
    def test_valid_temp_path(self):
        """Should accept valid temporary file paths."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
        
        try:
            validated = validate_file_path(tmp_path, must_exist=True)
            assert validated.exists()
        finally:
            tmp_path.unlink()
    
    def test_reject_relative_path(self):
        """Should reject relative paths."""
        with pytest.raises(ValidationError, match="must be absolute"):
            validate_file_path("relative/path.txt", must_exist=False)
    
    def test_must_exist_check(self):
        """Should check file existence when required."""
        fake_path = Path("/tmp/nonexistent_file_12345.txt")
        with pytest.raises(ValidationError, match="does not exist"):
            validate_file_path(fake_path, must_exist=True)
    
    def test_allow_nonexistent_when_not_required(self):
        """Should allow nonexistent files when must_exist=False."""
        temp_dir = Path(tempfile.gettempdir())
        fake_path = temp_dir / "nonexistent.txt"
        validated = validate_file_path(fake_path, must_exist=False)
        assert validated == fake_path.resolve()


class TestResolutionValidation:
    """Test resolution string validation."""
    
    def test_valid_resolutions(self):
        """Should accept valid resolution strings."""
        for res in ['1k', '2k', '4k', '8k']:
            assert validate_resolution(res) == res
    
    def test_case_insensitive(self):
        """Should be case-insensitive."""
        assert validate_resolution('2K') == '2k'
        assert validate_resolution('4K') == '4k'
    
    def test_reject_invalid_resolution(self):
        """Should reject invalid resolutions."""
        with pytest.raises(ValidationError, match="Invalid resolution"):
            validate_resolution('3k')
        
        with pytest.raises(ValidationError, match="Invalid resolution"):
            validate_resolution('high')


class TestHostValidation:
    """Test hostname validation."""
    
    def test_localhost(self):
        """Should accept localhost."""
        assert validate_host("localhost") == "localhost"
    
    def test_valid_ip_addresses(self):
        """Should accept valid IP addresses."""
        assert validate_host("127.0.0.1") == "127.0.0.1"
        assert validate_host("192.168.1.1") == "192.168.1.1"
    
    def test_reject_invalid_ip(self):
        """Should reject invalid IP addresses."""
        with pytest.raises(ValidationError, match="Invalid IP"):
            validate_host("999.999.999.999")
    
    def test_valid_hostnames(self):
        """Should accept valid hostnames."""
        assert validate_host("example.com") == "example.com"
        assert validate_host("sub.example.com") == "sub.example.com"
    
    def test_reject_invalid_hostname(self):
        """Should reject invalid hostnames."""
        with pytest.raises(ValidationError, match="Invalid hostname"):
            validate_host("invalid host name")
        
        with pytest.raises(ValidationError, match="Invalid hostname"):
            validate_host("host!name")
    
    def test_reject_empty(self):
        """Should reject empty host."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_host("")
