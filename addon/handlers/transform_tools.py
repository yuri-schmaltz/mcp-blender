import bpy
import mathutils
import math

def transform_object(scene, name, location=None, rotation=None, scale=None, relative=False):
    """
    Transform an object (location, rotation, scale).
    Rotation should be a list of 3 floats in degrees.
    """
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}
        
        if location:
            loc_vec = mathutils.Vector(location)
            if relative:
                obj.location += loc_vec
            else:
                obj.location = loc_vec
                
        if rotation:
            rot_vec = [math.radians(r) for r in rotation]
            if relative:
                obj.rotation_euler.x += rot_vec[0]
                obj.rotation_euler.y += rot_vec[1]
                obj.rotation_euler.z += rot_vec[2]
            else:
                obj.rotation_euler = rot_vec
                
        if scale:
            scale_vec = mathutils.Vector(scale)
            if relative:
                obj.scale.x *= scale_vec.x
                obj.scale.y *= scale_vec.y
                obj.scale.z *= scale_vec.z
            else:
                obj.scale = scale_vec
                
        bpy.context.view_layer.update()
        
        return {
            "success": True,
            "message": f"Object '{name}' transformed.",
            "location": list(obj.location),
            "rotation": [math.degrees(r) for r in obj.rotation_euler],
            "scale": list(obj.scale)
        }
    except Exception as e:
        return {"error": str(e)}

def add_primitive(scene, type, name=None, location=(0,0,0), scale=(1,1,1)):
    """
    Add a primitive object to the scene.
    Type can be: CUBE, SPHERE, PLANE, MONKEY, CYLINDER, CONE, TORUS
    """
    try:
        type = type.upper()
        if type == "CUBE":
            bpy.ops.mesh.primitive_cube_add(location=location)
        elif type == "SPHERE":
            bpy.ops.mesh.primitive_uv_sphere_add(location=location)
        elif type == "PLANE":
            bpy.ops.mesh.primitive_plane_add(location=location)
        elif type == "MONKEY":
            bpy.ops.mesh.primitive_monkey_add(location=location)
        elif type == "CYLINDER":
            bpy.ops.mesh.primitive_cylinder_add(location=location)
        elif type == "CONE":
            bpy.ops.mesh.primitive_cone_add(location=location)
        elif type == "TORUS":
            bpy.ops.mesh.primitive_torus_add(location=location)
        else:
            return {"error": f"Unsupported primitive type: {type}"}
            
        obj = bpy.context.active_object
        if name:
            obj.name = name
        
        obj.scale = scale
        bpy.context.view_layer.update()
        
        return {
            "success": True,
            "message": f"Added {type} named '{obj.name}'.",
            "name": obj.name,
            "location": list(obj.location)
        }
    except Exception as e:
        return {"error": str(e)}

def delete_object(scene, name):
    """Delete an object by name."""
    try:
        obj = scene.objects.get(name)
        if not obj:
            return {"error": f"Object '{name}' not found."}
        
        bpy.data.objects.remove(obj, do_unlink=True)
        return {"success": True, "message": f"Object '{name}' deleted."}
    except Exception as e:
        return {"error": str(e)}
