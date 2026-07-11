import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH_ROOT = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
ASSET_ID = 'real_sherman_chassis_scratch_v1'
REVISION = 'scratch-v1-joined-manufactured-shell'
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
    # Runtime X length, Y height, Z width -> Blender X, Y, Z-up.
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
    return {
        'min': [min(xs), min(ys), min(zs)],
        'max': [max(xs), max(ys), max(zs)],
        'center': [(min(xs)+max(xs))*0.5, (min(ys)+max(ys))*0.5, (min(zs)+max(zs))*0.5],
        'size': [max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)],
    }

def register(obj, role, note, material_class='armor', bevel=0.0):
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = role
    obj['note'] = note
    obj['source_policy'] = 'Authored scratch geometry using v14 as shape teacher; no Meshy topology copy; not production accepted.'
    if bevel:
        mod = obj.modifiers.new('soft_small_manufactured_bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
        mod.affect = 'EDGES'
        mod.profile = 0.55
    obj.modifiers.new('weighted_normals_for_manual_review', 'WEIGHTED_NORMAL')
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

def make_box(name, center, size, material, role, note, material_class='detail', bevel=0.002):
    cx, cy, cz = center; sx, sy, sz = size
    x0, x1 = cx-sx/2, cx+sx/2; y0, y1 = cy-sy/2, cy+sy/2; z0, z1 = cz-sz/2, cz+sz/2
    verts = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    faces = [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
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

def make_ring(name, center, outer, inner, height, material, role, note, segments=32, bevel=0.002):
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

# Stronger-than-v14 broad shell: one lower tub silhouette whose side shoulders are more continuous.
lower_sections = [
    {'x': -1.55, 'points': [(-0.095,-0.54),(0.055,-0.73),(0.230,-0.76),(0.315,-0.68),(0.315,0.68),(0.230,0.76),(0.055,0.73),(-0.095,0.54)]},
    {'x': -0.82, 'points': [(-0.115,-0.58),(0.090,-0.79),(0.300,-0.82),(0.405,-0.735),(0.405,0.735),(0.300,0.82),(0.090,0.79),(-0.115,0.58)]},
    {'x': 0.22, 'points': [(-0.105,-0.56),(0.105,-0.795),(0.335,-0.825),(0.430,-0.735),(0.430,0.735),(0.335,0.825),(0.105,0.795),(-0.105,0.56)]},
    {'x': 1.50, 'points': [(-0.075,-0.50),(0.090,-0.68),(0.275,-0.705),(0.355,-0.63),(0.355,0.63),(0.275,0.705),(0.090,0.68),(-0.075,0.50)]},
]
make_section_shell('scratch_real_chassis_v1_continuous_lower_tub_and_side_shoulders', lower_sections, 'scratch_darker_side_armor', 'lower_tub_primary_shell', 'continuous tub with shoulders; reduces v14 separated bucket/side read', bevel=0.006)

front_glacis = [(0.08,0.760,-0.780),(0.08,0.760,0.780),(1.52,0.500,0.875),(1.52,0.500,-0.875)]
make_prism('scratch_real_chassis_v1_broad_front_glacis_skin', front_glacis, offset(front_glacis, dy=-0.075), 'scratch_olive_cast_armor', 'front_glacis_skin', 'single broad sloped glacis skin, deliberately larger than v14 to own front read', bevel=0.010)
front_cap = [(0.83,0.255,-0.705),(0.83,0.255,0.705),(1.58,0.175,0.575),(1.58,0.175,-0.575)]
make_prism('scratch_real_chassis_v1_front_transmission_cap_joined_under_glacis', front_cap, offset(front_cap, dy=-0.085), 'scratch_darker_side_armor', 'front_transmission_cap', 'front lower cap closes glacis into tub without a pasted panel', bevel=0.009)

left_side = [(-1.48,0.315,-0.925),(-0.78,0.675,-0.955),(0.22,0.692,-0.970),(1.42,0.455,-0.935),(1.38,0.170,-0.795),(-1.42,0.150,-0.790)]
right_side = [(x,y,-z) for x,y,z in left_side]
make_prism('scratch_real_chassis_v1_left_one_piece_sidewall', left_side, [(x,y,-0.790) for x,y,z in left_side], 'scratch_darker_side_armor', 'left_sidewall', 'one-piece left sidewall; side plane owns sponson/track socket edge', bevel=0.007)
make_prism('scratch_real_chassis_v1_right_one_piece_sidewall', right_side, [(x,y,0.790) for x,y,z in right_side], 'scratch_darker_side_armor', 'right_sidewall', 'one-piece right sidewall; mirror kept broad but judged visually', bevel=0.007)

# Integrated sponson shoulders are thicker and longer than v14 so the hull belongs to the tread context.
left_sponson = [(-1.48,0.205,-1.035),(1.42,0.195,-1.035),(1.36,0.140,-0.790),(-1.42,0.145,-0.790)]
right_sponson = [(x,y,-z) for x,y,z in left_sponson]
make_prism('scratch_real_chassis_v1_left_integrated_sponson_shelf', left_sponson, offset(left_sponson, dy=-0.075), 'scratch_darker_side_armor', 'left_sponson_shelf', 'broad left shelf reads as hull-to-tread socket, not a cover slab', bevel=0.006)
make_prism('scratch_real_chassis_v1_right_integrated_sponson_shelf', right_sponson, offset(right_sponson, dy=-0.075), 'scratch_darker_side_armor', 'right_sponson_shelf', 'broad right shelf reads as hull-to-tread socket, not a cover slab', bevel=0.006)

# Bigger rear solution: one skin plus short wrap cheeks; fewer stacked rear parts than v14.
rear_skin = [(-1.54,0.555,-0.790),(-1.54,0.555,0.790),(-1.54,0.150,0.610),(-1.54,0.150,-0.610)]
make_prism('scratch_real_chassis_v1_single_broad_rear_bulkhead_skin', rear_skin, offset(rear_skin, dx=0.120), 'scratch_deck_armor', 'rear_bulkhead_skin', 'one broad rear closing skin replacing stacked patch behavior', bevel=0.008)
left_rear_wrap = [(-1.54,0.545,-0.790),(-1.42,0.330,-0.925),(-1.40,0.150,-0.790),(-1.54,0.150,-0.610)]
right_rear_wrap = [(x,y,-z) for x,y,z in left_rear_wrap]
make_prism('scratch_real_chassis_v1_left_rear_wrap_cheek', left_rear_wrap, offset(left_rear_wrap, dz=0.070), 'scratch_darker_side_armor', 'left_rear_wrap', 'short wrap cheek makes rear skin belong to sidewall', bevel=0.005)
make_prism('scratch_real_chassis_v1_right_rear_wrap_cheek', right_rear_wrap, offset(right_rear_wrap, dz=-0.070), 'scratch_darker_side_armor', 'right_rear_wrap', 'short wrap cheek makes rear skin belong to sidewall', bevel=0.005)

engine_deck = [(-1.42,0.380,-0.755),(-0.26,0.718,-0.755),(-0.26,0.718,0.755),(-1.42,0.380,0.755)]
make_prism('scratch_real_chassis_v1_clean_engine_deck_plate', engine_deck, offset(engine_deck, dy=-0.065), 'scratch_deck_armor', 'engine_deck', 'one clean rear deck; detail intentionally restrained', bevel=0.006)

# Front cheek triangles are broad joins, not extra slivers.
left_front_wrap = [(1.38,0.170,-0.795),(1.42,0.455,-0.935),(1.52,0.500,-0.875),(1.50,0.240,-0.650)]
right_front_wrap = [(x,y,-z) for x,y,z in left_front_wrap]
make_prism('scratch_real_chassis_v1_left_front_wrap_cheek', left_front_wrap, offset(left_front_wrap, dz=0.075), 'scratch_olive_cast_armor', 'left_front_wrap', 'front cheek visually joins glacis to left sidewall', bevel=0.006)
make_prism('scratch_real_chassis_v1_right_front_wrap_cheek', right_front_wrap, offset(right_front_wrap, dz=-0.075), 'scratch_olive_cast_armor', 'right_front_wrap', 'front cheek visually joins glacis to right sidewall', bevel=0.006)

# Turret socket: keep the lesson, avoid fake black disk.
def make_boolean_deck_plate():
    name='scratch_real_chassis_v1_boolean_cut_turret_deck_plate'
    cx,cy,cz = -0.020,0.735,0.0
    sx,sy,sz = 1.000,0.078,1.035
    bpy.ops.mesh.primitive_cube_add(size=1, location=P(cx,cy,cz))
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name + '_mesh'
    obj.dimensions = (sx, sz, sy)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(materials['scratch_deck_armor'])
    bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=0.282, depth=sy*5.0, location=P(cx,cy,cz))
    cutter = bpy.context.object
    cutter.name = name + '__actual_hole_cutter'
    bool_mod = obj.modifiers.new('actual_open_turret_socket_boolean', 'BOOLEAN')
    bool_mod.operation = 'DIFFERENCE'
    bool_mod.object = cutter
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=bool_mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    obj['runtime_bbox'] = json.dumps(runtime_bbox([(cx-sx/2,cy-sy/2,cz-sz/2),(cx+sx/2,cy+sy/2,cz+sz/2)]))
    obj['socket_policy'] = 'actual through cut, not a black disk'
    register(obj, 'turret_socket_cut_deck', 'solid deck with boolean-cut turret hole', 'socket', 0.003)
make_boolean_deck_plate()
make_ring('scratch_real_chassis_v1_low_turret_ring_lip', (-0.020,0.793,0.0), 0.352, 0.282, 0.028, 'scratch_cut_edge_wear', 'turret_ring_lip', 'low raised lip around real cut metal', segments=32, bevel=0.002)
make_ring('scratch_real_chassis_v1_dark_vertical_turret_well_wall', (-0.020,0.690,0.0), 0.282, 0.247, 0.185, 'scratch_shadow_interior', 'turret_socket_inner_wall', 'dark vertical well wall only; no bottom disk', segments=32, bevel=0.001)

# Minimal controlled deck cues only, avoiding v14 noisy detail field.
for idx, x in enumerate([-1.12, -0.78, -0.44]):
    make_box(f'scratch_real_chassis_v1_restrained_engine_deck_seam_{idx+1}', (x, 0.590 + idx*0.025, 0.0), (0.030, 0.014, 1.05), 'scratch_shadow_interior', f'engine_deck_seam_{idx+1}', 'restrained deck seam; visual cue only after shell is broad', bevel=0.001)

# Add two ghost tread exterior reference rails as hidden/non-exported viewport helpers, not GLB scope.
for side, z in [('left', -1.13), ('right', 1.13)]:
    helper = make_box(f'not_exported_{side}_frozen_tread_exterior_plane_reference', (0.0, 0.02, z), (3.20, 0.018, 0.025), 'scratch_cut_edge_wear', f'not_exported_{side}_tread_reference', 'viewport-only frozen tread exterior side plane reference', 'helper', bevel=0.0)
    helper.hide_render = True
    helper.hide_viewport = True
    if helper in created:
        created.remove(helper)
        assemblies.pop(f'not_exported_{side}_tread_reference', None)

# Lighting and cameras for local scratch judgment.
bpy.ops.object.light_add(type='AREA', location=(0, -4.5, 4.5))
light = bpy.context.object
light.name = 'scratch_large_softbox'
light.data.energy = 550
light.data.size = 5.5
bpy.ops.object.camera_add(location=P(3.15, 1.08, 2.42), rotation=(math.radians(63), 0, math.radians(45)))
front_cam = bpy.context.object
front_cam.name = 'scratch_front_three_quarter_camera'
bpy.ops.object.camera_add(location=P(-3.05, 1.28, 2.38), rotation=(math.radians(62), 0, math.radians(137)))
rear_cam = bpy.context.object
rear_cam.name = 'scratch_rear_three_quarter_camera'

# Aim cameras at chassis center.
def look_at(obj, target):
    loc = obj.location
    direction = Vector((target[0], target[1], target[2])) - loc
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
for cam in (front_cam, rear_cam):
    look_at(cam, Vector(P(0.0, 0.34, 0.0)))
    cam.data.lens = 58

# Save, export selected chassis parts only, render two scratch PNGs.
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
bpy.ops.object.select_all(action='DESELECT')
for obj in created:
    obj.select_set(True)
bpy.context.view_layer.objects.active = created[0]
bpy.ops.export_scene.gltf(filepath=str(GLB_PATH), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)

bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
bpy.context.scene.render.resolution_x = 1280
bpy.context.scene.render.resolution_y = 840
for cam, filename in [(front_cam, 'front_three_quarter.png'), (rear_cam, 'rear_three_quarter.png')]:
    bpy.context.scene.camera = cam
    bpy.context.scene.render.filepath = str(RENDER_DIR / filename)
    bpy.ops.render.render(write_still=True)

source = {}
try:
    source = json.loads(SOURCE_MANIFEST.read_text(encoding='utf8'))
except Exception as exc:
    source = {'read_error': str(exc)}
manifest = {
    'asset_id': ASSET_ID,
    'scratch_mode': True,
    'artifact_type': 'scratch_real_sherman_chassis_candidate',
    'revision': REVISION,
    'source_teacher': {
        'asset_id': source.get('asset_id', 'sherman_hull_candidate_current'),
        'silhouette_revision': source.get('silhouette_revision'),
        'policy': 'used as measured visual/assembly teacher only, not production truth or topology source'
    },
    'scope': 'hull/chassis shell only; no treads, wheels, bogies, turret, mantlet, barrel, or coaxial MG',
    'improvement_intent': [
        'fewer stronger visible assemblies than v14',
        'broader front/side/rear joins before detail',
        'single broad rear bulkhead skin with wrap cheeks',
        'retain real cut-metal turret socket',
        'restrain decorative strips and rivets'
    ],
    'outputs': {
        'blend': str(BLEND_PATH.relative_to(ROOT)),
        'glb': str(GLB_PATH.relative_to(ROOT)),
        'front_render': str((RENDER_DIR / 'front_three_quarter.png').relative_to(ROOT)),
        'rear_render': str((RENDER_DIR / 'rear_three_quarter.png').relative_to(ROOT)),
    },
    'assemblies': assemblies,
    'judgment_notes': 'Scratch candidate for manual review only. No cloud/Sense acceptance, no production promotion, no formal validators.'
}
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
NOTES_PATH.write_text(f'''# {ASSET_ID} Scratch Notes\n\nMode: scratch / experimental. Not production accepted.\n\n## Goal\n\nEscape the almost-good-enough v14 loop by making fewer, stronger manufactured hull relationships before adding details.\n\n## What Changed\n\n- Built a broader continuous lower tub and side-shoulder shell.\n- Enlarged the front glacis skin so it owns the front read instead of relying on slivers.\n- Replaced stacked rear repairs with one broad rear bulkhead skin plus short wrap cheeks.\n- Kept the actual cut-metal turret socket: boolean deck cut, low raised lip, vertical dark wall, no black disk.\n- Restrained detail to three deck seams; no bolts/rivets/HD texture pass.\n\n## What To Judge\n\n- Front three-quarter: do glacis, sidewall, sponson shelf, and lower tub read as joined armor?\n- Rear three-quarter: does the rear close as one manufactured skin, with sidewalls and engine deck belonging to it?\n- Turret socket: does it still read as a real cut opening rather than a disk or decoration?\n\n## Known Risks\n\n- Still hand-authored scratch proportions, not a measured blueprint.\n- Shell is intentionally broad and may need tuning against frozen treads if promoted later.\n- Local renders are judgment aids only, not cloud/Sense acceptance.\n''', encoding='utf8')
print(json.dumps({'ok': True, 'asset_id': ASSET_ID, 'blend': str(BLEND_PATH), 'glb': str(GLB_PATH), 'renders': [str(RENDER_DIR / 'front_three_quarter.png'), str(RENDER_DIR / 'rear_three_quarter.png')], 'object_count': len(created)}, indent=2))
