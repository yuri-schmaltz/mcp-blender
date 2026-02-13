"""Input validation utilities for BlenderMCP."""

import os
import re
from pathlib import Path
from typing import Union


class ValidationError(ValueError):
    """Raised when validation fails."""

    pass


def validate_port(port: Union[int, str]) -> int:
    """Validate port number is in acceptable range.

    Args:
        port: Port number to validate

    Returns:
        Validated port number as integer

    Raises:
        ValidationError: If port is out of range or invalid
    """
    try:
        port_int = int(port)
    except (ValueError, TypeError):
        raise ValidationError(f"Port must be an integer, got: {port}")

    if not 1024 <= port_int <= 65535:
        raise ValidationError(
            f"Port must be between 1024-65535 (privileged ports not allowed), " f"got: {port_int}"
        )

    return port_int


def validate_api_key(key: str, min_length: int = 10, name: str = "API key") -> str:
    """Validate API key format and length.

    Args:
        key: API key to validate
        min_length: Minimum required length
        name: Name of the key for error messages

    Returns:
        Validated API key

    Raises:
        ValidationError: If key is invalid
    """
    if not isinstance(key, str):
        raise ValidationError(f"{name} must be a string")

    if not key:
        raise ValidationError(f"{name} cannot be empty")

    if len(key) < min_length:
        raise ValidationError(
            f"{name} too short (minimum {min_length} characters), " f"got {len(key)} characters"
        )

    # Check for suspicious patterns
    if key.startswith(("test_", "dummy_", "fake_")):
        raise ValidationError(f"{name} appears to be a placeholder")

    return key


def validate_asset_id(asset_id: str) -> str:
    """Validate asset ID for PolyHaven/Sketchfab.

    Args:
        asset_id: Asset identifier to validate

    Returns:
        Validated asset ID

    Raises:
        ValidationError: If asset ID is invalid
    """
    if not isinstance(asset_id, str):
        raise ValidationError("Asset ID must be a string")

    if not asset_id:
        raise ValidationError("Asset ID cannot be empty")

    # Allow alphanumeric, underscores, hyphens
    if not re.match(r"^[a-zA-Z0-9_-]+$", asset_id):
        raise ValidationError(
            f"Asset ID contains invalid characters: {asset_id}. "
            "Only alphanumeric, underscores, and hyphens allowed."
        )

    if len(asset_id) > 100:
        raise ValidationError(f"Asset ID too long (max 100 chars): {asset_id}")

    return asset_id


def secure_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename (basename only, no directory components)

    Raises:
        ValidationError: If filename is invalid
    """
    if not isinstance(filename, str):
        raise ValidationError("Filename must be a string")

    if not filename:
        raise ValidationError("Filename cannot be empty")

    # Remove any path components
    safe_name = os.path.basename(filename)

    # Additional validation
    if safe_name.startswith("."):
        raise ValidationError(f"Hidden files not allowed: {safe_name}")

    if ".." in safe_name:
        raise ValidationError(f"Parent directory references not allowed: {safe_name}")

    # Check for null bytes
    if "\x00" in safe_name:
        raise ValidationError("Null bytes in filename not allowed")

    return safe_name


def validate_file_path(path: Union[str, Path], must_exist: bool = True) -> Path:
    """Validate file path is safe and optionally exists.

    Args:
        path: File path to validate
        must_exist: Whether the file must exist

    Returns:
        Validated Path object

    Raises:
        ValidationError: If path is invalid or doesn't exist
    """
    try:
        path_obj = Path(path)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"Invalid path: {e}")

    # Must be absolute for security
    if not path_obj.is_absolute():
        raise ValidationError(f"Path must be absolute to avoid unintended locations: {path}")

    # Check for path traversal
    try:
        path_obj.resolve().relative_to(Path.home())
    except ValueError:
        # Not under home directory - check if it's a temp directory
        import tempfile

        temp_dir = Path(tempfile.gettempdir())
        try:
            path_obj.resolve().relative_to(temp_dir)
        except ValueError:
            raise ValidationError(f"Path must be under home directory or temp directory: {path}")

    if must_exist and not path_obj.exists():
        raise ValidationError(f"Path does not exist: {path}")

    return path_obj


def validate_resolution(resolution: str) -> str:
    """Validate asset resolution format.

    Args:
        resolution: Resolution string (e.g., '1k', '2k', '4k')

    Returns:
        Validated resolution string

    Raises:
        ValidationError: If resolution is invalid
    """
    valid_resolutions = ["1k", "2k", "4k", "8k", "16k"]

    if resolution.lower() not in valid_resolutions:
        raise ValidationError(
            f"Invalid resolution: {resolution}. " f"Must be one of: {', '.join(valid_resolutions)}"
        )

    return resolution.lower()


def validate_host(host: str) -> str:
    """Validate hostname or IP address.

    Args:
        host: Hostname or IP to validate

    Returns:
        Validated host string

    Raises:
        ValidationError: If host is invalid
    """
    if not isinstance(host, str):
        raise ValidationError("Host must be a string")

    if not host:
        raise ValidationError("Host cannot be empty")

    # Basic validation - allow localhost, IPs, and hostnames
    if host == "localhost":
        return host

    # Check for IP address pattern
    ip_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
    if re.match(ip_pattern, host):
        # Validate IP octets
        octets = host.split(".")
        for octet in octets:
            if not 0 <= int(octet) <= 255:
                raise ValidationError(f"Invalid IP address: {host}")
        return host

    # Check for valid hostname pattern
    hostname_pattern = r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
    if not re.match(hostname_pattern, host):
        raise ValidationError(f"Invalid hostname: {host}. Must be valid IP or hostname.")

    return host
