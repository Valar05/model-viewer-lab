import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH_ROOT = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
ASSET_ID = 'real_sherman_chassis_kit_scratch_v1'
REVISION = 'scratch-kit-v1-eight-piece-low-poly-clean-uv'
MODEL_DIR = SCRATCH_ROOT / 'models' / ASSET_ID
BLEND_DIR = SCRATCH_ROOT / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH_ROOT / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH_ROOT / 'notes'
BLEND_PATH = BLEND_DIR / f'{ASSET_ID}.blend'
GLB_PATH = MODEL_DIR / f'{ASSET_ID}.glb'
MANIFEST_PATH = MODEL_DIR / 'model_manifest.json'
NOTES_PATH = NOTES_DIR / f'{ASSET_ID}.md'
REFERENCE_GLB = ROOT / 'public' / 'tftm' / 'models' / 'sherman_hull_candidate_current' / 'sherman_hull_candidate_current.glb'
SOURCE_MANIFEST = ROOT / 'public' / 'tftm' / 'models' / 'sherman_hull_candidate_current' / 'model_manifest.json'

for directory in (MODEL_DIR, BLEND_DIR, RENDER_DIR, NOTES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def P(x, y, z):
    return (x, -z, y)

created = []
assemblies = {}

mat = bpy.data.materials.new('scratch_kit_neutral_clay_ignore_materials')
mat.diffuse_color = (0.70, 0.74, 0.65, 1)
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.70, 0.74, 0.65, 1)
bsdf.inputs['Roughness'].default_value = 0.92
shadow = bpy.data.materials.new('scratch_kit_socket_shadow_ignore_materials')
shadow.diffuse_color = (0.025, 0.025, 0.022, 1)
shadow.use_nodes = True
shadow.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.025, 0.025, 0.022, 1)
shadow.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value = 0.96

def bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return {'min': [min(xs), min(ys), min(zs)], 'max': [max(xs), max(ys), max(zs)], 'center': [(min(xs)+max(xs))*0.5, (min(ys)+max(ys))*0.5, (min(zs)+max(zs))*0.5], 'size': [max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)]}

def uv_for_point(point, uv_mode, bounds):
    x, y, z = point
    (minx, miny, minz), (maxx, maxy, maxz) = bounds
    def n(v, lo, hi):
        span = hi - lo
        return 0.03 + 0.94 * ((v - lo) / span if span > 1e-6 else 0.5)
    if uv_mode == 'top':
        return (n(x, minx, maxx), n(z, minz, maxz))
    if uv_mode == 'front':
        return (n(z, minz, maxz), n(y, miny, maxy))
    if uv_mode == 'side_x':
        return (n(x, minx, maxx), n(y, miny, maxy))
    if uv_mode == 'side_z':
        return (n(z, minz, maxz), n(y, miny, maxy))
    return (n(x, minx, maxx), n(z, minz, maxz))

def apply_clean_uv(mesh, runtime_verts, uv_mode):
    xs = [v[0] for v in runtime_verts]
    ys = [v[1] for v in runtime_verts]
    zs = [v[2] for v in runtime_verts]
    bounds = ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))
    uv_layer = mesh.uv_layers.new(name='kit_clean_uv')
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            vi = mesh.loops[loop_index].vertex_index
            uv_layer.data[loop_index].uv = uv_for_point(runtime_verts[vi], uv_mode, bounds)

def register(obj, role, note, points, uv_mode, material_class, nominal_triangles):
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['kit_piece'] = True
    obj['role'] = role
    obj['note'] = note
    obj['uv_layer'] = 'kit_clean_uv'
    obj['uv_policy'] = uv_mode
    obj['runtime_bbox'] = json.dumps(bbox(points))
    obj['source_policy'] = 'Kit piece is authored low-poly hard-surface mesh against current hull envelope; not a decimated copy and not production promotion.'
    assemblies[role] = {'object': obj.name, 'role': role, 'note': note, 'material_class': material_class, 'uv_layer': 'kit_clean_uv', 'uv_policy': uv_mode, 'bbox': json.loads(obj['runtime_bbox']), 'nominal_triangles_before_modifiers': nominal_triangles}
    created.append(obj)
    return obj

def make_mesh(name, verts, faces, role, note, uv_mode='top', material=mat, material_class='armor_plate', bevel=0.003):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata([P(*v) for v in verts], [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(material)
    for p in mesh.polygons:
        p.use_smooth = False
    apply_clean_uv(mesh, verts, uv_mode)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if bevel > 0:
        mod = obj.modifiers.new('small_real_plate_edge_bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
        mod.affect = 'EDGES'
    obj.modifiers.new('hard_surface_weighted_normals', 'WEIGHTED_NORMAL')
    return register(obj, role, note, verts, uv_mode, material_class, sum(max(0, len(f)-2) for f in faces))

def thick_plate(name, top, bottom, role, note, uv_mode='top', material=mat, bevel=0.003):
    n = len(top)
    verts = top + bottom
    faces = [tuple(range(n)), tuple(range(2*n-1, n-1, -1))]
    for i in range(n):
        faces.append((i, (i+1)%n, n+(i+1)%n, n+i))
    return make_mesh(name, verts, faces, role, note, uv_mode, material, 'thick_plate', bevel)

def section_mesh(name, sections, role, note, uv_mode='side_x', bevel=0.004):
    verts = []
    count = len(sections[0]['points'])
    for section in sections:
        x = section['x']
        for y, z in section['points']:
            verts.append((x, y, z))
    faces = []
    for s in range(len(sections)-1):
        a = s * count
        b = (s + 1) * count
        for i in range(count):
            faces.append((a+i, b+i, b+((i+1)%count), a+((i+1)%count)))
    faces.append(tuple(range(count-1, -1, -1)))
    last = (len(sections)-1) * count
    faces.append(tuple(last+i for i in range(count)))
    return make_mesh(name, verts, faces, role, note, uv_mode, mat, 'section_shell', bevel)

def mirror_z(points):
    return [(x, y, -z) for x, y, z in points]

def ray_to_convex_polygon(cx, cz, ca, sa, polygon):
    best = None
    for i in range(len(polygon)):
        x1, z1 = polygon[i]
        x2, z2 = polygon[(i + 1) % len(polygon)]
        ex = x2 - x1
        ez = z2 - z1
        det = ca * (-ez) - (-ex) * sa
        if abs(det) < 1e-7:
            continue
        rx = x1 - cx
        rz = z1 - cz
        t = (rx * (-ez) - (-ex) * rz) / det
        u = (ca * rz - rx * sa) / det
        if t > 0 and -1e-6 <= u <= 1 + 1e-6:
            if best is None or t < best:
                best = t
    return best if best is not None else 0.45

def deck_with_ring_opening(name, role, note, center=(-0.04, 0.0), radius=0.285, top_y=0.686, thickness=0.024, segments=24):
    cx, cz = center
    outer_polygon = [
        (-0.74, -0.805), (0.30, -0.805), (0.62, -0.650), (0.68, -0.300),
        (0.62, 0.650), (0.30, 0.805), (-0.74, 0.805), (-0.88, 0.570),
        (-0.86, -0.570),
    ]
    verts = []
    for y in (top_y, top_y-thickness):
        for mode in ('outer', 'inner'):
            for i in range(segments):
                a = math.tau * i / segments
                ca = math.cos(a)
                sa = math.sin(a)
                if mode == 'inner':
                    verts.append((cx + ca * radius, y, cz + sa * radius))
                else:
                    t = ray_to_convex_polygon(cx, cz, ca, sa, outer_polygon)
                    verts.append((cx + ca * t, y, cz + sa * t))
    top_outer = 0
    top_inner = segments
    bot_outer = segments * 2
    bot_inner = segments * 3
    faces = []
    for i in range(segments):
        j = (i+1) % segments
        faces.append((top_outer+i, top_outer+j, top_inner+j, top_inner+i))
        faces.append((bot_outer+j, bot_outer+i, bot_inner+i, bot_inner+j))
        faces.append((top_outer+j, top_outer+i, bot_outer+i, bot_outer+j))
        faces.append((top_inner+i, top_inner+j, bot_inner+j, bot_inner+i))
    return make_mesh(name, verts, faces, role, note, 'top', mat, 'deck_with_cutout', 0.0015)

def socket_wall(name, role, note, center=(-0.04, 0.0), outer_radius=0.286, inner_radius=0.247, top_y=0.670, bottom_y=0.515, segments=24):
    cx, cz = center
    verts = []
    for y in (top_y, bottom_y):
        for r in (outer_radius, inner_radius):
            for i in range(segments):
                a = math.tau * i / segments
                verts.append((cx + math.cos(a) * r, y, cz + math.sin(a) * r))
    top_outer = 0
    top_inner = segments
    bot_outer = segments * 2
    bot_inner = segments * 3
    faces = []
    for i in range(segments):
        j = (i+1) % segments
        faces.append((top_outer+i, top_outer+j, top_inner+j, top_inner+i))
        faces.append((top_outer+j, top_outer+i, bot_outer+i, bot_outer+j))
        faces.append((top_inner+i, top_inner+j, bot_inner+j, bot_inner+i))
    return make_mesh(name, verts, faces, role, note, 'top', shadow, 'socket_wall', 0.001)

reference_imported = False
if REFERENCE_GLB.exists():
    try:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(REFERENCE_GLB))
        imported = [obj for obj in bpy.data.objects if obj not in before]
        for obj in imported:
            obj.name = 'not_exported_reference_current_hull__' + obj.name
            obj.hide_viewport = True
            obj.hide_render = True
            obj['reference_only'] = True
        reference_imported = bool(imported)
    except Exception:
        reference_imported = False

section_mesh('kit_v1_01_lower_tub_single_bucket', [
    {'x': -1.52, 'points': [(-0.095,-0.55),(0.050,-0.755),(0.300,-0.805),(0.390,-0.655),(0.390,0.655),(0.300,0.805),(0.050,0.755),(-0.095,0.55)]},
    {'x': -0.52, 'points': [(-0.112,-0.59),(0.086,-0.835),(0.350,-0.875),(0.455,-0.700),(0.455,0.700),(0.350,0.875),(0.086,0.835),(-0.112,0.59)]},
    {'x': 0.48, 'points': [(-0.108,-0.57),(0.096,-0.820),(0.365,-0.860),(0.465,-0.685),(0.465,0.685),(0.365,0.860),(0.096,0.820),(-0.108,0.57)]},
    {'x': 1.50, 'points': [(-0.080,-0.52),(0.102,-0.680),(0.315,-0.700),(0.395,-0.560),(0.395,0.560),(0.315,0.700),(0.102,0.680),(-0.080,0.52)]},
], 'lower_tub', 'one manufactured lower hull bucket; no side shelves or blockers split away from it', 'side_x', 0.004)

glacis_top = [(0.12,0.758,-0.855),(0.12,0.758,0.855),(1.48,0.478,0.895),(1.60,0.205,0.620),(1.60,0.205,-0.620),(1.48,0.478,-0.895)]
glacis_bottom = [(0.18,0.682,-0.810),(0.18,0.682,0.810),(1.42,0.397,0.830),(1.52,0.090,0.555),(1.52,0.090,-0.555),(1.42,0.397,-0.830)]
thick_plate('kit_v1_02_upper_glacis_and_front_nose', glacis_top, glacis_bottom, 'upper_glacis_front_nose', 'front armor kit piece merges glacis, corner rake, and lower transmission nose into one retopo part', 'front', mat, 0.004)

left_outer = [(-1.47,0.322,-0.972),(-0.74,0.670,-0.988),(0.22,0.690,-0.992),(1.42,0.448,-0.960),(1.52,0.222,-0.700),(1.44,0.126,-1.055),(-1.48,0.128,-1.055),(-1.56,0.172,-0.710)]
left_inner = [(-1.39,0.292,-0.782),(-0.68,0.612,-0.790),(0.20,0.630,-0.792),(1.35,0.398,-0.772),(1.43,0.148,-0.600),(1.36,0.072,-0.792),(-1.38,0.074,-0.792),(-1.46,0.104,-0.610)]
thick_plate('kit_v1_03_left_side_and_sponson_one_piece', left_outer, left_inner, 'left_side_sponson', 'left kit part merges side armor, sponson shelf, and front/rear cheek joins so it reads as one plate assembly', 'side_x', mat, 0.004)
thick_plate('kit_v1_04_right_side_and_sponson_one_piece', mirror_z(left_outer), mirror_z(left_inner), 'right_side_sponson', 'right kit part mirrors the integrated side armor and shelf; no extra wrap helper pieces', 'side_x', mat, 0.004)

rear_outer = [(-1.58,0.575,-0.815),(-1.58,0.575,0.815),(-1.58,0.112,0.640),(-1.58,0.055,-0.640)]
rear_inner = [(-1.425,0.502,-0.735),(-1.425,0.502,0.735),(-1.430,0.024,0.550),(-1.430,-0.012,-0.550)]
thick_plate('kit_v1_05_rear_bulkhead_butt_plate', rear_outer, rear_inner, 'rear_bulkhead', 'single rear closure plate with broad butt cover; keeps the one improvement from retopo v1 without side helper noise', 'front', mat, 0.004)

engine_top = [(-1.42,0.388,-0.755),(-0.36,0.682,-0.755),(-0.36,0.682,0.755),(-1.42,0.388,0.755)]
engine_bottom = [(-1.35,0.322,-0.708),(-0.42,0.628,-0.708),(-0.42,0.628,0.708),(-1.35,0.322,0.708)]
thick_plate('kit_v1_06_engine_deck_plain_plate', engine_top, engine_bottom, 'engine_deck', 'one low-poly engine deck plate, deliberately no grilles, rivets, or protuberances in this pass', 'top', mat, 0.003)

deck_with_ring_opening('kit_v1_07_turret_deck_with_real_socket_cutout', 'turret_deck_socket', 'single deck kit plate with a real circular opening; no tank turret or top pad candidate')
socket_wall('kit_v1_08_turret_socket_inner_wall', 'turret_socket_inner_wall', 'separate low-poly ring wall for retopo/texture boundary; dark only for Blender readability')

for obj in created:
    obj['kit_delivery_mode'] = 'assembled_for_screenshot_parity; objects remain independent kit meshes for retopo/UV work'

bpy.ops.object.light_add(type='AREA', location=(0, -4.8, 4.8))
light = bpy.context.object
light.name = 'scratch_kit_large_softbox'
light.data.energy = 620
light.data.size = 5.8
bpy.ops.object.camera_add(location=P(3.05, 1.05, 2.36))
front_cam = bpy.context.object
front_cam.name = 'scratch_kit_front_three_quarter_camera'
bpy.ops.object.camera_add(location=P(-3.08, 1.20, 2.36))
rear_cam = bpy.context.object
rear_cam.name = 'scratch_kit_rear_three_quarter_camera'

def look_at(obj, target_runtime):
    direction = Vector(P(*target_runtime)) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
for cam in (front_cam, rear_cam):
    look_at(cam, (0.0, 0.34, 0.0))
    cam.data.lens = 58

bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
bpy.ops.object.select_all(action='DESELECT')
for obj in created:
    obj.select_set(True)
bpy.context.view_layer.objects.active = created[0]
bpy.ops.export_scene.gltf(filepath=str(GLB_PATH), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)

engine_items = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
if hasattr(bpy.context.scene, 'eevee'):
    bpy.context.scene.eevee.taa_render_samples = 48
bpy.context.scene.render.resolution_x = 1280
bpy.context.scene.render.resolution_y = 840
for cam, filename in ((front_cam, 'front_three_quarter.png'), (rear_cam, 'rear_three_quarter.png')):
    bpy.context.scene.camera = cam
    bpy.context.scene.render.filepath = str(RENDER_DIR / filename)
    bpy.ops.render.render(write_still=True)

try:
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding='utf8'))
except Exception as exc:
    source_manifest = {'read_error': str(exc)}

manifest = {
    'asset_id': ASSET_ID,
    'artifact_type': 'scratch_hard_surface_kit_not_tank',
    'revision': REVISION,
    'scratch_mode': True,
    'revision_note': 'rerun after Blender read: lowered and reshaped turret deck to reduce top-pad read and long side/top shadow seams',
    'source_reference_asset': str(REFERENCE_GLB.relative_to(ROOT)) if REFERENCE_GLB.exists() else None,
    'source_reference_imported_hidden_in_blend': reference_imported,
    'source_reference_manifest_revision': source_manifest.get('silhouette_revision'),
    'output_glb': str(GLB_PATH.relative_to(ROOT)),
    'source_blend': str(BLEND_PATH.relative_to(ROOT)),
    'renders': {'front_three_quarter': str((RENDER_DIR / 'front_three_quarter.png').relative_to(ROOT)), 'rear_three_quarter': str((RENDER_DIR / 'rear_three_quarter.png').relative_to(ROOT))},
    'kit_policy': {'make_tank': False, 'assembled_for_screenshot_parity': True, 'piece_count': len(created), 'expected_piece_count': '8ish', 'no_protuberances': True, 'materials_ignored_except_neutral_render_readability': True, 'uv_requirement': 'Every exported mesh owns a kit_clean_uv layer with simple normalized planar UVs; no packed atlas yet.', 'low_poly_policy': 'Large manufactured hull plates only; bevels are one-segment diagnostic modifiers for edge readability.'},
    'assemblies': assemblies,
}
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding='utf8')

notes = f'''# {ASSET_ID}\n\nPrompt: make the kit, not the tank. Keep scratch mode, target screenshot parity, clean real UVs, and low-poly hard-surface realism.\n\nWhat changed from retopo scratch v1:\n\n- Exported exactly eight large kit meshes instead of sixteen separate wrap/shelf/helper meshes.\n- Merged front nose into the glacis kit piece.\n- Merged each side armor, sponson shelf, and cheek joins into one side kit piece.\n- Preserved the rear/butt coverage lesson as a single rear bulkhead piece.\n- Kept engine deck and turret deck/socket as separate retopo-friendly plates.\n- Added kit_clean_uv UV layers on every exported mesh with simple normalized planar UVs.\n- Ignored material design beyond neutral clay/dark socket render readability.\n\nKnown limits:\n\n- This is a scratch diagnostic artifact, not production acceptance.\n- Blender renders are local diagnostic truth for this scratch loop, not cloud/Sense acceptance.\n- UVs are real and clean enough for plate painting/decal tests, but not a final packed production atlas.\n- No running gear, turret, barrel, rivets, grilles, hatches, or protuberances are included.\n\nOutputs:\n\n- GLB: {GLB_PATH.relative_to(ROOT)}\n- Blend: {BLEND_PATH.relative_to(ROOT)}\n- Manifest: {MANIFEST_PATH.relative_to(ROOT)}\n- Renders: {(RENDER_DIR / 'front_three_quarter.png').relative_to(ROOT)}, {(RENDER_DIR / 'rear_three_quarter.png').relative_to(ROOT)}\n'''
NOTES_PATH.write_text(notes, encoding='utf8')

print(json.dumps({'asset_id': ASSET_ID, 'pieces': len(created), 'glb': str(GLB_PATH), 'blend': str(BLEND_PATH)}, indent=2))
