"""Centralized constants for BlenderMCP."""

# API Endpoints
POLYHAVEN_API_BASE = "https://api.polyhaven.com"
SKETCHFAB_API_BASE = "https://api.sketchfab.com/v3"

# Network Configuration
DEFAULT_BLENDER_HOST = "localhost"
DEFAULT_BLENDER_PORT = 9876
DEFAULT_SOCKET_TIMEOUT = 10  # seconds
DEFAULT_CONNECT_ATTEMPTS = 3
DEFAULT_COMMAND_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 0.5

# File Limits
MAX_SCREENSHOT_SIZE = 800  # pixels
MAX_POLYHAVEN_ASSETS_RETURNED = 20
MAX_SKETCHFAB_SEARCH_RESULTS = 100

# Timeouts
CODE_EXECUTION_TIMEOUT = 5  # seconds
DOWNLOAD_CHUNK_SIZE = 8192  # bytes

# Rate Limiting
DEFAULT_RATE_LIMIT_REQUESTS = 10
DEFAULT_RATE_LIMIT_WINDOW = 60  # seconds

# Logging
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "text"  # text or json
DEFAULT_LOG_HANDLER = "console"  # console or file
DEFAULT_LOG_FILE = "blender_mcp.log"

# Validation
MIN_PORT = 1024
MAX_PORT = 65535
MIN_API_KEY_LENGTH = 10
MAX_ASSET_ID_LENGTH = 100
MAX_QUERY_LENGTH = 200

# Asset Types
POLYHAVEN_ASSET_TYPES = ["hdris", "textures", "models"]
POLYHAVEN_RESOLUTIONS = ["1k", "2k", "4k", "8k", "16k"]

# HTTP Headers
DEFAULT_USER_AGENT = "blender-mcp/1.2"
