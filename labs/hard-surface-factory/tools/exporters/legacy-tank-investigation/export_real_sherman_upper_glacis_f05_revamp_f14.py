"""Scratch exporter for the planar-fit anti-lump experiment.

Assumptions:
- Broad armor should be generated from fitted planar coordinates instead of source-raycast height samples.
- The exporter is expected to prove whether planarity removes lumpy shading.
- A flat pancake with a clean ring is a red build even if topology and plane residuals pass.
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
ASSET_ID = 'real_sherman_upper_glacis_f05_revamp_scratch_f14'
REVISION = 'f14-planar-fit-watertight-socket-ring-no-hatch-cap'
MODEL_DIR = SCRATCH / 'models' / ASSET_ID
BLEND_DIR = SCRATCH / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH / 'notes'
SOURCE_NEEDLE = 'source_component_0_upper_front_glacis'
DEPTH_W = 160
DEPTH_H = 112
SEGMENTS = 96
THICKNESS = 0.045
RING_HEIGHT = 0.020
RING_RADIAL_WIDTH = 0.030
PLANE_TOLERANCE = 1e-5


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
        normals = [(mw.to_3x3() @ p.normal).normalized() for p in mesh.polygons]
        return verts, polys, normals
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
    return area, (acc / area if area > 1e-12 else mean(points))


def fit_dominant_deck_plane(verts, polys, normals):
    z_vals = [p.z for p in verts]
    high_z = q(z_vals, 0.52)
    seed_faces = []
    for fi, face in enumerate(polys):
        pts = [verts[i] for i in face]
        area, centroid = polygon_area_centroid(pts)
        n = normals[fi]
        if area > 1e-8 and centroid.z >= high_z and n.z > 0.25:
            seed_faces.append((fi, area, centroid, n))
    if not seed_faces:
        raise RuntimeError('no deck plane seed faces found')
    avg_n = Vector((0, 0, 0))
    weighted_cent = Vector((0, 0, 0))
    total = 0.0
    for _fi, area, centroid, n in seed_faces:
        if n.z < 0:
            n = -n
        avg_n += n * area
        weighted_cent += centroid * area
        total += area
    avg_n.normalize()
    weighted_cent /= total
    cluster = []
    for fi, face in enumerate(polys):
        pts = [verts[i] for i in face]
        area, centroid = polygon_area_centroid(pts)
        n = normals[fi]
        if n.dot(avg_n) < 0:
            n = -n
        dist = abs((centroid - weighted_cent).dot(avg_n))
        if area > 1e-8 and centroid.z >= q(z_vals, 0.35) and n.dot(avg_n) >= 0.86 and dist <= 0.075:
            cluster.append((fi, area, centroid, n, dist))
    if len(cluster) < 8:
        cluster = [(*row, abs((row[2] - weighted_cent).dot(avg_n))) for row in seed_faces]
    plane_n = Vector((0, 0, 0))
    plane_p = Vector((0, 0, 0))
    total = 0.0
    for _fi, area, centroid, n, _dist in cluster:
        if n.dot(avg_n) < 0:
            n = -n
        plane_n += n * area
        plane_p += centroid * area
        total += area
    plane_n.normalize()
    plane_p /= total
    # Choose a stable axis basis in the plane. World X normally carries hull length.
    u = Vector((1, 0, 0)) - plane_n * Vector((1, 0, 0)).dot(plane_n)
    if u.length < 1e-5:
        u = Vector((0, 1, 0)) - plane_n * Vector((0, 1, 0)).dot(plane_n)
    u.normalize()
    v = plane_n.cross(u).normalized()
    residuals = [abs((centroid - plane_p).dot(plane_n)) for _fi, _area, centroid, _n, _dist in cluster]
    rejected = max(0, len(polys) - len(cluster))
    return {
        'point': plane_p,
        'normal': plane_n,
        'u': u,
        'v': v,
        'cluster_face_count': len(cluster),
        'seed_face_count': len(seed_faces),
        'rejected_face_count': rejected,
        'source_plane_residual_mean': sum(residuals) / max(1, len(residuals)),
        'source_plane_residual_max': max(residuals) if residuals else 0.0,
    }


def project_to_plane(plane, point):
    return point - plane['normal'] * (point - plane['point']).dot(plane['normal'])


def plane_to_uv(plane, point):
    p = project_to_plane(plane, point) - plane['point']
    return (p.dot(plane['u']), p.dot(plane['v']))


def uv_to_plane(plane, u, v, offset=0.0):
    return plane['point'] + plane['u'] * u + plane['v'] * v + plane['normal'] * offset


def angle_distance(a, b):
    return abs((a - b + math.pi) % math.tau - math.pi)


def simplify_loop_uv(points_uv, center_uv):
    smoothed = []
    n = len(points_uv)
    for i, (u, v) in enumerate(points_uv):
        au = av = weight = 0.0
        for off, w in [(-2, 0.10), (-1, 0.22), (0, 0.36), (1, 0.22), (2, 0.10)]:
            pu, pv = points_uv[(i + off) % n]
            au += pu * w
            av += pv * w
            weight += w
        smoothed.append((au / weight, av / weight))
    return smoothed


def measure_source_features(source_obj):
    verts, polys, normals = world_mesh_data(source_obj)
    bvh = build_bvh_from_data(verts, polys)
    plane = fit_dominant_deck_plane(verts, polys, normals)
    uv_points = [(p, *plane_to_uv(plane, p)) for p in verts]
    z_vals = [p.z for p in verts]
    deck_candidates = [(p, u, v) for p, u, v in uv_points if p.z >= q(z_vals, 0.35) and abs((p - plane['point']).dot(plane['normal'])) <= max(0.09, plane['source_plane_residual_max'] * 2.5)]
    if len(deck_candidates) < 20:
        deck_candidates = uv_points
    center_u = sum(u for _p, u, _v in deck_candidates) / len(deck_candidates)
    center_v = sum(v for _p, _u, v in deck_candidates) / len(deck_candidates)
    ring_points = []
    for p, u, v in deck_candidates:
        r = math.hypot(u - center_u, v - center_v)
        if 0.09 <= r <= 0.38 and p.z >= q(z_vals, 0.60):
            ring_points.append((p, u, v))
    if len(ring_points) < 20:
        ring_points = deck_candidates
    ring_u = sum(u for _p, u, _v in ring_points) / len(ring_points)
    ring_v = sum(v for _p, _u, v in ring_points) / len(ring_points)
    ring_radii = sorted(math.hypot(u - ring_u, v - ring_v) for _p, u, v in ring_points)
    socket_radius = max(0.105, min(0.185, ring_radii[int(len(ring_radii) * 0.56)] if ring_radii else 0.13))
    outer_uv = []
    for i in range(SEGMENTS):
        a = math.tau * i / SEGMENTS
        candidates = []
        for _p, u, v in deck_candidates:
            d = angle_distance(math.atan2(v - center_v, u - center_u), a)
            if d <= math.tau / SEGMENTS * 2.4:
                r = math.hypot(u - center_u, v - center_v)
                candidates.append((r, u, v))
        if not candidates:
            r, u, v = max((math.hypot(u - center_u, v - center_v), u, v) for _p, u, v in deck_candidates)
        else:
            r, u, v = max(candidates, key=lambda row: row[0])
        outer_uv.append((center_u + (u - center_u) * 0.965, center_v + (v - center_v) * 0.965))
    outer_uv = simplify_loop_uv(outer_uv, (center_u, center_v))
    min_outer_dist = min(math.hypot(u - ring_u, v - ring_v) for u, v in outer_uv)
    if min_outer_dist < socket_radius + RING_RADIAL_WIDTH + 0.035:
        ring_u, ring_v = center_u, center_v
    ring_center = uv_to_plane(plane, ring_u, ring_v, 0.0)
    outer_loop = [uv_to_plane(plane, u, v, 0.0) for u, v in outer_uv]
    return {
        'verts': verts,
        'polys': polys,
        'bvh': bvh,
        'plane': plane,
        'outer_loop_uv': outer_uv,
        'outer_loop': outer_loop,
        'ring_center_uv': [ring_u, ring_v],
        'ring_center': ring_center,
        'socket_radius': socket_radius,
        'source_vertex_count': len(verts),
        'deck_candidate_count': len(deck_candidates),
        'ring_candidate_count': len(ring_points),
    }


def add_uvs(obj):
    mesh = obj.data
    uv = mesh.uv_layers.new(name='uv_planar_fit_f14') if not mesh.uv_layers else mesh.uv_layers.active
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
    plane = features['plane']
    radius = features['socket_radius']
    center_u, center_v = features['ring_center_uv']
    outer_uv = features['outer_loop_uv']
    verts = []
    rings = {'outer_top': [], 'outer_bottom': [], 'inner_top': [], 'inner_bottom': []}
    for i in range(SEGMENTS):
        a = math.tau * i / SEGMENTS
        ou, ov = outer_uv[i]
        outer_top = uv_to_plane(plane, ou, ov, 0.0)
        outer_bottom = uv_to_plane(plane, ou, ov, -THICKNESS)
        iu = center_u + radius * math.cos(a)
        iv = center_v + radius * math.sin(a)
        inner_top = uv_to_plane(plane, iu, iv, 0.0)
        inner_bottom = uv_to_plane(plane, iu, iv, -THICKNESS)
        rings['outer_top'].append(len(verts)); verts.append(tuple(outer_top))
        rings['outer_bottom'].append(len(verts)); verts.append(tuple(outer_bottom))
        rings['inner_top'].append(len(verts)); verts.append(tuple(inner_top))
        rings['inner_bottom'].append(len(verts)); verts.append(tuple(inner_bottom))
    faces = []
    tags = []
    def add(face, tag):
        faces.append(face); tags.append(tag)
    for i in range(SEGMENTS):
        j = (i + 1) % SEGMENTS
        add((rings['outer_top'][i], rings['outer_top'][j], rings['inner_top'][j], rings['inner_top'][i]), 'solid_top_armor_plate_planar')
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
    obj = bpy.data.objects.new(ASSET_ID + '_solid_planar_top_plate_with_cylindrical_cut', mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['role'] = 'solid_planar_top_plate_with_cylindrical_cut'
    obj['topology_contract'] = 'closed armor shell built from fitted deck plane; no broad-plate source raycast height sampling.'
    add_uvs(obj)
    obj.modifiers.new('weighted_normals_planar_plate', 'WEIGHTED_NORMAL')
    return obj, {'face_tags': sorted(set(tags)), 'segments': SEGMENTS, 'thickness': THICKNESS, 'socket_radius': radius, 'ring_center_uv': [center_u, center_v]}


def make_annular_ring(features, mats):
    plane = features['plane']
    center_u, center_v = features['ring_center_uv']
    inner = features['socket_radius'] + 0.004
    outer = inner + RING_RADIAL_WIDTH
    verts = []
    idx = {'outer_low': [], 'outer_high': [], 'inner_high': [], 'inner_low': []}
    for i in range(SEGMENTS):
        a = math.tau * i / SEGMENTS
        for key, r, offset in (
            ('outer_low', outer, 0.003), ('outer_high', outer, RING_HEIGHT),
            ('inner_high', inner, RING_HEIGHT * 0.82), ('inner_low', inner, 0.003),
        ):
            p = uv_to_plane(plane, center_u + r * math.cos(a), center_v + r * math.sin(a), offset)
            idx[key].append(len(verts)); verts.append(tuple(p))
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
    obj = bpy.data.objects.new(ASSET_ID + '_separate_planar_seated_watertight_ring', mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['role'] = 'separate_planar_seated_watertight_ring'
    obj['topology_contract'] = 'closed separate annular ring seated on fitted plane over owned cylindrical socket.'
    add_uvs(obj)
    obj.modifiers.new('weighted_normals_planar_ring', 'WEIGHTED_NORMAL')
    return obj, {'face_tags': sorted(set(tags)), 'segments': SEGMENTS, 'inner_radius': inner, 'outer_radius': outer, 'height': RING_HEIGHT}


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


def plane_residual_report(plane, objects):
    broad = []
    ring_contact = []
    for obj in objects:
        for v in obj.data.vertices:
            wp = obj.matrix_world @ v.co
            d = (wp - plane['point']).dot(plane['normal'])
            if obj.get('role') == 'solid_planar_top_plate_with_cylindrical_cut':
                # Top and bottom broad vertices are exactly at offsets 0 or -THICKNESS; measure nearest intended plane offset.
                broad.append(min(abs(d), abs(d + THICKNESS)))
            elif obj.get('role') == 'separate_planar_seated_watertight_ring':
                ring_contact.append(min(abs(d - 0.003), abs(d - RING_HEIGHT), abs(d - RING_HEIGHT * 0.82)))
    broad_max = max(broad) if broad else 0.0
    broad_mean = sum(broad) / max(1, len(broad))
    ring_max = max(ring_contact) if ring_contact else 0.0
    ok = broad_max <= PLANE_TOLERANCE and ring_max <= PLANE_TOLERANCE
    return {
        'plane_status': 'pass' if ok else 'red',
        'plane_pass': ok,
        'broad_plate_residual_mean': broad_mean,
        'broad_plate_residual_max': broad_max,
        'ring_offset_residual_max': ring_max,
        'tolerance': PLANE_TOLERANCE,
    }


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
    n = features['plane']['normal']
    loc = c - Vector((0, 1.05, -0.54))
    if (loc - c).length < 0.1:
        loc = c + n * 0.6 + features['plane']['v'] * -0.9
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.object
    cam.name = ASSET_ID + '_hatch_socket_close_camera'
    look_at(cam, c - n * 0.01)
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
            _loc, _normal, face_index, dist = source_bvh.find_nearest(wp, 1.0)
            rows.append({
                'output_object': obj.name,
                'output_vertex': i,
                'support': {
                    'kind': 'fitted_plane_projected_source_supported',
                    'source_object': SOURCE_NEEDLE,
                    'source_face': int(face_index) if face_index is not None else -1,
                    'distance_to_source_surface': float(dist) if dist is not None else None,
                },
                'semantic_patch': obj.get('role', ''),
                'world': [float(wp.x), float(wp.y), float(wp.z)],
            })
    path = MODEL_DIR / 'retopo_vertex_provenance.json'
    path.write_text(json.dumps({'asset_id': ASSET_ID, 'vertices': rows}, indent=2) + '\n')
    return path, rows


def write_plane_and_landmark_reports(features, output_objects, plane_gate):
    plane = features['plane']
    plane_report = {
        'asset_id': ASSET_ID,
        'plane_status': plane_gate['plane_status'],
        'plane_point': [plane['point'].x, plane['point'].y, plane['point'].z],
        'plane_normal': [plane['normal'].x, plane['normal'].y, plane['normal'].z],
        'plane_u': [plane['u'].x, plane['u'].y, plane['u'].z],
        'plane_v': [plane['v'].x, plane['v'].y, plane['v'].z],
        'seed_face_count': plane['seed_face_count'],
        'cluster_face_count': plane['cluster_face_count'],
        'rejected_face_count': plane['rejected_face_count'],
        'source_plane_residual_mean': plane['source_plane_residual_mean'],
        'source_plane_residual_max': plane['source_plane_residual_max'],
        **plane_gate,
    }
    plane_path = MODEL_DIR / 'plane_fit_report.json'
    plane_path.write_text(json.dumps(plane_report, indent=2) + '\n')
    landmarks = {
        'asset_id': ASSET_ID,
        'loops': {
            'outer_silhouette_loop': {'kind': 'source_boundary_candidate_simplified_in_plane_uv', 'samples': len(features['outer_loop_uv'])},
            'dominant_plane_loop': {'kind': 'fitted_deck_plane', 'cluster_face_count': plane['cluster_face_count']},
            'turret_socket_loop': {'kind': 'regularized_circle_in_fitted_plane', 'segments': SEGMENTS, 'radius': features['socket_radius']},
            'raised_ring_loop': {'kind': 'separate_annular_closed_mesh_in_fitted_plane', 'segments': SEGMENTS},
        },
        'hatch': {'omitted': True, 'reason': 'do not continue hatch cap modeling in this pass'},
    }
    landmarks_path = MODEL_DIR / 'retopo_landmarks.json'
    landmarks_path.write_text(json.dumps(landmarks, indent=2) + '\n')
    return plane_path, landmarks_path


def main():
    ensure_dirs()
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_obj = find_source_object()
    source_obj.name = ASSET_ID + '_hidden_source_upper_glacis'
    source_mat = make_mat(ASSET_ID + '_source_gray', (0.66, 0.67, 0.62, 1), 0.9)
    armor_mat = make_mat('armor_plate_planar_fit', (0.58, 0.61, 0.54, 1), 0.92)
    socket_mat = make_mat('cylindrical_socket_wall', (0.48, 0.50, 0.46, 1), 0.94)
    ring_mat = make_mat('separate_ring_armor', (0.62, 0.64, 0.56, 1), 0.90)
    source_obj.data.materials.clear()
    source_obj.data.materials.append(source_mat)
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj != source_obj:
            obj.hide_viewport = True
            obj.hide_render = True
    features = measure_source_features(source_obj)
    mats = [armor_mat, socket_mat, ring_mat]
    plate, plate_primitive = make_solid_top_plate(features, mats)
    ring, ring_primitive = make_annular_ring(features, mats)
    output_objects = [plate, ring]
    topology_reports = [topology_report(o) for o in output_objects]
    topology_gate = aggregate_gate(topology_reports)
    plane_gate = plane_residual_report(features['plane'], output_objects)
    cam_basis = camera_basis(features['verts'])
    depth_report = depth_compare(features['bvh'], output_objects, cam_basis)
    shape_status = 'red_depth_parity_weak' if depth_report['silhouette_iou'] < 0.90 else 'diagnostic_promising'
    candidate = bool(topology_gate['topology_pass'] and plane_gate['plane_pass'] and shape_status != 'red_depth_parity_weak')
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
    plane_path, landmarks_path = write_plane_and_landmark_reports(features, output_objects, plane_gate)
    primitive_path = MODEL_DIR / 'solid_primitives.json'
    primitive_path.write_text(json.dumps({
        'asset_id': ASSET_ID,
        'plate': plate_primitive,
        'ring': ring_primitive,
        'hatch': {'omitted': True, 'reason': 'do not continue hatch-cap modeling in this pass'},
        'source_feature_policy': 'source samples solve boundary/landmarks only; broad armor vertices are projected to fitted deck plane, not raycast back onto source noise.',
    }, indent=2) + '\n')
    total_stats = {'vertices': sum(r['vertices'] for r in topology_reports), 'polygons': sum(r['polygons'] for r in topology_reports), 'triangles': sum(r['triangles'] for r in topology_reports)}
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'scratch_planar_fit_watertight_upper_glacis_socket_ring_no_hatch_cap',
        'revision': REVISION,
        'candidate': candidate,
        'candidate_reason': 'requires topology pass, plane pass, and non-red shape parity; topology alone cannot set candidate true',
        'topology_status': topology_gate['topology_status'],
        'plane_status': plane_gate['plane_status'],
        'shape_review_status': shape_status,
        'source_glb': str(SOURCE_GLB.relative_to(ROOT)),
        'source_component': SOURCE_NEEDLE,
        'authoring_policy': 'Dominant deck plane is fitted from source faces. Broad armor vertices are generated in plane UV coordinates and offset along plane normal. Source samples are used for boundary/landmark support only, not broad-plate height.',
        'current_prompt_contract': {
            'current_user_command': 'Implement f14 planar-fit watertight pass.',
            'forbidden_stale_premise': 'Sampling/raycasting broad planar armor vertices from source noise and accepting lumps because topology passes.',
            'intended_mutation': 'Create one new scratch mesh artifact with fitted planar armor, cylindrical cut, separate closed ring, no hatch cap, plane/topology/shape diagnostics, and viewer handoff.',
            'why_this_satisfies_command': 'It replaces the lumpy source-sampling method with mode planar coordinates while preserving watertight shell architecture.',
        },
        'statistics': total_stats,
        'topology_gate': topology_gate,
        'plane_gate': plane_gate,
        'topology_reports': topology_reports,
        'material_slots': [m.name for m in mats],
        'solid_primitives': str(primitive_path.relative_to(ROOT)),
        'plane_fit_report': str(plane_path.relative_to(ROOT)),
        'retopo_landmarks': str(landmarks_path.relative_to(ROOT)),
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
    }
    (MODEL_DIR / 'model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    note_status = 'diagnostic candidate' if candidate else 'NOT a visual candidate'
    note = '# ' + ASSET_ID + '\n\n' + note_status + '. Scratch diagnostic only; not production/cloud accepted.\n\n'
    note += '## Process Fix\n\nBroad armor is generated from a fitted deck plane. Source samples define boundary and socket landmarks, but broad top-plate vertices are not raycast back onto source height noise.\n\n'
    note += '## Gates\n\n'
    note += '- Topology: ' + topology_gate['topology_status'] + ' boundary=' + str(topology_gate['boundary_edges_total']) + ' nonmanifold=' + str(topology_gate['nonmanifold_edges_total']) + '\n'
    note += '- Plane: ' + plane_gate['plane_status'] + ' broad_max=' + str(plane_gate['broad_plate_residual_max']) + '\n'
    note += '- Shape: ' + shape_status + ' IoU=' + str(depth_report['silhouette_iou']) + '\n'
    note += '- Candidate flag: ' + str(candidate) + '\n\n'
    note += '## Stats\n\n- Vertices: ' + str(total_stats['vertices']) + '\n- Polygons: ' + str(total_stats['polygons']) + '\n- Triangles: ' + str(total_stats['triangles']) + '\n\n'
    note += '## Review Note\n\nIf this still looks too simplified, the next pass should improve the source-supported outer/manufactured plate loops in plane UV space, not return to source-raycast heights.\n'
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    print(json.dumps({'asset_id': ASSET_ID, 'candidate': candidate, 'topology_gate': topology_gate, 'plane_gate': plane_gate, 'shape_review_status': shape_status, 'stats': total_stats, 'depth_report': depth_report, 'glb': str(glb_path)}, indent=2))


main()
