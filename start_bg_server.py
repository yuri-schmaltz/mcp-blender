import bpy
import time

print("Enabling addon...")
bpy.ops.preferences.addon_enable(module='mcp_blender')

print("Starting server...")
try:
    bpy.ops.blendermcp.start_server()
    print("Server started successfully.")
except Exception as e:
    print(f"Error starting server: {e}")

# Keep blender running in background
# We just need to prevent the script from exiting immediately
class ModalTimerOperator(bpy.types.Operator):
    bl_idname = "wm.modal_timer_operator"
    bl_label = "Modal Timer Operator"

    _timer = None

    def modal(self, context, event):
        if event.type == 'TIMER':
            pass
        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

bpy.utils.register_class(ModalTimerOperator)
bpy.ops.wm.modal_timer_operator()
print("Blender running in background, waiting for MCP requests...")
