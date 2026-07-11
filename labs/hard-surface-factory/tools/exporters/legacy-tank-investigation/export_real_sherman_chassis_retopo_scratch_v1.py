import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH_ROOT = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
ASSET_ID = 'real_sherman_chassis_retopo_scratch_v1'
REVISION = 'scratch-retopo-v1-large-hard-surface-plates'
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

# Materials are not part of this pass. One neutral clay material exists only so Blender renders the forms legibly.
clay = bpy.data.materials.new('scratch_neutral_clay_ignore_materials')
clay.diffuse_color = (0.72, 0.76, 0.66, 1)
clay.use_nodes = True
bsdf = clay.node_tree.nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (0.72, 0.76, 0.66, 1)
bsdf.inputs['Roughness'].default_value = 0.93
bsdf.inputs['Metallic'].default_value = 0.0
shadow = bpy.data.materials.new('scratch_neutral_dark_socket_ignore_materials')
shadow.diffuse_color = (0.02, 0.02, 0.018, 1)
shadow.use_nodes = True
shadow.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.02, 0.02, 0.018, 1)

created = []
assemblies = {}
reference_imported = False

def runtime_bbox(points):
    xs = [p[0] for p in points]; ys = [p[1] for p in points]; zs = [p[2] for p in points]
    return {'min':[min(xs),min(ys),min(zs)], 'max':[max(xs),max(ys),max(zs)], 'center':[(min(xs)+max(xs))*0.5,(min(ys)+max(ys))*0.5,(min(zs)+max(zs))*0.5], 'size':[max(xs)-min(xs),max(ys)-min(ys),max(zs)-min(zs)]}

def register(obj, role, note, points, material_class='large_plate', bevel=0.0):
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = role
    obj['note'] = note
    obj['source_policy'] = 'Authored retopo scratch mesh: v14/current candidate is reference/point cloud only, not a decimated or copied topology.'
    obj['runtime_bbox'] = json.dumps(runtime_bbox(points))
    if bevel:
        mod = obj.modifiers.new('small_hard_surface_edge_bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
        mod.affect = 'EDGES'
        mod.profile = 0.5
    obj.modifiers.new('hard_surface_weighted_normals', 'WEIGHTED_NORMAL')
    created.append(obj)
    assemblies[role] = {'object': obj.name, 'note': note, 'material_class': material_class, 'bbox': json.loads(obj['runtime_bbox'])}
    return obj

def make_mesh(name, verts, faces, role, note, material=None, material_class='large_plate', bevel=0.004):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata([P(*v) for v in verts], [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(material or clay)
    for poly in mesh.polygons:
        poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cube_project(cube_size=1.0, correct_aspect=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(False)
    return register(obj, role, note, verts, material_class, bevel)

def plate_mesh(name, outer, inner, role, note, material=None, material_class='large_plate', bevel=0.004):
    verts = outer + inner
    n = len(outer)
    faces = [tuple(range(n)), tuple(range(2*n-1, n-1, -1))]
    for i in range(n):
        faces.append((i, (i+1)%n, n+(i+1)%n, n+i))
    return make_mesh(name, verts, faces, role, note, material, material_class, bevel)

def offset(points, dx=0, dy=0, dz=0):
    return [(x+dx, y+dy, z+dz) for x,y,z in points]

def section_shell(name, sections, role, note, bevel=0.005):
    verts = []
    count = len(sections[0]['points'])
    for s in sections:
        x = s['x']
        for y,z in s['points']:
            verts.append((x,y,z))
    faces = []
    for i in range(len(sections)-1):
        a = i*count; b = (i+1)*count
        for j in range(count):
            faces.append((a+j, b+j, b+((j+1)%count), a+((j+1)%count)))
    faces.append(tuple(range(count-1, -1, -1)))
    last = (len(sections)-1)*count
    faces.append(tuple(last+j for j in range(count)))
    return make_mesh(name, verts, faces, role, note, clay, 'retopo_shell', bevel)

def circle_ring_mesh(name, center, outer_radius, inner_radius, height, role, note, material=None, segments=48, bevel=0.001):
    cx, cy, cz = center
    verts = []
    for y in (cy+height/2, cy-height/2):
        for r in (outer_radius, inner_radius):
            for i in range(segments):
                a = math.tau*i/segments
                verts.append((cx+math.cos(a)*r, y, cz+math.sin(a)*r))
    top_outer=0; top_inner=segments; bottom_outer=segments*2; bottom_inner=segments*3
    faces=[]
    for i in range(segments):
        j=(i+1)%segments
        faces.append((top_outer+i, top_outer+j, top_inner+j, top_inner+i))
        faces.append((bottom_outer+j, bottom_outer+i, bottom_inner+i, bottom_inner+j))
        faces.append((top_outer+j, top_outer+i, bottom_outer+i, bottom_outer+j))
        faces.append((top_inner+i, top_inner+j, bottom_inner+j, bottom_inner+i))
    return make_mesh(name, verts, faces, role, note, material or clay, 'socket', bevel)

def deck_with_hole(name, center, rect_half_x, rect_half_z, inner_radius, top_y, thickness, role, note, segments=64):
    cx, _, cz = center
    verts = []
    # Radial rectangular boundary around hole: real mesh surface, not a cube/boolean slab.
    for y in (top_y, top_y-thickness):
        for radius_mode in ('outer', 'inner'):
            for i in range(segments):
                a = math.tau*i/segments
                ca = math.cos(a); sa = math.sin(a)
                if radius_mode == 'inner':
                    x = cx + ca*inner_radius; z = cz + sa*inner_radius
                else:
                    t_candidates = []
                    if abs(ca) > 1e-5:
                        t_candidates.append(rect_half_x/abs(ca))
                    if abs(sa) > 1e-5:
                        t_candidates.append(rect_half_z/abs(sa))
                    t = min(t_candidates)
                    x = cx + ca*t; z = cz + sa*t
                verts.append((x,y,z))
    top_outer=0; top_inner=segments; bot_outer=segments*2; bot_inner=segments*3
    faces=[]
    for i in range(segments):
        j=(i+1)%segments
        faces.append((top_outer+i, top_outer+j, top_inner+j, top_inner+i))
        faces.append((bot_outer+j, bot_outer+i, bot_inner+i, bot_inner+j))
        faces.append((top_outer+j, top_outer+i, bot_outer+i, bot_outer+j))
        faces.append((top_inner+i, top_inner+j, bot_inner+j, bot_inner+i))
    return make_mesh(name, verts, faces, role, note, clay, 'retopo_deck_with_hole', 0.0015)

# Hidden reference import. This is in the .blend only and never part of the exported GLB selection.
if REFERENCE_GLB.exists():
    try:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(REFERENCE_GLB))
        after = [obj for obj in bpy.data.objects if obj not in before]
        for obj in after:
            obj.name = 'not_exported_reference_current_candidate__' + obj.name
            obj.hide_viewport = True
            obj.hide_render = True
            obj['reference_only'] = True
        reference_imported = bool(after)
    except Exception as exc:
        reference_imported = False

# Retopo plates: large authored meshes using v14 angles, no primitive-box requirement.
section_shell('retopo_v1_lower_tub_real_mesh_shell', [
    {'x': -1.56, 'points': [(-0.10,-0.56),(0.055,-0.77),(0.250,-0.86),(0.355,-0.78),(0.365,0.78),(0.250,0.86),(0.055,0.77),(-0.10,0.56)]},
    {'x': -0.80, 'points': [(-0.12,-0.61),(0.090,-0.86),(0.330,-0.93),(0.455,-0.82),(0.455,0.82),(0.330,0.93),(0.090,0.86),(-0.12,0.61)]},
    {'x': 0.26, 'points': [(-0.11,-0.59),(0.108,-0.86),(0.365,-0.94),(0.485,-0.82),(0.485,0.82),(0.365,0.94),(0.108,0.86),(-0.11,0.59)]},
    {'x': 1.54, 'points': [(-0.08,-0.53),(0.098,-0.73),(0.312,-0.78),(0.405,-0.69),(0.405,0.69),(0.312,0.78),(0.098,0.73),(-0.08,0.53)]},
], 'lower_tub', 'single real mesh tub with angled shoulder sections, not separate boxes', bevel=0.006)

plate_mesh('retopo_v1_upper_glacis_real_mesh_plate', [(0.02,0.738,-0.83),(0.02,0.738,0.83),(1.56,0.478,0.91),(1.56,0.478,-0.91)], [(0.06,0.665,-0.80),(0.06,0.665,0.80),(1.50,0.408,0.86),(1.50,0.408,-0.86)], 'upper_glacis', 'broad sloped front plate with its own thickness and Sherman angle', bevel=0.008)
plate_mesh('retopo_v1_front_transmission_cap_real_mesh_plate', [(0.68,0.292,-0.74),(0.68,0.292,0.74),(1.62,0.160,0.61),(1.62,0.160,-0.61)], [(0.75,0.170,-0.69),(0.75,0.170,0.69),(1.54,0.060,0.55),(1.54,0.060,-0.55)], 'front_transmission_cap', 'large lower front closure plate, shaped instead of plugged', bevel=0.006)

left_side_outer = [(-1.50,0.304,-0.955),(-0.78,0.660,-0.970),(0.20,0.684,-0.985),(1.47,0.440,-0.958),(1.42,0.150,-0.800),(-1.44,0.142,-0.800)]
right_side_outer = [(x,y,-z) for x,y,z in left_side_outer]
plate_mesh('retopo_v1_left_side_armor_real_mesh_plate', left_side_outer, [(x,y,-0.785) for x,y,z in left_side_outer], 'left_side_armor', 'left side is one custom side armor mesh plate', bevel=0.006)
plate_mesh('retopo_v1_right_side_armor_real_mesh_plate', right_side_outer, [(x,y,0.785) for x,y,z in right_side_outer], 'right_side_armor', 'right side is one custom side armor mesh plate', bevel=0.006)

left_shelf = [(-1.52,0.230,-1.060),(1.48,0.220,-1.060),(1.44,0.122,-0.800),(-1.46,0.126,-0.800)]
right_shelf = [(x,y,-z) for x,y,z in left_shelf]
plate_mesh('retopo_v1_left_sponson_shelf_real_mesh_plate', left_shelf, offset(left_shelf, dy=-0.098), 'left_sponson_shelf', 'left shelf is a shaped track-socket plate, not a slab cover', bevel=0.005)
plate_mesh('retopo_v1_right_sponson_shelf_real_mesh_plate', right_shelf, offset(right_shelf, dy=-0.098), 'right_sponson_shelf', 'right shelf is a shaped track-socket plate, not a slab cover', bevel=0.005)

rear_outer = [(-1.58,0.558,-0.82),(-1.58,0.558,0.82),(-1.58,0.112,0.64),(-1.58,0.112,-0.64)]
rear_inner = [(-1.43,0.500,-0.78),(-1.43,0.500,0.78),(-1.45,0.018,0.55),(-1.45,0.018,-0.55)]
plate_mesh('retopo_v1_rear_bulkhead_real_mesh_plate', rear_outer, rear_inner, 'rear_bulkhead', 'single rear bulkhead plate with lower closure integrated into its mesh', bevel=0.006)
left_rear = [(-1.58,0.548,-0.82),(-1.44,0.304,-0.955),(-1.44,0.126,-0.800),(-1.58,0.112,-0.64)]
right_rear = [(x,y,-z) for x,y,z in left_rear]
plate_mesh('retopo_v1_left_rear_wrap_real_mesh_plate', left_rear, offset(left_rear, dz=0.080), 'left_rear_wrap', 'left rear wrap shares the bulkhead/side relationship', bevel=0.004)
plate_mesh('retopo_v1_right_rear_wrap_real_mesh_plate', right_rear, offset(right_rear, dz=-0.080), 'right_rear_wrap', 'right rear wrap shares the bulkhead/side relationship', bevel=0.004)

engine = [(-1.42,0.382,-0.765),(-0.34,0.696,-0.765),(-0.34,0.696,0.765),(-1.42,0.382,0.765)]
plate_mesh('retopo_v1_engine_deck_real_mesh_plate', engine, offset(engine, dy=-0.062), 'engine_deck', 'plain large rear deck plate; no protuberances', bevel=0.004)

left_front = [(1.42,0.150,-0.800),(1.47,0.440,-0.958),(1.56,0.478,-0.91),(1.58,0.235,-0.63)]
right_front = [(x,y,-z) for x,y,z in left_front]
plate_mesh('retopo_v1_left_front_wrap_real_mesh_plate', left_front, offset(left_front, dz=0.080), 'left_front_wrap', 'left front wrap joins side armor to glacis', bevel=0.004)
plate_mesh('retopo_v1_right_front_wrap_real_mesh_plate', right_front, offset(right_front, dz=-0.080), 'right_front_wrap', 'right front wrap joins side armor to glacis', bevel=0.004)

deck_with_hole('retopo_v1_integrated_turret_socket_deck_real_mesh', (-0.055,0.0,0.0), 0.78, 0.78, 0.292, 0.704, 0.035, 'turret_socket_deck', 'one real mesh deck surface with circular hole; not a rectangular pad or boolean cube', segments=64)
circle_ring_mesh('retopo_v1_low_socket_lip_real_mesh', (-0.055,0.727,0.0), 0.335, 0.294, 0.018, 'turret_socket_lip', 'low hard-surface lip around the cut opening', clay, segments=48, bevel=0.001)
circle_ring_mesh('retopo_v1_dark_inner_turret_wall_real_mesh', (-0.055,0.630,0.0), 0.292, 0.250, 0.180, 'turret_socket_inner_wall', 'dark inner vertical wall only; no bottom disk', shadow, segments=48, bevel=0.001)

# Lighting and cameras for Blender-truth review.
bpy.ops.object.light_add(type='AREA', location=(0, -4.5, 4.6))
light = bpy.context.object
light.name = 'scratch_large_softbox'
light.data.energy = 590
light.data.size = 5.5
bpy.ops.object.camera_add(location=P(3.10, 1.05, 2.36))
front_cam = bpy.context.object
front_cam.name = 'scratch_front_three_quarter_camera'
bpy.ops.object.camera_add(location=P(-3.05, 1.25, 2.34))
rear_cam = bpy.context.object
rear_cam.name = 'scratch_rear_three_quarter_camera'

def look_at(obj, target):
    direction = Vector((target[0], target[1], target[2])) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
for cam in (front_cam, rear_cam):
    look_at(cam, Vector(P(0.0, 0.34, 0.0)))
    cam.data.lens = 58

bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
bpy.ops.object.select_all(action='DESELECT')
for obj in created:
    obj.select_set(True)
bpy.context.view_layer.objects.active = created[0]
bpy.ops.export_scene.gltf(filepath=str(GLB_PATH), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)

bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
bpy.context.scene.eevee.taa_render_samples = 48
bpy.context.scene.render.resolution_x = 1280
bpy.context.scene.render.resolution_y = 840
for cam, filename in [(front_cam, 'front_three_quarter.png'), (rear_cam, 'rear_three_quarter.png')]:
    bpy.context.scene.camera = cam
    bpy.context.scene.render.filepath = str(RENDER_DIR / filename)
    bpy.ops.render.render(write_still=True)

try:
    source = json.loads(SOURCE_MANIFEST.read_text(encoding='utf8'))
except Exception as exc:
    source = {'read_error': str(exc)}
manifest = {
    'asset_id': ASSET_ID,
    'scratch_mode': True,
    'artifact_type': 'scratch_hard_surface_retopo_hull_candidate',
    'revision': REVISION,
    'source_teacher': {'asset_id': source.get('asset_id', 'sherman_hull_candidate_current'), 'silhouette_revision': source.get('silhouette_revision'), 'policy': 'candidate GLB optionally imported as hidden reference only; exported geometry is authored retopo plates'},
    'reference_imported_hidden': reference_imported,
    'scope': 'hull/chassis shell only; large plates only; no treads, wheels, bogies, turret, mantlet, barrel, coaxial MG, protuberances, material plan, or UV polish',
    'outputs': {'blend': str(BLEND_PATH.relative_to(ROOT)), 'glb': str(GLB_PATH.relative_to(ROOT)), 'front_render': str((RENDER_DIR / 'front_three_quarter.png').relative_to(ROOT)), 'rear_render': str((RENDER_DIR / 'rear_three_quarter.png').relative_to(ROOT))},
    'assemblies': assemblies,
    'judgment_notes': 'Scratch retopo branch using large authored mesh plates. Materials/UVs ignored except a neutral clay render material. No production promotion or cloud acceptance.'
}
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
NOTES_PATH.write_text(f'''# {ASSET_ID} Scratch Notes\n\nMode: scratch / experimental. Not production accepted.\n\n## Goal\n\nFollow the alternate plan: keep the strong v14 angles, but model the exploded hull pieces as real hard-surface mesh plates instead of primitive boxes. Materials and UVs are ignored.\n\n## What Changed\n\n- Started a separate retopo scratch branch instead of extending v2.\n- Imported the current candidate only as a hidden/non-exported Blender reference.\n- Authored each large hull piece as custom vertices/faces with thickness and hard-surface normals.\n- Kept only large plates: lower tub, glacis, transmission cap, side armor, sponson shelves, rear bulkhead/wraps, engine deck, and turret socket.\n- Avoided protuberances, bolts, rivets, hatches, material work, UV polish, and full-tank parts.\n\n## What To Judge In Blender Renders\n\n- Does the hull read as authored armor plates rather than primitive boxes?\n- Does the turret opening read as a deck cut, not a pad?\n- Do the lower front/rear voids feel solved by plate shape rather than blockers?\n\n## Status\n\nScratch evidence only. Blender renders are judgment aids, not acceptance.\n''', encoding='utf8')
print(json.dumps({'ok': True, 'asset_id': ASSET_ID, 'blend': str(BLEND_PATH), 'glb': str(GLB_PATH), 'renders': [str(RENDER_DIR / 'front_three_quarter.png'), str(RENDER_DIR / 'rear_three_quarter.png')], 'object_count': len(created), 'reference_imported_hidden': reference_imported}, indent=2))
