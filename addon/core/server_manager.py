import bpy


class BlenderMCPServerManager:
    """Manages the lifecycle of the MCP socket server within Blender."""

    @staticmethod
    def get_server():
        return getattr(bpy.types, "blendermcp_server", None)

    @staticmethod
    def is_running():
        server = BlenderMCPServerManager.get_server()
        return server is not None and server.running

    @staticmethod
    def start(port=9876, allow_code=False):
        # Implementation will be moved from addon.py
        pass

    @staticmethod
    def stop():
        server = BlenderMCPServerManager.get_server()
        if server:
            server.stop()
            if hasattr(bpy.types, "blendermcp_server"):
                del bpy.types.blendermcp_server
            return True
        return False
