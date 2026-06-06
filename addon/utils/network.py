"""Network utilities for BlenderMCP: retry logic, session management, and friendly errors."""

import time

import requests

# Shared session with connection pooling and default timeout
_session = None


def get_session() -> requests.Session:
    """Get or create a shared requests session with retry defaults."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(
            {
                "User-Agent": "BlenderMCP/1.3.5 (Blender Addon)",
            }
        )
    return _session


def robust_get(url: str, *, max_retries: int = 2, timeout: int = 30, **kwargs) -> requests.Response:
    """GET with automatic retry on transient failures.

    Retries on: ConnectionError, Timeout, 429, 500, 502, 503, 504.
    Uses exponential backoff (1s, 2s).
    """
    session = get_session()
    last_error = None
    retryable_codes = {429, 500, 502, 503, 504}

    for attempt in range(max_retries + 1):
        try:
            response = session.get(url, timeout=timeout, **kwargs)
            if response.status_code not in retryable_codes or attempt == max_retries:
                return response
            # Server overloaded — wait and retry
            wait = min(2**attempt, 4)
            print(f"[blender-mcp] HTTP {response.status_code} from {url}, retrying in {wait}s...")
            time.sleep(wait)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
            if attempt == max_retries:
                raise
            wait = min(2**attempt, 4)
            print(f"[blender-mcp] Network error ({type(exc).__name__}), retrying in {wait}s...")
            time.sleep(wait)

    # Should not reach here, but just in case
    if last_error:
        raise last_error


def friendly_error(context: str, exc: Exception) -> dict:
    """Convert an exception into a user-friendly error dict."""
    if isinstance(exc, requests.Timeout):
        return {
            "error": f"{context}: Request timed out. Check your internet connection and try again."
        }
    if isinstance(exc, requests.ConnectionError):
        return {"error": f"{context}: Could not connect. Check your internet connection."}
    if isinstance(exc, requests.HTTPError):
        return {"error": f"{context}: Server returned an error ({exc.response.status_code})."}
    # Generic
    msg = str(exc)
    if len(msg) > 200:
        msg = msg[:200] + "..."
    return {"error": f"{context}: {msg}"}


# Resolution fallback chain for Poly Haven
POLYHAVEN_RESOLUTION_FALLBACKS = {
    "8k": ["4k", "2k", "1k"],
    "4k": ["2k", "1k"],
    "2k": ["1k"],
    "1k": [],
}


def resolve_polyhaven_resolution(
    files_data: dict, section: str, requested_resolution: str, file_format: str
) -> tuple:
    """Try requested resolution, then fall back to lower ones.

    Returns (resolution, file_info) or (None, None) if nothing found.
    """
    if section not in files_data:
        return None, None

    # Try requested first
    if requested_resolution in files_data[section]:
        fmt_data = files_data[section][requested_resolution]
        if file_format in fmt_data:
            return requested_resolution, fmt_data[file_format]

    # Fallback chain
    fallbacks = POLYHAVEN_RESOLUTION_FALLBACKS.get(requested_resolution, [])
    for res in fallbacks:
        if res in files_data[section]:
            fmt_data = files_data[section][res]
            if file_format in fmt_data:
                print(
                    f"[blender-mcp] Resolution {requested_resolution} not available, using {res} instead"
                )
                return res, fmt_data[file_format]

    return None, None


def validate_sketchfab_key(api_key: str) -> dict:
    """Validate Sketchfab API key and return user info or error."""
    if not api_key or not api_key.strip():
        return {
            "valid": False,
            "error": "API key is empty. Get yours at sketchfab.com/settings/password",
        }

    try:
        response = robust_get(
            "https://api.sketchfab.com/v3/me",
            headers={"Authorization": f"Token {api_key}"},
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json()
            return {"valid": True, "username": data.get("username", "Unknown")}
        if response.status_code == 401:
            return {
                "valid": False,
                "error": "Invalid API key. Check your key at sketchfab.com/settings/password",
            }
        return {"valid": False, "error": f"Sketchfab returned status {response.status_code}"}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


# Asset session log (tracks downloads in current Blender session)
_session_log: list[dict] = []


def log_asset_download(
    source: str, asset_id: str, asset_type: str, resolution: str = "", extra: str = ""
):
    """Log an asset download for the current session."""
    entry = {
        "source": source,
        "asset_id": asset_id,
        "asset_type": asset_type,
        "resolution": resolution,
        "extra": extra,
        "time": time.strftime("%H:%M:%S"),
    }
    _session_log.append(entry)
    print(
        f"[blender-mcp] Downloaded: {source}/{asset_id} ({asset_type}, {resolution or 'default'})"
    )


def get_session_log() -> list[dict]:
    """Return the asset download log for the current session."""
    return list(_session_log)


def clear_session_log():
    """Clear the download log."""
    _session_log.clear()
