"""Functional part management for BlenderMCP."""
from ..core.router import mcp_command


import bpy
import json


# =============================================================================
# Part Presets – predefined roles for common project types
# =============================================================================
PART_PRESETS = {
    "CAR": {
        "label": "Car",
        "icon": "AUTO",
        "roles": [
            ("CHASSIS", "Chassis", "Main body / structural frame"),
            ("WHEEL_FL", "Wheel FL", "Front-left wheel"),
            ("WHEEL_FR", "Wheel FR", "Front-right wheel"),
            ("WHEEL_RL", "Wheel RL", "Rear-left wheel"),
            ("WHEEL_RR", "Wheel RR", "Rear-right wheel"),
            ("DOOR_L", "Door Left", "Left door"),
            ("DOOR_R", "Door Right", "Right door"),
            ("HOOD", "Hood", "Front hood / bonnet"),
            ("TRUNK", "Trunk", "Rear trunk / boot"),
            ("BUMPER_F", "Bumper Front", "Front bumper"),
            ("BUMPER_R", "Bumper Rear", "Rear bumper"),
            ("WINDSHIELD", "Windshield", "Front windshield"),
            ("REAR_GLASS", "Rear Glass", "Rear window glass"),
            ("MIRROR_L", "Mirror Left", "Left side mirror"),
            ("MIRROR_R", "Mirror Right", "Right side mirror"),
            ("HEADLIGHT_L", "Headlight L", "Left headlight"),
            ("HEADLIGHT_R", "Headlight R", "Right headlight"),
            ("TAILLIGHT_L", "Taillight L", "Left taillight"),
            ("TAILLIGHT_R", "Taillight R", "Right taillight"),
            ("ENGINE", "Engine", "Engine block"),
            ("EXHAUST", "Exhaust", "Exhaust system"),
            ("INTERIOR", "Interior", "Interior / cabin"),
            ("SEAT_FL", "Seat FL", "Front-left seat"),
            ("SEAT_FR", "Seat FR", "Front-right seat"),
            ("SEAT_RL", "Seat RL", "Rear-left seat"),
            ("SEAT_RR", "Seat RR", "Rear-right seat"),
            ("STEERING", "Steering Wheel", "Steering wheel"),
            ("DASHBOARD", "Dashboard", "Dashboard / instrument panel"),
            ("SUSPENSION", "Suspension", "Suspension system"),
            ("SPOILER", "Spoiler", "Rear spoiler / wing"),
            ("FENDER_FL", "Fender FL", "Front-left fender"),
            ("FENDER_FR", "Fender FR", "Front-right fender"),
            ("FENDER_RL", "Fender RL", "Rear-left fender"),
            ("FENDER_RR", "Fender RR", "Rear-right fender"),
            ("GRILLE", "Grille", "Front grille"),
            ("ROOF", "Roof", "Roof panel"),
            ("OTHER", "Other", "Custom / other part"),
        ],
    },
    "AIRPLANE": {
        "label": "Airplane",
        "icon": "EMPTY_ARROWS",
        "roles": [
            ("FUSELAGE", "Fuselage", "Main body"),
            ("WING_L", "Wing Left", "Left wing"),
            ("WING_R", "Wing Right", "Right wing"),
            ("ENGINE_L", "Engine Left", "Left engine"),
            ("ENGINE_R", "Engine Right", "Right engine"),
            ("TAIL_V", "Vertical Tail", "Vertical stabilizer"),
            ("TAIL_H", "Horizontal Tail", "Horizontal stabilizer"),
            ("COCKPIT", "Cockpit", "Cockpit / cabin"),
            ("LANDING_GEAR", "Landing Gear", "Landing gear"),
            ("PROPELLER", "Propeller", "Propeller / fan"),
            ("OTHER", "Other", "Custom / other part"),
        ],
    },
    "BOAT": {
        "label": "Boat",
        "icon": "FORCE_WIND",
        "roles": [
            ("HULL", "Hull", "Main hull"),
            ("DECK", "Deck", "Deck"),
            ("CABIN", "Cabin", "Cabin / bridge"),
            ("MAST", "Mast", "Mast / tower"),
            ("SAIL", "Sail", "Sail"),
            ("PROPELLER", "Propeller", "Propeller"),
            ("RUDDER", "Rudder", "Rudder"),
            ("ENGINE", "Engine", "Engine / motor"),
            ("OTHER", "Other", "Custom / other part"),
        ],
    },
    "GENERIC": {
        "label": "Generic",
        "icon": "OBJECT_DATA",
        "roles": [
            ("PART", "Part", "Generic part"),
            ("FRAME", "Frame", "Structural frame"),
            ("COVER", "Cover", "Outer cover / shell"),
            ("MECHANISM", "Mechanism", "Internal mechanism"),
            ("FASTENER", "Fastener", "Bolt, screw, or connector"),
            ("OTHER", "Other", "Custom / other part"),
        ],
    },
}


def get_preset_items(self, context):
    """Return EnumProperty items for available presets."""
    return [
        (key, data["label"], f"Preset: {data['label']}", data["icon"], i)
        for i, (key, data) in enumerate(PART_PRESETS.items())
    ]


def get_role_items(self, context):
    """Return EnumProperty items for roles based on the active preset."""
    preset_key = context.scene.blendermcp_part_preset
    preset = PART_PRESETS.get(preset_key, PART_PRESETS["GENERIC"])
    return preset["roles"]


@mcp_command(name="mark_as_functional_part", read_only=False)
def mark_as_functional_part(scene, object_name, role="Generic", preset="GENERIC", metadata=None):
    """Mark an object as a functional part with specific metadata."""
    try:
        if object_name not in scene.objects:
            return {"error": f"Object '{object_name}' not found."}
        
        obj = scene.objects[object_name]
        
        # Tag the object
        obj["mcp_functional_part"] = True
        obj["mcp_part_role"] = str(role)
        obj["mcp_part_preset"] = str(preset)
        
        if metadata:
            if isinstance(metadata, dict):
                obj["mcp_part_metadata"] = json.dumps(metadata)
            else:
                obj["mcp_part_metadata"] = str(metadata)
        
        # Find the human-readable label for the role
        preset_data = PART_PRESETS.get(preset, PART_PRESETS["GENERIC"])
        role_label = role
        for r_id, r_name, _ in preset_data["roles"]:
            if r_id == role:
                role_label = r_name
                break
        
        return {
            "success": True,
            "message": f"'{object_name}' → {preset_data['label']} / {role_label}",
            "preset": preset,
            "role": role,
            "metadata": obj.get("mcp_part_metadata", "{}")
        }
    except Exception as e:
        return {"error": f"Failed to mark part: {str(e)}"}

@mcp_command(name="list_functional_parts", read_only=False)
def list_functional_parts(scene):
    """List all functional parts in the scene with their properties."""
    try:
        parts = []
        for obj in scene.objects:
            if obj.get("mcp_functional_part"):
                role = obj.get("mcp_part_role", "Unknown")
                preset = obj.get("mcp_part_preset", "GENERIC")
                metadata_raw = obj.get("mcp_part_metadata", "{}")
                
                try:
                    metadata = json.loads(metadata_raw)
                except:
                    metadata = metadata_raw
                
                parts.append({
                    "name": obj.name,
                    "role": role,
                    "preset": preset,
                    "dimensions_mm": [d * 1000 for d in obj.dimensions],
                    "location": list(obj.location),
                    "metadata": metadata
                })
        
        return {
            "success": True,
            "parts_count": len(parts),
            "parts": parts
        }
    except Exception as e:
        return {"error": f"Failed to list parts: {str(e)}"}
