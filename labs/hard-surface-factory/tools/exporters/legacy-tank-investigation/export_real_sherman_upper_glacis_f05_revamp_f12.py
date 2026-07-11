"""Scratch exporter for the first watertight upper-glacis recovery attempt.

Assumptions:
- f05/source geometry is visual reference only; open f05 topology must not be reused as final mesh.
- The turret socket must be represented as an owned cylindrical wall through a solid plate.
- Topology passing is necessary, but shape parity can still mark the result red.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
SOURCE_GLB = SCRATCH / 'models' / 'real_sherman_chassis_reference_kit_scratch_v1' / 'real_sherman_chassis_reference_kit_scratch_v1.glb'
ASSET_ID = 'real_sherman_upper_glacis_f05_revamp_scratch_f12'
REVISION = 'f12-watertight-solid-plate-cylinder-cut-separate-ring'
MODEL_DIR = SCRATCH / 'models' / ASSET_ID
BLEND_DIR = SCRATCH / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH / 'notes'
SOURCE_NEEDLE = 'source_component_0_upper_front_glacis'
DEPTH_W = 160
DEPTH_H = 112
SEGMENTS = 72
THICKNESS = 0.045
RING_HEIGHT = 0.020
RING_RADIAL_WIDTH = 0.030


def ensure_dirs():
    for d in (MODEL_DIR, BLEND_DIR, RENDER_DIR, NOTES_DIR):
        d.mkdir(parents=True, exist_ok=True)


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


def find_source_object():
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and SOURCE_NEEDLE in obj.name:
            return obj
    raise RuntimeError('upper glacis source object not found')


def world_mesh_data(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    mesh = eo.to_mesh()
    try:
        mw = obj.matrix_world.copy()
        verts = [mw @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
        return verts, polys
    finally:
        eo.to_mesh_clear()


def build_bvh_from_data(verts, polys):
    return BVHTree.FromPolygons(verts, polys, all_triangles=False)


def q(vals, t):
    vals = sorted(vals)
    return vals[int((len(vals) - 1) * t)]


def mean(points):
    acc = Vector((0, 0, 0))
    for p in points:
        acc += p
    return acc / max(1, len(points))


def angle_key(center, p):
    return math.atan2(p.y - center.y, p.x - center.x)


def angle_distance(a, b):
    return abs((a - b + math.pi) % math.tau - math.pi)


def z_at(bvh, x, y, fallback):
    loc, _normal, _face_index, _dist = bvh.ray_cast(Vector((x, y, fallback + 2.0)), Vector((0, 0, -1)), 5.0)
    return loc.z if loc is not None else fallback


def measure_source_features(source_obj):
    verts, polys = world_mesh_data(source_obj)
    bvh = build_bvh_from_data(verts, polys)
    z_vals = [p.z for p in verts]
    top_cut = q(z_vals, 0.40)
    top_points = [p for p in verts if p.z >= top_cut]
    center = mean(top_points)
    ring_points = []
    for p in top_points:
        r = math.sqrt((p.x - center.x) ** 2 + (p.y - center.y) ** 2)
        if 0.09 <= r <= 0.36 and p.z >= q(z_vals, 0.72):
            ring_points.append(p)
    if len(ring_points) < 30:
        ring_points = top_points
    ring_center = mean(ring_points)
    radii = sorted(math.sqrt((p.x - ring_center.x) ** 2 + (p.y - ring_center.y) ** 2) for p in ring_points)
    socket_radius = max(0.105, min(0.185, radii[int(len(radii) * 0.56)] if radii else 0.13))
    outer = []
    for i in range(SEGMENTS):
        a = math.tau * i / SEGMENTS
        candidates = []
        for p in top_points:
            d = angle_distance(angle_key(center, p), a)
            if d <= math.tau / SEGMENTS * 2.2:
                r = math.sqrt((p.x - center.x) ** 2 + (p.y - center.y) ** 2)
                candidates.append((r, p))
        if not candidates:
            p = max(top_points, key=lambda pp: math.sqrt((pp.x - center.x) ** 2 + (pp.y - center.y) ** 2) - angle_distance(angle_key(center, pp), a) * 0.18)
        else:
            p = max(candidates, key=lambda rp: rp[0])[1]
        rel = p - center
        out = center + rel * 0.965
        out.z = z_at(bvh, out.x, out.y, p.z)
        outer.append(out)
    min_outer_dist = min(math.sqrt((p.x - ring_center.x) ** 2 + (p.y - ring_center.y) ** 2) for p in outer)
    if min_outer_dist < socket_radius + RING_RADIAL_WIDTH + 0.035:
        ring_center = center
    hatch_center = Vector((ring_center.x + socket_radius * 1.20, ring_center.y + socket_radius * 0.95, ring_center.z))
    hatch_radius = socket_radius * 0.36
    return {
        'verts': verts,
        'polys': polys,
        'bvh': bvh,
        'center': center,
        'outer_loop': outer,
        'ring_center': ring_center,
        'socket_radius': socket_radius,
        'hatch_center': hatch_center,
        'hatch_radius': hatch_radius,
        'top_fallback_z': q(z_vals, 0.78),
    }


def add_uvs(obj):
    mesh = obj.data
    uv = mesh.uv_layers.new(name='uv_watertight_f12') if not mesh.uv_layers else mesh.uv_layers.active
    for poly in mesh.polygons:
        n = poly.normal
        for li in poly.loop_indices:
            co = mesh.vertices[mesh.loops[li].vertex_index].co
            if abs(n.z) >= abs(n.x) and abs(n.z) >= abs(n.y):
                uv.data[li].uv = (co.x * 3.0, co.y * 3.0)
            elif abs(n.x) >= abs(n.y):
                uv.data[li].uv = (co.y * 3.0, co.z * 8.0)
            else:
                uv.data[li].uv = (co.x * 3.0, co.z * 8.0)


def make_solid_top_plate(features, mats):
    bvh = features['bvh']
    center = features['ring_center']
    radius = features['socket_radius']
    outer = features['outer_loop']
    verts = []
    rings = {'outer_top': [], 'outer_bottom': [], 'inner_top': [], 'inner_bottom': []}
    for i in range(SEGMENTS):
        a = math.tau * i / SEGMENTS
        op = outer[i]
        top_z = op.z
        rings['outer_top'].append(len(verts)); verts.append((op.x, op.y, top_z))
        rings['outer_bottom'].append(len(verts)); verts.append((op.x, op.y, top_z - THICKNESS))
        ix = center.x + radius * math.cos(a)
        iy = center.y + radius * math.sin(a)
        iz = z_at(bvh, ix, iy, features['top_fallback_z']) + 0.001
        rings['inner_top'].append(len(verts)); verts.append((ix, iy, iz))
        rings['inner_bottom'].append(len(verts)); verts.append((ix, iy, iz - THICKNESS))
    faces = []
    tags = []
    def add(face, tag):
        faces.append(face); tags.append(tag)
    for i in range(SEGMENTS):
        j = (i + 1) % SEGMENTS
        add((rings['outer_top'][i], rings['outer_top'][j], rings['inner_top'][j], rings['inner_top'][i]), 'solid_top_armor_plate')
        add((rings['outer_bottom'][j], rings['outer_bottom'][i], rings['inner_bottom'][i], rings['inner_bottom'][j]), 'plate_bottom_closure')
        add((rings['outer_bottom'][i], rings['outer_bottom'][j], rings['outer_top'][j], rings['outer_top'][i]), 'outer_plate_wall')
        add((rings['inner_top'][i], rings['inner_top'][j], rings['inner_bottom'][j], rings['inner_bottom'][i]), 'cylindrical_socket_wall')
    mesh = bpy.data.meshes.new(ASSET_ID + '_solid_top_plate_mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    for m in mats:
        mesh.materials.append(m)
    for p, tag in zip(mesh.polygons, tags):
        p.material_index = 0 if tag != 'cylindrical_socket_wall' else 1
        p.use_smooth = tag == 'cylindrical_socket_wall'
    obj = bpy.data.objects.new(ASSET_ID + '_solid_top_plate_with_cylindrical_cut', mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['role'] = 'solid_top_plate_with_cylindrical_cut'
    obj['topology_contract'] = 'closed armor shell with top, bottom, outer wall, and owned cylindrical socket wall; not a plane and not an overlay cover.'
    add_uvs(obj)
    obj.modifiers.new('weighted_normals_solid_plate', 'WEIGHTED_NORMAL')
    return obj, {'face_tags': sorted(set(tags)), 'segments': SEGMENTS, 'thickness': THICKNESS, 'socket_radius': radius, 'ring_center': [center.x, center.y, center.z]}


def make_annular_ring(features, mats):
    bvh = features['bvh']
    center = features['ring_center']
    inner = features['socket_radius'] + 0.004
    outer = inner + RING_RADIAL_WIDTH
    verts = []
    idx = {'outer_low': [], 'outer_high': [], 'inner_high': [], 'inner_low': []}
    for i in range(SEGMENTS):
        a = math.tau * i / SEGMENTS
        for key, r, dz in (
            ('outer_low', outer, 0.003), ('outer_high', outer, RING_HEIGHT),
            ('inner_high', inner, RING_HEIGHT * 0.82), ('inner_low', inner, 0.003),
        ):
            x = center.x + r * math.cos(a)
            y = center.y + r * math.sin(a)
            z = z_at(bvh, x, y, features['top_fallback_z']) + dz
            idx[key].append(len(verts)); verts.append((x, y, z))
    faces = []
    tags = []
    def add(face, tag):
        faces.append(face); tags.append(tag)
    for i in range(SEGMENTS):
        j = (i + 1) % SEGMENTS
        add((idx['outer_high'][i], idx['outer_high'][j], idx['inner_high'][j], idx['inner_high'][i]), 'raised_ring_top')
        add((idx['outer_low'][j], idx['outer_low'][i], idx['outer_high'][i], idx['outer_high'][j]), 'raised_ring_outer_wall')
        add((idx['inner_low'][i], idx['inner_low'][j], idx['inner_high'][j], idx['inner_high'][i]), 'raised_ring_inner_wall')
        add((idx['outer_low'][i], idx['inner_low'][i], idx['inner_low'][j], idx['outer_low'][j]), 'raised_ring_contact_closure')
    mesh = bpy.data.meshes.new(ASSET_ID + '_separate_ring_mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    for m in mats:
        mesh.materials.append(m)
    for p in mesh.polygons:
        p.material_index = 2
        p.use_smooth = True
    obj = bpy.data.objects.new(ASSET_ID + '_separate_watertight_raised_ring', mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['role'] = 'separate_watertight_raised_ring'
    obj['topology_contract'] = 'closed separate ring seated over the cylindrical cut; not used to hide an open plate boundary.'
    add_uvs(obj)
    obj.modifiers.new('weighted_normals_separate_ring', 'WEIGHTED_NORMAL')
    return obj, {'face_tags': sorted(set(tags)), 'segments': SEGMENTS, 'inner_radius': inner, 'outer_radius': outer, 'height': RING_HEIGHT}


def make_hatch_cap(features, mats):
    bvh = features['bvh']
    center = features['hatch_center']
    r = features['hatch_radius']
    n = 32
    verts = []
    top = []
    bottom = []
    for i in range(n):
        a = math.tau * i / n
        x = center.x + r * 1.22 * math.cos(a)
        y = center.y + r * 0.72 * math.sin(a)
        z = z_at(bvh, x, y, features['top_fallback_z']) + 0.012
        top.append(len(verts)); verts.append((x, y, z))
        bottom.append(len(verts)); verts.append((x, y, z - 0.010))
    faces = [tuple(top), tuple(reversed(bottom))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((bottom[i], bottom[j], top[j], top[i]))
    mesh = bpy.data.meshes.new(ASSET_ID + '_separate_hatch_cap_mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    for m in mats:
        mesh.materials.append(m)
    for p in mesh.polygons:
        p.material_index = 3
        p.use_smooth = False
    obj = bpy.data.objects.new(ASSET_ID + '_separate_closed_hatch_cap', mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['role'] = 'separate_closed_hatch_cap'
    obj['topology_contract'] = 'simple closed hatch cap; cylinder/oval primitive, not arbitrary noisy seam vertices.'
    add_uvs(obj)
    obj.modifiers.new('weighted_normals_hatch_cap', 'WEIGHTED_NORMAL')
    return obj, {'segments': n, 'radius_x': r * 1.22, 'radius_y': r * 0.72, 'height': 0.010}


def topology_report(obj):
    mesh = obj.data
    mesh.update(calc_edges=True)
    edge_faces = defaultdict(int)
    for p in mesh.polygons:
        vs = list(p.vertices)
        for i, a in enumerate(vs):
            b = vs[(i + 1) % len(vs)]
            edge_faces[tuple(sorted((a, b)))] += 1
    return {
        'object': obj.name,
        'vertices': len(mesh.vertices),
        'polygons': len(mesh.polygons),
        'triangles': tri_count(mesh),
        'boundary_edges': sum(1 for c in edge_faces.values() if c == 1),
        'nonmanifold_edges': sum(1 for c in edge_faces.values() if c != 2),
        'uv_layers': [uv.name for uv in mesh.uv_layers],
    }


def aggregate_gate(reports):
    boundary = sum(r['boundary_edges'] for r in reports)
    nonmanifold = sum(r['nonmanifold_edges'] for r in reports)
    passed = boundary == 0 and nonmanifold == 0
    reasons = []
    if boundary:
        reasons.append(f'boundary_edges={boundary}')
    if nonmanifold:
        reasons.append(f'nonmanifold_edges={nonmanifold}')
    return {'topology_status': 'pass' if passed else 'red', 'topology_pass': bool(passed), 'boundary_edges_total': boundary, 'nonmanifold_edges_total': nonmanifold, 'failure_reasons': reasons}


def object_bvh(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    mesh = eo.to_mesh()
    try:
        verts = [obj.matrix_world @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
        return build_bvh_from_data(verts, polys), verts, polys
    finally:
        eo.to_mesh_clear()


def joined_bvh(objects):
    all_verts = []
    all_polys = []
    for obj in objects:
        _bvh, verts, polys = object_bvh(obj)
        offset = len(all_verts)
        all_verts.extend(verts)
        all_polys.extend(tuple(v + offset for v in poly) for poly in polys)
    return build_bvh_from_data(all_verts, all_polys), all_verts, all_polys


def camera_basis(points):
    center = mean(points)
    view_dir = Vector((0.08, 1.0, -0.12)).normalized()
    right = Vector((1, 0, 0))
    up = right.cross(view_dir).normalized()
    right = view_dir.cross(up).normalized()
    coords = [((p - center).dot(right), (p - center).dot(up)) for p in points]
    min_r = min(c[0] for c in coords); max_r = max(c[0] for c in coords)
    min_u = min(c[1] for c in coords); max_u = max(c[1] for c in coords)
    span_r = max_r - min_r; span_u = max_u - min_u
    margin = 0.14
    return {'center': center, 'view_dir': view_dir, 'right': right, 'up': up, 'min_r': min_r - span_r * margin, 'max_r': max_r + span_r * margin, 'min_u': min_u - span_u * margin, 'max_u': max_u + span_u * margin, 'origin_base': center - view_dir * 5.0}


def ray_for_uv(cam, ix, iy, w, h):
    r = cam['min_r'] + (cam['max_r'] - cam['min_r']) * (ix / w)
    u = cam['min_u'] + (cam['max_u'] - cam['min_u']) * (iy / h)
    origin = cam['origin_base'] + cam['right'] * r + cam['up'] * u
    return origin, cam['view_dir']


def sample_depth_image(bvh, cam, w, h):
    vals = []
    mask = []
    for y in range(h):
        for x in range(w):
            origin, direction = ray_for_uv(cam, x + 0.5, y + 0.5, w, h)
            loc, _normal, _face_index, dist = bvh.ray_cast(origin, direction, 20.0)
            vals.append(float(dist) if loc is not None else None)
            mask.append(loc is not None)
    return vals, mask


def save_gray_png(path, values, mask, w, h, lo=None, hi=None):
    present = [v for v, m in zip(values, mask) if m and v is not None] or [0.0]
    if lo is None:
        lo = min(present)
    if hi is None:
        hi = max(present)
    if abs(hi - lo) < 1e-8:
        hi = lo + 1.0
    img = bpy.data.images.new(path.stem, width=w, height=h, alpha=True, float_buffer=False)
    pix = [0.0] * (w * h * 4)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            j = i * 4
            if mask[i] and values[i] is not None:
                g = max(0.0, min(1.0, (values[i] - lo) / (hi - lo)))
                pix[j:j+4] = [g, g, g, 1.0]
            else:
                pix[j:j+4] = [0, 0, 0, 0]
    img.pixels.foreach_set(pix)
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def depth_compare(source_bvh, output_objects, cam):
    retopo_bvh, _verts, _polys = joined_bvh(output_objects)
    src_vals, src_mask = sample_depth_image(source_bvh, cam, DEPTH_W, DEPTH_H)
    ret_vals, ret_mask = sample_depth_image(retopo_bvh, cam, DEPTH_W, DEPTH_H)
    shared = [a and b for a, b in zip(src_mask, ret_mask)]
    union = [a or b for a, b in zip(src_mask, ret_mask)]
    errors = []
    err_vals = []
    for sv, rv, m in zip(src_vals, ret_vals, shared):
        if m:
            e = abs(sv - rv)
            errors.append(e)
            err_vals.append(e)
        else:
            err_vals.append(None)
    errors_sorted = sorted(errors)
    def pct(qv):
        if not errors_sorted:
            return None
        return errors_sorted[min(len(errors_sorted) - 1, int(qv * (len(errors_sorted) - 1)))]
    report = {
        'depth_resolution': [DEPTH_W, DEPTH_H],
        'shared_pixels': int(sum(shared)),
        'source_pixels': int(sum(src_mask)),
        'retopo_pixels': int(sum(ret_mask)),
        'silhouette_iou': float(sum(shared) / max(1, sum(union))),
        'mean_abs_depth_error': float(sum(errors) / max(1, len(errors))),
        'p50_abs_depth_error': pct(0.50),
        'p95_abs_depth_error': pct(0.95),
        'max_abs_depth_error': max(errors) if errors else None,
    }
    present = [v for v, m in zip(src_vals, src_mask) if m and v is not None]
    save_gray_png(RENDER_DIR / 'source_depth.png', src_vals, src_mask, DEPTH_W, DEPTH_H, min(present), max(present))
    save_gray_png(RENDER_DIR / 'retopo_depth.png', ret_vals, ret_mask, DEPTH_W, DEPTH_H, min(present), max(present))
    save_gray_png(RENDER_DIR / 'depth_abs_error.png', err_vals, shared, DEPTH_W, DEPTH_H, 0.0, max(errors) if errors else 1.0)
    (MODEL_DIR / 'depth_error_report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def add_camera_from_basis(cam_basis):
    center = cam_basis['center']
    view_dir = cam_basis['view_dir']
    bpy.ops.object.camera_add(location=center - view_dir * 3.2)
    cam = bpy.context.object
    cam.name = ASSET_ID + '_depth_parity_camera'
    look_at(cam, center)
    cam.data.type = 'ORTHO'
    span_r = cam_basis['max_r'] - cam_basis['min_r']
    span_u = cam_basis['max_u'] - cam_basis['min_u']
    cam.data.ortho_scale = max(span_u, span_r * 0.68)
    return cam


def add_close_camera(features):
    c = features['ring_center']
    bpy.ops.object.camera_add(location=(c.x + 0.10, c.y - 1.05, c.z + 0.54))
    cam = bpy.context.object
    cam.name = ASSET_ID + '_hatch_socket_close_camera'
    look_at(cam, (c.x, c.y, c.z - 0.01))
    cam.data.lens = 70
    return cam


def render_shaded(source_obj, output_objects, overview_cam, close_cam):
    bpy.ops.object.light_add(type='AREA', location=overview_cam.location + Vector((0, -1.0, 2.2)))
    light = bpy.context.object
    light.name = ASSET_ID + '_softbox'
    light.data.energy = 760
    light.data.size = 4.0
    engine_items = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
    if hasattr(bpy.context.scene, 'eevee'):
        bpy.context.scene.eevee.taa_render_samples = 48
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 840
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    render_jobs = [
        (overview_cam, [source_obj], 'source_shaded_same_angle.png'),
        (overview_cam, output_objects, 'retopo_shaded_same_angle.png'),
        (close_cam, output_objects, 'hatch_deck_close.png'),
    ]
    for cam, visible, fn in render_jobs:
        for m in meshes:
            m.hide_render = m not in visible
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(RENDER_DIR / fn)
        bpy.ops.render.render(write_still=True)
    for m in meshes:
        m.hide_render = m not in output_objects


def write_provenance(features, objects):
    rows = []
    source_bvh = features['bvh']
    for obj in objects:
        for i, v in enumerate(obj.data.vertices):
            wp = obj.matrix_world @ v.co
            loc, _normal, face_index, dist = source_bvh.find_nearest(wp, 1.0)
            rows.append({
                'output_object': obj.name,
                'output_vertex': i,
                'support': {
                    'kind': 'nearest_source_surface_from_reference_upper_glacis',
                    'source_object': SOURCE_NEEDLE,
                    'source_face': int(face_index) if face_index is not None else -1,
                    'distance': float(dist) if dist is not None else None,
                },
                'world': [float(wp.x), float(wp.y), float(wp.z)],
            })
    path = MODEL_DIR / 'retopo_vertex_provenance.json'
    path.write_text(json.dumps({'asset_id': ASSET_ID, 'vertices': rows}, indent=2) + '\n')
    return path, rows


def main():
    ensure_dirs()
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_obj = find_source_object()
    source_obj.name = ASSET_ID + '_hidden_source_upper_glacis'
    source_mat = make_mat(ASSET_ID + '_source_gray', (0.66, 0.67, 0.62, 1), 0.9)
    armor_mat = make_mat('armor_plate', (0.58, 0.61, 0.54, 1), 0.92)
    socket_mat = make_mat('cylindrical_socket_wall', (0.48, 0.50, 0.46, 1), 0.94)
    ring_mat = make_mat('separate_ring_armor', (0.62, 0.64, 0.56, 1), 0.90)
    hatch_mat = make_mat('closed_hatch_cap', (0.55, 0.58, 0.51, 1), 0.92)
    source_obj.data.materials.clear()
    source_obj.data.materials.append(source_mat)
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj != source_obj:
            obj.hide_viewport = True
            obj.hide_render = True
    features = measure_source_features(source_obj)
    mats = [armor_mat, socket_mat, ring_mat, hatch_mat]
    plate, plate_primitive = make_solid_top_plate(features, mats)
    ring, ring_primitive = make_annular_ring(features, mats)
    hatch, hatch_primitive = make_hatch_cap(features, mats)
    output_objects = [plate, ring, hatch]
    topology_reports = [topology_report(o) for o in output_objects]
    topology_gate = aggregate_gate(topology_reports)
    cam_basis = camera_basis(features['verts'])
    depth_report = depth_compare(features['bvh'], output_objects, cam_basis)
    overview_cam = add_camera_from_basis(cam_basis)
    close_cam = add_close_camera(features)
    render_shaded(source_obj, output_objects, overview_cam, close_cam)
    blend_path = BLEND_DIR / (ASSET_ID + '.blend')
    glb_path = MODEL_DIR / (ASSET_ID + '.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in output_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = output_objects[0]
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    provenance_path, provenance = write_provenance(features, output_objects)
    primitive_path = MODEL_DIR / 'solid_primitives.json'
    primitive_path.write_text(json.dumps({
        'asset_id': ASSET_ID,
        'plate': plate_primitive,
        'ring': ring_primitive,
        'hatch': hatch_primitive,
        'source_feature_policy': 'outer loop and socket/ring placement are measured from source upper-glacis mesh vertices/surface; final topology is newly built closed solids, not copied/open f05/f11 topology.',
    }, indent=2) + '\n')
    total_stats = {
        'vertices': sum(r['vertices'] for r in topology_reports),
        'polygons': sum(r['polygons'] for r in topology_reports),
        'triangles': sum(r['triangles'] for r in topology_reports),
    }
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'scratch_watertight_upper_glacis_solid_plate_socket_ring',
        'revision': REVISION,
        'candidate': False,
        'candidate_reason': 'false until topology passes and visual diagnostics show the broad f05/source relationship is strong enough for another review pass',
        'topology_status': topology_gate['topology_status'],
        'source_glb': str(SOURCE_GLB.relative_to(ROOT)),
        'source_component': SOURCE_NEEDLE,
        'authoring_policy': 'New closed hard-surface solids measured from source/f05 reference. f05/f11 topology is not used as final mesh base. Top plate is solid, aperture has cylindrical wall ownership, and raised ring is a separate closed mesh.',
        'current_prompt_contract': {
            'current_user_command': 'Implement the full watertight-first recovery plan, including the corrected hatch workflow.',
            'forbidden_stale_premise': 'Calling a nonmanifold overlay revamp a candidate or continuing to patch f11 cover-up geometry.',
            'intended_mutation': 'Create one new scratch mesh artifact with watertight solid plate, cylindrical cut, separate closed ring, objective topology gate, notes, and viewer handoff.',
            'why_this_satisfies_command': 'It changes the process gate and geometry architecture rather than tweaking the rejected overlay workflow.',
        },
        'statistics': total_stats,
        'topology_gate': topology_gate,
        'shape_review_status': 'red_depth_parity_weak' if depth_report['silhouette_iou'] < 0.90 else 'diagnostic_promising',
        'topology_reports': topology_reports,
        'material_slots': [m.name for m in mats],
        'solid_primitives': str(primitive_path.relative_to(ROOT)),
        'provenance': {'path': str(provenance_path.relative_to(ROOT)), 'output_vertices': len(provenance)},
        'depth_parity': {'path': str((MODEL_DIR / 'depth_error_report.json').relative_to(ROOT)), **depth_report},
        'outputs': {
            'blend': str(blend_path.relative_to(ROOT)),
            'glb': str(glb_path.relative_to(ROOT)),
            'source_shaded_same_angle': str((RENDER_DIR / 'source_shaded_same_angle.png').relative_to(ROOT)),
            'retopo_shaded_same_angle': str((RENDER_DIR / 'retopo_shaded_same_angle.png').relative_to(ROOT)),
            'hatch_deck_close': str((RENDER_DIR / 'hatch_deck_close.png').relative_to(ROOT)),
            'source_depth': str((RENDER_DIR / 'source_depth.png').relative_to(ROOT)),
            'retopo_depth': str((RENDER_DIR / 'retopo_depth.png').relative_to(ROOT)),
            'depth_abs_error': str((RENDER_DIR / 'depth_abs_error.png').relative_to(ROOT)),
        },
        'review_language_gate': 'If topology_status is red, do not call this almost-there, selected, textureable, promoted, or viewer-ready. If topology_status passes, visual review is still diagnostic in scratch mode.',
    }
    (MODEL_DIR / 'model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    note_status = 'topology PASS but NOT a visual candidate' if topology_gate['topology_pass'] else 'RED topology failure'
    note = "# " + ASSET_ID + "\n\n" + note_status + ". Scratch diagnostic only; not production/cloud accepted.\n\n"
    note += "## Process Fix\n\nThis pass stops the f10/f11 overlay premise. The final exported geometry is newly built from closed solids measured against the source upper-glacis reference: a solid top armor shell, an owned cylindrical socket wall, a separate closed raised ring, and a separate closed hatch cap.\n\n"
    note += "## Topology Gate\n\n"
    note += "- Total boundary edges: " + str(topology_gate['boundary_edges_total']) + "\n"
    note += "- Total nonmanifold edges: " + str(topology_gate['nonmanifold_edges_total']) + "\n"
    note += "- Candidate flag: " + str(False) + "\n\n"
    note += "## Stats\n\n"
    note += "- Vertices: " + str(total_stats['vertices']) + "\n"
    note += "- Polygons: " + str(total_stats['polygons']) + "\n"
    note += "- Triangles: " + str(total_stats['triangles']) + "\n\n"
    note += "## Depth Diagnostic\n\n"
    note += "- Silhouette IoU: " + str(depth_report['silhouette_iou']) + "\n"
    note += "- Mean abs depth error: " + str(depth_report['mean_abs_depth_error']) + "\n"
    note += "- p95 abs depth error: " + str(depth_report['p95_abs_depth_error']) + "\n\n"
    note += "## Review Note\n\nTopology passing only earns the right to inspect the shape. It is not visual acceptance. If the shape reads too primitive, the next pass must add source-supported manufactured plate loops while preserving the same watertight architecture.\n"
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    print(json.dumps({'asset_id': ASSET_ID, 'topology_gate': topology_gate,
        'shape_review_status': 'red_depth_parity_weak' if depth_report['silhouette_iou'] < 0.90 else 'diagnostic_promising', 'stats': total_stats, 'depth_report': depth_report, 'glb': str(glb_path)}, indent=2))


main()
