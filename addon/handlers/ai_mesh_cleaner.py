"""AI Mesh Cleaner — Multi-stage pipeline for cleaning AI-generated meshes.

AI-generated meshes (from Meshy, Tripo3D, CSM, Rodin, etc.) share systematic
defects that no single Blender tool handles well. This pipeline addresses each
defect type in the correct order for maximum effectiveness.

Pipeline stages:
  1. Purge Garbage   — remove loose verts/edges, degenerate faces
  2. Weld & Heal     — merge by distance, fill micro-holes, remove duplicates
  3. Fix Normals     — recalculate outward, fix inverted faces
  4. Planar Dissolve — dissolve flat regions to reduce vertex count
  5. Smart Decimate  — curvature-aware decimation preserving sharp features
  6. Final Polish    — smooth, auto-shade, weighted normals
"""
import math
import bpy
import bmesh
from ..core.router import mcp_command


def _get_bbox_diagonal(obj):
    """Calculate the diagonal length of an object's bounding box."""
    bbox = [obj.matrix_world @ v for v in [type(obj.matrix_world)(v) for v in [None]]]
    # Simpler: use bound_box directly
    corners = [obj.matrix_world @ type(obj.location)(c) for c in obj.bound_box]
    from mathutils import Vector
    min_c = Vector((min(c[0] for c in corners), min(c[1] for c in corners), min(c[2] for c in corners)))
    max_c = Vector((max(c[0] for c in corners), max(c[1] for c in corners), max(c[2] for c in corners)))
    return (max_c - min_c).length


def _get_bbox_diagonal_simple(obj):
    """Simple bounding box diagonal from mesh dimensions."""
    from mathutils import Vector
    d = obj.dimensions
    return Vector(d).length if d.length > 0 else 1.0


# ── Stage 1: Purge Garbage ─────────────────────────────────────────

def _stage_purge(bm, degenerate_threshold=0.00001):
    """Remove loose verts, loose edges, and degenerate (zero-area) faces."""
    report = {"loose_verts": 0, "loose_edges": 0, "degenerate_faces": 0}

    # Remove degenerate faces (area below threshold)
    faces_to_remove = []
    for f in bm.faces:
        if f.calc_area() < degenerate_threshold:
            faces_to_remove.append(f)
    report["degenerate_faces"] = len(faces_to_remove)
    for f in faces_to_remove:
        bm.faces.remove(f)

    # Remove loose edges (not connected to any face)
    edges_to_remove = [e for e in bm.edges if len(e.link_faces) == 0]
    report["loose_edges"] = len(edges_to_remove)
    for e in edges_to_remove:
        bm.edges.remove(e)

    # Remove loose verts (not connected to any edge)
    verts_to_remove = [v for v in bm.verts if len(v.link_edges) == 0]
    report["loose_verts"] = len(verts_to_remove)
    for v in verts_to_remove:
        bm.verts.remove(v)

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    return report


# ── Stage 2: Weld & Heal ──────────────────────────────────────────

def _stage_weld(bm, merge_distance=0.0001, max_hole_edges=8):
    """Merge vertices by distance, remove duplicate faces, fill micro-holes."""
    report = {"merged_verts": 0, "duplicate_faces": 0, "holes_filled": 0}

    initial_verts = len(bm.verts)

    # Merge by distance
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_distance)
    bm.verts.ensure_lookup_table()
    report["merged_verts"] = initial_verts - len(bm.verts)

    # Remove duplicate faces (faces that share all vertices)
    seen = set()
    dupes = []
    for f in bm.faces:
        key = frozenset(v.index for v in f.verts)
        if key in seen:
            dupes.append(f)
        else:
            seen.add(key)
    report["duplicate_faces"] = len(dupes)
    for f in dupes:
        bm.faces.remove(f)

    # Fill micro-holes: find boundary edge loops and fill small ones
    bm.edges.ensure_lookup_table()
    boundary_edges = [e for e in bm.edges if e.is_boundary]

    if boundary_edges:
        # Group boundary edges into loops
        visited = set()
        holes = []
        for start_edge in boundary_edges:
            if start_edge.index in visited:
                continue
            loop = []
            edge = start_edge
            vert = edge.verts[0]
            while True:
                visited.add(edge.index)
                loop.append(edge)
                # Find next boundary edge connected to the other vert
                next_vert = edge.other_vert(vert)
                next_edge = None
                for e in next_vert.link_edges:
                    if e.is_boundary and e.index not in visited:
                        next_edge = e
                        break
                if next_edge is None:
                    break
                vert = next_vert
                edge = next_edge

            if len(loop) <= max_hole_edges and len(loop) >= 3:
                holes.append(loop)

        # Fill each small hole
        for hole_edges in holes:
            try:
                verts = []
                for e in hole_edges:
                    for v in e.verts:
                        if v not in verts:
                            verts.append(v)
                if len(verts) >= 3:
                    bmesh.ops.contextual_create(bm, geom=verts)
                    report["holes_filled"] += 1
            except Exception:
                pass

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    return report


# ── Stage 3: Fix Normals ──────────────────────────────────────────

def _stage_normals(bm):
    """Recalculate normals to point outward consistently."""
    report = {"flipped": 0}

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    # Count how many were likely flipped (heuristic: faces whose normal
    # points toward the mesh center are suspicious)
    from mathutils import Vector
    center = Vector((0, 0, 0))
    for v in bm.verts:
        center += v.co
    if len(bm.verts) > 0:
        center /= len(bm.verts)

    flipped = 0
    for f in bm.faces:
        face_center = f.calc_center_median()
        direction = face_center - center
        if direction.dot(f.normal) < 0:
            flipped += 1

    report["flipped"] = flipped
    return report


# ── Stage 4: Planar Dissolve ──────────────────────────────────────

def _stage_planar_dissolve(bm, planar_angle=5.0):
    """Dissolve coplanar faces to reduce vertex count without losing shape."""
    report = {"verts_before": len(bm.verts), "faces_before": len(bm.faces)}

    bmesh.ops.dissolve_limit(
        bm,
        angle_limit=math.radians(planar_angle),
        use_dissolve_boundaries=False,
        verts=bm.verts,
        edges=bm.edges,
    )

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    report["verts_after"] = len(bm.verts)
    report["faces_after"] = len(bm.faces)
    report["verts_dissolved"] = report["verts_before"] - report["verts_after"]
    report["faces_dissolved"] = report["faces_before"] - report["faces_after"]
    return report


# ── Stage 5: Smart Decimate ───────────────────────────────────────

def _stage_smart_decimate(obj, target_ratio=0.3, target_face_count=None, preserve_sharp_angle=30.0):
    """Curvature-aware decimation using vertex groups for weight control.
    
    Strategy: Calculate local curvature at each vertex. Assign high weights
    to high-curvature verts (protect them) and low weights to flat-area verts
    (sacrifice them). Then use Decimate modifier with vertex group.
    """
    report = {"faces_before": len(obj.data.polygons)}

    mesh = obj.data

    # Calculate per-vertex curvature approximation using face angle deviation
    vert_curvatures = [0.0] * len(mesh.vertices)

    # For each vertex, measure the deviation of connected face normals
    # Higher deviation = higher curvature = more important to keep
    # Ensure normals are up to date
    mesh.update()

    # Build vertex -> face map
    vert_faces = [[] for _ in range(len(mesh.vertices))]
    for poly in mesh.polygons:
        for vi in poly.vertices:
            vert_faces[vi].append(poly)

    for vi, faces in enumerate(vert_faces):
        if len(faces) < 2:
            vert_curvatures[vi] = 1.0  # Boundary vertices are important
            continue

        # Average angular deviation between all pairs of adjacent face normals
        total_angle = 0.0
        count = 0
        ref_normal = faces[0].normal
        for f in faces[1:]:
            angle = ref_normal.angle(f.normal, 0.0)
            total_angle += angle
            count += 1

        avg_angle = total_angle / max(count, 1)
        # Normalize: 0° = flat (low importance), 90° = very curved (high importance)
        vert_curvatures[vi] = min(avg_angle / math.radians(90), 1.0)

    # Create or get vertex group for curvature weighting
    vg_name = "_AIMeshClean_Curvature"
    if vg_name in obj.vertex_groups:
        obj.vertex_groups.remove(obj.vertex_groups[vg_name])
    vg = obj.vertex_groups.new(name=vg_name)

    for vi, curv in enumerate(vert_curvatures):
        # Invert: high curvature = high weight = PROTECTED from decimation
        vg.add([vi], curv, 'REPLACE')

    # Compute actual ratio
    if target_face_count and len(mesh.polygons) > 0:
        actual_ratio = target_face_count / len(mesh.polygons)
        actual_ratio = max(0.01, min(actual_ratio, 1.0))
    else:
        actual_ratio = target_ratio

    # Add Decimate modifier with vertex group
    mod = obj.modifiers.new(name="_AIMeshClean_Decimate", type='DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = actual_ratio
    mod.vertex_group = vg_name
    mod.invert_vertex_group = True  # Low curvature = more decimation
    mod.vertex_group_factor = 1.0

    # Apply modifier
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)

    # Clean up vertex group
    if vg_name in obj.vertex_groups:
        obj.vertex_groups.remove(obj.vertex_groups[vg_name])

    report["faces_after"] = len(obj.data.polygons)
    report["faces_removed"] = report["faces_before"] - report["faces_after"]
    report["actual_ratio"] = round(report["faces_after"] / max(report["faces_before"], 1), 3)
    return report


# ── Stage 6: Final Polish ────────────────────────────────────────

def _stage_polish(obj, smooth_iterations=1, smooth_factor=0.3, auto_smooth_angle=30.0):
    """Final smoothing and shading cleanup."""
    report = {}

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    # Light smooth pass
    if smooth_iterations > 0:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        for _ in range(smooth_iterations):
            bpy.ops.mesh.vertices_smooth(factor=smooth_factor)
        bpy.ops.object.mode_set(mode='OBJECT')
        report["smooth_passes"] = smooth_iterations

    # Set smooth shading
    bpy.ops.object.shade_smooth()

    # Add Weighted Normal modifier for clean shading
    if "WeightedNormal" not in obj.modifiers:
        mod = obj.modifiers.new(name="WeightedNormal", type='WEIGHTED_NORMAL')
        mod.weight = 50
        mod.keep_sharp = True
        report["weighted_normal"] = True

    report["shading"] = "smooth"
    return report


# ── Main Pipeline ─────────────────────────────────────────────────

@mcp_command(name="ai_mesh_clean", read_only=False)
def ai_mesh_clean(
    scene,
    name,
    stages="ALL",
    degenerate_threshold=0.00001,
    merge_threshold_factor=0.001,
    max_hole_edges=8,
    planar_angle=5.0,
    target_face_count=None,
    target_ratio=0.3,
    preserve_sharp_angle=30.0,
    smooth_iterations=1,
    auto_smooth_angle=30.0,
):
    """
    Multi-stage AI mesh cleaning pipeline.
    
    Cleans meshes generated by AI tools (Meshy, Tripo3D, CSM, Rodin, etc.)
    that suffer from excessive vertices, degenerate faces, inconsistent normals,
    and other systematic defects.
    
    Stages:
      1 = Purge Garbage (loose verts/edges, degenerate faces)
      2 = Weld & Heal (merge by distance, fill micro-holes)
      3 = Fix Normals (recalculate outward)
      4 = Planar Dissolve (dissolve flat regions)
      5 = Smart Decimate (curvature-aware reduction)
      6 = Final Polish (smooth, auto-shade, weighted normals)
    
    Use stages="ALL" for the full pipeline or stages="1,2,3" for specific stages.
    """
    try:
        obj = scene.objects.get(name)
        if not obj or obj.type != 'MESH':
            return {"error": f"Mesh object '{name}' not found."}

        # Parse stages
        if stages == "ALL":
            active_stages = {1, 2, 3, 4, 5, 6}
        else:
            try:
                active_stages = set(int(s.strip()) for s in str(stages).split(","))
            except ValueError:
                return {"error": f"Invalid stages format: '{stages}'. Use 'ALL' or '1,2,3'."}

        # Ensure we're in object mode
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Record initial state
        initial_verts = len(obj.data.vertices)
        initial_edges = len(obj.data.edges)
        initial_faces = len(obj.data.polygons)

        full_report = {
            "object": name,
            "initial": {"verts": initial_verts, "edges": initial_edges, "faces": initial_faces},
            "stages": {},
        }

        # Calculate adaptive merge distance from bounding box
        bbox_diag = _get_bbox_diagonal_simple(obj)
        merge_distance = bbox_diag * merge_threshold_factor

        # ── Stages 1-4: bmesh operations ──
        if active_stages & {1, 2, 3, 4}:
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            if 1 in active_stages:
                full_report["stages"]["1_purge"] = _stage_purge(bm, degenerate_threshold)

            if 2 in active_stages:
                full_report["stages"]["2_weld"] = _stage_weld(bm, merge_distance, max_hole_edges)

            if 3 in active_stages:
                full_report["stages"]["3_normals"] = _stage_normals(bm)

            if 4 in active_stages:
                full_report["stages"]["4_planar"] = _stage_planar_dissolve(bm, planar_angle)

            bm.to_mesh(obj.data)
            bm.free()
            obj.data.update()

        # ── Stage 5: Smart Decimate (modifier-based, needs mesh data) ──
        if 5 in active_stages:
            full_report["stages"]["5_decimate"] = _stage_smart_decimate(
                obj, target_ratio, target_face_count, preserve_sharp_angle
            )

        # ── Stage 6: Final Polish ──
        if 6 in active_stages:
            full_report["stages"]["6_polish"] = _stage_polish(
                obj, smooth_iterations, 0.3, auto_smooth_angle
            )

        # Record final state
        final_verts = len(obj.data.vertices)
        final_edges = len(obj.data.edges)
        final_faces = len(obj.data.polygons)

        full_report["final"] = {"verts": final_verts, "edges": final_edges, "faces": final_faces}
        full_report["reduction"] = {
            "verts": f"{initial_verts} → {final_verts} ({100 - (final_verts / max(initial_verts, 1) * 100):.1f}% removed)",
            "faces": f"{initial_faces} → {final_faces} ({100 - (final_faces / max(initial_faces, 1) * 100):.1f}% removed)",
        }

        # Build summary message
        summary = (
            f"AI Mesh Clean complete on '{name}'.\n"
            f"  Vertices: {initial_verts:,} → {final_verts:,} "
            f"(-{100 - (final_verts / max(initial_verts, 1) * 100):.1f}%)\n"
            f"  Faces: {initial_faces:,} → {final_faces:,} "
            f"(-{100 - (final_faces / max(initial_faces, 1) * 100):.1f}%)"
        )

        full_report["status"] = "success"
        full_report["message"] = summary

        print(f"BlenderMCP: {summary}")
        return full_report

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Ensure we return to object mode on error
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
        return {"error": f"AI Mesh Clean failed: {str(e)}"}
