"""Cluster-discovered hard-surface reconstruction for the Sherman upper glacis.

This scratch exporter is the reviewed successor to v04. It removes fixed UV
rectangle feature labels and discovers manufactured regions from source face
evidence: adjacency, normals, projected boundaries, and silhouette/depth position.
The source mesh remains measurement only; exported geometry is fresh closed solids.

Forbidden here:
- source triangle copying
- source-shell solidify
- blanket vertex snapping
- dense raycast reconstruction
- radial main-plate construction organized around the socket
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
ASSET_ID = 'real_sherman_upper_glacis_measurement_clusters_scratch_v04'
REVISION = 'v04-discovered-feature-clusters-authored-closed-solids'
MODEL_DIR = SCRATCH / 'models' / ASSET_ID
BLEND_DIR = SCRATCH / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH / 'notes'
DEPTH_W = 180
DEPTH_H = 126
SOCKET_SEGMENTS = 72
MIN_REQUIRED_SAMPLES = 24
REQUIRED_FEATURES = [
    'main_glacis',
    'left_shoulder',
    'right_shoulder',
    'front_face',
    'deck_transition',
    'socket',
    'ring',
]
FEATURE_ORDER = [
    'main_glacis',
    'left_shoulder',
    'right_shoulder',
    'front_face',
    'deck_transition',
    'left_return',
    'right_return',
]
THICKNESS_BY_FEATURE = {
    'main_glacis': 0.055,
    'left_shoulder': 0.080,
    'right_shoulder': 0.080,
    'front_face': 0.090,
    'deck_transition': 0.060,
    'left_return': 0.060,
    'right_return': 0.060,
}
RING_RADIAL_WIDTH = 0.032
RING_HEIGHT = 0.020
SOCKET_DEPTH = 0.090


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


def uv_to_plane(plane, u, v, offset=0.0):
    return plane['point'] + plane['u'] * u + plane['v'] * v + plane['normal'] * offset


def make_feature_plane(name, rows, fallback_plane):
    if not rows:
        plane = dict(fallback_plane)
        plane.update({'source_sample_count': 0, 'status': 'red_under_sampled'})
        return plane
    total = sum(max(r['area'], 1e-8) for r in rows)
    point = Vector((0, 0, 0))
    normal = Vector((0, 0, 0))
    ref = fallback_plane['normal']
    for r in rows:
        area = max(r['area'], 1e-8)
        n = r['normal']
        if n.dot(ref) < 0:
            n = -n
        point += r['centroid'] * area
        normal += n * area
    point /= total
    if normal.length < 1e-8:
        normal = ref.copy()
    normal.normalize()
    raw_normal = normal.copy()
    normal_clamped = False
    # Feature samples on noisy scan debris can average into a valid but unusable
    # plane. Keep the measured normal in the report, but author from the shared
    # manufactured reference plane when the feature normal would explode seams.
    if normal.dot(ref) < math.cos(math.radians(12.0)):
        normal = ref.copy()
        point = project_to_plane(fallback_plane, point)
        normal_clamped = True
    u = fallback_plane['u'] - normal * fallback_plane['u'].dot(normal)
    if u.length < 1e-5:
        u = Vector((1, 0, 0)) - normal * Vector((1, 0, 0)).dot(normal)
    if u.length < 1e-5:
        u = Vector((0, 1, 0)) - normal * Vector((0, 1, 0)).dot(normal)
    u.normalize()
    v = normal.cross(u).normalized()
    residuals = [abs((r['centroid'] - point).dot(normal)) for r in rows]
    return {
        'point': point,
        'normal': normal,
        'u': u,
        'v': v,
        'source_sample_count': len(rows),
        'raw_measured_normal': raw_normal,
        'normal_clamped_to_manufactured_reference': normal_clamped,
        'source_plane_residual_mean': sum(residuals) / max(1, len(residuals)),
        'source_plane_residual_max': max(residuals) if residuals else 0.0,
        'status': 'pass' if len(rows) >= MIN_REQUIRED_SAMPLES else 'red_under_sampled',
        'feature_name': name,
    }


def corners_from_uv_bounds(feature_plane, uv_bounds):
    u0, u1 = uv_bounds['u_min'], uv_bounds['u_max']
    v0, v1 = uv_bounds['v_min'], uv_bounds['v_max']
    return [
        uv_to_plane(feature_plane, u0, v0, 0.0),
        uv_to_plane(feature_plane, u1, v0, 0.0),
        uv_to_plane(feature_plane, u1, v1, 0.0),
        uv_to_plane(feature_plane, u0, v1, 0.0),
    ]


def convex_hull_2d(points):
    pts = sorted(set((round(u, 8), round(v, 8)) for u, v in points))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def simplify_polygon(points, max_points=10):
    if len(points) <= max_points:
        return points
    pts = list(points)
    def tri_area(a, b, c):
        return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) * 0.5
    while len(pts) > max_points:
        scored = []
        for i, p in enumerate(pts):
            scored.append((tri_area(pts[i - 1], p, pts[(i + 1) % len(pts)]), i))
        _area, idx = min(scored, key=lambda row: row[0])
        pts.pop(idx)
    return pts


def build_face_adjacency(polys):
    edge_faces = defaultdict(list)
    for fi, face in enumerate(polys):
        vs = list(face)
        for i, a in enumerate(vs):
            b = vs[(i + 1) % len(vs)]
            edge_faces[tuple(sorted((a, b)))].append(fi)
    adjacency = defaultdict(set)
    for faces in edge_faces.values():
        if len(faces) < 2:
            continue
        for a in faces:
            for b in faces:
                if a != b:
                    adjacency[a].add(b)
    return adjacency


def cluster_source_faces(face_rows, adjacency):
    normal_cos = math.cos(math.radians(14.0))
    rows_by_id = {r['face_index']: r for r in face_rows}
    seen = set()
    clusters = []
    for seed in face_rows:
        fi = seed['face_index']
        if fi in seen:
            continue
        stack = [fi]
        seen.add(fi)
        members = []
        ref = seed['normal'].copy()
        if ref.z < 0:
            ref = -ref
        while stack:
            cur = stack.pop()
            row = rows_by_id[cur]
            members.append(row)
            for nb in adjacency.get(cur, []):
                if nb in seen:
                    continue
                n = rows_by_id[nb]['normal']
                if n.dot(ref) < 0:
                    n = -n
                if n.dot(ref) >= normal_cos:
                    seen.add(nb)
                    stack.append(nb)
        clusters.append(cluster_summary(len(clusters), members))
    # Merge very small debris into nearest normal-compatible large cluster for measurement.
    large = [c for c in clusters if c['area'] >= 0.0008 and c['face_count'] >= 10]
    small = [c for c in clusters if c not in large]
    for c in small:
        candidates = [g for g in large if c['normal'].dot(g['normal']) >= math.cos(math.radians(18.0))]
        if not candidates:
            continue
        target = min(candidates, key=lambda g: (c['centroid'] - g['centroid']).length)
        target['merged_debris_cluster_ids'].append(c['cluster_id'])
        target['members'].extend(c['members'])
    return [cluster_summary(i, c['members'], c.get('merged_debris_cluster_ids', [])) for i, c in enumerate(large)]


def cluster_summary(cluster_id, members, merged_debris=None):
    merged_debris = merged_debris or []
    total = sum(max(r['area'], 1e-8) for r in members)
    centroid = Vector((0, 0, 0))
    normal = Vector((0, 0, 0))
    uv = []
    for r in members:
        area = max(r['area'], 1e-8)
        centroid += r['centroid'] * area
        n = r['normal']
        if n.z < 0:
            n = -n
        normal += n * area
        uv.append((r['u'], r['v']))
    centroid /= max(total, 1e-8)
    if normal.length < 1e-8:
        normal = Vector((0, 0, 1))
    normal.normalize()
    us = [p[0] for p in uv] or [0.0]
    vs = [p[1] for p in uv] or [0.0]
    return {
        'cluster_id': cluster_id,
        'members': list(members),
        'face_count': len(members),
        'area': total,
        'centroid': centroid,
        'normal': normal,
        'u_min': min(us), 'u_max': max(us), 'v_min': min(vs), 'v_max': max(vs),
        'u_center': sum(us) / len(us), 'v_center': sum(vs) / len(vs),
        'merged_debris_cluster_ids': merged_debris,
    }


def choose_cluster(clusters, predicate, score):
    candidates = [c for c in clusters if predicate(c)]
    if not candidates:
        return None
    return max(candidates, key=score)


def feature_from_cluster(name, cluster, fallback_plane, thickness, source_note):
    if not cluster:
        plane = dict(fallback_plane)
        plane.update({'source_sample_count': 0, 'status': 'red_missing_cluster', 'feature_name': name})
        return {'name': name, 'plane': plane, 'uv_bounds': {}, 'world_corners': [], 'boundary_uv': [], 'thickness': thickness, 'source_sample_count': 0, 'status': 'red_missing_cluster', 'source_cluster_ids': []}
    plane = make_feature_plane(name, cluster['members'], fallback_plane)
    # Keep cluster-discovered boundaries. Use member centroids plus face vertices projected to the fitted plane.
    points = []
    for r in cluster['members']:
        points.append((r['u'], r['v']))
        for p in r.get('points', []):
            points.append(plane_to_uv(fallback_plane, p))
    hull = simplify_polygon(convex_hull_2d(points), 10)
    corners = [uv_to_plane(plane, u, v, 0.0) for u, v in hull]
    return {
        'name': name,
        'plane': plane,
        'uv_bounds': {'u_min': cluster['u_min'], 'u_max': cluster['u_max'], 'v_min': cluster['v_min'], 'v_max': cluster['v_max']},
        'world_corners': corners,
        'boundary_uv': hull,
        'thickness': thickness,
        'source_sample_count': cluster['face_count'],
        'projected_cluster_area': cluster['area'],
        'source_cluster_ids': [cluster['cluster_id']],
        'merged_debris_cluster_ids': cluster.get('merged_debris_cluster_ids', []),
        'source_note': source_note,
        'status': plane['status'] if len(hull) >= 3 else 'red_invalid_boundary',
    }


def discover_feature_clusters(clusters, source_uv_bounds):
    u_min, u_max = source_uv_bounds['u_min'], source_uv_bounds['u_max']
    v_min, v_max = source_uv_bounds['v_min'], source_uv_bounds['v_max']
    u_span = max(1e-5, u_max - u_min)
    v_span = max(1e-5, v_max - v_min)
    u_mid = (u_min + u_max) * 0.5
    v_mid = (v_min + v_max) * 0.5
    # These predicates use cluster position as evidence after adjacency/normal clustering;
    # they do not create rectangular features from bounds.
    main = choose_cluster(
        clusters,
        lambda c: abs(c['u_center'] - u_mid) < u_span * 0.32 and abs(c['v_center'] - v_mid) < v_span * 0.34 and c['normal'].z > 0.40,
        lambda c: c['area'],
    )
    front = choose_cluster(
        clusters,
        lambda c: c['v_center'] < v_min + v_span * 0.43,
        lambda c: c['area'] * (1.0 + max(0.0, v_mid - c['v_center'])),
    )
    deck = choose_cluster(
        clusters,
        lambda c: c['v_center'] > v_max - v_span * 0.43,
        lambda c: c['area'] * (1.0 + max(0.0, c['v_center'] - v_mid)),
    )
    left_shoulder = choose_cluster(
        clusters,
        lambda c: c['u_center'] < u_min + u_span * 0.42 and c is not front and c is not deck,
        lambda c: c['area'] * (1.0 + max(0.0, u_mid - c['u_center'])),
    )
    right_shoulder = choose_cluster(
        clusters,
        lambda c: c['u_center'] > u_max - u_span * 0.42 and c is not front and c is not deck,
        lambda c: c['area'] * (1.0 + max(0.0, c['u_center'] - u_mid)),
    )
    left_return = choose_cluster(
        clusters,
        lambda c: c['u_min'] <= u_min + u_span * 0.15,
        lambda c: c['area'] * (1.0 + max(0.0, u_mid - c['u_center'])),
    )
    right_return = choose_cluster(
        clusters,
        lambda c: c['u_max'] >= u_max - u_span * 0.15,
        lambda c: c['area'] * (1.0 + max(0.0, c['u_center'] - u_mid)),
    )
    return {
        'main_glacis': main,
        'front_face': front,
        'deck_transition': deck,
        'left_shoulder': left_shoulder,
        'right_shoulder': right_shoulder,
        'left_return': left_return,
        'right_return': right_return,
    }

def feature_json(feature):
    plane = feature['plane']
    return {
        'name': feature['name'],
        'status': feature['status'],
        'source_sample_count': feature['source_sample_count'],
        'uv_bounds': feature['uv_bounds'],
        'world_corners': [[p.x, p.y, p.z] for p in feature['world_corners']],
        'boundary_uv': feature.get('boundary_uv', []),
        'source_cluster_ids': feature.get('source_cluster_ids', []),
        'merged_debris_cluster_ids': feature.get('merged_debris_cluster_ids', []),
        'projected_cluster_area': feature.get('projected_cluster_area'),
        'thickness': feature['thickness'],
        'plane': {
            'point': [plane['point'].x, plane['point'].y, plane['point'].z],
            'normal': [plane['normal'].x, plane['normal'].y, plane['normal'].z],
            'u': [plane['u'].x, plane['u'].y, plane['u'].z],
            'v': [plane['v'].x, plane['v'].y, plane['v'].z],
            'source_plane_residual_mean': plane.get('source_plane_residual_mean', 0.0),
            'source_plane_residual_max': plane.get('source_plane_residual_max', 0.0),
            'raw_measured_normal': [plane.get('raw_measured_normal', plane['normal']).x, plane.get('raw_measured_normal', plane['normal']).y, plane.get('raw_measured_normal', plane['normal']).z],
            'normal_clamped_to_manufactured_reference': plane.get('normal_clamped_to_manufactured_reference', False),
        },
    }


def measure_features(source_obj):
    verts, polys, normals = world_mesh_data(source_obj)
    fallback_plane = fit_global_reference_plane(verts, polys, normals)
    source_bvh = build_bvh(verts, polys)
    face_rows = []
    for fi, face in enumerate(polys):
        pts = [verts[i] for i in face]
        area, centroid = polygon_area_centroid(pts)
        if area <= 1e-10:
            continue
        u, v = plane_to_uv(fallback_plane, centroid)
        face_rows.append({'face_index': fi, 'centroid': centroid, 'normal': normals[fi], 'area': area, 'u': u, 'v': v, 'points': pts})
    z_vals = [p.z for p in verts]
    uv_points = [plane_to_uv(fallback_plane, p) for p in verts]
    us = [u for u, _v in uv_points]
    vs = [v for _u, v in uv_points]
    source_uv_bounds = {'u_min': q(us, 0.025), 'u_max': q(us, 0.975), 'v_min': q(vs, 0.035), 'v_max': q(vs, 0.965)}
    adjacency = build_face_adjacency(polys)
    clusters = cluster_source_faces(face_rows, adjacency)
    assigned = discover_feature_clusters(clusters, source_uv_bounds)
    features = {}
    for name in FEATURE_ORDER:
        features[name] = feature_from_cluster(
            name,
            assigned.get(name),
            fallback_plane,
            THICKNESS_BY_FEATURE[name],
            'discovered from adjacent source face normal cluster; not a fixed UV rectangle',
        )
    # Socket/ring are landmark fits from the measured cloud, secondary to hull clusters.
    center_u = sum(u for u, _v in uv_points) / len(uv_points)
    center_v = sum(v for _u, v in uv_points) / len(uv_points)
    top_rows = [(p, *plane_to_uv(fallback_plane, p)) for p in verts if p.z >= q(z_vals, 0.42)]
    if not top_rows:
        top_rows = [(p, *plane_to_uv(fallback_plane, p)) for p in verts]
    ring_candidates = []
    for p, u, v in top_rows:
        r = math.hypot(u - center_u, v - center_v)
        if 0.08 <= r <= 0.42 and p.z >= q(z_vals, 0.58):
            ring_candidates.append((p, u, v, r))
    if len(ring_candidates) < 20:
        ring_candidates = [(p, u, v, math.hypot(u - center_u, v - center_v)) for p, u, v in top_rows]
    ring_u = sum(u for _p, u, _v, _r in ring_candidates) / len(ring_candidates)
    ring_v = sum(v for _p, _u, v, _r in ring_candidates) / len(ring_candidates)
    radii = sorted(math.hypot(u - ring_u, v - ring_v) for _p, u, v, _r in ring_candidates)
    socket_radius = max(0.105, min(0.180, radii[int(len(radii) * 0.52)] if radii else 0.13))
    socket_plane = features['main_glacis']['plane'] if features['main_glacis']['status'] == 'pass' else fallback_plane
    features['socket'] = {
        'name': 'socket', 'plane': socket_plane,
        'uv_bounds': {'u_min': ring_u - socket_radius, 'u_max': ring_u + socket_radius, 'v_min': ring_v - socket_radius, 'v_max': ring_v + socket_radius},
        'world_corners': [], 'boundary_uv': [], 'thickness': SOCKET_DEPTH,
        'source_sample_count': len(ring_candidates), 'status': 'pass' if len(ring_candidates) >= MIN_REQUIRED_SAMPLES else 'red_under_sampled',
        'center_uv': [ring_u, ring_v], 'center_world': uv_to_plane(socket_plane, ring_u, ring_v, 0.0), 'radius': socket_radius,
    }
    features['ring'] = {
        'name': 'ring', 'plane': socket_plane,
        'uv_bounds': {'u_min': ring_u - socket_radius - RING_RADIAL_WIDTH, 'u_max': ring_u + socket_radius + RING_RADIAL_WIDTH, 'v_min': ring_v - socket_radius - RING_RADIAL_WIDTH, 'v_max': ring_v + socket_radius + RING_RADIAL_WIDTH},
        'world_corners': [], 'boundary_uv': [], 'thickness': RING_HEIGHT,
        'source_sample_count': len(ring_candidates), 'status': 'pass' if len(ring_candidates) >= MIN_REQUIRED_SAMPLES else 'red_under_sampled',
        'center_uv': [ring_u, ring_v], 'center_world': uv_to_plane(socket_plane, ring_u, ring_v, 0.0),
        'inner_radius': socket_radius + 0.004, 'outer_radius': socket_radius + 0.004 + RING_RADIAL_WIDTH,
    }
    missing = [name for name in REQUIRED_FEATURES if name not in features or features[name]['status'] != 'pass']
    return {
        'verts': verts,
        'polys': polys,
        'bvh': source_bvh,
        'fallback_plane': fallback_plane,
        'features': features,
        'clusters': clusters,
        'cluster_assignments': {name: (assigned[name]['cluster_id'] if assigned.get(name) else None) for name in assigned},
        'missing_required_features': missing,
        'source_vertex_count': len(verts),
        'source_polygon_count': len(polys),
        'source_z_quantiles': {'z08': q(z_vals, 0.08), 'z25': q(z_vals, 0.25), 'z70': q(z_vals, 0.70), 'z92': q(z_vals, 0.92)},
        'source_uv_bounds': source_uv_bounds,
    }

def add_uvs(obj, name='uv_measurement_features_v04'):
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


def make_closed_solid_from_feature(feature, name, mat, role):
    n = feature['plane']['normal']
    top = feature['world_corners']
    if len(top) < 3:
        raise RuntimeError(f'feature {role} has invalid boundary with {len(top)} points')
    bottom = [p - n * feature['thickness'] for p in top]
    verts = top + bottom
    count = len(top)
    faces = [tuple(range(count)), tuple(reversed(range(count, count * 2)))]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, j + count, i + count))
    return make_mesh_object(
        name,
        verts,
        faces,
        mat,
        role,
        'closed polygonal prism authored from discovered source feature cluster boundary and feature plane normal',
    )

def make_socket_cylinder(feature, mat):
    plane = feature['plane']
    cu, cv = feature['center_uv']
    radius = feature['radius'] * 0.985
    verts = []
    top = []
    bottom = []
    for i in range(SOCKET_SEGMENTS):
        a = math.tau * i / SOCKET_SEGMENTS
        u = cu + math.cos(a) * radius
        v = cv + math.sin(a) * radius
        top.append(len(verts)); verts.append(uv_to_plane(plane, u, v, 0.004))
        bottom.append(len(verts)); verts.append(uv_to_plane(plane, u, v, -SOCKET_DEPTH))
    faces = []
    for i in range(SOCKET_SEGMENTS):
        j = (i + 1) % SOCKET_SEGMENTS
        faces.append((top[i], top[j], bottom[j], bottom[i]))
    faces.append(tuple(reversed(top)))
    faces.append(tuple(bottom))
    return make_mesh_object(ASSET_ID + '_socket_secondary_closed_cylinder', verts, faces, mat, 'socket', 'secondary closed socket cylinder measured from feature cloud landmark', smooth=True)


def make_raised_ring(feature, mat):
    plane = feature['plane']
    cu, cv = feature['center_uv']
    inner = feature['inner_radius']
    outer = feature['outer_radius']
    verts = []
    idx = {'outer_low': [], 'outer_high': [], 'inner_high': [], 'inner_low': []}
    for i in range(SOCKET_SEGMENTS):
        a = math.tau * i / SOCKET_SEGMENTS
        for key, rad, off in (
            ('outer_low', outer, 0.006),
            ('outer_high', outer, RING_HEIGHT),
            ('inner_high', inner, RING_HEIGHT * 0.90),
            ('inner_low', inner, 0.006),
        ):
            idx[key].append(len(verts)); verts.append(uv_to_plane(plane, cu + math.cos(a) * rad, cv + math.sin(a) * rad, off))
    faces = []
    for i in range(SOCKET_SEGMENTS):
        j = (i + 1) % SOCKET_SEGMENTS
        faces.append((idx['outer_high'][i], idx['outer_high'][j], idx['inner_high'][j], idx['inner_high'][i]))
        faces.append((idx['outer_low'][j], idx['outer_low'][i], idx['outer_high'][i], idx['outer_high'][j]))
        faces.append((idx['inner_low'][i], idx['inner_low'][j], idx['inner_high'][j], idx['inner_high'][i]))
        faces.append((idx['outer_low'][i], idx['inner_low'][i], idx['inner_low'][j], idx['outer_low'][j]))
    return make_mesh_object(ASSET_ID + '_raised_ring_secondary_closed_solid', verts, faces, mat, 'ring', 'secondary closed raised ring; not the visual organizing feature', smooth=True)


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


def projected_poly_area(points, cam):
    if len(points) < 3:
        return 0.0
    coords = [((p - cam['center']).dot(cam['right']), (p - cam['center']).dot(cam['up'])) for p in points]
    area = 0.0
    for i in range(1, len(coords) - 1):
        ax, ay = coords[i][0] - coords[0][0], coords[i][1] - coords[0][1]
        bx, by = coords[i + 1][0] - coords[0][0], coords[i + 1][1] - coords[0][1]
        area += abs(ax * by - ay * bx) * 0.5
    return area


def region_area_report(objects, cam):
    report = {}
    total = 0.0
    for obj in objects:
        role = obj.get('role', obj.name)
        area = 0.0
        for poly in obj.data.polygons:
            pts = [obj.matrix_world @ obj.data.vertices[i].co for i in poly.vertices]
            area += projected_poly_area(pts, cam)
        report[role] = report.get(role, 0.0) + area
        total += area
    ring_socket = report.get('ring', 0.0) + report.get('socket', 0.0)
    non_ring = max(0.0, total - ring_socket)
    pass_area = total > 0 and non_ring > ring_socket * 2.0 and ring_socket / total < 0.35
    return {
        'status': 'pass' if pass_area else 'red_ring_socket_visual_dominance',
        'total_projected_area': total,
        'non_ring_projected_area': non_ring,
        'ring_socket_projected_area': ring_socket,
        'ring_socket_fraction': ring_socket / total if total else None,
        'regions': report,
    }


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
    c = features['features']['ring']['center_world']
    bpy.ops.object.camera_add(location=c - Vector((0.0, 1.05, -0.55)))
    close = bpy.context.object
    close.name = ASSET_ID + '_feature_close_camera'
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
        (close, output_objects, 'feature_close.png'),
    ]
    for cam, visible, fn in jobs:
        for m in meshes:
            m.hide_render = m not in visible
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(RENDER_DIR / fn)
        bpy.ops.render.render(write_still=True)
    for m in meshes:
        m.hide_render = m not in output_objects


def cluster_json(cluster):
    return {
        'cluster_id': cluster['cluster_id'],
        'face_count': cluster['face_count'],
        'projected_area': cluster['area'],
        'centroid': [cluster['centroid'].x, cluster['centroid'].y, cluster['centroid'].z],
        'normal': [cluster['normal'].x, cluster['normal'].y, cluster['normal'].z],
        'uv_bounds': {'u_min': cluster['u_min'], 'u_max': cluster['u_max'], 'v_min': cluster['v_min'], 'v_max': cluster['v_max']},
        'merged_debris_cluster_ids': cluster.get('merged_debris_cluster_ids', []),
    }

def write_missing_feature_manifest(features):
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'measurement_cluster_discovery_upper_glacis',
        'revision': REVISION,
        'candidate': False,
        'shape_review_status': 'red_missing_required_feature_cluster',
        'missing_required_features': features['missing_required_features'],
        'required_features': REQUIRED_FEATURES,
        'source_component': SOURCE_NEEDLE,
        'authoring_policy': 'Source cloud is measurement only; export stops if required named features cannot be measured.',
    }
    (MODEL_DIR / 'model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (MODEL_DIR / 'measurement_report.json').write_text(json.dumps({
        'asset_id': ASSET_ID,
        'status': 'red_missing_required_feature_cluster',
        'features': {name: feature_json(f) for name, f in features['features'].items() if name in FEATURE_ORDER},
        'missing_required_features': features['missing_required_features'],
    }, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


def write_reports(features, output_objects, topology_reports, topology_gate, depth_report, area_report, primitive_rows):
    measurement_path = MODEL_DIR / 'measurement_report.json'
    measurement_path.write_text(json.dumps({
        'asset_id': ASSET_ID,
        'status': 'pass' if not features['missing_required_features'] else 'red_missing_required_feature_cluster',
        'policy': 'source mesh is measurement only; named features are measured, then fresh closed solids are authored',
        'source_component': SOURCE_NEEDLE,
        'source_vertex_count': features['source_vertex_count'],
        'source_polygon_count': features['source_polygon_count'],
        'source_uv_bounds': features['source_uv_bounds'],
        'source_z_quantiles': features['source_z_quantiles'],
        'required_features': REQUIRED_FEATURES,
        'features': {name: feature_json(f) for name, f in features['features'].items() if name in REQUIRED_FEATURES or name in FEATURE_ORDER},
        'cluster_assignments': features.get('cluster_assignments', {}),
        'forbidden_operations': ['copy_source_triangles', 'source_shell_solidify', 'blanket_vertex_snapping', 'dense_raycast_reconstruction', 'radial_main_plate_from_socket'],
        'plane_authoring_note': 'raw feature normals are measured; outlier normals are clamped to the manufactured reference plane before authoring to prevent exploded closed solids',
    }, indent=2) + '\n')
    cluster_path = MODEL_DIR / 'feature_cluster_report.json'
    cluster_path.write_text(json.dumps({'asset_id': ASSET_ID, 'clusters': [cluster_json(c) for c in features.get('clusters', [])], 'assignments': features.get('cluster_assignments', {})}, indent=2) + '\n')
    solids_path = MODEL_DIR / 'authored_solids.json'
    solids_path.write_text(json.dumps({'asset_id': ASSET_ID, 'regions': primitive_rows}, indent=2) + '\n')
    landmarks_path = MODEL_DIR / 'retopo_landmarks.json'
    landmarks_path.write_text(json.dumps({
        'asset_id': ASSET_ID,
        'landmarks': {
            'main_glacis': 'named feature plate with its own measured plane and world_corners',
            'left_shoulder': 'closed shoulder solid from measured side feature bounds',
            'right_shoulder': 'closed shoulder solid from measured side feature bounds',
            'front_face': 'closed front/lower face feature, not endpoint wall extrusion',
            'deck_transition': 'closed upper/deck transition feature behind socket',
            'left_return': 'closed side-return feature',
            'right_return': 'closed side-return feature',
            'socket': 'secondary measured cylinder landmark',
            'ring': 'secondary measured annular ring landmark',
        },
        'hatch': {'omitted': True, 'reason': 'feature decomposition must pass before hatch detail'},
    }, indent=2) + '\n')
    stats = {'vertices': sum(r['vertices'] for r in topology_reports), 'polygons': sum(r['polygons'] for r in topology_reports), 'triangles': sum(r['triangles'] for r in topology_reports)}
    shape_status = 'diagnostic_promising' if depth_report['silhouette_iou'] > 0.64 and (depth_report['p95_abs_depth_error'] or 999) < 0.364 and area_report['status'] == 'pass' else 'red_depth_or_silhouette'
    candidate = bool(topology_gate['topology_pass'] and area_report['status'] == 'pass' and shape_status == 'diagnostic_promising')
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'measurement_cluster_discovery_upper_glacis',
        'revision': REVISION,
        'candidate': candidate,
        'candidate_reason': 'requires required feature measurements, closed independent regions, topology pass, non-ring projected area dominance, and improved shape diagnostics; cloud review still required',
        'topology_status': topology_gate['topology_status'],
        'shape_review_status': shape_status,
        'source_glb': str(SOURCE_GLB.relative_to(ROOT)),
        'source_component': SOURCE_NEEDLE,
        'authoring_policy': 'Source cloud measures named features only. Output solids are authored from measured constraints and do not preserve source topology.',
        'current_prompt_contract': {
            'current_user_command': 'Implement v04 feature-decomposition scratch pass from PR review.',
            'forbidden_stale_premise': 'Tweaking v02 constants, preserving source topology, source-shell solidify, blanket snapping, or letting topology pass imply visual pass.',
            'intended_mutation': 'Create a new v04 exporter and artifacts that measure named manufactured hull features and author separate closed solids.',
            'why_this_satisfies_command': 'The review says the next useful artifact proves feature decomposition, not a prettier v02 slab.',
        },
        'required_features': REQUIRED_FEATURES,
        'missing_required_features': features['missing_required_features'],
        'statistics': stats,
        'topology_gate': topology_gate,
        'topology_reports': topology_reports,
        'region_area_report': area_report,
        'measurement_report': str(measurement_path.relative_to(ROOT)),
        'feature_cluster_report': str(cluster_path.relative_to(ROOT)),
        'authored_solids': str(solids_path.relative_to(ROOT)),
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
            'feature_close': str((RENDER_DIR / 'feature_close.png').relative_to(ROOT)),
        },
    }
    (MODEL_DIR / 'model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    note = f"# {ASSET_ID}\n\n"
    note += ('diagnostic candidate' if candidate else 'NOT a candidate') + '. Scratch diagnostic only; not production/cloud accepted.\n\n'
    note += '## Construction Strategy\n\nCluster discovery replaces the v04 UV-rectangle labels. The source cloud is clustered by adjacency and face normals, then named manufactured regions are authored as fresh closed solids from cluster boundaries.\n\n'
    note += '## Gates\n\n'
    note += f"- Topology: {topology_gate['topology_status']} boundary={topology_gate['boundary_edges_total']} nonmanifold={topology_gate['nonmanifold_edges_total']}\n"
    note += f"- Region area: {area_report['status']} ring_socket_fraction={area_report['ring_socket_fraction']}\n"
    note += f"- Shape: {shape_status} IoU={depth_report['silhouette_iou']} p95={depth_report['p95_abs_depth_error']}\n"
    note += f"- Candidate: {candidate}\n\n"
    note += '## Stats\n\n'
    note += f"- Vertices: {stats['vertices']}\n- Polygons: {stats['polygons']}\n- Triangles: {stats['triangles']}\n\n"
    note += '## Lesson\n\nThis pass is useful if it proves manufactured feature clusters can improve silhouette while preserving manifold topology. It is still red unless visual/cloud review later accepts the manufactured Sherman read.\n'
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    return manifest


def main():
    ensure_dirs()
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_obj = find_source_object()
    source_obj.name = ASSET_ID + '_hidden_source_upper_glacis'
    source_mat = make_mat(ASSET_ID + '_source_gray', (0.66, 0.67, 0.62, 1), 0.9)
    mats = {
        'main_glacis': make_mat('feature_main_glacis', (0.58, 0.61, 0.54, 1), 0.92),
        'left_shoulder': make_mat('feature_left_shoulder', (0.50, 0.54, 0.49, 1), 0.94),
        'right_shoulder': make_mat('feature_right_shoulder', (0.50, 0.54, 0.49, 1), 0.94),
        'front_face': make_mat('feature_front_face', (0.46, 0.50, 0.45, 1), 0.94),
        'deck_transition': make_mat('feature_deck_transition', (0.55, 0.58, 0.52, 1), 0.93),
        'left_return': make_mat('feature_left_return', (0.43, 0.47, 0.42, 1), 0.94),
        'right_return': make_mat('feature_right_return', (0.43, 0.47, 0.42, 1), 0.94),
        'socket': make_mat('feature_socket_secondary', (0.45, 0.47, 0.44, 1), 0.93),
        'ring': make_mat('feature_ring_secondary', (0.62, 0.64, 0.56, 1), 0.90),
    }
    source_obj.data.materials.clear()
    source_obj.data.materials.append(source_mat)
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj != source_obj:
            obj.hide_viewport = True
            obj.hide_render = True
    features = measure_features(source_obj)
    if features['missing_required_features']:
        write_missing_feature_manifest(features)
        return
    objects = []
    primitive_rows = []
    for name in FEATURE_ORDER:
        obj = make_closed_solid_from_feature(features['features'][name], ASSET_ID + '_' + name + '_closed_solid', mats[name], name)
        objects.append(obj)
        primitive_rows.append({
            'region': name,
            'topology': 'closed feature plate prism',
            'source_use': 'named feature plane/bounds/corners only',
            'source_sample_count': features['features'][name]['source_sample_count'],
            'thickness': features['features'][name]['thickness'],
        })
    socket = make_socket_cylinder(features['features']['socket'], mats['socket'])
    ring = make_raised_ring(features['features']['ring'], mats['ring'])
    objects.extend([socket, ring])
    primitive_rows.extend([
        {'region': 'socket', 'topology': 'closed secondary cylinder', 'source_use': 'measured socket center/radius only', 'source_sample_count': features['features']['socket']['source_sample_count'], 'radius': features['features']['socket']['radius']},
        {'region': 'ring', 'topology': 'closed secondary annular prism', 'source_use': 'measured ring center/radius only', 'source_sample_count': features['features']['ring']['source_sample_count'], 'inner_radius': features['features']['ring']['inner_radius'], 'outer_radius': features['features']['ring']['outer_radius']},
    ])
    topology_reports = [topology_report(o) for o in objects]
    topology_gate = aggregate_topology(topology_reports)
    cam = camera_basis(features['verts'])
    area_report = region_area_report(objects, cam)
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
    manifest = write_reports(features, objects, topology_reports, topology_gate, depth_report, area_report, primitive_rows)
    print(json.dumps({
        'asset_id': ASSET_ID,
        'candidate': manifest['candidate'],
        'topology_gate': topology_gate,
        'shape_review_status': manifest['shape_review_status'],
        'region_area_report': area_report,
        'stats': manifest['statistics'],
        'depth_report': depth_report,
        'glb': str(glb_path),
    }, indent=2))


main()
