import sys
import os
import bpy
import time

# ROOT path
ROOT = '/home/yurix/Documentos/mcp-blender'
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import components
from addon.server import BlenderMCPServer
import addon.core.router as router
import addon.handlers as handlers

# Load handlers
handlers.load_all_handlers()

# Monkeypatch timers for background mode
print("--- MONKEYPATCHING TIMERS FOR BACKGROUND MODE ---")
def immediate_timer(func, first_interval=0):
    func()
    return None

bpy.app.timers.register = immediate_timer

class IntegratedServer(BlenderMCPServer):
    def __init__(self, port):
        super().__init__(host="0.0.0.0", port=port)
        self.command_executor = router.execute_command

# Initialize and start
bpy.types.blendermcp_server = IntegratedServer(9876)
bpy.types.blendermcp_server.start()

print("--- BLENDER SIDE SERVER LISTENING ON 9876 (IMMEDIATE MODE) ---")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    if hasattr(bpy.types, "blendermcp_server"):
        bpy.types.blendermcp_server.stop()
