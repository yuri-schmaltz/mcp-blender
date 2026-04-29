"""Reporting tools for BlenderMCP."""
from ..core.router import mcp_command


import os


@mcp_command(name="generate_print_report", read_only=False)
def generate_print_report(scene, filepath=None):
    """Generate a technical report about the 3D model (dimensions, volume, parts)."""
    try:
        if not filepath:
            filepath = os.path.join(os.path.expanduser("~"), "blender_mcp_report.txt")

        meshes = [obj for obj in scene.objects if obj.type == 'MESH' and not obj.hide_get()]

        lines = [
            "========================================",
            "   BLENDER MCP 3D PRINT TECHNICAL REPORT",
            "========================================",
            f"Scene: {scene.name}",
            f"Total Mesh Objects: {len(meshes)}",
            ""
        ]

        total_volume = 0
        for obj in meshes:
            dims = obj.dimensions
            lines.append(f"Object: {obj.name}")
            lines.append(f" - Dimensions (mm): {dims.x*1000:.2f} x {dims.y*1000:.2f} x {dims.z*1000:.2f}")
            # Volume estimation (bounding box volume as proxy or BMesh volume)
            vol = dims.x * dims.y * dims.z
            total_volume += vol
            lines.append(f" - Volume (approx cm3): {vol * 1000000:.2f}")
            lines.append("-" * 20)

        lines.append("")
        lines.append(f"Total Estimated Volume (cm3): {total_volume * 1000000:.2f}")
        lines.append("Recommendation: Use 0.2mm layer height and 15% infill.")
        lines.append("========================================")

        content = "\n".join(lines)
        with open(filepath, "w") as f:
            f.write(content)

        return {"success": True, "message": f"Report generated at {filepath}", "filepath": filepath}
    except Exception as e:
        return {"error": f"Failed to generate report: {str(e)}"}
