
import json
import math
from pathlib import Path
from mathutils import Vector
import bpy

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
SOURCE_GLB = SCRATCH / 'models' / 'real_sherman_chassis_reference_kit_scratch_v1' / 'real_sherman_chassis_reference_kit_scratch_v1.glb'
REF_IMAGE = SCRATCH / 'renders' / 'real_sherman_chassis_reference_kit_scratch_v1' / 'front_reference_config.png'
ASSET_ID = 'real_sherman_chassis_retopo_only_referencekit_scratch_e01'
REVISION = 'e01-source-vertex-retopo-only-no-bbox-authoring'
MODEL_DIR = SCRATCH / 'models' / ASSET_ID
BLEND_DIR = SCRATCH / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH / 'notes'
PROV_PATH = MODEL_DIR / 'retopo_vertex_provenance.json'

ROLE_MATCHES = [
    ('source_component_0_upper_front_glacis_assembly', 'source_component_0_upper_front_glacis'),
    ('source_component_1_lower_hull_floor_tub', 'source_component_1_lower_hull_floor_tub'),
    ('source_component_2_engine_deck_assembly', 'source_component_2_engine_deck'),
    ('source_component_3_rear_plate_assembly', 'source_component_3_rear_plate'),
    ('source_component_4_left_side_assembly', 'source_component_4_left_side'),
    ('source_component_5_right_side_assembly', 'source_component_5_right_side'),
    ('source_component_6_remaining_reference_plate', 'source_component_6_remaining_reference'),
]

PROFILE = {
    'source_component_0_upper_front_glacis_assembly': {'rings': 4, 'bins': 24, 'axis': 2},
    'source_component_1_lower_hull_floor_tub': {'rings': 4, 'bins': 22, 'axis': 2},
    'source_component_2_engine_deck_assembly': {'rings': 4, 'bins': 22, 'axis': 2},
    'source_component_3_rear_plate_assembly': {'rings': 4, 'bins': 20, 'axis': 0},
    'source_component_4_left_side_assembly': {'rings': 4, 'bins': 20, 'axis': 1},
    'source_component_5_right_side_assembly': {'rings': 4, 'bins': 20, 'axis': 0},
    'source_component_6_remaining_reference_plate': {'rings': 3, 'bins': 18, 'axis': 1},
}


def reset_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def make_mat(name, color, rough=0.9):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = rough
    return mat


def tri_count(mesh):
    return sum(max(0, len(p.vertices) - 2) for p in mesh.polygons)


def object_vertices_world(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    mesh = eo.to_mesh()
    out = []
    try:
        mw = obj.matrix_world.copy()
        for v in mesh.vertices:
            out.append((v.index, mw @ v.co))
    finally:
        eo.to_mesh_clear()
    return out


def mean_point(points):
    acc = Vector((0, 0, 0))
    for _, p in points:
        acc += p
    return acc / max(1, len(points))


def nearest_source_index(point, points):
    best_i = -1
    best_d = 10**9
    for idx, p in points:
        d = (point - p).length_squared
        if d < best_d:
            best_d = d
            best_i = idx
    return best_i, math.sqrt(best_d)


def pick_directional_sample(points, center, axis, ring_idx, ring_count, bin_idx, bin_count, inner=False):
    axes = [0, 1, 2]
    axes.remove(axis)
    a0, a1 = axes
    angle = math.tau * (bin_idx / bin_count)
    target = Vector((math.cos(angle), math.sin(angle)))
    candidates = []
    for src_i, p in points:
        rel = p - center
        planar = Vector((rel[a0], rel[a1]))
        plen = planar.length
        if plen <= 1e-8:
            continue
        unit = planar / plen
        score = unit.dot(target)
        if score < math.cos(math.pi / bin_count * 1.6):
            continue
        candidates.append((p[axis], plen, score, src_i, p))
    if not candidates:
        for src_i, p in points:
            rel = p - center
            planar = Vector((rel[a0], rel[a1]))
            plen = planar.length
            if plen <= 1e-8:
                continue
            unit = planar / plen
            candidates.append((p[axis], plen, unit.dot(target), src_i, p))
    candidates.sort(key=lambda item: item[0])
    q = ring_idx / max(1, ring_count - 1)
    ranked = candidates[max(0, min(len(candidates)-1, int(round(q * (len(candidates)-1))))):]
    if not ranked:
        ranked = candidates
    if inner:
        ranked.sort(key=lambda item: (item[1], -item[2]))
    else:
        ranked.sort(key=lambda item: (item[1], item[2]), reverse=True)
    return ranked[0][3], ranked[0][4]


def build_shell_from_source(role, src_obj, material, provenance, created):
    cfg = PROFILE[role]
    points = object_vertices_world(src_obj)
    center = mean_point(points)
    rings = cfg['rings']
    bins = cfg['bins']
    axis = cfg['axis']
    verts = []
    src_indices = []
    for r in range(rings):
        for b in range(bins):
            src_i, p = pick_directional_sample(points, center, axis, r, rings, b, bins, False)
            verts.append(tuple(p))
            src_indices.append(src_i)
    faces = []
    def vi(r, b):
        return r * bins + (b % bins)
    for r in range(rings - 1):
        for b in range(bins):
            faces.append((vi(r, b), vi(r, b+1), vi(r+1, b+1), vi(r+1, b)))
    faces.append(tuple(reversed([vi(0, b) for b in range(bins)])))
    faces.append(tuple(vi(rings-1, b) for b in range(bins)))
    if role == 'source_component_0_upper_front_glacis_assembly':
        inner_start = len(verts)
        for b in range(bins):
            src_i, p = pick_directional_sample(points, center, axis, rings - 1, rings, b, bins, True)
            verts.append(tuple(p))
            src_indices.append(src_i)
        top_start = (rings - 1) * bins
        for b in range(bins):
            faces.append((top_start + b, top_start + ((b+1) % bins), inner_start + ((b+1) % bins), inner_start + b))
    mesh = bpy.data.meshes.new(ASSET_ID + '_' + role + '_mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(material)
    for poly in mesh.polygons:
        poly.use_smooth = False
    obj = bpy.data.objects.new(ASSET_ID + '_' + role, mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = role
    obj['source_object'] = src_obj.name
    obj['primary_kit_piece'] = True
    obj['retopo_only'] = True
    obj['authoring_policy'] = 'Output vertices are selected from imported source mesh vertices. No envelope placement, no generated panel construction, no decimation, no source topology copy.'
    obj.modifiers.new('weighted_normals_for_retopo_planes', 'WEIGHTED_NORMAL')
    created.append(obj)
    for out_i, src_i in enumerate(src_indices):
        co = Vector(verts[out_i])
        _, dist = nearest_source_index(co, points)
        provenance.append({'output_object': obj.name, 'output_vertex': out_i, 'source_object': src_obj.name, 'source_vertex': int(src_i), 'distance_to_source_vertex': dist, 'world': [float(co.x), float(co.y), float(co.z)]})
    return obj


def add_reference_sheet(created):
    if not REF_IMAGE.exists():
        return
    img = bpy.data.images.load(str(REF_IMAGE))
    mat = bpy.data.materials.new(ASSET_ID + '_reference_sheet_emissive')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage'); tex.image = img
    em = nodes.new('ShaderNodeEmission'); em.inputs['Strength'].default_value = 0.75
    out = nodes.new('ShaderNodeOutputMaterial')
    mat.node_tree.links.new(tex.outputs['Color'], em.inputs['Color'])
    mat.node_tree.links.new(em.outputs['Emission'], out.inputs['Surface'])
    verts = [(-1.62, 1.42, -0.82), (1.62, 1.42, -0.82), (1.62, 1.42, 0.90), (-1.62, 1.42, 0.90)]
    mesh = bpy.data.meshes.new(ASSET_ID + '_reference_sheet_mesh')
    mesh.from_pydata(verts, [], [(0,1,2,3)])
    mesh.update(calc_edges=True)
    uv = mesh.uv_layers.new(name='reference_sheet_uv')
    for loop, co in zip(mesh.polygons[0].loop_indices, [(0,0),(1,0),(1,1),(0,1)]):
        uv.data[loop].uv = co
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(ASSET_ID + '_reference_sheet_background', mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['role'] = 'visible_reference_sheet_background'
    obj.visible_shadow = False
    created.append(obj)


def find_source_objects():
    out = {}
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    for role, needle in ROLE_MATCHES:
        match = None
        for o in meshes:
            if needle in o.name:
                match = o
                break
        if match is None:
            raise RuntimeError('missing source object for ' + role)
        out[role] = match
    return out


def evaluated_counts(obj, depsgraph):
    eo = obj.evaluated_get(depsgraph)
    mesh = eo.to_mesh()
    try:
        return {'triangles': tri_count(mesh), 'polygons': len(mesh.polygons), 'vertices': len(mesh.vertices)}
    finally:
        eo.to_mesh_clear()


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def build():
    for d in (MODEL_DIR, BLEND_DIR, RENDER_DIR, NOTES_DIR):
        d.mkdir(parents=True, exist_ok=True)
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_objects = find_source_objects()
    source_collection = bpy.data.collections.new(ASSET_ID + '_hidden_source_reference')
    bpy.context.scene.collection.children.link(source_collection)
    for o in source_objects.values():
        for c in list(o.users_collection):
            c.objects.unlink(o)
        source_collection.objects.link(o)
        o.hide_viewport = True
        o.hide_render = True
    material = make_mat(ASSET_ID + '_source_sampled_clay', (0.62, 0.64, 0.56, 1), 0.93)
    provenance = []
    created = []
    for role, _needle in ROLE_MATCHES:
        build_shell_from_source(role, source_objects[role], material, provenance, created)
    add_reference_sheet(created)
    bpy.ops.object.light_add(type='AREA', location=(0, -4.6, 3.0))
    light = bpy.context.object
    light.name = ASSET_ID + '_softbox'
    light.data.energy = 760
    light.data.size = 4.4
    bpy.ops.object.camera_add(location=(0, -3.75, 0.78))
    front = bpy.context.object; front.name = ASSET_ID + '_front_reference_camera'; look_at(front, (0,0,0.02)); front.data.lens = 34
    bpy.ops.object.camera_add(location=(0.12, -2.35, 0.55))
    close = bpy.context.object; close.name = ASSET_ID + '_hatch_deck_close_camera'; look_at(close, (0.12,0.18,0.16)); close.data.lens = 55
    bpy.ops.object.camera_add(location=(0, 3.30, 0.74))
    rear = bpy.context.object; rear.name = ASSET_ID + '_rear_oblique_camera'; look_at(rear, (0,0,0.02)); rear.data.lens = 38
    deps = bpy.context.evaluated_depsgraph_get()
    manifest_parts = []
    for o in created:
        if o.type != 'MESH':
            continue
        c = evaluated_counts(o, deps)
        role = o.get('role', '')
        manifest_parts.append({'object': o.name, 'role': role, 'source_object': o.get('source_object', ''), 'primary_kit_piece': bool(o.get('primary_kit_piece', False)), 'retopo_only': bool(o.get('retopo_only', False)), **c})
    hand = [p for p in manifest_parts if not p['role'].startswith('visible_reference_sheet')]
    primary = [p for p in hand if p['primary_kit_piece']]
    stats_all = {k: sum(p[k] for p in hand) for k in ('triangles','polygons','vertices')}
    stats_primary = {k: sum(p[k] for p in primary) for k in ('triangles','polygons','vertices')}
    max_distance = max((p['distance_to_source_vertex'] for p in provenance), default=0)
    blend_path = BLEND_DIR / (ASSET_ID + '.blend')
    glb_path = MODEL_DIR / (ASSET_ID + '.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT')
    for o in created:
        o.select_set(True)
    bpy.context.view_layer.objects.active = created[0]
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    engine_items = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
    if hasattr(bpy.context.scene, 'eevee'):
        bpy.context.scene.eevee.taa_render_samples = 48
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 840
    for cam, name in ((front, 'front_with_reference_sheet.png'), (close, 'hatch_deck_close.png'), (rear, 'rear_oblique.png')):
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(RENDER_DIR / name)
        bpy.ops.render.render(write_still=True)
    PROV_PATH.write_text(json.dumps({'asset_id': ASSET_ID, 'revision': REVISION, 'vertices': provenance}, indent=2) + '\n')
    manifest = {'asset_id': ASSET_ID, 'scratch_mode': True, 'artifact_type': 'scratch_retopo_only_reference_kit', 'revision': REVISION, 'source_glb': str(SOURCE_GLB.relative_to(ROOT)), 'authoring_policy': 'Retopo-only from imported source mesh vertices. No envelope placement, generated panel construction, decimation, shrinkwrap, or direct source topology copy.', 'forbidden_authoring_patterns': ['legacy envelope mapping helper', 'envelope minmax interpolation', 'unit component coordinate authoring', 'generated panel construction', 'decimation', 'shrinkwrap', 'autoretopo wrapper'], 'statistics_all_retopo_mesh_excluding_reference_sheet': stats_all, 'statistics_primary_kit_pieces': stats_primary, 'primary_kit_piece_count': len(primary), 'all_hand_mesh_object_count': len(hand), 'provenance': {'path': str(PROV_PATH.relative_to(ROOT)), 'output_vertices': len(provenance), 'max_distance_to_source_vertex': max_distance, 'policy': 'Every output retopo vertex is an actual sampled source mesh vertex from the imported reference kit.'}, 'outputs': {'blend': str(blend_path.relative_to(ROOT)), 'glb': str(glb_path.relative_to(ROOT)), 'front_with_reference_sheet': str((RENDER_DIR/'front_with_reference_sheet.png').relative_to(ROOT)), 'hatch_deck_close': str((RENDER_DIR/'hatch_deck_close.png').relative_to(ROOT)), 'rear_oblique': str((RENDER_DIR/'rear_oblique.png').relative_to(ROOT))}, 'parts': manifest_parts}
    (MODEL_DIR / 'model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    note = '# ' + ASSET_ID + '\n\nRetopo-only scratch pass.\n\n- Source: imported reference kit GLB.\n- Authoring rule: every output vertex is selected from source mesh vertices.\n- Forbidden: envelope placement, legacy mapping helpers, generated panel construction, decimation, shrinkwrap, autoretopo wrapper.\n- All retopo mesh excluding reference sheet: ' + str(stats_all) + '\n- Primary kit pieces: ' + str(stats_primary) + '\n- Provenance vertices: ' + str(len(provenance)) + '; max distance to source vertex: ' + str(max_distance) + '\n- Scratch diagnostic only; not production/cloud accepted.\n'
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    print(json.dumps({'asset_id': ASSET_ID, 'stats_all': stats_all, 'stats_primary': stats_primary, 'provenance_vertices': len(provenance), 'max_distance_to_source_vertex': max_distance, 'glb': str(glb_path)}, indent=2))

build()
