"""Generate a safe, deterministic Blender Python script from a validated JSON spec."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_script(spec: dict[str, Any], glb_path: Path) -> str:
    # Keep the JSON data inside a Python string literal, then parse it in Blender.
    # JSON's true/false/null are not Python literals; interpolating the raw object
    # directly into exec()-ed Python causes NameError (e.g. `true` is undefined).
    payload = json.dumps(spec, ensure_ascii=True, separators=(",", ":"))
    payload_literal = repr(payload)
    output = json.dumps(str(glb_path.resolve()), ensure_ascii=True)
    template = r'''
import bpy
import json
import math
from mathutils import Vector

SPEC = json.loads(__SPEC_JSON__)
GLB_PATH = __GLB_PATH_JSON__
PREFIX = "GR_"
COLLECTION_NAME = "RoForge_GobbleRail_POC"
if not hasattr(bpy.ops.export_scene, "gltf"):
    raise RuntimeError("Blender glTF 2.0 exporter is unavailable. Enable/install the glTF 2.0 importer/exporter in Blender, then retry.")

# Only replace this PoC's own collection; all unrelated user objects are left alone.
old_collection = bpy.data.collections.get(COLLECTION_NAME)
if old_collection:
    for old_obj in list(old_collection.objects):
        bpy.data.objects.remove(old_obj, do_unlink=True)
    bpy.data.collections.remove(old_collection)
collection = bpy.data.collections.new(COLLECTION_NAME)
bpy.context.scene.collection.children.link(collection)
created = []

def link_obj(obj):
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    collection.objects.link(obj)
    created.append(obj)
    return obj

def color_srgb_to_linear(hex_color):
    raw = [int(hex_color[i:i+2], 16) / 255.0 for i in (1, 3, 5)]
    return [((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in raw]

def make_material(key, hex_color):
    name = PREFIX + "MAT_" + key
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color_srgb_to_linear(hex_color), 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color_srgb_to_linear(hex_color), 1.0)
        roughness = {"brass_trim": 0.30, "cranberry_gel": 0.28, "corn_kernels": 0.58, "roast_skin": 0.62, "bone": 0.48}.get(key, 0.48)
        metallic = 0.68 if key == "brass_trim" else 0.0
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat

MATS = {key: make_material(key, value) for key, value in SPEC["palette"].items()}
PARTS = {part["id"]: part for part in SPEC["parts"]}
S = float(SPEC["overall"]["length"]) / 10.0


def mat_for(part_id, fallback="roast_skin"):
    part = PARTS.get(part_id, {})
    key = part.get("color", fallback)
    return MATS.get(key, MATS[fallback])

def uv_sphere(name, location, dimensions, material, segments=20, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1.0, location=location)
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.scale = (dimensions[0] / 2.0, dimensions[1] / 2.0, dimensions[2] / 2.0)
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return link_obj(obj)

def cube(name, location, dimensions, material, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel > 0:
        mod = obj.modifiers.new("Soft low-poly edges", "BEVEL")
        mod.width = bevel
        mod.segments = 1
    return link_obj(obj)

def rod_between(name, start, end, radius, material, vertices=12):
    a, b = Vector(start), Vector(end)
    delta = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=delta.length, location=(a + b) / 2.0)
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(delta.normalized())
    obj.data.materials.append(material)
    return link_obj(obj)

def cylinder_x(name, x, y, z, length, radius, material, vertices=16):
    return rod_between(name, (x - length/2, y, z), (x + length/2, y, z), radius, material, vertices)

def torus_x(name, x, y, z, major, minor, material):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=24, minor_segments=6, location=(x, y, z))
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Vector((1, 0, 0)))
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return link_obj(obj)

def feather(name, center, angle, length, width, base_mat, tip_mat):
    # Thin extruded leaf silhouette in the XY plane, with its own tip material.
    direction = Vector((math.cos(angle), math.sin(angle), 0.0))
    across = Vector((-direction.y, direction.x, 0.0))
    stations = [(0.0, 0.025), (0.18, 0.62), (0.70, 1.0), (0.82, 0.82), (1.0, 0.0)]
    verts = []
    zhalf = 0.045 * S
    origin = Vector(center)
    for t, half in stations:
        point = origin + direction * (length * S * t)
        side = across * (width * S * half)
        verts.extend([tuple(point - side + Vector((0,0,-zhalf))), tuple(point + side + Vector((0,0,-zhalf))),
                      tuple(point - side + Vector((0,0,zhalf))), tuple(point + side + Vector((0,0,zhalf)))])
    faces = []
    face_tips = []
    for i in range(len(stations)-1):
        a = i * 4
        b = (i+1) * 4
        faces.extend([(a, a+1, b+1, b), (a+2, b+2, b+3, a+3), (a, b, b+2, a+2), (a+1, a+3, b+3, b+1)])
        is_tip = stations[i][0] >= 0.82
        face_tips.extend([is_tip, is_tip, is_tip, is_tip])
    mesh = bpy.data.meshes.new(PREFIX + name + "_Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(base_mat)
    mesh.materials.append(tip_mat)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    collection.objects.link(obj)
    created.append(obj)
    for poly, is_tip in zip(mesh.polygons, face_tips):
        poly.material_index = 1 if is_tip else 0
    return obj

def kernel_cluster(name, centers, dimensions, material):
    # Pack the stylized kernels for one cob into one mesh (fast to build/import,
    # while each cob remains its own named and recolorable component).
    verts, faces = [], []
    segs, rings = 6, 4
    rx, ry, rz = (d / 2.0 for d in dimensions)
    for cx, cy, cz in centers:
        first = len(verts)
        for r in range(rings + 1):
            phi = math.pi * r / rings
            for j in range(segs):
                theta = 2.0 * math.pi * j / segs
                verts.append((cx + rx * math.sin(phi) * math.cos(theta),
                              cy + ry * math.sin(phi) * math.sin(theta),
                              cz + rz * math.cos(phi)))
        for r in range(rings):
            for j in range(segs):
                a = first + r * segs + j
                b = first + r * segs + (j + 1) % segs
                c = first + (r + 1) * segs + (j + 1) % segs
                d = first + (r + 1) * segs + j
                faces.append((a, b, c, d))
    mesh = bpy.data.meshes.new(PREFIX + name + "_Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    collection.objects.link(obj)
    created.append(obj)
    return obj

def parent_to_pivot(obj, pivot_name, location, motion):
    pivot = bpy.data.objects.new(PREFIX + "Pivot_" + pivot_name, None)
    collection.objects.link(pivot)
    pivot.empty_display_type = "PLAIN_AXES"
    pivot.empty_display_size = 0.16 * S
    pivot.location = location
    pivot["motion_type"] = str(motion.get("type", "unspecified"))
    pivot["motion_axis"] = str(motion.get("axis", "unspecified"))
    if motion.get("angle_degrees") is not None:
        pivot["motion_degrees"] = float(motion["angle_degrees"])
    pivot["motion_provisional"] = bool(motion.get("provisional", True))
    created.append(pivot)
    world = obj.matrix_world.copy()
    obj.parent = pivot
    obj.matrix_parent_inverse = pivot.matrix_world.inverted()
    obj.matrix_world = world
    return pivot

# Overall normalized ratios come from the reference spec. X is the long axis.
L = float(SPEC["overall"]["length"])
H = float(SPEC["overall"]["height"])
W = float(SPEC["overall"]["width"])

# Turkey body / receiver, built as separate meshes for straightforward recoloring.
body_x = -2.05 * S
body = uv_sphere("Turkey_Body", (body_x, 0.0, 0.0), (1.95*S, 1.42*S, 1.18*S), mat_for("turkey_receiver"))
uv_sphere("Turkey_Roast_Breast", (body_x + 0.24*S, 0.05*S, 0.0), (1.18*S, 1.02*S, 0.98*S), mat_for("turkey_receiver"))
uv_sphere("Turkey_Head", (body_x + 0.78*S, 0.39*S, 0.0), (0.74*S, 0.70*S, 0.66*S), mat_for("turkey_receiver"))
uv_sphere("Turkey_Beak", (body_x + 1.16*S, 0.36*S, 0.0), (0.30*S, 0.19*S, 0.26*S), mat_for("wishbone_muzzle", "bone"))
uv_sphere("Eye_L", (body_x + 0.90*S, 0.56*S, 0.30*S), (0.11*S, 0.11*S, 0.07*S), MATS.get("brass_trim", mat_for("turkey_receiver")))
uv_sphere("Eye_R", (body_x + 0.90*S, 0.56*S, -0.30*S), (0.11*S, 0.11*S, 0.07*S), MATS.get("brass_trim", mat_for("turkey_receiver")))

# Exactly the approved count; uncertain silhouette and exact feather placement remain editable.
feather_part = PARTS.get("primary_feathers", {})
feather_count = int(feather_part.get("count", 13))
for i in range(feather_count):
    angle = math.radians(55.0 + (250.0 * i / max(1, feather_count - 1)))
    feather("Primary_Feather_{:02d}".format(i+1), (-3.10*S, 0.0, 0.0), angle, 1.60, 0.23,
            mat_for("turkey_receiver"), mat_for("primary_feathers", "feather_tips"))

# Two stylized corn rails, each separated into kernels, rings, and trim.
cob_part = PARTS.get("corn_cobs", {})
cob_count = int(cob_part.get("count", 2))
row_part = PARTS.get("kernel_rows_per_cob", {})
rows = int(row_part.get("count", 10))
rail_x = 1.30 * S
rail_length = 3.75 * S
rail_zs = [-0.24*S, 0.24*S] if cob_count == 2 else [((i - (cob_count-1)/2) * 0.24*S) for i in range(cob_count)]
for ci, z in enumerate(rail_zs):
    uv_sphere("Corn_Cob_{:02d}".format(ci+1), (rail_x, 0.16*S, z), (rail_length, 0.42*S, 0.42*S), mat_for("corn_cobs"), 20, 12)
    # Longitudinal rows follow the supplied 10–12 row range; this starter uses 10.
    kernel_centers = []
    for row in range(rows):
        theta = (2.0 * math.pi * row / rows)
        yoff = 0.16*S + math.sin(theta) * 0.19*S
        zoff = z + math.cos(theta) * 0.19*S
        for k in range(10):
            x = rail_x - rail_length*0.40 + (rail_length*0.80*k/9.0)
            kernel_centers.append((x, yoff, zoff))
    kernel_cluster("Cob_{:02d}_Kernels".format(ci+1), kernel_centers,
                   (0.23*S, 0.13*S, 0.13*S), mat_for("corn_kernels"))

# Structural rails and brass separators.
for z in (-0.40*S, 0.40*S):
    cylinder_x("Barrel_Rail_{:+.0f}".format(z), 1.45*S, 0.08*S, z, 4.35*S, 0.075*S, mat_for("brass_trim"), 12)
for j, x in enumerate((0.02*S, 0.83*S, 1.78*S, 2.75*S, 3.20*S)):
    for z in rail_zs:
        torus_x("Brass_Collar_{:02d}_{:+.0f}".format(j+1, z), x, 0.16*S, z, 0.31*S, 0.075*S, mat_for("brass_trim"))

# Two decorative pie-coil rings, each an independently named object.
ring_part = PARTS.get("pie_coil_rings", {})
for i in range(int(ring_part.get("count", 2))):
    x = 0.55*S + i * 1.42*S
    torus_x("Pie_Coil_Ring_{:02d}".format(i+1), x, 0.16*S, 0.0, 0.47*S, 0.085*S, mat_for("pie_coil_rings"))

# Cranberry magazine/can with eight separate ribs; angle and pivot are provisional.
mag_center = (-1.35*S, -0.95*S, 0.0)
mag = cube("Magazine", mag_center, (0.52*S, 1.14*S, 0.42*S), mat_for("magazine"), 0.10*S)
mag.rotation_euler[2] = math.radians(15.0)
for i in range(int(PARTS.get("cranberry_can_ribs", {}).get("count", 8))):
    yy = mag_center[1] - 0.49*S + i * (0.98*S / 7.0)
    rib = cube("Magazine_Rib_{:02d}".format(i+1), (mag_center[0], yy, mag_center[2]), (0.55*S, 0.055*S, 0.45*S), mat_for("brass_trim"), 0.02*S)
    rib.rotation_euler[2] = math.radians(15.0)

# Trigger and guard stay independent from the receiver.
trigger = rod_between("Trigger", (-1.65*S, -0.30*S, 0.0), (-1.48*S, -0.66*S, 0.0), 0.075*S, mat_for("trigger"), 10)
rod_between("Trigger_Guard", (-1.94*S, -0.24*S, 0.0), (-1.18*S, -0.40*S, 0.0), 0.045*S, mat_for("brass_trim"), 10)

# Muzzle fork / wishbone prongs.
root = (3.72*S, 0.16*S, 0.0)
rod_between("Wishbone_Stem", root, (4.35*S, 0.16*S, 0.0), 0.095*S, mat_for("wishbone_muzzle", "bone"), 10)
rod_between("Wishbone_Upper", (4.25*S, 0.16*S, 0.0), (4.76*S, 0.42*S, 0.0), 0.065*S, mat_for("wishbone_muzzle", "bone"), 10)
rod_between("Wishbone_Lower", (4.25*S, 0.16*S, 0.0), (4.76*S, -0.10*S, 0.0), 0.065*S, mat_for("wishbone_muzzle", "bone"), 10)
uv_sphere("Muzzle_Tip", (4.81*S, 0.16*S, 0.0), (0.20*S, 0.14*S, 0.16*S), mat_for("brass_trim"))

# Keep the wattle small and tuck it directly under the beak so it reads as
# turkey anatomy instead of obscuring the receiver. Its pivot remains provisional.
wattle = uv_sphere("Wattle", (-0.82*S, 0.15*S, 0.0), (0.14*S, 0.26*S, 0.13*S), mat_for("wattle"), 16, 10)

# Draft pivot empties make intended articulation visible in Blender; Roblox constraints are a later step.
motion_by_part = {m.get("part_id"): m for m in SPEC.get("motions", [])}
parent_to_pivot(trigger, "Trigger", (-1.67*S, -0.31*S, 0.0), motion_by_part.get("trigger", {}))
parent_to_pivot(mag, "Magazine", (-1.35*S, -0.43*S, 0.0), motion_by_part.get("magazine", {}))
parent_to_pivot(wattle, "Wattle", (-0.84*S, 0.27*S, 0.0), motion_by_part.get("wattle", {}))

# Add scene metadata for later Blender/Roblox automation.
root_obj = bpy.data.objects.new(PREFIX + "Assembly", None)
collection.objects.link(root_obj)
created.append(root_obj)
# A cube-shaped Empty visually obscures the assembly in the viewport.
root_obj.empty_display_type = "PLAIN_AXES"
root_obj.empty_display_size = 0.08*S
root_obj["asset_name"] = SPEC["asset_name"]
root_obj["unit_mode"] = SPEC.get("unit_mode", "normalized")
root_obj["proportion_length_height_width"] = "{}:{}:{}".format(L, H, W)
root_obj["source_of_truth"] = "RoForge structured spec JSON; dimensions and pivots marked provisional must be reviewed."
# Scale the assembly as a hierarchy so its bounding box matches the approved overall dimensions.
# Values remain normalized units until the user specifies a Roblox stud length.
mesh_objects = [obj for obj in created if obj.type == "MESH"]
world_corners = [obj.matrix_world @ Vector(corner) for obj in mesh_objects for corner in obj.bound_box]
mins = Vector((min(p.x for p in world_corners), min(p.y for p in world_corners), min(p.z for p in world_corners)))
maxs = Vector((max(p.x for p in world_corners), max(p.y for p in world_corners), max(p.z for p in world_corners)))
extent = maxs - mins
if min(extent.x, extent.y, extent.z) <= 0:
    raise RuntimeError("Generated geometry has a zero-size axis; refusing to export.")
scale = Vector((L / extent.x, H / extent.y, W / extent.z))
center = (mins + maxs) / 2.0
root_obj.scale = scale
root_obj.location = Vector((-center.x * scale.x, -center.y * scale.y, -center.z * scale.z))
root_obj["target_dimensions_normalized"] = (L, H, W)
for obj in list(created):
    if obj == root_obj:
        continue
    if obj.parent is None:
        obj.parent = root_obj
    elif obj.parent.name.startswith(PREFIX + "Pivot_") and obj.parent.parent is None:
        obj.parent.parent = root_obj

# Export only the PoC collection; do not save or overwrite the user's current .blend.
bpy.ops.object.select_all(action="DESELECT")
for obj in created:
    obj.select_set(True)
bpy.context.view_layer.objects.active = root_obj
bpy.ops.export_scene.gltf(filepath=GLB_PATH, export_format="GLB", use_selection=True, export_apply=True)
print("ROFORGE_POC_RESULT=" + SPEC["asset_name"] + "|" + GLB_PATH + "|objects=" + str(len(created)))
'''
    return template.replace("__GLB_PATH_JSON__", output).replace("__SPEC_JSON__", payload_literal)
