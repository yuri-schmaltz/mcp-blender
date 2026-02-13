"""Constants and configuration for BlenderMCP addon."""

import os

import requests

# Security: Free trial key can be set via environment variable
# If not set, addon will prompt user to configure it manually
RODIN_FREE_TRIAL_KEY = os.getenv(
    "RODIN_FREE_TRIAL_KEY", "k9TcfFoEhNd9cCPP2guHAHHHkctZHIRhZDywZ1euGUXwihbYLpOjQhofby80NJez"
)

# Add User-Agent as required by Poly Haven API
REQ_HEADERS = requests.utils.default_headers()
REQ_HEADERS.update({"User-Agent": "blender-mcp"})

# MP-05: Asset cache configuration
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".blender_mcp", "cache")
CACHE_TTL_DAYS = 7  # Cache expires after 7 days
