"""MCP Tool Schemas for BlenderMCP.
Defines the input parameters for each tool to help LLMs generate correct calls.
"""

TOOL_SCHEMAS = {
    # ── Scene & Object Info ────────────────────────────────────────
    "get_scene_info": {
        "description": "Get general information about the current Blender scene (objects, collections, render settings).",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_type": {
                    "type": "string",
                    "description": "Filter by object type (MESH, LIGHT, CAMERA, etc.)",
                },
                "filter_name": {
                    "type": "string",
                    "description": "Filter objects whose name contains this string",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of objects to return",
                    "default": 100,
                },
            },
        },
    },
    "get_object_info": {
        "description": "Get detailed information about a specific object (location, rotation, scale, mesh data, materials, modifiers).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to inspect"}
            },
            "required": ["name"],
        },
    },
    "get_active_object": {
        "description": "Get the currently active (selected) object in the scene.",
        "parameters": {"type": "object", "properties": {}},
    },
    "set_active_object": {
        "description": "Set the active object by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to make active"}
            },
            "required": ["name"],
        },
    },
    # ── Transform & Primitives ─────────────────────────────────────
    "transform_object": {
        "description": "Move, rotate or scale an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to transform"},
                "location": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "New location (x, y, z)",
                },
                "rotation": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "New rotation in degrees (x, y, z)",
                },
                "scale": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "New scale (x, y, z)",
                },
                "relative": {
                    "type": "boolean",
                    "description": "If true, transforms are relative to current values",
                    "default": False,
                },
            },
            "required": ["name"],
        },
    },
    "add_primitive": {
        "description": "Add a new primitive object to the scene.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["cube", "sphere", "plane", "cylinder", "cone", "torus", "monkey"],
                    "description": "Type of primitive",
                },
                "name": {"type": "string", "description": "Name for the new object"},
                "location": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "scale": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
            },
            "required": ["type"],
        },
    },
    "delete_object": {
        "description": "Delete an object from the scene by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to delete"}
            },
            "required": ["name"],
        },
    },
    # ── Materials ──────────────────────────────────────────────────
    "create_pbr_material": {
        "description": "Create a new PBR material with color, roughness, and metallic properties. Optionally apply it to an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the material"},
                "color_hex": {
                    "type": "string",
                    "description": "Hex color code (e.g., '#FF0000' for red)",
                    "default": "#CCCCCC",
                },
                "roughness": {
                    "type": "number",
                    "description": "Roughness value (0.0 = glossy, 1.0 = rough)",
                    "default": 0.5,
                },
                "metallic": {
                    "type": "number",
                    "description": "Metallic value (0.0 = non-metal, 1.0 = metal)",
                    "default": 0.0,
                },
                "apply_to_object": {
                    "type": "string",
                    "description": "Name of the object to apply the material to",
                },
            },
            "required": ["name"],
        },
    },
    "set_texture": {
        "description": "Apply a previously downloaded texture (from Poly Haven or AmbientCG) to an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Name of the object to apply the texture to",
                },
                "texture_id": {"type": "string", "description": "ID of the downloaded texture"},
            },
            "required": ["object_name", "texture_id"],
        },
    },
    # ── Camera & Render ────────────────────────────────────────────
    "setup_camera": {
        "description": "Set up the active camera, optionally pointing it at a specific object.",
        "parameters": {
            "type": "object",
            "properties": {
                "focus_object_name": {
                    "type": "string",
                    "description": "Name of the object to point the camera at",
                },
                "location": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Camera position (x, y, z)",
                },
                "create_new": {
                    "type": "boolean",
                    "description": "Create a new camera instead of using existing one",
                    "default": False,
                },
            },
        },
    },
    "configure_render_settings": {
        "description": "Configure render settings like engine, resolution, samples, and GPU usage.",
        "parameters": {
            "type": "object",
            "properties": {
                "engine": {
                    "type": "string",
                    "enum": ["BLENDER_EEVEE", "CYCLES"],
                    "description": "Render engine to use",
                    "default": "BLENDER_EEVEE",
                },
                "resolution_x": {
                    "type": "integer",
                    "description": "Horizontal resolution in pixels",
                    "default": 1920,
                },
                "resolution_y": {
                    "type": "integer",
                    "description": "Vertical resolution in pixels",
                    "default": 1080,
                },
                "samples": {
                    "type": "integer",
                    "description": "Number of render samples",
                    "default": 64,
                },
                "use_gpu": {
                    "type": "boolean",
                    "description": "Use GPU for rendering (Cycles only)",
                    "default": True,
                },
                "transparent_background": {
                    "type": "boolean",
                    "description": "Use transparent background",
                    "default": False,
                },
            },
        },
    },
    # ── Studio & Product Shots ─────────────────────────────────────
    "setup_product_studio": {
        "description": "Set up a complete product photography studio with backdrop, lights, and camera.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_name": {"type": "string", "description": "Name of the object to showcase"},
                "backdrop_color": {
                    "type": "string",
                    "description": "Hex color for the backdrop",
                    "default": "#FFFFFF",
                },
            },
        },
    },
    "render_catalog_angles": {
        "description": "Render the active object from multiple catalog angles (front, side, top, perspective).",
        "parameters": {
            "type": "object",
            "properties": {
                "target_name": {"type": "string", "description": "Name of the object to render"},
                "output_dir": {
                    "type": "string",
                    "description": "Directory to save rendered images",
                },
            },
            "required": ["target_name", "output_dir"],
        },
    },
    # ── Animation ──────────────────────────────────────────────────
    "animate_rotation": {
        "description": "Animate an object rotating around an axis over a specified frame range.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to animate"},
                "axis": {
                    "type": "string",
                    "enum": ["X", "Y", "Z"],
                    "description": "Rotation axis",
                    "default": "Z",
                },
                "degrees": {
                    "type": "number",
                    "description": "Total rotation in degrees",
                    "default": 360,
                },
                "start_frame": {"type": "integer", "description": "Start frame", "default": 1},
                "end_frame": {"type": "integer", "description": "End frame", "default": 250},
            },
            "required": ["name"],
        },
    },
    "create_turntable_animation": {
        "description": "Create a turntable animation that rotates the camera around a target object.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_name": {
                    "type": "string",
                    "description": "Name of the object to orbit around",
                },
                "frames": {
                    "type": "integer",
                    "description": "Total frames for one full rotation",
                    "default": 120,
                },
                "radius": {
                    "type": "number",
                    "description": "Distance from camera to target",
                    "default": 5.0,
                },
            },
            "required": ["target_name"],
        },
    },
    # ── Mesh Tools ─────────────────────────────────────────────────
    "separate_loose_parts": {
        "description": "Separate an object into individual loose parts (disconnected mesh islands).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to separate"}
            },
            "required": ["name"],
        },
    },
    "check_mesh_integrity": {
        "description": "Check a mesh for common issues (non-manifold edges, loose vertices, degenerate faces).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to check"}
            },
            "required": ["name"],
        },
    },
    "auto_repair_mesh": {
        "description": "Automatically repair common mesh issues (fill holes, remove doubles, fix normals).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to repair"}
            },
            "required": ["name"],
        },
    },
    "resolve_self_intersections": {
        "description": "Detect and attempt to resolve self-intersecting geometry in a mesh.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Name of the object to fix"}},
            "required": ["name"],
        },
    },
    # ── 3D Printing ────────────────────────────────────────────────
    "set_exact_dimensions": {
        "description": "Set exact real-world dimensions (in mm) for an object for 3D printing.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object"},
                "width": {"type": "number", "description": "Width in mm"},
                "height": {"type": "number", "description": "Height in mm"},
                "depth": {"type": "number", "description": "Depth in mm"},
            },
            "required": ["name"],
        },
    },
    "apply_boolean_operation": {
        "description": "Apply a boolean operation (union, difference, intersect) between two objects.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_name": {"type": "string", "description": "Name of the target object"},
                "cutter_name": {"type": "string", "description": "Name of the cutter object"},
                "operation": {
                    "type": "string",
                    "enum": ["UNION", "DIFFERENCE", "INTERSECT"],
                    "description": "Boolean operation type",
                },
            },
            "required": ["target_name", "cutter_name", "operation"],
        },
    },
    "apply_print_thickness": {
        "description": "Add a Solidify modifier to ensure minimum wall thickness for 3D printing.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object"},
                "thickness_mm": {
                    "type": "number",
                    "description": "Wall thickness in mm",
                    "default": 2.0,
                },
            },
            "required": ["name"],
        },
    },
    "export_for_printing": {
        "description": "Export an object as STL for 3D printing, with proper scaling and transformations applied.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to export"},
                "filepath": {"type": "string", "description": "Output STL file path"},
                "scale": {
                    "type": "number",
                    "description": "Scale factor (1.0 = use scene units)",
                    "default": 1.0,
                },
            },
            "required": ["name", "filepath"],
        },
    },
    "assign_print_color": {
        "description": "Assign a color to an object for multi-color 3D printing (3MF export).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object"},
                "color_hex": {"type": "string", "description": "Hex color code (e.g., '#FF0000')"},
                "extruder_index": {
                    "type": "integer",
                    "description": "Extruder/tool index for multi-material printers",
                    "default": 0,
                },
            },
            "required": ["name", "color_hex"],
        },
    },
    "snap_objects_by_proximity": {
        "description": "Snap two objects together by aligning their closest faces.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_name": {"type": "string", "description": "Object to move"},
                "target_name": {"type": "string", "description": "Object to snap to"},
            },
            "required": ["source_name", "target_name"],
        },
    },
    # ── Export & File ──────────────────────────────────────────────
    "export_model": {
        "description": "Export the scene or specific objects to various formats (GLB, FBX, OBJ, STL).",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Output file path (extension determines format)",
                },
                "format": {
                    "type": "string",
                    "enum": ["GLB", "FBX", "OBJ", "STL"],
                    "description": "Export format",
                },
                "selected_only": {
                    "type": "boolean",
                    "description": "Export only selected objects",
                    "default": False,
                },
            },
            "required": ["filepath", "format"],
        },
    },
    # ── Asset Libraries ────────────────────────────────────────────
    "download_polyhaven_asset": {
        "description": "Download and import an asset (HDRI, texture, or 3D model) from Poly Haven.",
        "parameters": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "ID of the asset (e.g., 'forest_slope')",
                },
                "asset_type": {
                    "type": "string",
                    "enum": ["hdris", "textures", "models"],
                    "description": "Type of asset",
                },
                "resolution": {"type": "string", "enum": ["1k", "2k", "4k", "8k"], "default": "2k"},
            },
            "required": ["asset_id", "asset_type"],
        },
    },
    "search_polyhaven_assets": {
        "description": "Search for assets on Poly Haven by keyword.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'wood', 'concrete', 'forest')",
                },
                "asset_type": {
                    "type": "string",
                    "enum": ["hdris", "textures", "models"],
                    "description": "Type of asset to search for",
                },
            },
            "required": ["query", "asset_type"],
        },
    },
    "search_ambientcg_materials": {
        "description": "Search for PBR materials on AmbientCG by keyword.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'metal', 'brick', 'wood')",
                },
                "limit": {"type": "integer", "description": "Max results to return", "default": 10},
            },
            "required": ["query"],
        },
    },
    "download_ambientcg_material": {
        "description": "Download and apply a PBR material from AmbientCG.",
        "parameters": {
            "type": "object",
            "properties": {
                "material_id": {"type": "string", "description": "ID of the AmbientCG material"},
                "apply_to_object": {
                    "type": "string",
                    "description": "Name of the object to apply it to",
                },
                "resolution": {"type": "string", "enum": ["1K", "2K", "4K"], "default": "2K"},
            },
            "required": ["material_id"],
        },
    },
    "search_sketchfab_models": {
        "description": "Search for 3D models on Sketchfab.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "downloadable": {
                    "type": "boolean",
                    "description": "Only show downloadable models",
                    "default": True,
                },
            },
            "required": ["query"],
        },
    },
    "download_sketchfab_model": {
        "description": "Download and import a 3D model from Sketchfab (requires API key).",
        "parameters": {
            "type": "object",
            "properties": {
                "model_uid": {
                    "type": "string",
                    "description": "UID of the Sketchfab model to download",
                }
            },
            "required": ["model_uid"],
        },
    },
    # ── Functional Parts ───────────────────────────────────────────
    "mark_as_functional_part": {
        "description": "Mark an object as a functional part with a specific role (e.g., wheel, axle, body).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to mark"},
                "role": {
                    "type": "string",
                    "description": "Functional role (e.g., 'wheel', 'axle', 'body', 'lid')",
                },
                "preset": {
                    "type": "string",
                    "description": "Project preset (e.g., 'vehicle', 'enclosure')",
                },
            },
            "required": ["name", "role"],
        },
    },
    "list_functional_parts": {
        "description": "List all objects marked as functional parts in the scene.",
        "parameters": {"type": "object", "properties": {}},
    },
    # ── Reporting ──────────────────────────────────────────────────
    "generate_print_report": {
        "description": "Generate a comprehensive 3D print readiness report for the scene or selected objects.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_name": {
                    "type": "string",
                    "description": "Name of a specific object to report on (optional, reports all if omitted)",
                }
            },
        },
    },
    # ── System ─────────────────────────────────────────────────────
    "execute_code": {
        "description": "Execute arbitrary Python code in Blender. Use this as a last resort when no specific tool exists for the task.",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python code to execute"}},
            "required": ["code"],
        },
    },
    "list_tools": {
        "description": "List all available MCP tools and their descriptions.",
        "parameters": {"type": "object", "properties": {}},
    },
    "list_blender_operators": {
        "description": "List available Blender operators, optionally filtered by category.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g., 'mesh', 'object', 'render')",
                }
            },
        },
    },
    "get_operator_help": {
        "description": "Get detailed help and parameter info for a specific Blender operator.",
        "parameters": {
            "type": "object",
            "properties": {
                "operator_id": {
                    "type": "string",
                    "description": "Full operator ID (e.g., 'mesh.primitive_cube_add')",
                }
            },
            "required": ["operator_id"],
        },
    },
    # ── Modeling Operations ────────────────────────────────────────
    "extrude_faces": {
        "description": "Extrude faces of a mesh along their normals by a given amount.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "amount": {"type": "number", "description": "Extrusion distance", "default": 1.0},
                "select_all": {
                    "type": "boolean",
                    "description": "Select all faces before extruding",
                    "default": True,
                },
            },
            "required": ["name"],
        },
    },
    "inset_faces": {
        "description": "Create an inset (recessed frame) on faces of a mesh.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "thickness": {"type": "number", "description": "Inset thickness", "default": 0.1},
                "depth": {
                    "type": "number",
                    "description": "Inset depth (positive = inward)",
                    "default": 0.0,
                },
                "select_all": {
                    "type": "boolean",
                    "description": "Select all faces before insetting",
                    "default": True,
                },
            },
            "required": ["name"],
        },
    },
    "bevel_edges": {
        "description": "Apply bevel to edges of a mesh for smoother transitions.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "width": {"type": "number", "description": "Bevel width", "default": 0.1},
                "segments": {
                    "type": "integer",
                    "description": "Number of bevel segments",
                    "default": 1,
                },
                "profile": {
                    "type": "number",
                    "description": "Bevel profile shape (0-1)",
                    "default": 0.5,
                },
                "select_all": {
                    "type": "boolean",
                    "description": "Select all edges before beveling",
                    "default": True,
                },
            },
            "required": ["name"],
        },
    },
    "subdivide_mesh": {
        "description": "Subdivide a mesh to add more geometry detail.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "number_cuts": {
                    "type": "integer",
                    "description": "Number of subdivision cuts",
                    "default": 1,
                },
                "smoothness": {
                    "type": "number",
                    "description": "Smoothing factor (0-1)",
                    "default": 0.0,
                },
            },
            "required": ["name"],
        },
    },
    "merge_vertices": {
        "description": "Merge overlapping vertices by distance (remove doubles).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "threshold": {
                    "type": "number",
                    "description": "Merge distance threshold",
                    "default": 0.0001,
                },
            },
            "required": ["name"],
        },
    },
    "fill_hole": {
        "description": "Fill holes in a mesh by selecting non-manifold boundaries and creating faces.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "method": {"type": "string", "enum": ["BEAUTY", "NGON"], "default": "BEAUTY"},
            },
            "required": ["name"],
        },
    },
    "spin_mesh": {
        "description": "Create rotational geometry by spinning a mesh profile around an axis (like a lathe).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "axis": {"type": "string", "enum": ["X", "Y", "Z"], "default": "Z"},
                "angle": {"type": "number", "description": "Spin angle in degrees", "default": 360},
                "steps": {"type": "integer", "description": "Number of spin steps", "default": 32},
            },
            "required": ["name"],
        },
    },
    "recalculate_normals": {
        "description": "Recalculate mesh normals to point outward (or inward). Fixes dark/inverted faces.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "inside": {
                    "type": "boolean",
                    "description": "Flip normals inward instead",
                    "default": False,
                },
            },
            "required": ["name"],
        },
    },
    "mark_sharp_by_angle": {
        "description": "Mark edges as sharp based on face angle threshold for hard-surface shading.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "angle": {
                    "type": "number",
                    "description": "Angle threshold in degrees",
                    "default": 30.0,
                },
            },
            "required": ["name"],
        },
    },
    # ── Modifier Shortcuts ─────────────────────────────────────────
    "add_modifier": {
        "description": "Add any modifier to an object by type name (MIRROR, ARRAY, SOLIDIFY, SUBSURF, BEVEL, BOOLEAN, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object"},
                "modifier_type": {
                    "type": "string",
                    "description": "Modifier type (e.g., MIRROR, ARRAY, SOLIDIFY, SUBSURF, BEVEL)",
                },
                "properties": {
                    "type": "object",
                    "description": "Optional dict of modifier properties to set",
                },
            },
            "required": ["name", "modifier_type"],
        },
    },
    "apply_modifier": {
        "description": "Apply a specific modifier, making its effect permanent on the mesh.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object"},
                "modifier_name": {"type": "string", "description": "Name of the modifier to apply"},
            },
            "required": ["name", "modifier_name"],
        },
    },
    "apply_all_modifiers": {
        "description": "Apply all modifiers on an object at once.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Name of the object"}},
            "required": ["name"],
        },
    },
    "add_mirror_modifier": {
        "description": "Add a mirror modifier with clipping for symmetrical modeling.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object"},
                "axis": {
                    "type": "string",
                    "description": "Mirror axis (X, Y, Z, or combination like XY)",
                    "default": "X",
                },
                "use_clipping": {
                    "type": "boolean",
                    "description": "Prevent vertices from crossing the mirror plane",
                    "default": True,
                },
            },
            "required": ["name"],
        },
    },
    "add_array_modifier": {
        "description": "Add an array modifier for linear duplication of an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object"},
                "count": {"type": "integer", "description": "Number of copies", "default": 3},
                "offset": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Offset per copy (x, y, z)",
                },
                "use_relative": {
                    "type": "boolean",
                    "description": "Use relative offset based on object size",
                    "default": True,
                },
            },
            "required": ["name"],
        },
    },
    "add_screw_modifier": {
        "description": "Add a Screw modifier for creating revolution geometry (vases, cups, screws, springs).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object"},
                "axis": {"type": "string", "enum": ["X", "Y", "Z"], "default": "Z"},
                "angle": {
                    "type": "number",
                    "description": "Revolution angle in degrees",
                    "default": 360,
                },
                "steps": {"type": "integer", "description": "Number of steps", "default": 32},
                "screw_offset": {
                    "type": "number",
                    "description": "Height offset per revolution (for spirals)",
                    "default": 0.0,
                },
            },
            "required": ["name"],
        },
    },
    "add_curve_modifier": {
        "description": "Deform a mesh along a curve path using a Curve modifier.",
        "parameters": {
            "type": "object",
            "properties": {
                "mesh_name": {"type": "string", "description": "Name of the mesh to deform"},
                "curve_name": {"type": "string", "description": "Name of the curve to follow"},
            },
            "required": ["mesh_name", "curve_name"],
        },
    },
    "decimate_mesh": {
        "description": "Reduce polygon count while preserving overall shape.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "ratio": {
                    "type": "number",
                    "description": "Target ratio (0.1 = 10% of original)",
                    "default": 0.5,
                },
                "method": {
                    "type": "string",
                    "enum": ["COLLAPSE", "UNSUBDIV", "PLANAR"],
                    "default": "COLLAPSE",
                },
            },
            "required": ["name"],
        },
    },
    "remesh_voxel": {
        "description": "Remesh with voxels for clean, uniform topology.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "voxel_size": {
                    "type": "number",
                    "description": "Voxel size (smaller = more detail)",
                    "default": 0.1,
                },
            },
            "required": ["name"],
        },
    },
    "smooth_mesh": {
        "description": "Smooth a mesh using vertex smoothing iterations.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "iterations": {
                    "type": "integer",
                    "description": "Number of smoothing passes",
                    "default": 10,
                },
                "factor": {
                    "type": "number",
                    "description": "Smoothing strength (0-1)",
                    "default": 0.5,
                },
            },
            "required": ["name"],
        },
    },
    "shade_smooth": {
        "description": "Set smooth or flat shading on an object.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "smooth": {
                    "type": "boolean",
                    "description": "True for smooth, False for flat",
                    "default": True,
                },
            },
            "required": ["name"],
        },
    },
    # ── Scene Organization ─────────────────────────────────────────
    "duplicate_object": {
        "description": "Duplicate an object with optional position offset.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the object to duplicate"},
                "linked": {
                    "type": "boolean",
                    "description": "Create a linked duplicate (shares mesh data)",
                    "default": False,
                },
                "offset": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Position offset (x, y, z)",
                },
            },
            "required": ["name"],
        },
    },
    "join_objects": {
        "description": "Join multiple mesh objects into a single object.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of object names to join",
                }
            },
            "required": ["object_names"],
        },
    },
    "create_collection": {
        "description": "Create a new collection and optionally move objects into it.",
        "parameters": {
            "type": "object",
            "properties": {
                "collection_name": {"type": "string", "description": "Name for the new collection"},
                "object_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Objects to move into the collection",
                },
            },
            "required": ["collection_name"],
        },
    },
    "move_to_collection": {
        "description": "Move objects to an existing collection.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Objects to move",
                },
                "collection_name": {"type": "string", "description": "Target collection name"},
            },
            "required": ["object_names", "collection_name"],
        },
    },
    "parent_objects": {
        "description": "Set parent-child relationship between objects.",
        "parameters": {
            "type": "object",
            "properties": {
                "parent_name": {"type": "string", "description": "Name of the parent object"},
                "child_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Names of child objects",
                },
            },
            "required": ["parent_name", "child_names"],
        },
    },
    "align_objects": {
        "description": "Align multiple objects along an axis.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Objects to align",
                },
                "axis": {"type": "string", "enum": ["X", "Y", "Z"], "default": "X"},
                "align_to": {
                    "type": "string",
                    "enum": ["MIN", "CENTER", "MAX"],
                    "default": "CENTER",
                },
            },
            "required": ["object_names"],
        },
    },
    "distribute_objects": {
        "description": "Distribute objects evenly along an axis with uniform spacing.",
        "parameters": {
            "type": "object",
            "properties": {
                "object_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Objects to distribute",
                },
                "axis": {"type": "string", "enum": ["X", "Y", "Z"], "default": "X"},
                "spacing": {
                    "type": "number",
                    "description": "Distance between objects",
                    "default": 2.0,
                },
            },
            "required": ["object_names"],
        },
    },
    "smart_uv_project": {
        "description": "Automatically unwrap UVs using Smart UV Project.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the mesh object"},
                "angle_limit": {
                    "type": "number",
                    "description": "Angle limit for island detection",
                    "default": 66.0,
                },
                "island_margin": {
                    "type": "number",
                    "description": "Margin between UV islands",
                    "default": 0.02,
                },
            },
            "required": ["name"],
        },
    },
    "text_to_mesh": {
        "description": "Create 3D text and optionally convert to editable mesh.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text content to create"},
                "size": {"type": "number", "description": "Text size", "default": 1.0},
                "extrude": {
                    "type": "number",
                    "description": "Extrusion depth for 3D effect",
                    "default": 0.1,
                },
                "bevel_depth": {
                    "type": "number",
                    "description": "Bevel depth for rounded edges",
                    "default": 0.01,
                },
                "convert": {
                    "type": "boolean",
                    "description": "Convert to mesh after creation",
                    "default": True,
                },
            },
            "required": ["text"],
        },
    },
    "separate_by_material": {
        "description": "Separate a mesh into individual objects based on material slots.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Name of the mesh object"}},
            "required": ["name"],
        },
    },
    # ── Visual Critic ──────────────────────────────────────────────
    "analyze_viewport_visuals": {
        "description": "Capture a screenshot of the active 3D viewport and use a local or cloud vision model (like moondream or llava via Ollama) to analyze the scene. Highly useful for checking floating objects, overlapping geometries, clipping, or visual alignment.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The specific question or instructions for the vision model regarding the viewport visual analysis.",
                    "default": "Describe the current 3D scene from the viewport's perspective. Check for any floating objects, overlapping geometries, clipping, or incorrect physical alignments.",
                },
                "model": {
                    "type": "string",
                    "description": "The vision model name to query. Defaults to 'moondream' for Ollama.",
                    "default": "moondream",
                },
            },
        },
    },
}


def get_tools_list():
    """Return a list of tools formatted for MCP discovery."""
    return [
        {"name": name, "description": schema["description"], "inputSchema": schema["parameters"]}
        for name, schema in TOOL_SCHEMAS.items()
    ]
