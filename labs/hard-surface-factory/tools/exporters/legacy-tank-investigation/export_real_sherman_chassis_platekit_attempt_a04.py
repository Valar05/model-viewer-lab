import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH_ROOT = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
SERIES_ID = 'real_sherman_chassis_platekit_scratch'
REVISION = 'platekit-authored-lowpoly-attempts-a01-a03'
SOURCE_POLICY = 'Source/reference meshes are visual teachers only. Exported topology is authored hard-surface plate geometry; no Meshy/source topology copy and no decimation.'

ATTEMPTS = [
    {'suffix': 'a04', 'label': 'quad-side topology cleanup candidate', 'spacing': 0.52, 'z_gap': 0.26, 'front_refine': 0.10, 'rear_refine': 0.08, 'socket_segments': 12, 'side_taper': 0.06, 'deck_cut': True, 'quad_side': True, 'ring_lip': False, 'judgment': 'Candidate cleanup: side armor is true quad topology and the separate ring object is removed to keep the kit simple.'},
]

for d in [SCRATCH_ROOT / 'models', SCRATCH_ROOT / 'source_blends', SCRATCH_ROOT / 'renders', SCRATCH_ROOT / 'notes']:
    d.mkdir(parents=True, exist_ok=True)

def P(x, y, z):
    return (x, -z, y)

def reset_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for datablock in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for item in list(datablock):
            if item.users == 0:
                datablock.remove(item)

def make_mat(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = 0.9
    bsdf.inputs['Metallic'].default_value = 0.0
    return mat

def addv(v, off):
    return (v[0] + off[0], v[1] + off[1], v[2] + off[2])

def runtime_bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return {'min': [min(xs), min(ys), min(zs)], 'max': [max(xs), max(ys), max(zs)], 'center': [(min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5, (min(zs) + max(zs)) * 0.5], 'size': [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]}

def face_tri_count(face):
    return max(0, len(face) - 2)

def make_mesh(asset_id, created, manifest_parts, name, verts, faces, mat, role, note, visible_face_indices, face_labels, extra=None):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata([P(*v) for v in verts], [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = asset_id
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = role
    obj['source_policy'] = SOURCE_POLICY
    obj['note'] = note
    obj['authored_lowpoly'] = True
    obj['decimated'] = False
    obj['source_topology_copied'] = False
    obj['runtime_bbox'] = json.dumps(runtime_bbox(verts))
    obj['visible_face_triangles'] = json.dumps({face_labels.get(i, f'face_{i}'): face_tri_count(faces[i]) for i in visible_face_indices})
    created.append(obj)
    tris = sum(face_tri_count(f) for f in faces)
    visible_truth = {face_labels.get(i, f'face_{i}'): face_tri_count(faces[i]) for i in visible_face_indices}
    part = {
        'object': name,
        'role': role,
        'note': note,
        'vertex_count': len(verts),
        'face_count': len(faces),
        'triangle_count': tris,
        'visible_face_triangles': visible_truth,
        'flat_visible_faces_all_two_tris': all(v == 2 for v in visible_truth.values()),
        'bbox_runtime': runtime_bbox(verts),
        'authored_lowpoly': True,
        'decimated': False,
        'source_topology_copied': False,
    }
    if extra:
        part.update(extra)
    manifest_parts.append(part)
    return obj

def prism(asset_id, created, manifest_parts, name, outer, inner, mat, role, note):
    verts = outer + inner
    n = len(outer)
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        faces.append((i, (i + 1) % n, n + (i + 1) % n, n + i))
    face_labels = {0: 'visible_outer_plate_face', 1: 'inner_back_face'}
    return make_mesh(asset_id, created, manifest_parts, name, verts, faces, mat, role, note, [0], face_labels)

def shell(asset_id, created, manifest_parts, name, sections, mat, role, note):
    verts = []
    count = len(sections[0]['points'])
    for sec in sections:
        for y, z in sec['points']:
            verts.append((sec['x'], y, z))
    faces = []
    for i in range(len(sections) - 1):
        a = i * count
        b = (i + 1) * count
        for j in range(count):
            faces.append((a + j, b + j, b + ((j + 1) % count), a + ((j + 1) % count)))
    faces.append(tuple(range(count - 1, -1, -1)))
    last = (len(sections) - 1) * count
    faces.append(tuple(last + j for j in range(count)))
    labels = {i: f'longitudinal_panel_{i}' for i in range((len(sections) - 1) * count)}
    return make_mesh(asset_id, created, manifest_parts, name, verts, faces, mat, role, note, list(labels.keys()), labels)

def oct_deck(asset_id, created, manifest_parts, name, center, half_x, half_z, radius, y, thickness, segments, mat, role, note):
    cx, cz = center
    verts = []
    outer_top = [(cx - half_x, y, cz - half_z), (cx + half_x, y, cz - half_z), (cx + half_x, y, cz + half_z), (cx - half_x, y, cz + half_z)]
    outer_bot = [(x, y - thickness, z) for x, _, z in outer_top]
    inner_top = []
    inner_bot = []
    for i in range(segments):
        a = math.tau * i / segments
        inner_top.append((cx + math.cos(a) * radius, y, cz + math.sin(a) * radius))
        inner_bot.append((cx + math.cos(a) * radius, y - thickness, cz + math.sin(a) * radius))
    verts = outer_top + inner_top + outer_bot + inner_bot
    faces = []
    labels = {}
    for i in range(segments):
        j = (i + 1) % segments
        side = int((i / segments) * 4) % 4
        o0 = side
        o1 = (side + 1) % 4
        faces.append((o0, o1, 4 + j, 4 + i))
        labels[len(faces) - 1] = f'top_deck_cut_segment_{i}'
    bot_outer = 4 + segments
    bot_inner = bot_outer + 4
    for i in range(segments):
        j = (i + 1) % segments
        side = int((i / segments) * 4) % 4
        o0 = bot_outer + side
        o1 = bot_outer + ((side + 1) % 4)
        faces.append((o1, o0, bot_inner + i, bot_inner + j))
    for i in range(4):
        faces.append((i, bot_outer + i, bot_outer + ((i + 1) % 4), (i + 1) % 4))
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((4 + i, 4 + j, bot_inner + j, bot_inner + i))
    return make_mesh(asset_id, created, manifest_parts, name, verts, faces, mat, role, note, list(labels.keys()), labels, {'flat_visible_faces_all_two_tris': 'not_applicable_cutout_faces'})

def ring(asset_id, created, manifest_parts, name, center, outer, inner, y, height, segments, mat, role, note):
    cx, cz = center
    verts = []
    for yy in (y + height / 2, y - height / 2):
        for r in (outer, inner):
            for i in range(segments):
                a = math.tau * i / segments
                verts.append((cx + math.cos(a) * r, yy, cz + math.sin(a) * r))
    top_o = 0
    top_i = segments
    bot_o = segments * 2
    bot_i = segments * 3
    faces = []
    labels = {}
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((top_o + i, top_o + j, top_i + j, top_i + i))
        labels[len(faces) - 1] = f'top_ring_segment_{i}'
        faces.append((bot_o + j, bot_o + i, bot_i + i, bot_i + j))
        faces.append((top_o + j, top_o + i, bot_o + i, bot_o + j))
        faces.append((top_i + i, top_i + j, bot_i + j, bot_i + i))
    return make_mesh(asset_id, created, manifest_parts, name, verts, faces, mat, role, note, list(labels.keys()), labels, {'essential_curved_opening': True})

def build_attempt(attempt):
    reset_scene()
    suffix = attempt['suffix']
    asset_id = f'{SERIES_ID}_{suffix}'
    model_dir = SCRATCH_ROOT / 'models' / asset_id
    blend_dir = SCRATCH_ROOT / 'source_blends' / asset_id
    render_dir = SCRATCH_ROOT / 'renders' / asset_id
    notes_dir = SCRATCH_ROOT / 'notes'
    for d in (model_dir, blend_dir, render_dir, notes_dir):
        d.mkdir(parents=True, exist_ok=True)
    clay = make_mat(asset_id + '_neutral_clay_topology_visible', (0.66, 0.69, 0.60, 1))
    dark = make_mat(asset_id + '_dark_socket_only', (0.03, 0.03, 0.025, 1))
    side = make_mat(asset_id + '_slightly_darker_side_planes', (0.53, 0.57, 0.49, 1))
    created = []
    parts = []
    z_gap = attempt['z_gap']
    spacing = attempt['spacing']
    side_taper = attempt['side_taper']
    fr = attempt['front_refine']
    rr = attempt['rear_refine']
    offsets = {
        'lower_tub': (0.00, 0.00, 0.00),
        'upper_glacis': (0.42, spacing * 1.35, 0.00),
        'front_cap': (1.18, -spacing * 0.85, 0.00),
        'engine_deck': (-0.95, spacing * 1.65, 0.00),
        'rear_bulkhead': (-1.48, -spacing * 0.68, 0.00),
        'left_side': (0.00, spacing * 0.18, -1.10 - z_gap),
        'right_side': (0.00, spacing * 0.18, 1.10 + z_gap),
        'left_sponson': (0.00, -spacing * 0.48, -1.08 - z_gap * 0.62),
        'right_sponson': (0.00, -spacing * 0.48, 1.08 + z_gap * 0.62),
        'left_front_wrap': (1.42, spacing * 0.50, -0.98 - z_gap * 0.45),
        'right_front_wrap': (1.42, spacing * 0.50, 0.98 + z_gap * 0.45),
        'left_rear_wrap': (-1.52, spacing * 0.48, -0.98 - z_gap * 0.45),
        'right_rear_wrap': (-1.52, spacing * 0.48, 0.98 + z_gap * 0.45),
        'turret_socket': (-0.12, spacing * 2.18, 0.0),
    }
    def O(role, verts):
        off = offsets[role]
        return [addv(v, off) for v in verts]
    tub_sections = []
    for x, widen, rise in [(-1.48, 0.00, 0.00), (-0.62, 0.06, 0.04), (0.42, 0.08, 0.05), (1.42, -0.04, -0.02)]:
        pts = [(-0.10, -0.55 - widen), (0.06, -0.75 - widen), (0.25 + rise, -0.86 - widen), (0.36 + rise, -0.78 - widen), (0.36 + rise, 0.78 + widen), (0.25 + rise, 0.86 + widen), (0.06, 0.75 + widen), (-0.10, 0.55 + widen)]
        off = offsets['lower_tub']
        tub_sections.append({'x': x + off[0], 'points': [(y + off[1], z + off[2]) for y, z in pts]})
    shell(asset_id, created, parts, f'{asset_id}_lower_tub_single_authored_shell', tub_sections, clay, 'lower_tub', 'one low-poly authored tub shell with eight-sided sections; no primitive boxes and no source topology')
    upper = [(0.00, 0.58, -0.86), (0.00, 0.58, 0.86), (1.42 + fr, 0.32, 0.94), (1.42 + fr, 0.32, -0.94)]
    prism(asset_id, created, parts, f'{asset_id}_upper_front_glacis_plate', O('upper_glacis', upper), O('upper_glacis', [(x, y - 0.055, z) for x, y, z in upper]), clay, 'upper_glacis', 'broad sloped glacis as one authored quad plate; visible face exports as two tris')
    cap = [(0.70, 0.22, -0.70), (0.70, 0.22, 0.70), (1.58 + fr, 0.08, 0.56), (1.58 + fr, 0.08, -0.56)]
    prism(asset_id, created, parts, f'{asset_id}_front_transmission_cap_plate', O('front_cap', cap), O('front_cap', [(x, y - 0.08, z) for x, y, z in cap]), clay, 'front_transmission_cap', 'single lower front transmission cap plate with two-tri visible face')
    rear = [(-1.58 - rr, 0.44, -0.78), (-1.58 - rr, 0.44, 0.78), (-1.58 - rr, 0.05, 0.58), (-1.58 - rr, 0.05, -0.58)]
    prism(asset_id, created, parts, f'{asset_id}_rear_bulkhead_plate', O('rear_bulkhead', rear), O('rear_bulkhead', [(x + 0.10, y - 0.02, z) for x, y, z in rear]), clay, 'rear_bulkhead', 'one rear armor bulkhead plate, not a pasted blocker')
    engine = [(-1.34, 0.46, -0.72), (-0.24, 0.68, -0.72), (-0.24, 0.68, 0.72), (-1.34, 0.46, 0.72)]
    prism(asset_id, created, parts, f'{asset_id}_engine_deck_plate', O('engine_deck', engine), O('engine_deck', [(x, y - 0.04, z) for x, y, z in engine]), clay, 'engine_deck', 'plain engine deck plate; no grille or molded detail')
    if attempt.get('quad_side'):
        left = [(-1.40, 0.16, -0.88), (-0.36, 0.58 + side_taper, -0.93), (1.34, 0.34, -0.88), (1.22, 0.09, -0.76)]
    else:
        left = [(-1.40, 0.18, -0.88), (-0.70, 0.54 + side_taper, -0.92), (0.34, 0.56 + side_taper, -0.94), (1.34, 0.36, -0.88), (1.24, 0.10, -0.76), (-1.34, 0.10, -0.76)]
    right = [(x, y, -z) for x, y, z in left]
    prism(asset_id, created, parts, f'{asset_id}_left_side_armor_plate', O('left_side', left), O('left_side', [(x, y, -0.72 - z_gap * 0.05) for x, y, z in left]), side, 'left_side_armor', 'left side armor as one authored polygonal plate; non-rectangular face uses only required silhouette vertices')
    prism(asset_id, created, parts, f'{asset_id}_right_side_armor_plate', O('right_side', right), O('right_side', [(x, y, 0.72 + z_gap * 0.05) for x, y, z in right]), side, 'right_side_armor', 'right side armor as one authored polygonal plate; mirrored without source topology')
    shelf = [(-1.36, 0.08, -0.98), (1.34, 0.08, -0.98), (1.28, 0.00, -0.76), (-1.30, 0.00, -0.76)]
    rshelf = [(x, y, -z) for x, y, z in shelf]
    prism(asset_id, created, parts, f'{asset_id}_left_sponson_shelf_plate', O('left_sponson', shelf), O('left_sponson', [(x, y - 0.07, z) for x, y, z in shelf]), side, 'left_sponson_shelf', 'track-socket shelf is a single authored quad face, not a slab cover')
    prism(asset_id, created, parts, f'{asset_id}_right_sponson_shelf_plate', O('right_sponson', rshelf), O('right_sponson', [(x, y - 0.07, z) for x, y, z in rshelf]), side, 'right_sponson_shelf', 'right track-socket shelf is a single authored quad face')
    lf = [(-0.06, 0.10, -0.76), (0.02, 0.36, -0.92), (0.18 + fr, 0.34, -0.82), (0.12 + fr, 0.08, -0.60)]
    rf = [(x, y, -z) for x, y, z in lf]
    lr = [(-0.10, 0.38, -0.82), (0.02, 0.12, -0.76), (0.10 + rr, 0.08, -0.56), (-0.04 + rr, 0.36, -0.70)]
    rrw = [(x, y, -z) for x, y, z in lr]
    prism(asset_id, created, parts, f'{asset_id}_left_front_wrap_plate', O('left_front_wrap', lf), O('left_front_wrap', [(x, y, z + 0.06) for x, y, z in lf]), clay, 'left_front_wrap', 'left front wrap owns the corner relationship between side and glacis')
    prism(asset_id, created, parts, f'{asset_id}_right_front_wrap_plate', O('right_front_wrap', rf), O('right_front_wrap', [(x, y, z - 0.06) for x, y, z in rf]), clay, 'right_front_wrap', 'right front wrap owns the corner relationship between side and glacis')
    prism(asset_id, created, parts, f'{asset_id}_left_rear_wrap_plate', O('left_rear_wrap', lr), O('left_rear_wrap', [(x, y, z + 0.06) for x, y, z in lr]), clay, 'left_rear_wrap', 'left rear wrap ties side armor to rear bulkhead')
    prism(asset_id, created, parts, f'{asset_id}_right_rear_wrap_plate', O('right_rear_wrap', rrw), O('right_rear_wrap', [(x, y, z - 0.06) for x, y, z in rrw]), clay, 'right_rear_wrap', 'right rear wrap ties side armor to rear bulkhead')
    if attempt['deck_cut']:
        oct_deck(asset_id, created, parts, f'{asset_id}_turret_socket_deck_cut_plate', (offsets['turret_socket'][0], offsets['turret_socket'][2]), 0.70, 0.64, 0.26, offsets['turret_socket'][1] + 0.58, 0.035, attempt['socket_segments'], clay, 'turret_socket_deck', 'low-poly deck panel with essential turret aperture; cutout faces are controlled, not source noise')
        if attempt.get('ring_lip', True):
            ring(asset_id, created, parts, f'{asset_id}_low_turret_ring_lip', (offsets['turret_socket'][0], offsets['turret_socket'][2]), 0.31, 0.26, offsets['turret_socket'][1] + 0.612, 0.024, attempt['socket_segments'], dark, 'turret_ring_lip', 'low-segment turret ring, the only deliberate curved feature in the plate kit')
    bpy.ops.object.light_add(type='AREA', location=(0, -5, 4.6))
    light = bpy.context.object
    light.name = asset_id + '_softbox'
    light.data.energy = 620
    light.data.size = 5.5
    bpy.ops.object.camera_add(location=P(3.2, 2.25, 2.55))
    front_cam = bpy.context.object
    front_cam.name = asset_id + '_front_review_camera'
    bpy.ops.object.camera_add(location=P(-3.25, 2.22, 2.45))
    rear_cam = bpy.context.object
    rear_cam.name = asset_id + '_rear_review_camera'
    def look_at(obj, target):
        direction = Vector(target) - obj.location
        obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    for cam in (front_cam, rear_cam):
        look_at(cam, Vector(P(0.0, 0.48, 0.0)))
        cam.data.lens = 54
    blend_path = blend_dir / f'{asset_id}.blend'
    glb_path = model_dir / f'{asset_id}.glb'
    manifest_path = model_dir / 'model_manifest.json'
    notes_path = notes_dir / f'{asset_id}.md'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in created:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = created[0]
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    engine_items = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
    if hasattr(bpy.context.scene, 'eevee'):
        bpy.context.scene.eevee.taa_render_samples = 32
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 840
    for cam, filename in [(front_cam, 'front_three_quarter.png'), (rear_cam, 'rear_three_quarter.png')]:
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(render_dir / filename)
        bpy.ops.render.render(write_still=True)
    total_tris = sum(p['triangle_count'] for p in parts)
    visible_flat_failures = []
    for p in parts:
        if p.get('essential_curved_opening') or p.get('flat_visible_faces_all_two_tris') == 'not_applicable_cutout_faces':
            continue
        if not p['flat_visible_faces_all_two_tris']:
            visible_flat_failures.append(p['object'])
    manifest = {
        'asset_id': asset_id,
        'series_id': SERIES_ID,
        'attempt': suffix,
        'attempt_label': attempt['label'],
        'scratch_mode': True,
        'artifact_type': 'scratch_authored_lowpoly_hard_surface_plate_kit',
        'revision': REVISION,
        'source_policy': SOURCE_POLICY,
        'configuration_policy': 'Exploded/reference kit layout only; not assembled into a tank pose.',
        'topology_policy': 'Authored mesh faces. No decimation. Broad rectangular visible plate faces are quads in Blender and two tris in GLB.',
        'scope': 'Hull/chassis large plates only. No treads, wheels, turret body, mantlet, barrel, coaxial MG, bolts, rivets, tools, material pass, or UV polish.',
        'outputs': {'blend': str(blend_path.relative_to(ROOT)), 'glb': str(glb_path.relative_to(ROOT)), 'front_render': str((render_dir / 'front_three_quarter.png').relative_to(ROOT)), 'rear_render': str((render_dir / 'rear_three_quarter.png').relative_to(ROOT))},
        'object_count': len(parts),
        'total_triangle_count': total_tris,
        'total_vertex_count': sum(p['vertex_count'] for p in parts),
        'flat_visible_face_failures': visible_flat_failures,
        'passes_topology_gate': total_tris <= 1500 and not visible_flat_failures and len(parts) >= 8 and len(parts) <= 14,
        'judgment': attempt['judgment'],
        'parts': parts,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    notes_path.write_text(f"""# {asset_id}\n\nScratch attempt {suffix}: {attempt['label']}\n\n- Source/reference topology copied: no.\n- Decimation used: no.\n- Configuration: exploded/reference kit layout, not assembled tank pose.\n- Total triangles: {total_tris}.\n- Object count: {len(parts)}.\n- Flat visible face failures: {visible_flat_failures or 'none'}.\n- Verdict: {attempt['judgment']}\n\nOutputs:\n\n- GLB: {glb_path.relative_to(ROOT)}\n- Manifest: {manifest_path.relative_to(ROOT)}\n- Front render: {(render_dir / 'front_three_quarter.png').relative_to(ROOT)}\n- Rear render: {(render_dir / 'rear_three_quarter.png').relative_to(ROOT)}\n""", encoding='utf8')
    return manifest

all_manifests = []
for attempt in ATTEMPTS:
    all_manifests.append(build_attempt(attempt))
summary_path = SCRATCH_ROOT / 'notes' / f'{SERIES_ID}_attempt_summary.md'
summary_path.write_text('# real_sherman_chassis_platekit_scratch attempt summary\n\n' + '\n'.join(f"- {m['asset_id']}: {m['total_triangle_count']} tris, {m['object_count']} objects, topology_gate={m['passes_topology_gate']}" for m in all_manifests) + '\n', encoding='utf8')
print(json.dumps({'series_id': SERIES_ID, 'attempts': [{'asset_id': m['asset_id'], 'tris': m['total_triangle_count'], 'objects': m['object_count'], 'topology_gate': m['passes_topology_gate']} for m in all_manifests]}, indent=2))
