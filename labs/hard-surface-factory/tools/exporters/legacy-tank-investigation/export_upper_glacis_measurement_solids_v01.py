"""Measurement-to-solids hard-surface reconstruction for the Sherman upper glacis.

Doctrine for this scratch exporter:
- The source mesh is measurement, not geometry.
- Source vertices answer fitted-plane, boundary, socket, and seam questions, then are discarded.
- The output is authored from a small set of closed solids with explicit topology contracts.
- No source triangles, source-shell solidify, blanket snapping, or dense raycast surface rebuild is allowed.

This is intentionally not named f17. It replaces the construction strategy instead of
continuing the f12-f16 variant chain.
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
ASSET_ID = 'real_sherman_upper_glacis_measurement_solids_scratch_v01'
REVISION = 'v01-measurement-cloud-authored-closed-solids'
MODEL_DIR = SCRATCH / 'models' / ASSET_ID
BLEND_DIR = SCRATCH / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH / 'notes'
DEPTH_W = 180
DEPTH_H = 126
SOCKET_SEGMENTS = 72
THICKNESS = 0.050
RETURN_WIDTH = 0.035
LOWER_SEAM_WIDTH = 0.045
RING_RADIAL_WIDTH = 0.032
RING_HEIGHT = 0.020
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


def fit_dominant_plane(verts, polys, normals):
    z_vals = [p.z for p in verts]
    high_z = q(z_vals, 0.50)
    seeds = []
    for fi, face in enumerate(polys):
        pts = [verts[i] for i in face]
        area, centroid = polygon_area_centroid(pts)
        n = normals[fi]
        if area > 1e-8 and centroid.z >= high_z and n.z > 0.18:
            seeds.append((fi, area, centroid, n))
    if not seeds:
        raise RuntimeError('no dominant upper-glacis plane seeds found')
    avg_n = Vector((0, 0, 0))
    avg_p = Vector((0, 0, 0))
    total = 0.0
    for _fi, area, centroid, n in seeds:
        if n.z < 0:
            n = -n
        avg_n += n * area
        avg_p += centroid * area
        total += area
    avg_n.normalize()
    avg_p /= total
    cluster = []
    for fi, face in enumerate(polys):
        pts = [verts[i] for i in face]
        area, centroid = polygon_area_centroid(pts)
        n = normals[fi]
        if n.dot(avg_n) < 0:
            n = -n
        dist = abs((centroid - avg_p).dot(avg_n))
        if area > 1e-8 and centroid.z >= q(z_vals, 0.32) and n.dot(avg_n) >= 0.82 and dist <= 0.10:
            cluster.append((fi, area, centroid, n, dist))
    if len(cluster) < 8:
        cluster = [(*row, abs((row[2] - avg_p).dot(avg_n))) for row in seeds]
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
    u = Vector((1, 0, 0)) - plane_n * Vector((1, 0, 0)).dot(plane_n)
    if u.length < 1e-5:
        u = Vector((0, 1, 0)) - plane_n * Vector((0, 1, 0)).dot(plane_n)
    u.normalize()
    v = plane_n.cross(u).normalized()
    residuals = [abs((centroid - plane_p).dot(plane_n)) for _fi, _area, centroid, _n, _dist in cluster]
    return {
        'point': plane_p,
        'normal': plane_n,
        'u': u,
        'v': v,
        'seed_face_count': len(seeds),
        'cluster_face_count': len(cluster),
        'source_plane_residual_mean': sum(residuals) / max(1, len(residuals)),
        'source_plane_residual_max': max(residuals) if residuals else 0.0,
    }


def project_to_plane(plane, p):
    return p - plane['normal'] * (p - plane['point']).dot(plane['normal'])


def plane_to_uv(plane, p):
    pp = project_to_plane(plane, p) - plane['point']
    return pp.dot(plane['u']), pp.dot(plane['v'])


def uv_to_plane(plane, u, v, offset=0.0):
    return plane['point'] + plane['u'] * u + plane['v'] * v + plane['normal'] * offset


def build_bvh(verts, polys):
    return BVHTree.FromPolygons(verts, polys, all_triangles=False)


def slice_quantile(points_uv, u_center, span, side):
    vals = [v for u, v in points_uv if abs(u - u_center) <= span]
    if len(vals) < 6:
        vals = [v for _u, v in points_uv]
    return q(vals, 0.08 if side < 0 else 0.92)


def ray_segment_intersection(origin, direction, a, b):
    ox, oy = origin
    dx, dy = direction
    ax, ay = a
    bx, by = b
    sx, sy = bx - ax, by - ay
    den = dx * sy - dy * sx
    if abs(den) < 1e-9:
        return None
    qx, qy = ax - ox, ay - oy
    t = (qx * sy - qy * sx) / den
    s = (qx * dy - qy * dx) / den
    if t > 1e-7 and -1e-7 <= s <= 1.0 + 1e-7:
        return t, (ox + dx * t, oy + dy * t)
    return None


def ray_polygon_intersection(center, angle, polygon):
    direction = (math.cos(angle), math.sin(angle))
    hits = []
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        hit = ray_segment_intersection(center, direction, a, b)
        if hit:
            hits.append(hit)
    if not hits:
        return None
    return min(hits, key=lambda h: h[0])[1]


def measure_features(source_obj):
    verts, polys, normals = world_mesh_data(source_obj)
    plane = fit_dominant_plane(verts, polys, normals)
    source_bvh = build_bvh(verts, polys)
    z_vals = [p.z for p in verts]
    uv_rows = [(p, *plane_to_uv(plane, p)) for p in verts]
    deck_rows = [row for row in uv_rows if row[0].z >= q(z_vals, 0.33) and abs((row[0] - plane['point']).dot(plane['normal'])) <= max(0.12, plane['source_plane_residual_max'] * 3.0)]
    if len(deck_rows) < 25:
        deck_rows = uv_rows
    deck_uv = [(u, v) for _p, u, v in deck_rows]
    us = [u for u, _v in deck_uv]
    vs = [v for _u, v in deck_uv]
    u_min, u_max = q(us, 0.025), q(us, 0.975)
    v_min, v_max = q(vs, 0.035), q(vs, 0.965)
    u_span = max(1e-5, u_max - u_min)
    station_us = [u_min, u_min + u_span * 0.30, u_min + u_span * 0.70, u_max]
    slice_span = u_span * 0.13
    left = [(u, slice_quantile(deck_uv, u, slice_span, -1)) for u in station_us]
    right = [(u, slice_quantile(deck_uv, u, slice_span, 1)) for u in reversed(station_us)]
    # A manufactured, low-control-point boundary. Measurements choose the stations;
    # the output polygon is freshly authored and deliberately not a source loop.
    outer_uv = left + right
    center_u = sum(u for u, _v in deck_uv) / len(deck_uv)
    center_v = sum(v for _u, v in deck_uv) / len(deck_uv)
    ring_rows = []
    for p, u, v in deck_rows:
        r = math.hypot(u - center_u, v - center_v)
        if 0.08 <= r <= 0.40 and p.z >= q(z_vals, 0.58):
            ring_rows.append((p, u, v, r))
    if len(ring_rows) < 20:
        ring_rows = [(p, u, v, math.hypot(u - center_u, v - center_v)) for p, u, v in deck_rows]
    ring_u = sum(u for _p, u, _v, _r in ring_rows) / len(ring_rows)
    ring_v = sum(v for _p, _u, v, _r in ring_rows) / len(ring_rows)
    radii = sorted(math.hypot(u - ring_u, v - ring_v) for _p, u, v, _r in ring_rows)
    socket_radius = max(0.105, min(0.180, radii[int(len(radii) * 0.52)] if radii else 0.13))
    min_boundary_radius = min(math.hypot(u - ring_u, v - ring_v) for u, v in outer_uv)
    if min_boundary_radius < socket_radius + RING_RADIAL_WIDTH + 0.055:
        ring_u, ring_v = center_u, center_v
    return {
        'verts': verts,
        'polys': polys,
        'bvh': source_bvh,
        'plane': plane,
        'deck_candidate_count': len(deck_rows),
        'outer_boundary_uv': outer_uv,
        'outer_boundary_world': [uv_to_plane(plane, u, v, 0.0) for u, v in outer_uv],
        'stations': {'left': left, 'right': list(reversed(right))},
        'bounds_uv': {'u_min': u_min, 'u_max': u_max, 'v_min': v_min, 'v_max': v_max},
        'ring_center_uv': [ring_u, ring_v],
        'ring_center_world': uv_to_plane(plane, ring_u, ring_v, 0.0),
        'socket_radius': socket_radius,
        'source_vertex_count': len(verts),
        'source_polygon_count': len(polys),
    }


def add_uvs(obj, name='uv_measurement_solids'):
    mesh = obj.data
    uv = mesh.uv_layers.new(name=name) if not mesh.uv_layers else mesh.uv_layers.active
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


def make_mesh_object(name, verts, faces, mat, role, contract, smooth=False):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(mat)
    for p in mesh.polygons:
        p.material_index = 0
        p.use_smooth = smooth
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['role'] = role
    obj['topology_contract'] = contract
    add_uvs(obj)
    obj.modifiers.new('weighted_normals_' + role[:24], 'WEIGHTED_NORMAL')
    return obj


def make_main_glacis_plate(features, mat):
    plane = features['plane']
    center = tuple(features['ring_center_uv'])
    outer_poly = features['outer_boundary_uv']
    r = features['socket_radius']
    verts = []
    top_outer = []
    bottom_outer = []
    top_inner = []
    bottom_inner = []
    for i in range(SOCKET_SEGMENTS):
        a = math.tau * i / SOCKET_SEGMENTS
        hit = ray_polygon_intersection(center, a, outer_poly)
        if hit is None:
            # Fallback is an authored rectangle radius from measured extents, not a source point.
            bu = max(abs(features['bounds_uv']['u_min'] - center[0]), abs(features['bounds_uv']['u_max'] - center[0]))
            bv = max(abs(features['bounds_uv']['v_min'] - center[1]), abs(features['bounds_uv']['v_max'] - center[1]))
            hit = (center[0] + math.cos(a) * bu, center[1] + math.sin(a) * bv)
        iu = center[0] + math.cos(a) * r
        iv = center[1] + math.sin(a) * r
        ot = uv_to_plane(plane, hit[0], hit[1], 0.0)
        ob = uv_to_plane(plane, hit[0], hit[1], -THICKNESS)
        it = uv_to_plane(plane, iu, iv, 0.0)
        ib = uv_to_plane(plane, iu, iv, -THICKNESS)
        top_outer.append(len(verts)); verts.append(ot)
        bottom_outer.append(len(verts)); verts.append(ob)
        top_inner.append(len(verts)); verts.append(it)
        bottom_inner.append(len(verts)); verts.append(ib)
    faces = []
    for i in range(SOCKET_SEGMENTS):
        j = (i + 1) % SOCKET_SEGMENTS
        faces.append((top_outer[i], top_outer[j], top_inner[j], top_inner[i]))
        faces.append((bottom_outer[j], bottom_outer[i], bottom_inner[i], bottom_inner[j]))
        faces.append((bottom_outer[i], bottom_outer[j], top_outer[j], top_outer[i]))
        faces.append((top_inner[i], top_inner[j], bottom_inner[j], bottom_inner[i]))
    obj = make_mesh_object(
        ASSET_ID + '_main_glacis_closed_plate', verts, faces, mat,
        'main_glacis_armor_plate',
        'closed authored annular armor plate from measured plane/boundary/socket landmarks; source vertices not copied',
    )
    return obj, {
        'region': 'main_glacis_armor_plate',
        'topology': 'closed annular prism with outer wall and socket wall',
        'source_use': 'plane, manufactured boundary stations, socket center/radius only',
        'segments': SOCKET_SEGMENTS,
        'thickness': THICKNESS,
    }


def make_strip_solid(name, polyline_uv, width, offset_side, features, mat, role):
    plane = features['plane']
    if len(polyline_uv) < 2:
        raise RuntimeError('strip requires at least two points')
    verts = []
    a = polyline_uv[0]
    b = polyline_uv[-1]
    tangent = Vector((b[0] - a[0], b[1] - a[1], 0))
    if tangent.length < 1e-8:
        tangent = Vector((1, 0, 0))
    tangent.normalize()
    normal2 = Vector((-tangent.y, tangent.x, 0)) * offset_side
    # Ensure the return strip grows away from the socket center, not over the plate.
    cu, cv = features['ring_center_uv']
    mid = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
    if (Vector((mid[0] - cu, mid[1] - cv, 0))).dot(normal2) < 0:
        normal2 = -normal2
    top_a = []
    top_b = []
    bot_a = []
    bot_b = []
    for u, v in polyline_uv:
        u2 = u + normal2.x * width
        v2 = v + normal2.y * width
        top_a.append(len(verts)); verts.append(uv_to_plane(plane, u, v, -0.004))
        top_b.append(len(verts)); verts.append(uv_to_plane(plane, u2, v2, -0.010))
        bot_a.append(len(verts)); verts.append(uv_to_plane(plane, u, v, -THICKNESS * 1.15))
        bot_b.append(len(verts)); verts.append(uv_to_plane(plane, u2, v2, -THICKNESS * 1.15))
    faces = []
    for i in range(len(polyline_uv) - 1):
        j = i + 1
        faces.append((top_a[i], top_a[j], top_b[j], top_b[i]))
        faces.append((bot_a[j], bot_a[i], bot_b[i], bot_b[j]))
        faces.append((top_a[i], bot_a[i], bot_a[j], top_a[j]))
        faces.append((top_b[j], bot_b[j], bot_b[i], top_b[i]))
    faces.append((top_a[0], top_b[0], bot_b[0], bot_a[0]))
    faces.append((top_a[-1], bot_a[-1], bot_b[-1], top_b[-1]))
    return make_mesh_object(name, verts, faces, mat, role, 'closed strip/return solid authored from measured seam line and offset width')


def make_returns_and_seam(features, mat_return, mat_seam):
    left = features['stations']['left']
    right = features['stations']['right']
    lower = [left[0], right[0]]
    left_obj = make_strip_solid(ASSET_ID + '_left_edge_return_closed_solid', left, RETURN_WIDTH, -1, features, mat_return, 'left_edge_return')
    right_obj = make_strip_solid(ASSET_ID + '_right_edge_return_closed_solid', right, RETURN_WIDTH, 1, features, mat_return, 'right_edge_return')
    seam_obj = make_strip_solid(ASSET_ID + '_lower_hull_seam_closed_solid', lower, LOWER_SEAM_WIDTH, -1, features, mat_seam, 'lower_hull_seam')
    return [left_obj, right_obj, seam_obj], [
        {'region': 'left_edge_return', 'topology': 'closed strip solid', 'source_use': 'measured left seam stations only'},
        {'region': 'right_edge_return', 'topology': 'closed strip solid', 'source_use': 'measured right seam stations only'},
        {'region': 'lower_hull_seam', 'topology': 'closed seam bar solid', 'source_use': 'measured lower seam endpoints only'},
    ]


def make_socket_cylinder(features, mat):
    plane = features['plane']
    cu, cv = features['ring_center_uv']
    r = features['socket_radius'] * 0.985
    verts = []
    top = []
    bottom = []
    for i in range(SOCKET_SEGMENTS):
        a = math.tau * i / SOCKET_SEGMENTS
        u = cu + math.cos(a) * r
        v = cv + math.sin(a) * r
        top.append(len(verts)); verts.append(uv_to_plane(plane, u, v, 0.004))
        bottom.append(len(verts)); verts.append(uv_to_plane(plane, u, v, -THICKNESS * 1.28))
    faces = []
    for i in range(SOCKET_SEGMENTS):
        j = (i + 1) % SOCKET_SEGMENTS
        faces.append((top[i], top[j], bottom[j], bottom[i]))
    faces.append(tuple(reversed(top)))
    faces.append(tuple(bottom))
    obj = make_mesh_object(ASSET_ID + '_socket_cylinder_closed_solid', verts, faces, mat, 'socket_cylinder', 'closed socket cylinder measured from source ring landmark', smooth=True)
    return obj, {'region': 'socket_cylinder', 'topology': 'closed cylinder with capped top/bottom', 'segments': SOCKET_SEGMENTS, 'radius': r}


def make_raised_ring(features, mat):
    plane = features['plane']
    cu, cv = features['ring_center_uv']
    inner = features['socket_radius'] + 0.004
    outer = inner + RING_RADIAL_WIDTH
    verts = []
    idx = {'outer_low': [], 'outer_high': [], 'inner_high': [], 'inner_low': []}
    for i in range(SOCKET_SEGMENTS):
        a = math.tau * i / SOCKET_SEGMENTS
        for key, rad, off in (
            ('outer_low', outer, 0.004),
            ('outer_high', outer, RING_HEIGHT),
            ('inner_high', inner, RING_HEIGHT * 0.90),
            ('inner_low', inner, 0.004),
        ):
            idx[key].append(len(verts)); verts.append(uv_to_plane(plane, cu + math.cos(a) * rad, cv + math.sin(a) * rad, off))
    faces = []
    for i in range(SOCKET_SEGMENTS):
        j = (i + 1) % SOCKET_SEGMENTS
        faces.append((idx['outer_high'][i], idx['outer_high'][j], idx['inner_high'][j], idx['inner_high'][i]))
        faces.append((idx['outer_low'][j], idx['outer_low'][i], idx['outer_high'][i], idx['outer_high'][j]))
        faces.append((idx['inner_low'][i], idx['inner_low'][j], idx['inner_high'][j], idx['inner_high'][i]))
        faces.append((idx['outer_low'][i], idx['inner_low'][i], idx['inner_low'][j], idx['outer_low'][j]))
    obj = make_mesh_object(ASSET_ID + '_raised_ring_closed_solid', verts, faces, mat, 'raised_ring', 'closed annular ring seated on the authored armor plate', smooth=True)
    return obj, {'region': 'raised_ring', 'topology': 'closed annular prism', 'segments': SOCKET_SEGMENTS, 'inner_radius': inner, 'outer_radius': outer, 'height': RING_HEIGHT}


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
        'uv_layers': [uv.name for uv in mesh.uv_layers],
    }


def aggregate_topology(reports):
    boundary = sum(r['boundary_edges'] for r in reports)
    nonmanifold = sum(r['nonmanifold_edges'] for r in reports)
    return {
        'topology_status': 'pass' if boundary == 0 and nonmanifold == 0 else 'red',
        'topology_pass': boundary == 0 and nonmanifold == 0,
        'boundary_edges_total': boundary,
        'nonmanifold_edges_total': nonmanifold,
        'failure_reasons': ([] if boundary == 0 and nonmanifold == 0 else [f'boundary_edges={boundary}', f'nonmanifold_edges={nonmanifold}']),
    }


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
    margin = 0.14
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


def render_shaded(source_obj, output_objects, cam_basis, features):
    center = cam_basis['center']; view_dir = cam_basis['view_dir']
    bpy.ops.object.camera_add(location=center - view_dir * 3.2)
    overview = bpy.context.object
    overview.name = ASSET_ID + '_depth_parity_camera'
    look_at(overview, center)
    overview.data.type = 'ORTHO'
    span_r = cam_basis['max_r'] - cam_basis['min_r']
    span_u = cam_basis['max_u'] - cam_basis['min_u']
    overview.data.ortho_scale = max(span_u, span_r * 0.68)
    c = features['ring_center_world']
    bpy.ops.object.camera_add(location=c - Vector((0.0, 1.05, -0.55)))
    close = bpy.context.object
    close.name = ASSET_ID + '_socket_close_camera'
    look_at(close, c)
    close.data.lens = 70
    bpy.ops.object.light_add(type='AREA', location=overview.location + Vector((0, -1.0, 2.2)))
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
    jobs = [
        (overview, [source_obj], 'source_shaded_same_angle.png'),
        (overview, output_objects, 'retopo_shaded_same_angle.png'),
        (close, output_objects, 'socket_close.png'),
    ]
    for cam, visible, fn in jobs:
        for m in meshes:
            m.hide_render = m not in visible
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(RENDER_DIR / fn)
        bpy.ops.render.render(write_still=True)
    for m in meshes:
        m.hide_render = m not in output_objects


def write_reports(features, output_objects, topology_reports, topology_gate, depth_report, primitive_rows):
    plane = features['plane']
    plane_report = {
        'asset_id': ASSET_ID,
        'policy': 'source mesh is measurement only; plane fit survives, source triangles do not',
        'plane_point': [plane['point'].x, plane['point'].y, plane['point'].z],
        'plane_normal': [plane['normal'].x, plane['normal'].y, plane['normal'].z],
        'plane_u': [plane['u'].x, plane['u'].y, plane['u'].z],
        'plane_v': [plane['v'].x, plane['v'].y, plane['v'].z],
        'seed_face_count': plane['seed_face_count'],
        'cluster_face_count': plane['cluster_face_count'],
        'source_plane_residual_mean': plane['source_plane_residual_mean'],
        'source_plane_residual_max': plane['source_plane_residual_max'],
    }
    plane_path = MODEL_DIR / 'measurement_report.json'
    plane_path.write_text(json.dumps({
        **plane_report,
        'source_vertex_count': features['source_vertex_count'],
        'source_polygon_count': features['source_polygon_count'],
        'deck_candidate_count': features['deck_candidate_count'],
        'bounds_uv': features['bounds_uv'],
        'outer_boundary_uv': features['outer_boundary_uv'],
        'ring_center_uv': features['ring_center_uv'],
        'socket_radius': features['socket_radius'],
        'forbidden_operations': ['copy_source_triangles', 'source_shell_solidify', 'blanket_vertex_snapping', 'dense_raycast_reconstruction'],
    }, indent=2) + '\n')
    primitives_path = MODEL_DIR / 'authored_solids.json'
    primitives_path.write_text(json.dumps({'asset_id': ASSET_ID, 'regions': primitive_rows}, indent=2) + '\n')
    landmarks_path = MODEL_DIR / 'retopo_landmarks.json'
    landmarks_path.write_text(json.dumps({
        'asset_id': ASSET_ID,
        'landmarks': {
            'main_plane': 'dominant upper armor plane fit from source face measurements',
            'outer_boundary': 'manufactured low-control polygon from measured boundary stations',
            'socket': 'regularized cylinder from measured ring center/radius',
            'edge_returns': 'authored closed strips from measured side seam stations',
            'lower_hull_seam': 'authored closed seam bar from measured lower endpoints',
        },
        'hatch': {'omitted': True, 'reason': 'socket/ring/plate architecture must pass before hatch detail'},
    }, indent=2) + '\n')
    stats = {'vertices': sum(r['vertices'] for r in topology_reports), 'polygons': sum(r['polygons'] for r in topology_reports), 'triangles': sum(r['triangles'] for r in topology_reports)}
    shape_status = 'pass' if depth_report['silhouette_iou'] >= 0.88 and depth_report['p95_abs_depth_error'] is not None and depth_report['p95_abs_depth_error'] <= 0.18 else 'red_depth_or_silhouette'
    candidate = bool(topology_gate['topology_pass'] and shape_status == 'pass')
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'measurement_to_authored_closed_solids_upper_glacis',
        'revision': REVISION,
        'candidate': candidate,
        'candidate_reason': 'requires zero boundary/nonmanifold edges plus depth/silhouette parity; cloud review still required for visual acceptance',
        'topology_status': topology_gate['topology_status'],
        'shape_review_status': shape_status,
        'source_glb': str(SOURCE_GLB.relative_to(ROOT)),
        'source_component': SOURCE_NEEDLE,
        'authoring_policy': 'Source cloud measures features only. Output regions are authored closed solids and never preserve source topology.',
        'current_prompt_contract': {
            'current_user_command': 'Continue upper-glacis recovery by replacing construction strategy with source-as-measurement and authored solids.',
            'forbidden_stale_premise': 'Tweaking f12-f16 meshes, preserving source triangles, source-shell solidify, blanket vertex snapping, or raycasting an entire surface back to the cloud.',
            'intended_mutation': 'Create a reusable scratch exporter that measures planes/boundary/socket/seams, discards sampled vertices, and generates independent closed hard-surface solids.',
            'why_this_satisfies_command': 'It makes the source cloud scaffolding and the authored solids the product, matching the new doctrine instead of tuning the failed loop.',
        },
        'statistics': stats,
        'topology_gate': topology_gate,
        'topology_reports': topology_reports,
        'measurement_report': str(plane_path.relative_to(ROOT)),
        'authored_solids': str(primitives_path.relative_to(ROOT)),
        'retopo_landmarks': str(landmarks_path.relative_to(ROOT)),
        'depth_parity': {'path': str((MODEL_DIR / 'depth_error_report.json').relative_to(ROOT)), **depth_report},
        'outputs': {
            'blend': str((BLEND_DIR / (ASSET_ID + '.blend')).relative_to(ROOT)),
            'glb': str((MODEL_DIR / (ASSET_ID + '.glb')).relative_to(ROOT)),
            'source_depth': str((RENDER_DIR / 'source_depth.png').relative_to(ROOT)),
            'retopo_depth': str((RENDER_DIR / 'retopo_depth.png').relative_to(ROOT)),
            'depth_abs_error': str((RENDER_DIR / 'depth_abs_error.png').relative_to(ROOT)),
            'depth_side_by_side': str((RENDER_DIR / 'depth_side_by_side.png').relative_to(ROOT)),
            'source_shaded_same_angle': str((RENDER_DIR / 'source_shaded_same_angle.png').relative_to(ROOT)),
            'retopo_shaded_same_angle': str((RENDER_DIR / 'retopo_shaded_same_angle.png').relative_to(ROOT)),
            'socket_close': str((RENDER_DIR / 'socket_close.png').relative_to(ROOT)),
        },
    }
    manifest_path = MODEL_DIR / 'model_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    note = f"# {ASSET_ID}\n\n"
    note += ('diagnostic candidate' if candidate else 'NOT a candidate') + '. Scratch diagnostic only; not production/cloud accepted.\n\n'
    note += '## Construction Strategy\n\nThe source mesh is used as a measuring instrument only. Plane, boundary, socket, and seam landmarks are measured, then fresh closed solids are authored: main glacis armor plate, left/right edge returns, lower hull seam, socket cylinder, and raised ring. No source topology is preserved.\n\n'
    note += '## Gates\n\n'
    note += f"- Topology: {topology_gate['topology_status']} boundary={topology_gate['boundary_edges_total']} nonmanifold={topology_gate['nonmanifold_edges_total']}\n"
    note += f"- Shape: {shape_status} IoU={depth_report['silhouette_iou']} p95={depth_report['p95_abs_depth_error']}\n"
    note += f"- Candidate: {candidate}\n\n"
    note += '## Stats\n\n'
    note += f"- Vertices: {stats['vertices']}\n- Polygons: {stats['polygons']}\n- Triangles: {stats['triangles']}\n\n"
    note += '## Lesson\n\nThis pass makes flat collapse harder by requiring named solids/regions instead of one dominant surface, and makes source-shell debris impossible by never consuming source triangles as output geometry.\n'
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    return manifest, manifest_path


def main():
    ensure_dirs()
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_obj = find_source_object()
    source_obj.name = ASSET_ID + '_hidden_source_upper_glacis'
    source_mat = make_mat(ASSET_ID + '_source_gray', (0.66, 0.67, 0.62, 1), 0.9)
    armor_mat = make_mat('authored_main_glacis_armor', (0.58, 0.61, 0.54, 1), 0.92)
    return_mat = make_mat('authored_edge_returns', (0.50, 0.54, 0.49, 1), 0.94)
    seam_mat = make_mat('authored_lower_hull_seam', (0.43, 0.46, 0.42, 1), 0.94)
    socket_mat = make_mat('authored_socket_cylinder', (0.45, 0.47, 0.44, 1), 0.93)
    ring_mat = make_mat('authored_raised_ring', (0.62, 0.64, 0.56, 1), 0.90)
    source_obj.data.materials.clear()
    source_obj.data.materials.append(source_mat)
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj != source_obj:
            obj.hide_viewport = True
            obj.hide_render = True
    features = measure_features(source_obj)
    objects = []
    primitive_rows = []
    plate, row = make_main_glacis_plate(features, armor_mat)
    objects.append(plate); primitive_rows.append(row)
    returns, rows = make_returns_and_seam(features, return_mat, seam_mat)
    objects.extend(returns); primitive_rows.extend(rows)
    socket, row = make_socket_cylinder(features, socket_mat)
    objects.append(socket); primitive_rows.append(row)
    ring, row = make_raised_ring(features, ring_mat)
    objects.append(ring); primitive_rows.append(row)
    topology_reports = [topology_report(o) for o in objects]
    topology_gate = aggregate_topology(topology_reports)
    cam = camera_basis(features['verts'])
    depth_report = depth_compare(features['bvh'], objects, cam)
    render_shaded(source_obj, objects, cam, features)
    blend_path = BLEND_DIR / (ASSET_ID + '.blend')
    glb_path = MODEL_DIR / (ASSET_ID + '.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    manifest, _manifest_path = write_reports(features, objects, topology_reports, topology_gate, depth_report, primitive_rows)
    print(json.dumps({
        'asset_id': ASSET_ID,
        'candidate': manifest['candidate'],
        'topology_gate': topology_gate,
        'shape_review_status': manifest['shape_review_status'],
        'stats': manifest['statistics'],
        'depth_report': depth_report,
        'glb': str(glb_path),
    }, indent=2))


main()
