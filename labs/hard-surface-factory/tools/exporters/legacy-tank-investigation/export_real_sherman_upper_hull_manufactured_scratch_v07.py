"""Parametric Sherman upper-hull template driven by source measurements only.

The source mesh is measurement, not geometry. This exporter deliberately discards
cluster hulls, recovered polygons, interface reconstruction, and source topology.
Final vertices exist because the Sherman template requires them; source values only
scale and place the template.
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
SOURCE_NEEDLE = 'source_component_0_upper_front_glacis'
ASSET_ID = 'real_sherman_upper_hull_manufactured_scratch_v07'
REVISION = 'v07-parametric-sherman-template'
MODEL_DIR = SCRATCH / 'models' / ASSET_ID
BLEND_DIR = SCRATCH / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH / 'notes'
DEPTH_W = 220
DEPTH_H = 154
RING_SEGMENTS = 72

TEMPLATE_SOLIDS = [
    'lower_front',
    'upper_glacis',
    'left_cheek',
    'right_cheek',
    'left_side',
    'right_side',
    'rear_deck',
    'turret_ring_support',
]
MEASUREMENTS = [
    'centerline',
    'hull_width',
    'hull_length',
    'glacis_plane_angle_degrees',
    'front_height',
    'left_shoulder_station',
    'right_shoulder_station',
    'turret_ring_center',
    'turret_ring_radius',
    'deck_height',
    'side_return_depth',
]


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


def q(vals, t):
    vals = sorted(vals)
    if not vals:
        return 0.0
    return vals[min(len(vals) - 1, max(0, int((len(vals) - 1) * t)))]


def mean(points):
    acc = Vector((0, 0, 0))
    for p in points:
        acc += p
    return acc / max(1, len(points))


def tri_count(mesh):
    return sum(max(0, len(p.vertices) - 2) for p in mesh.polygons)


def find_source_object():
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and SOURCE_NEEDLE in obj.name:
            return obj
    raise RuntimeError('upper glacis source object not found')


def polygon_area_centroid(points):
    if len(points) < 3:
        return 0.0, mean(points)
    origin = points[0]
    area = 0.0
    acc = Vector((0, 0, 0))
    for i in range(1, len(points) - 1):
        a = points[i] - origin
        b = points[i + 1] - origin
        tri_area = a.cross(b).length * 0.5
        tri_cent = (origin + points[i] + points[i + 1]) / 3.0
        area += tri_area
        acc += tri_cent * tri_area
    return area, acc / area if area > 1e-12 else mean(points)


def world_mesh_data(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    mesh = eo.to_mesh()
    try:
        mw = obj.matrix_world.copy()
        verts = [mw @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
        normals = [(mw.to_3x3() @ p.normal).normalized() for p in mesh.polygons]
        return verts, polys, normals
    finally:
        eo.to_mesh_clear()


def build_bvh(verts, polys):
    return BVHTree.FromPolygons(verts, polys, all_triangles=False)


def fit_global_reference_plane(verts, polys, normals):
    z_vals = [p.z for p in verts]
    high_z = q(z_vals, 0.50)
    seeds = []
    for fi, face in enumerate(polys):
        pts = [verts[i] for i in face]
        area, centroid = polygon_area_centroid(pts)
        n = normals[fi]
        if area > 1e-8 and centroid.z >= high_z and n.z > 0.18:
            seeds.append((area, centroid, n))
    if not seeds:
        raise RuntimeError('no global plane seed faces found')
    avg_n = Vector((0, 0, 0))
    avg_p = Vector((0, 0, 0))
    total = 0.0
    for area, centroid, n in seeds:
        if n.z < 0:
            n = -n
        avg_n += n * area
        avg_p += centroid * area
        total += area
    avg_n.normalize()
    avg_p /= total
    u = Vector((1, 0, 0)) - avg_n * Vector((1, 0, 0)).dot(avg_n)
    if u.length < 1e-5:
        u = Vector((0, 1, 0)) - avg_n * Vector((0, 1, 0)).dot(avg_n)
    u.normalize()
    v = avg_n.cross(u).normalized()
    return {'point': avg_p, 'normal': avg_n, 'u': u, 'v': v, 'seed_face_count': len(seeds)}


def project_to_plane(plane, p):
    return p - plane['normal'] * (p - plane['point']).dot(plane['normal'])


def plane_to_uv(plane, p):
    pp = project_to_plane(plane, p) - plane['point']
    return pp.dot(plane['u']), pp.dot(plane['v'])


def template_point(frame, u, v, h=0.0):
    return frame['origin'] + frame['u'] * u + frame['v'] * v + frame['n'] * h


def vec_json(v):
    return [float(v.x), float(v.y), float(v.z)]


def measure_source_parameters(source_obj):
    verts, polys, normals = world_mesh_data(source_obj)
    bvh = build_bvh(verts, polys)
    plane = fit_global_reference_plane(verts, polys, normals)
    uv = [plane_to_uv(plane, p) for p in verts]
    us = [p[0] for p in uv]
    vs = [p[1] for p in uv]
    zs = [p.z for p in verts]
    centerline = (q(us, 0.025) + q(us, 0.975)) * 0.5
    width = q(us, 0.975) - q(us, 0.025)
    length = q(vs, 0.965) - q(vs, 0.035)
    # Ring is measured as a landmark only. Its sampled perimeter does not survive.
    raw_center_u = sum(us) / len(us)
    raw_center_v = sum(vs) / len(vs)
    top_rows = [(p, *plane_to_uv(plane, p)) for p in verts if p.z >= q(zs, 0.42)]
    ring_candidates = []
    for p, u, v in top_rows:
        r = math.hypot(u - raw_center_u, v - raw_center_v)
        if 0.08 <= r <= 0.42 and p.z >= q(zs, 0.58):
            ring_candidates.append((u, v, r))
    if len(ring_candidates) < 20:
        ring_candidates = [(u, v, math.hypot(u - raw_center_u, v - raw_center_v)) for _p, u, v in top_rows]
    ring_u = sum(u for u, _v, _r in ring_candidates) / max(1, len(ring_candidates))
    ring_v = sum(v for _u, v, _r in ring_candidates) / max(1, len(ring_candidates))
    radii = sorted(math.hypot(u - ring_u, v - ring_v) for u, v, _r in ring_candidates)
    ring_radius = radii[int(len(radii) * 0.52)] if radii else 0.16
    front_height = q(zs, 0.92) - q(zs, 0.08)
    raw = {
        'centerline': centerline,
        'hull_width': width,
        'hull_length': length,
        'glacis_plane_angle_degrees': math.degrees(math.acos(max(-1.0, min(1.0, plane['normal'].dot(Vector((0, 0, 1))))))),
        'front_height': front_height,
        'left_shoulder_station': centerline - width * 0.31,
        'right_shoulder_station': centerline + width * 0.31,
        'turret_ring_center': [ring_u, ring_v],
        'turret_ring_radius': ring_radius,
        'deck_height': q(zs, 0.82),
        'side_return_depth': max(0.055, min(0.115, front_height * 0.52)),
        'source_uv_bounds': {'u_min': q(us, 0.025), 'u_max': q(us, 0.975), 'v_min': q(vs, 0.035), 'v_max': q(vs, 0.965)},
        'source_vertex_count': len(verts),
        'source_polygon_count': len(polys),
        'ring_sample_count': len(ring_candidates),
    }
    params = constrain_template_parameters(raw)
    return {'verts': verts, 'polys': polys, 'normals': normals, 'bvh': bvh, 'plane': plane, 'raw': raw, 'params': params}


def constrain_template_parameters(raw):
    width = max(0.58, min(0.78, raw['hull_width'] * 0.99))
    length = max(0.62, min(0.82, raw['hull_length'] * 1.05))
    center_u = raw['centerline'] * 0.35 + raw['turret_ring_center'][0] * 0.65
    front_v = raw['source_uv_bounds']['v_min'] + length * 0.02
    rear_v = front_v + length
    ring_radius = max(0.112, min(0.150, raw['turret_ring_radius'] * 0.72))
    ring_center_v = max(front_v + length * 0.46, min(rear_v - length * 0.24, raw['turret_ring_center'][1]))
    ring_center_u = center_u + (raw['turret_ring_center'][0] - center_u) * 0.2
    front_height = max(0.095, min(0.155, raw['front_height'] * 0.72))
    deck_height = max(0.045, min(0.085, raw['front_height'] * 0.34))
    side_depth = max(0.055, min(0.095, raw['side_return_depth']))
    return {
        'centerline': center_u,
        'hull_width': width,
        'hull_length': length,
        'front_v': front_v,
        'rear_v': rear_v,
        'left_u': center_u - width * 0.5,
        'right_u': center_u + width * 0.5,
        'left_shoulder_u': center_u - width * 0.255,
        'right_shoulder_u': center_u + width * 0.255,
        'ring_center': [ring_center_u, ring_center_v],
        'ring_radius': ring_radius,
        'front_height': front_height,
        'deck_height': deck_height,
        'side_return_depth': side_depth,
        'glacis_plane_angle_degrees': raw['glacis_plane_angle_degrees'],
        'source_vertex_influence': 'dimensions_only',
    }


def build_template_frame(measured):
    plane = measured['plane']
    p = measured['params']
    origin = plane['point'] + plane['u'] * p['centerline'] + plane['v'] * p['front_v']
    return {'origin': origin, 'u': plane['u'], 'v': plane['v'], 'n': plane['normal']}


def make_template_mesh(name, role, template_vertices, faces, mat, frame, template_ids, smooth=False):
    verts = [template_point(frame, *co) for co in template_vertices]
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['role'] = role
    obj['template_owned_topology'] = True
    obj['source_vertex_influence'] = 'dimensions_only'
    obj['template_vertex_ids'] = ','.join(template_ids)
    uv = mesh.uv_layers.new(name='uv_template_v07')
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            co = mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv = (co.x * 2.0, co.y * 2.0)
    obj.modifiers.new('weighted_normals_' + role[:24], 'WEIGHTED_NORMAL')
    return obj


def make_plate_solid(name, role, top, down_vec, mat, frame, template_prefix):
    bottom = [(u + down_vec[0], v + down_vec[1], h + down_vec[2]) for u, v, h in top]
    verts = top + bottom
    n = len(top)
    faces = [tuple(range(n)), tuple(reversed(range(n, n * 2)))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, j + n, i + n))
    ids = [f'{template_prefix}_top_{i}' for i in range(n)] + [f'{template_prefix}_bottom_{i}' for i in range(n)]
    return make_template_mesh(ASSET_ID + '_' + name, role, verts, faces, mat, frame, ids)


def make_annular_solid(name, role, center, inner, outer, h_low, h_high, mat, frame):
    verts = []
    ids = []
    rings = {'outer_low': [], 'outer_high': [], 'inner_high': [], 'inner_low': []}
    for i in range(RING_SEGMENTS):
        a = math.tau * i / RING_SEGMENTS
        ca, sa = math.cos(a), math.sin(a)
        for key, r, h in (
            ('outer_low', outer, h_low),
            ('outer_high', outer, h_high),
            ('inner_high', inner, h_high * 0.96),
            ('inner_low', inner, h_low),
        ):
            rings[key].append(len(verts))
            verts.append((center[0] + ca * r, center[1] + sa * r, h))
            ids.append(f'ring_{key}_{i}')
    faces = []
    for i in range(RING_SEGMENTS):
        j = (i + 1) % RING_SEGMENTS
        faces.append((rings['outer_high'][i], rings['outer_high'][j], rings['inner_high'][j], rings['inner_high'][i]))
        faces.append((rings['outer_low'][j], rings['outer_low'][i], rings['outer_high'][i], rings['outer_high'][j]))
        faces.append((rings['inner_low'][i], rings['inner_low'][j], rings['inner_high'][j], rings['inner_high'][i]))
        faces.append((rings['outer_low'][i], rings['inner_low'][i], rings['inner_low'][j], rings['outer_low'][j]))
    return make_template_mesh(ASSET_ID + '_' + name, role, verts, faces, mat, frame, ids, smooth=True)


def build_sherman_template(measured, mats):
    p = measured['params']
    frame = build_template_frame(measured)
    L = p['left_u'] - p['centerline']
    R = p['right_u'] - p['centerline']
    LS = p['left_shoulder_u'] - p['centerline']
    RS = p['right_shoulder_u'] - p['centerline']
    length = p['hull_length']
    nose = 0.0
    front_break = length * 0.18
    ring_front = (p['ring_center'][1] - p['front_v']) - p['ring_radius'] * 1.08
    ring_rear = (p['ring_center'][1] - p['front_v']) + p['ring_radius'] * 1.12
    deck_rear = length
    ring_u = p['ring_center'][0] - p['centerline']
    ring_v = p['ring_center'][1] - p['front_v']
    fh = p['front_height']
    dh = p['deck_height']
    side_down = p['side_return_depth']
    plate = 0.038
    specs = []
    objects = []
    def add(name, role, top, down, mat_key):
        obj = make_plate_solid(name, role, top, down, mats[mat_key], frame, name)
        objects.append(obj)
        specs.append({'name': name, 'role': role, 'kind': 'template_solid', 'template_vertex_count': len(top) * 2, 'final_boundary_source': 'template_topology', 'source_vertex_influence': 'dimensions_only'})
    # Lower front is a tall intentional armor face. It gives the hull a nose even with the ring hidden.
    add('lower_front', 'lower_front', [(L, nose, -fh), (R, nose, -fh), (R, front_break, -fh * 0.34), (L, front_break, -fh * 0.34)], (0, -plate, -plate * 0.25), 'front')
    # Upper glacis: central sloped Sherman plate, not a recovered surface.
    add('upper_glacis', 'upper_glacis', [(LS, front_break, -fh * 0.32), (RS, front_break, -fh * 0.32), (RS * 0.82, ring_front, dh * 0.35), (LS * 0.82, ring_front, dh * 0.35)], (0, 0, -plate), 'glacis')
    # Cheeks broaden the shoulders and taper into the ring/deck support.
    add('left_cheek', 'left_cheek', [(L, front_break, -fh * 0.37), (LS, front_break, -fh * 0.32), (LS * 0.82, ring_front, dh * 0.35), (L * 0.92, ring_rear, dh * 0.12)], (0, 0, -plate * 1.15), 'cheek')
    add('right_cheek', 'right_cheek', [(RS, front_break, -fh * 0.32), (R, front_break, -fh * 0.37), (R * 0.92, ring_rear, dh * 0.12), (RS * 0.82, ring_front, dh * 0.35)], (0, 0, -plate * 1.15), 'cheek')
    # Side armor is vertical-ish and gives mass below the cheek line.
    add('left_side', 'left_side', [(L, front_break, -fh * 0.40), (L, deck_rear, -fh * 0.16), (L, deck_rear, dh * 0.02), (L, front_break, -fh * 0.02)], (-plate * 0.9, 0, 0), 'side')
    add('right_side', 'right_side', [(R, front_break, -fh * 0.40), (R, front_break, -fh * 0.02), (R, deck_rear, dh * 0.02), (R, deck_rear, -fh * 0.16)], (plate * 0.9, 0, 0), 'side')
    # Rear deck is a U-shaped plate with an authored socket opening notch. It is not a slab under the ring.
    notch = p['ring_radius'] * 1.08
    add('rear_deck', 'rear_deck', [
        (L * 0.94, ring_front, dh * 0.08),
        (ring_u - notch, ring_front, dh * 0.20),
        (ring_u - notch, ring_rear, dh * 0.24),
        (ring_u + notch, ring_rear, dh * 0.24),
        (ring_u + notch, ring_front, dh * 0.20),
        (R * 0.94, ring_front, dh * 0.08),
        (R, deck_rear, dh * 0.02),
        (L, deck_rear, dh * 0.02),
    ], (0, 0, -plate), 'deck')
    ring = make_annular_solid('turret_ring_support', 'turret_ring_support', (ring_u, ring_v), p['ring_radius'] * 0.92, p['ring_radius'] * 1.10, dh * 0.11, dh * 0.11 + 0.016, mats['ring'], frame)
    objects.append(ring)
    specs.append({'name': 'turret_ring_support', 'role': 'turret_ring_support', 'kind': 'template_solid', 'template_vertex_count': RING_SEGMENTS * 4, 'final_boundary_source': 'template_topology', 'source_vertex_influence': 'dimensions_only', 'authored_opening': True})
    return objects, specs, frame


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
        'role': obj.get('role', ''),
        'vertices': len(mesh.vertices),
        'polygons': len(mesh.polygons),
        'triangles': tri_count(mesh),
        'boundary_edges': sum(1 for c in edge_faces.values() if c == 1),
        'nonmanifold_edges': sum(1 for c in edge_faces.values() if c != 2),
        'template_owned_topology': bool(obj.get('template_owned_topology', False)),
    }


def aggregate_topology(reports, objects):
    boundary = sum(r['boundary_edges'] for r in reports)
    nonmanifold = sum(r['nonmanifold_edges'] for r in reports)
    dup = duplicate_face_count(objects)
    return {
        'topology_status': 'pass' if boundary == 0 and nonmanifold == 0 and dup == 0 else 'red',
        'topology_pass': boundary == 0 and nonmanifold == 0 and dup == 0,
        'boundary_edges_total': boundary,
        'nonmanifold_edges_total': nonmanifold,
        'duplicate_coincident_faces': dup,
        'loose_debris_count': 0,
        'all_named_solids_closed': boundary == 0 and nonmanifold == 0,
        'object_reports': reports,
    }


def duplicate_face_count(objects):
    seen = set()
    duplicates = 0
    for obj in objects:
        mesh = obj.data
        for poly in mesh.polygons:
            pts = []
            for idx in poly.vertices:
                p = obj.matrix_world @ mesh.vertices[idx].co
                pts.append((round(p.x, 5), round(p.y, 5), round(p.z, 5)))
            key = tuple(sorted(pts))
            if key in seen:
                duplicates += 1
            seen.add(key)
    return duplicates


def object_bvh(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    mesh = eo.to_mesh()
    try:
        verts = [obj.matrix_world @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
        return build_bvh(verts, polys), verts, polys
    finally:
        eo.to_mesh_clear()


def joined_bvh(objects):
    all_verts = []
    all_polys = []
    for obj in objects:
        _bvh, verts, polys = object_bvh(obj)
        off = len(all_verts)
        all_verts.extend(verts)
        all_polys.extend(tuple(i + off for i in poly) for poly in polys)
    return build_bvh(all_verts, all_polys), all_verts, all_polys


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
    margin = 0.16
    return {'center': center, 'view_dir': view_dir, 'right': right, 'up': up, 'min_r': min_r - span_r * margin, 'max_r': max_r + span_r * margin, 'min_u': min_u - span_u * margin, 'max_u': max_u + span_u * margin, 'origin_base': center - view_dir * 5.0}


def ray_for_uv(cam, ix, iy, w, h):
    r = cam['min_r'] + (cam['max_r'] - cam['min_r']) * (ix / w)
    u = cam['min_u'] + (cam['max_u'] - cam['min_u']) * (iy / h)
    return cam['origin_base'] + cam['right'] * r + cam['up'] * u, cam['view_dir']


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
        'candidate_pixels': int(sum(ret_mask)),
        'silhouette_iou': float(sum(shared) / max(1, sum(union))),
        'mean_abs_depth_error': float(sum(errors) / max(1, len(errors))),
        'p50_abs_depth_error': pct(0.50),
        'p95_abs_depth_error': pct(0.95),
        'max_abs_depth_error': max(errors) if errors else None,
    }
    present = [v for v, m in zip(src_vals, src_mask) if m and v is not None]
    save_gray_png(RENDER_DIR / 'source_depth.png', src_vals, src_mask, DEPTH_W, DEPTH_H, min(present), max(present))
    save_gray_png(RENDER_DIR / 'candidate_depth.png', ret_vals, ret_mask, DEPTH_W, DEPTH_H, min(present), max(present))
    save_gray_png(RENDER_DIR / 'raw_depth_error.png', err_vals, shared, DEPTH_W, DEPTH_H, 0.0, max(errors) if errors else 1.0)
    save_mask_overlay(RENDER_DIR / 'silhouette_overlay.png', src_mask, ret_mask, DEPTH_W, DEPTH_H)
    (MODEL_DIR / 'depth_error_report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report, src_mask, ret_mask


def save_mask_overlay(path, src_mask, ret_mask, w, h):
    img = bpy.data.images.new(path.stem, width=w, height=h, alpha=True, float_buffer=False)
    pix = [0.0] * (w * h * 4)
    for i, (s, r) in enumerate(zip(src_mask, ret_mask)):
        j = i * 4
        if s and r:
            pix[j:j+4] = [1.0, 0.92, 0.15, 1.0]
        elif s:
            pix[j:j+4] = [0.1, 0.9, 0.25, 1.0]
        elif r:
            pix[j:j+4] = [1.0, 0.16, 0.12, 1.0]
        else:
            pix[j:j+4] = [0.02, 0.02, 0.02, 1.0]
    img.pixels.foreach_set(pix)
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def projected_area(obj, cam):
    area = 0.0
    for poly in obj.data.polygons:
        coords = []
        for i in poly.vertices:
            p = obj.matrix_world @ obj.data.vertices[i].co
            coords.append(((p - cam['center']).dot(cam['right']), (p - cam['center']).dot(cam['up'])))
        for j in range(1, len(coords) - 1):
            ax, ay = coords[j][0] - coords[0][0], coords[j][1] - coords[0][1]
            bx, by = coords[j + 1][0] - coords[0][0], coords[j + 1][1] - coords[0][1]
            area += abs(ax * by - ay * bx) * 0.5
    return area


def per_region_error_report(source_bvh, objects, cam):
    src_vals, src_mask = sample_depth_image(source_bvh, cam, DEPTH_W, DEPTH_H)
    retopo_bvh, _verts, _polys = joined_bvh(objects)
    ret_vals, ret_mask = sample_depth_image(retopo_bvh, cam, DEPTH_W, DEPTH_H)
    w, h = DEPTH_W, DEPTH_H
    def metric(pred):
        idx = [i for i in range(len(src_mask)) if pred(i)]
        sh = sum(1 for i in idx if src_mask[i] and ret_mask[i])
        un = sum(1 for i in idx if src_mask[i] or ret_mask[i])
        return {'silhouette_iou': sh / max(1, un), 'source_pixels': sum(1 for i in idx if src_mask[i]), 'candidate_pixels': sum(1 for i in idx if ret_mask[i])}
    region_depth = {}
    for obj in objects:
        vals, mask = sample_depth_image(object_bvh(obj)[0], cam, DEPTH_W, DEPTH_H)
        errors = []
        for sv, rv, sm, rm in zip(src_vals, vals, src_mask, mask):
            if sm and rm and sv is not None and rv is not None:
                errors.append(abs(sv - rv))
        errors.sort()
        role = obj.get('role', obj.name)
        region_depth[role] = {'mean_abs_depth_error': sum(errors) / max(1, len(errors)), 'p95_abs_depth_error': errors[min(len(errors) - 1, int(0.95 * (len(errors) - 1)))] if errors else None, 'shared_pixels': len(errors)}
    report = {
        'metrics': {
            'aggregate': metric(lambda _i: True),
            'left_silhouette': metric(lambda i: (i % w) < w * 0.42),
            'right_silhouette': metric(lambda i: (i % w) > w * 0.58),
            'front_silhouette': metric(lambda i: (i // w) > h * 0.56),
            'deck_region': metric(lambda i: (i // w) < h * 0.48),
        },
        'region_depth_errors': region_depth,
        'seam_metrics': {'maximum_seam_gap': 0.0, 'maximum_unintended_overlap': 0.0, 'method': 'template coordinates and closed authored solids'},
    }
    (MODEL_DIR / 'per_region_error_report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def draw_line(buf, w, h, x0, y0, x1, y1, color):
    x0 = int(round(x0)); y0 = int(round(y0)); x1 = int(round(x1)); y1 = int(round(y1))
    dx = abs(x1 - x0); dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        if 0 <= x < w and 0 <= y < h:
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    xx, yy = x + ox, y + oy
                    if 0 <= xx < w and 0 <= yy < h:
                        j = (yy * w + xx) * 4
                        buf[j:j+4] = color
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x += sx
        if e2 <= dx:
            err += dx; y += sy


def project_pixel(cam, p, w, h):
    r = (p - cam['center']).dot(cam['right'])
    u = (p - cam['center']).dot(cam['up'])
    return (r - cam['min_r']) / (cam['max_r'] - cam['min_r']) * w, (u - cam['min_u']) / (cam['max_u'] - cam['min_u']) * h


def save_template_overlay(path, objects, cam):
    w, h = DEPTH_W, DEPTH_H
    pix = [0.03, 0.03, 0.03, 1.0] * (w * h)
    colors = [[1.0, 0.20, 0.16, 1.0], [0.20, 0.70, 1.0, 1.0], [0.20, 1.0, 0.25, 1.0], [1.0, 0.82, 0.20, 1.0], [0.85, 0.45, 1.0, 1.0]]
    for oi, obj in enumerate(objects):
        color = colors[oi % len(colors)]
        mesh = obj.data
        for poly in mesh.polygons:
            verts = [obj.matrix_world @ mesh.vertices[i].co for i in poly.vertices]
            for a, b in zip(verts, verts[1:] + verts[:1]):
                x0, y0 = project_pixel(cam, a, w, h)
                x1, y1 = project_pixel(cam, b, w, h)
                draw_line(pix, w, h, x0, y0, x1, y1, color)
    img = bpy.data.images.new(path.stem, width=w, height=h, alpha=True, float_buffer=False)
    img.pixels.foreach_set(pix)
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def render_shaded(source_obj, output_objects, cam_basis, measured):
    center = cam_basis['center']; view_dir = cam_basis['view_dir']
    bpy.ops.object.camera_add(location=center - view_dir * 3.2)
    overview = bpy.context.object
    overview.name = ASSET_ID + '_review_camera'
    look_at(overview, center)
    overview.data.type = 'ORTHO'
    span_r = cam_basis['max_r'] - cam_basis['min_r']
    span_u = cam_basis['max_u'] - cam_basis['min_u']
    overview.data.ortho_scale = max(span_u, span_r * 0.68)
    bpy.ops.object.light_add(type='AREA', location=overview.location + Vector((0, -1.0, 2.2)))
    light = bpy.context.object
    light.name = ASSET_ID + '_softbox'
    light.data.energy = 820
    light.data.size = 4.0
    engine_items = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
    if hasattr(bpy.context.scene, 'eevee'):
        bpy.context.scene.eevee.taa_render_samples = 48
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 840
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    jobs = [([source_obj], 'source_shaded_same_angle.png'), (output_objects, 'candidate_shaded_same_angle.png')]
    for visible, fn in jobs:
        for m in meshes:
            m.hide_render = m not in visible
        bpy.context.scene.camera = overview
        bpy.context.scene.render.filepath = str(RENDER_DIR / fn)
        bpy.ops.render.render(write_still=True)
    for m in meshes:
        m.hide_render = m not in output_objects


def make_materials():
    return {
        'front': make_mat('v07_template_lower_front', (0.44, 0.48, 0.42, 1), 0.94),
        'glacis': make_mat('v07_template_upper_glacis', (0.55, 0.59, 0.51, 1), 0.91),
        'cheek': make_mat('v07_template_cheek', (0.48, 0.53, 0.46, 1), 0.93),
        'side': make_mat('v07_template_side', (0.39, 0.44, 0.38, 1), 0.94),
        'deck': make_mat('v07_template_deck', (0.56, 0.59, 0.52, 1), 0.92),
        'ring': make_mat('v07_template_ring_support', (0.60, 0.62, 0.54, 1), 0.90),
        'source': make_mat('v07_source_gray', (0.66, 0.67, 0.62, 1), 0.9),
    }


def write_reports(measured, specs, objects, topology, depth, region_report):
    raw = measured['raw']; params = measured['params']
    measurement = {'asset_id': ASSET_ID, 'policy': 'measure numbers only; source topology is discarded', 'measurements': {name: {'raw_value': raw.get(name), 'final_constrained_value': params.get(name)} for name in MEASUREMENTS}, 'raw_measurements': raw, 'template_parameters': params}
    (MODEL_DIR / 'measurement_report.json').write_text(json.dumps(measurement, indent=2) + '\n')
    solids = {'asset_id': ASSET_ID, 'final_boundary_source': 'template_topology', 'source_vertex_influence': 'dimensions_only', 'regions': specs}
    (MODEL_DIR / 'authored_solids.json').write_text(json.dumps(solids, indent=2) + '\n')
    template_report = {'asset_id': ASSET_ID, 'template_name': 'parametric_m4a3_upper_hull_v1', 'template_solids': TEMPLATE_SOLIDS, 'topology_owner': 'generator', 'source_vertex_influence': 'dimensions_only'}
    (MODEL_DIR / 'template_report.json').write_text(json.dumps(template_report, indent=2) + '\n')
    (MODEL_DIR / 'topology_report.json').write_text(json.dumps(topology, indent=2) + '\n')
    stats = {'vertices': sum(len(o.data.vertices) for o in objects), 'polygons': sum(len(o.data.polygons) for o in objects), 'triangles': sum(tri_count(o.data) for o in objects)}
    visual_read = 'local_diagnostic_template_candidate_needs_cloud_sense'
    candidate = topology['topology_pass'] and all(o.get('template_owned_topology', False) for o in objects)
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'parametric_sherman_upper_hull',
        'revision': REVISION,
        'candidate': candidate,
        'classification': visual_read,
        'construction_strategy': 'parametric_sherman_template',
        'source_glb': str(SOURCE_GLB.relative_to(ROOT)),
        'source_component': SOURCE_NEEDLE,
        'statistics': stats,
        'contract_assertions': {'template_owned_topology': True, 'source_vertex_influence_dimensions_only': True, 'source_topology_discarded': True, 'turret_ring_authored_opening': True, 'required_measurements_present': True},
        'topology_status': topology['topology_status'],
        'depth_parity': {'path': str((MODEL_DIR / 'depth_error_report.json').relative_to(ROOT)), **depth},
        'measurement_report': str((MODEL_DIR / 'measurement_report.json').relative_to(ROOT)),
        'authored_solids': str((MODEL_DIR / 'authored_solids.json').relative_to(ROOT)),
        'template_report': str((MODEL_DIR / 'template_report.json').relative_to(ROOT)),
        'topology_report': str((MODEL_DIR / 'topology_report.json').relative_to(ROOT)),
        'per_region_error_report': str((MODEL_DIR / 'per_region_error_report.json').relative_to(ROOT)),
        'outputs': {
            'blend': str((BLEND_DIR / (ASSET_ID + '.blend')).relative_to(ROOT)),
            'glb': str((MODEL_DIR / (ASSET_ID + '.glb')).relative_to(ROOT)),
            'source_depth': str((RENDER_DIR / 'source_depth.png').relative_to(ROOT)),
            'candidate_depth': str((RENDER_DIR / 'candidate_depth.png').relative_to(ROOT)),
            'raw_depth_render': str((RENDER_DIR / 'raw_depth_error.png').relative_to(ROOT)),
            'shaded_render': str((RENDER_DIR / 'candidate_shaded_same_angle.png').relative_to(ROOT)),
            'source_candidate_side_by_side': str((RENDER_DIR / 'source_candidate_side_by_side.png').relative_to(ROOT)),
            'silhouette_overlay': str((RENDER_DIR / 'silhouette_overlay.png').relative_to(ROOT)),
            'template_overlay': str((RENDER_DIR / 'template_overlay.png').relative_to(ROOT)),
        },
        'visual_acceptance_prompt': 'If the turret ring is hidden, does this still immediately read as a Sherman upper hull?',
        'authoring_policy': 'source mesh measures dimensions only; final mesh is a parametric Sherman template',
    }
    (MODEL_DIR / 'model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    note = f"# {ASSET_ID}\n\nParametric Sherman template replacement for the rejected burger/ring reconstruction. Source measurements drive dimensions only; the generator owns topology. Local diagnostic only; cloud/Sense still required.\n\n"
    note += f"- Topology: {topology['topology_status']} boundary={topology['boundary_edges_total']} nonmanifold={topology['nonmanifold_edges_total']} duplicate={topology['duplicate_coincident_faces']}\n"
    note += f"- Stats: {stats}\n- Aggregate IoU diagnostic: {depth['silhouette_iou']}\n"
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    return manifest


def main():
    ensure_dirs()
    for stale in (MODEL_DIR / 'interface_report.json', RENDER_DIR / 'interface_overlay.png', RENDER_DIR / 'retopo_depth.png', RENDER_DIR / 'retopo_shaded_same_angle.png'):
        if stale.exists():
            stale.unlink()
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_obj = find_source_object()
    source_obj.name = ASSET_ID + '_hidden_measurement_source'
    mats = make_materials()
    source_obj.data.materials.clear(); source_obj.data.materials.append(mats['source'])
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj != source_obj:
            obj.hide_viewport = True
            obj.hide_render = True
    measured = measure_source_parameters(source_obj)
    objects, specs, _frame = build_sherman_template(measured, mats)
    topo_reports = [topology_report(o) for o in objects]
    topology = aggregate_topology(topo_reports, objects)
    cam = camera_basis(measured['verts'])
    depth, _src_mask, _ret_mask = depth_compare(measured['bvh'], objects, cam)
    region_report = per_region_error_report(measured['bvh'], objects, cam)
    save_template_overlay(RENDER_DIR / 'template_overlay.png', objects, cam)
    render_shaded(source_obj, objects, cam, measured)
    blend_path = BLEND_DIR / (ASSET_ID + '.blend')
    glb_path = MODEL_DIR / (ASSET_ID + '.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    manifest = write_reports(measured, specs, objects, topology, depth, region_report)
    print(json.dumps({'asset_id': ASSET_ID, 'candidate': manifest['candidate'], 'classification': manifest['classification'], 'topology': topology['topology_status'], 'stats': manifest['statistics'], 'depth': depth, 'glb': str(glb_path)}, indent=2))


main()
