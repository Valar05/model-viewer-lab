import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH_ROOT = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
ASSET_ID = 'real_sherman_chassis_scratch_v2'
REVISION = 'scratch-v2-flush-deck-closed-lower-voids'
MODEL_DIR = SCRATCH_ROOT / 'models' / ASSET_ID
BLEND_DIR = SCRATCH_ROOT / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH_ROOT / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH_ROOT / 'notes'
BLEND_PATH = BLEND_DIR / f'{ASSET_ID}.blend'
GLB_PATH = MODEL_DIR / f'{ASSET_ID}.glb'
MANIFEST_PATH = MODEL_DIR / 'model_manifest.json'
NOTES_PATH = NOTES_DIR / f'{ASSET_ID}.md'
SOURCE_MANIFEST = ROOT / 'public' / 'tftm' / 'models' / 'sherman_hull_candidate_current' / 'model_manifest.json'

for directory in (MODEL_DIR, BLEND_DIR, RENDER_DIR, NOTES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def P(x, y, z):
    return (x, -z, y)

materials = {}
def mat(name, color, rough=0.92, metal=0.03):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    materials[name] = m
    return m

mat('scratch_olive_cast_armor', (0.34, 0.40, 0.285, 1), 0.94, 0.025)
mat('scratch_darker_side_armor', (0.275, 0.325, 0.235, 1), 0.96, 0.025)
mat('scratch_deck_armor', (0.365, 0.425, 0.30, 1), 0.94, 0.025)
mat('scratch_shadow_interior', (0.015, 0.014, 0.011, 1), 0.99, 0.0)
mat('scratch_cut_edge_wear', (0.50, 0.54, 0.41, 1), 0.90, 0.035)

created = []
assemblies = {}

def runtime_bbox(points):
    xs = [p[0] for p in points]; ys = [p[1] for p in points]; zs = [p[2] for p in points]
    return {'min':[min(xs),min(ys),min(zs)], 'max':[max(xs),max(ys),max(zs)], 'center':[(min(xs)+max(xs))*0.5,(min(ys)+max(ys))*0.5,(min(zs)+max(zs))*0.5], 'size':[max(xs)-min(xs),max(ys)-min(ys),max(zs)-min(zs)]}

def register(obj, role, note, material_class='armor', bevel=0.0):
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = role
    obj['note'] = note
    obj['source_policy'] = 'Authored scratch geometry using v14/v1 as shape teachers; no Meshy topology copy; not production accepted.'
    if bevel:
        mod = obj.modifiers.new('soft_small_manufactured_bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
        mod.affect = 'EDGES'
        mod.profile = 0.55
    obj.modifiers.new('weighted_normals_for_blender_truth_render', 'WEIGHTED_NORMAL')
    created.append(obj)
    assemblies[role] = {'object': obj.name, 'note': note, 'material_class': material_class, 'bbox': json.loads(obj['runtime_bbox'])}
    return obj

def make_mesh(name, verts, faces, material_name, role, note, material_class='armor', bevel=0.004):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata([P(*v) for v in verts], [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(materials[material_name])
    for poly in mesh.polygons:
        poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj['runtime_bbox'] = json.dumps(runtime_bbox(verts))
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cube_project(cube_size=1.0, correct_aspect=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(False)
    return register(obj, role, note, material_class, bevel)

def offset(points, dx=0, dy=0, dz=0):
    return [(x+dx, y+dy, z+dz) for x, y, z in points]

def make_prism(name, outer, inner, material, role, note, material_class='armor', bevel=0.004):
    verts = outer + inner
    n = len(outer)
    faces = [tuple(range(n)), tuple(range(2*n-1, n-1, -1))]
    for i in range(n):
        faces.append((i, (i+1)%n, n+(i+1)%n, n+i))
    return make_mesh(name, verts, faces, material, role, note, material_class, bevel)

def make_section_shell(name, sections, material, role, note, bevel=0.005):
    verts = []
    for section in sections:
        x = section['x']
        for y, z in section['points']:
            verts.append((x, y, z))
    count = len(sections[0]['points'])
    faces = []
    for i in range(len(sections)-1):
        a = i*count; b = (i+1)*count
        for j in range(count):
            faces.append((a+j, b+j, b+((j+1)%count), a+((j+1)%count)))
    faces.append(tuple(range(count-1, -1, -1)))
    last = (len(sections)-1)*count
    faces.append(tuple(last+j for j in range(count)))
    return make_mesh(name, verts, faces, material, role, note, bevel=bevel)

def make_ring(name, center, outer, inner, height, material, role, note, segments=40, bevel=0.0015):
    cx, cy, cz = center
    verts = []
    for y in (cy+height/2, cy-height/2):
        for radius in (outer, inner):
            for i in range(segments):
                a = math.tau * i / segments
                verts.append((cx + math.cos(a)*radius, y, cz + math.sin(a)*radius))
    top_outer=0; top_inner=segments; bottom_outer=segments*2; bottom_inner=segments*3
    faces=[]
    for i in range(segments):
        j=(i+1)%segments
        faces.append((top_outer+i, top_outer+j, top_inner+j, top_inner+i))
        faces.append((bottom_outer+j, bottom_outer+i, bottom_inner+i, bottom_inner+j))
        faces.append((top_outer+j, top_outer+i, bottom_outer+i, bottom_outer+j))
        faces.append((top_inner+i, top_inner+j, bottom_inner+j, bottom_inner+i))
    return make_mesh(name, verts, faces, material, role, note, 'socket', bevel)

# V2: keep the broad tub, but raise/extend shoulder surfaces so lower dark voids are less visible from front/rear.
lower_sections = [
    {'x': -1.56, 'points': [(-0.095,-0.56),(0.060,-0.76),(0.245,-0.84),(0.345,-0.78),(0.355,0.78),(0.245,0.84),(0.060,0.76),(-0.095,0.56)]},
    {'x': -0.82, 'points': [(-0.115,-0.60),(0.095,-0.83),(0.330,-0.895),(0.455,-0.795),(0.455,0.795),(0.330,0.895),(0.095,0.83),(-0.115,0.60)]},
    {'x': 0.22, 'points': [(-0.105,-0.58),(0.112,-0.835),(0.365,-0.905),(0.482,-0.795),(0.482,0.795),(0.365,0.905),(0.112,0.835),(-0.105,0.58)]},
    {'x': 1.52, 'points': [(-0.078,-0.52),(0.095,-0.715),(0.305,-0.765),(0.398,-0.675),(0.398,0.675),(0.305,0.765),(0.095,0.715),(-0.078,0.52)]},
]
make_section_shell('scratch_real_chassis_v2_continuous_lower_tub_with_full_shoulders', lower_sections, 'scratch_darker_side_armor', 'lower_tub_primary_shell', 'broader continuous tub shoulders close the v1 lower angular voids', bevel=0.006)

front_glacis = [(0.04,0.742,-0.800),(0.04,0.742,0.800),(1.55,0.488,0.900),(1.55,0.488,-0.900)]
make_prism('scratch_real_chassis_v2_broad_front_glacis_skin', front_glacis, offset(front_glacis, dy=-0.072), 'scratch_olive_cast_armor', 'front_glacis_skin', 'broad sloped glacis lowered slightly to meet the flush deck', bevel=0.010)
front_cap = [(0.72,0.300,-0.740),(0.72,0.300,0.740),(1.62,0.165,0.610),(1.62,0.165,-0.610)]
make_prism('scratch_real_chassis_v2_integrated_front_transmission_closure', front_cap, offset(front_cap, dy=-0.105), 'scratch_darker_side_armor', 'front_transmission_cap', 'deeper front closure surface, not a separate blocker', bevel=0.008)

left_side = [(-1.50,0.310,-0.948),(-0.80,0.662,-0.965),(0.18,0.690,-0.980),(1.45,0.448,-0.950),(1.42,0.165,-0.800),(-1.43,0.148,-0.800)]
right_side = [(x,y,-z) for x,y,z in left_side]
make_prism('scratch_real_chassis_v2_left_one_piece_sidewall', left_side, [(x,y,-0.790) for x,y,z in left_side], 'scratch_darker_side_armor', 'left_sidewall', 'left sidewall kept as broad owner of side silhouette', bevel=0.007)
make_prism('scratch_real_chassis_v2_right_one_piece_sidewall', right_side, [(x,y,0.790) for x,y,z in right_side], 'scratch_darker_side_armor', 'right_sidewall', 'right sidewall kept as broad owner of side silhouette', bevel=0.007)

left_sponson = [(-1.52,0.235,-1.055),(1.48,0.225,-1.055),(1.43,0.135,-0.795),(-1.45,0.132,-0.795)]
right_sponson = [(x,y,-z) for x,y,z in left_sponson]
make_prism('scratch_real_chassis_v2_left_integrated_sponson_shelf', left_sponson, offset(left_sponson, dy=-0.095), 'scratch_darker_side_armor', 'left_sponson_shelf', 'thicker left shelf closes the side/tread socket read', bevel=0.006)
make_prism('scratch_real_chassis_v2_right_integrated_sponson_shelf', right_sponson, offset(right_sponson, dy=-0.095), 'scratch_darker_side_armor', 'right_sponson_shelf', 'thicker right shelf closes the side/tread socket read', bevel=0.006)

# V2: stronger full-width rear, with lower apron and side wraps as broad surfaces, not stacked small patches.
rear_skin = [(-1.57,0.555,-0.815),(-1.57,0.555,0.815),(-1.57,0.125,0.635),(-1.57,0.125,-0.635)]
make_prism('scratch_real_chassis_v2_single_broad_rear_bulkhead_skin', rear_skin, offset(rear_skin, dx=0.135), 'scratch_deck_armor', 'rear_bulkhead_skin', 'one broad rear closing skin, taller than v1 to cover lower slot', bevel=0.008)
rear_lower_apron = [(-1.60,0.145,-0.645),(-1.60,0.145,0.645),(-1.50,-0.035,0.535),(-1.50,-0.035,-0.535)]
make_prism('scratch_real_chassis_v2_rear_lower_apron_integrated_closure', rear_lower_apron, offset(rear_lower_apron, dx=0.105), 'scratch_darker_side_armor', 'rear_lower_apron', 'broad lower rear apron closes dark rear-bottom void as hull form', bevel=0.006)
left_rear_wrap = [(-1.57,0.545,-0.815),(-1.43,0.310,-0.948),(-1.43,0.132,-0.800),(-1.57,0.125,-0.635)]
right_rear_wrap = [(x,y,-z) for x,y,z in left_rear_wrap]
make_prism('scratch_real_chassis_v2_left_rear_wrap_skin', left_rear_wrap, offset(left_rear_wrap, dz=0.080), 'scratch_darker_side_armor', 'left_rear_wrap', 'left rear wrap integrated into rear bulkhead', bevel=0.005)
make_prism('scratch_real_chassis_v2_right_rear_wrap_skin', right_rear_wrap, offset(right_rear_wrap, dz=-0.080), 'scratch_darker_side_armor', 'right_rear_wrap', 'right rear wrap integrated into rear bulkhead', bevel=0.005)

engine_deck = [(-1.42,0.382,-0.760),(-0.30,0.704,-0.760),(-0.30,0.704,0.760),(-1.42,0.382,0.760)]
make_prism('scratch_real_chassis_v2_clean_engine_deck_plate', engine_deck, offset(engine_deck, dy=-0.060), 'scratch_deck_armor', 'engine_deck', 'clean rear deck; no black seam strips in v2', bevel=0.005)

left_front_wrap = [(1.42,0.165,-0.800),(1.45,0.448,-0.950),(1.55,0.488,-0.900),(1.55,0.255,-0.640)]
right_front_wrap = [(x,y,-z) for x,y,z in left_front_wrap]
make_prism('scratch_real_chassis_v2_left_front_wrap_skin', left_front_wrap, offset(left_front_wrap, dz=0.080), 'scratch_olive_cast_armor', 'left_front_wrap', 'broad front-side wrap closes visible front corner void', bevel=0.006)
make_prism('scratch_real_chassis_v2_right_front_wrap_skin', right_front_wrap, offset(right_front_wrap, dz=-0.080), 'scratch_olive_cast_armor', 'right_front_wrap', 'broad front-side wrap closes visible front corner void', bevel=0.006)

# V2 central deck: thin and flush, extended wide enough to read as deck surface rather than raised pad.
def make_flush_boolean_deck():
    name='scratch_real_chassis_v2_flush_turret_socket_deck_surface'
    cx,cy,cz = -0.055,0.704,0.0
    sx,sy,sz = 1.160,0.032,1.520
    bpy.ops.mesh.primitive_cube_add(size=1, location=P(cx,cy,cz))
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name + '_mesh'
    obj.dimensions = (sx, sz, sy)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(materials['scratch_deck_armor'])
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.292, depth=sy*6.0, location=P(cx,cy,cz))
    cutter = bpy.context.object
    cutter.name = name + '__actual_hole_cutter'
    bool_mod = obj.modifiers.new('actual_flush_turret_socket_boolean', 'BOOLEAN')
    bool_mod.operation = 'DIFFERENCE'
    bool_mod.object = cutter
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=bool_mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    obj['runtime_bbox'] = json.dumps(runtime_bbox([(cx-sx/2,cy-sy/2,cz-sz/2),(cx+sx/2,cy+sy/2,cz+sz/2)]))
    obj['socket_policy'] = 'flush deck cut; intentionally avoids v1 raised rectangular pad read'
    register(obj, 'flush_turret_socket_deck', 'thin flush central deck with real cut turret opening', 'socket', 0.0015)
make_flush_boolean_deck()
make_ring('scratch_real_chassis_v2_low_turret_ring_lip', (-0.055,0.733,0.0), 0.342, 0.292, 0.018, 'scratch_cut_edge_wear', 'turret_ring_lip', 'lower lip, meant to read as ring on deck rather than platform', segments=48, bevel=0.001)
make_ring('scratch_real_chassis_v2_dark_vertical_turret_well_wall', (-0.055,0.650,0.0), 0.292, 0.252, 0.170, 'scratch_shadow_interior', 'turret_socket_inner_wall', 'dark vertical well wall only; no bottom disk', segments=48, bevel=0.001)

# Lighting and cameras for Blender truth renders.
bpy.ops.object.light_add(type='AREA', location=(0, -4.5, 4.5))
light = bpy.context.object
light.name = 'scratch_large_softbox'
light.data.energy = 570
light.data.size = 5.5
bpy.ops.object.camera_add(location=P(3.10, 1.06, 2.36))
front_cam = bpy.context.object
front_cam.name = 'scratch_front_three_quarter_camera'
bpy.ops.object.camera_add(location=P(-3.05, 1.26, 2.34))
rear_cam = bpy.context.object
rear_cam.name = 'scratch_rear_three_quarter_camera'

def look_at(obj, target):
    loc = obj.location
    direction = Vector((target[0], target[1], target[2])) - loc
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
    'artifact_type': 'scratch_real_sherman_chassis_candidate',
    'revision': REVISION,
    'source_teacher': {'asset_id': source.get('asset_id', 'sherman_hull_candidate_current'), 'silhouette_revision': source.get('silhouette_revision'), 'policy': 'used as measured visual/assembly teacher only, not production truth or topology source'},
    'v1_visible_failures_addressed': ['raised rectangular turret deck pad', 'lower/front angular dark voids', 'rear lower dark slot', 'decorative black seam strips before shell readability'],
    'scope': 'hull/chassis shell only; no treads, wheels, bogies, turret, mantlet, barrel, or coaxial MG',
    'outputs': {'blend': str(BLEND_PATH.relative_to(ROOT)), 'glb': str(GLB_PATH.relative_to(ROOT)), 'front_render': str((RENDER_DIR / 'front_three_quarter.png').relative_to(ROOT)), 'rear_render': str((RENDER_DIR / 'rear_three_quarter.png').relative_to(ROOT))},
    'assemblies': assemblies,
    'judgment_notes': 'One-more-attempt scratch candidate for Blender render judgment only. No cloud/Sense acceptance, no production promotion, no formal validators.'
}
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
NOTES_PATH.write_text(f'''# {ASSET_ID} Scratch Notes\n\nMode: scratch / experimental. Not production accepted.\n\n## Goal\n\nMake one focused attempt to close v1's visible gap: raised deck pad read and lower/front/rear dark voids.\n\n## What Changed From V1\n\n- Replaced the thick raised turret deck pad with a thin flush central deck surface.\n- Lowered and narrowed the turret ring lip so it reads as a socket in armor, not a platform.\n- Removed black deck seam strips.\n- Extended the lower tub shoulders and sponson shelves to reduce angular lower voids.\n- Added a broad rear lower apron as hull form, not as a pasted patch.\n- Kept this to one attempt; if it misses, the visible miss should be named before further work.\n\n## What To Judge In Blender Renders\n\n- Front: does the front/right lower hull still show black angular holes?\n- Rear: does the rear lower area close as manufactured armor?\n- Top: does the turret socket read as cut into the deck instead of sitting on a rectangular pad?\n\n## Status\n\nScratch evidence only. Local Blender renders are judgment aids, not acceptance.\n''', encoding='utf8')
print(json.dumps({'ok': True, 'asset_id': ASSET_ID, 'blend': str(BLEND_PATH), 'glb': str(GLB_PATH), 'renders': [str(RENDER_DIR / 'front_three_quarter.png'), str(RENDER_DIR / 'rear_three_quarter.png')], 'object_count': len(created)}, indent=2))
