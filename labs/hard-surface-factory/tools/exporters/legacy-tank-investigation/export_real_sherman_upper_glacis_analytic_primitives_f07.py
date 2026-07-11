
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
ASSET_ID = 'real_sherman_upper_glacis_analytic_primitives_scratch_f07'
REVISION = 'f07-source-silhouette-analytic-primitive-fused-upper-glacis'
MODEL_DIR = SCRATCH / 'models' / ASSET_ID
BLEND_DIR = SCRATCH / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH / 'notes'
SOURCE_NEEDLE = 'source_component_0_upper_front_glacis'
ROLE = 'source_component_0_upper_front_glacis_assembly'
DEPTH_W = 160
DEPTH_H = 112


def ensure_dirs():
    for d in (MODEL_DIR, BLEND_DIR, RENDER_DIR, NOTES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def reset_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def make_mat(name, color, rough=0.88):
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


def bounds(points):
    return {
        'min_x': min(p.x for p in points), 'max_x': max(p.x for p in points),
        'min_y': min(p.y for p in points), 'max_y': max(p.y for p in points),
        'min_z': min(p.z for p in points), 'max_z': max(p.z for p in points),
    }



def convex_hull_2d(points):
    pts = sorted(set((round(p.x, 6), round(p.y, 6)) for p in points))
    if len(pts) <= 3:
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
    hull = lower[:-1] + upper[:-1]
    # Keep the convex identity but remove near-collinear micro-steps.
    simplified = []
    for p in hull:
        simplified.append(p)
        while len(simplified) >= 3:
            a, b, c = simplified[-3], simplified[-2], simplified[-1]
            ab = math.hypot(b[0] - a[0], b[1] - a[1])
            bc = math.hypot(c[0] - b[0], c[1] - b[1])
            if ab < 0.018 or bc < 0.018:
                simplified.pop(-2)
            else:
                break
    return simplified if len(simplified) >= 4 else hull


def ray_polygon_intersection(cx, cy, angle, polygon):
    dx = math.cos(angle)
    dy = math.sin(angle)
    best = None
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        ex = x2 - x1
        ey = y2 - y1
        den = dx * (-ey) - dy * (-ex)
        if abs(den) < 1e-8:
            continue
        rx = x1 - cx
        ry = y1 - cy
        t = (rx * (-ey) - ry * (-ex)) / den
        u = (dx * ry - dy * rx) / den
        if t > 0 and -1e-6 <= u <= 1.0 + 1e-6:
            if best is None or t < best[0]:
                best = (t, cx + t * dx, cy + t * dy)
    if best:
        return best[1], best[2]
    return rect_intersection(cx, cy, angle, min(p[0] for p in polygon), max(p[0] for p in polygon), min(p[1] for p in polygon), max(p[1] for p in polygon))

def connected_components(polys):
    v2f = defaultdict(list)
    for fi, face in enumerate(polys):
        for v in face:
            v2f[v].append(fi)
    seen = set()
    comps = []
    for fi in range(len(polys)):
        if fi in seen:
            continue
        stack = [fi]
        seen.add(fi)
        faces = []
        verts = set()
        while stack:
            f = stack.pop()
            faces.append(f)
            for v in polys[f]:
                verts.add(v)
                for nf in v2f[v]:
                    if nf not in seen:
                        seen.add(nf)
                        stack.append(nf)
        comps.append({'faces': faces, 'verts': sorted(verts)})
    return comps


def component_summary(comp, verts, polys, normals):
    pts = [verts[i] for i in comp['verts']]
    b = bounds(pts)
    ns = [normals[i] for i in comp['faces']]
    avg = Vector((0, 0, 0))
    for n in ns:
        avg += n
    if ns:
        avg.normalize()
    spread = sum(max(0.0, 1.0 - avg.dot(n)) for n in ns) / max(1, len(ns))
    return {
        'faces': len(comp['faces']),
        'tris': sum(max(0, len(polys[i]) - 2) for i in comp['faces']),
        'verts': len(comp['verts']),
        'min': [b['min_x'], b['min_y'], b['min_z']],
        'max': [b['max_x'], b['max_y'], b['max_z']],
        'center': [(b['min_x'] + b['max_x']) * 0.5, (b['min_y'] + b['max_y']) * 0.5, (b['min_z'] + b['max_z']) * 0.5],
        'size': [b['max_x'] - b['min_x'], b['max_y'] - b['min_y'], b['max_z'] - b['min_z']],
        'avg_normal': [avg.x, avg.y, avg.z],
        'normal_spread': spread,
    }


def classify_source(verts, polys, normals):
    b = bounds(verts)
    comps = connected_components(polys)
    summaries = [component_summary(c, verts, polys, normals) for c in comps]
    summaries.sort(key=lambda s: s['tris'], reverse=True)
    z_hi = q([p.z for p in verts], 0.86)
    candidates = []
    for s in summaries:
        sx, sy, sz = s['size']
        cx, cy, cz = s['center']
        if s['tris'] > 120 and cz > z_hi - 0.035 and 0.12 < sx < 0.48 and 0.12 < sy < 0.48 and sz < 0.04:
            ratio = sx / max(0.001, sy)
            if 0.55 <= ratio <= 1.75:
                candidates.append(s)
    ring = candidates[0] if candidates else summaries[0]
    rmin = ring['min']; rmax = ring['max']
    rcx = (rmin[0] + rmax[0]) * 0.5
    rcy = (rmin[1] + rmax[1]) * 0.5
    rx_outer = (rmax[0] - rmin[0]) * 0.5
    ry_outer = (rmax[1] - rmin[1]) * 0.5
    ring_pts = []
    for p in verts:
        if rmin[0] - 0.01 <= p.x <= rmax[0] + 0.01 and rmin[1] - 0.01 <= p.y <= rmax[1] + 0.01 and p.z >= rmin[2] - 0.01:
            rr = math.sqrt(((p.x - rcx) / max(rx_outer, 1e-4)) ** 2 + ((p.y - rcy) / max(ry_outer, 1e-4)) ** 2)
            if 0.2 < rr < 1.2:
                ring_pts.append(rr)
    inner_ratio = max(0.48, min(0.78, q(ring_pts, 0.18) if ring_pts else 0.64))
    details = []
    for s in summaries:
        sx, sy, sz = s['size']
        cx, cy, cz = s['center']
        dist = math.sqrt(((cx - rcx) / max(rx_outer, 1e-4)) ** 2 + ((cy - rcy) / max(ry_outer, 1e-4)) ** 2)
        if s['tris'] >= 40 and cz > z_hi - 0.075 and dist > inner_ratio * 0.72 and sx < 0.16 and sy < 0.16 and sz > 0.006:
            details.append(s)
    details = sorted(details, key=lambda s: (s['tris'], s['size'][0] * s['size'][1]), reverse=True)[:5]
    return {
        'source_bounds': b,
        'component_count': len(summaries),
        'outer_hull': convex_hull_2d([p for p in verts if p.z >= q([v.z for v in verts], 0.08)]),
        'top_components': summaries[:18],
        'ring': {
            'center': [rcx, rcy],
            'rx_outer': rx_outer,
            'ry_outer': ry_outer,
            'inner_ratio': inner_ratio,
            'z_min': rmin[2],
            'z_max': rmax[2],
            'source_component_summary': ring,
        },
        'detail_candidates': details,
    }


def chord_segments(rx, ry):
    r = max(rx, ry)
    target_error = r * 0.005
    if target_error <= 0:
        return 32
    # sagitta approx: error = r * (1 - cos(pi / n))
    n = math.pi / max(0.001, math.acos(max(-1.0, min(1.0, 1.0 - target_error / r))))
    return max(24, min(48, int(math.ceil(n))))


def rect_intersection(cx, cy, angle, x0, x1, y0, y1):
    dx = math.cos(angle)
    dy = math.sin(angle)
    candidates = []
    if abs(dx) > 1e-6:
        for x in (x0, x1):
            t = (x - cx) / dx
            y = cy + t * dy
            if t > 0 and y0 - 1e-6 <= y <= y1 + 1e-6:
                candidates.append((t, x, y))
    if abs(dy) > 1e-6:
        for y in (y0, y1):
            t = (y - cy) / dy
            x = cx + t * dx
            if t > 0 and x0 - 1e-6 <= x <= x1 + 1e-6:
                candidates.append((t, x, y))
    if not candidates:
        return cx, cy
    _t, x, y = min(candidates, key=lambda item: item[0])
    return x, y


def fit_top_plane(verts, source_bvh, source_bounds):
    zvals = [p.z for p in verts]
    z_top = q(zvals, 0.87)
    support = [p for p in verts if p.z >= z_top - 0.025]
    if len(support) < 12:
        support = verts
    # Least squares z = ax + by + c via normal equations.
    sx = sy = sz = sxx = syy = sxy = sxz = syz = 0.0
    n = len(support)
    for p in support:
        sx += p.x; sy += p.y; sz += p.z
        sxx += p.x * p.x; syy += p.y * p.y; sxy += p.x * p.y
        sxz += p.x * p.z; syz += p.y * p.z
    A = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]]
    B = [sxz, syz, sz]
    def det(m):
        return (m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1]) - m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0]) + m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))
    d = det(A)
    if abs(d) < 1e-9:
        return lambda x, y: z_top
    sol = []
    for col in range(3):
        M = [row[:] for row in A]
        for r in range(3):
            M[r][col] = B[r]
        sol.append(det(M) / d)
    a, b, c = sol
    lo = source_bounds['min_z'] + 0.02
    hi = source_bounds['max_z'] + 0.004
    return lambda x, y: max(lo, min(hi, a * x + b * y + c))


class MeshBuilder:
    def __init__(self, name, mat):
        self.name = name
        self.mat = mat
        self.verts = []
        self.faces = []
        self.face_classes = []

    def v(self, co):
        self.verts.append((float(co[0]), float(co[1]), float(co[2])))
        return len(self.verts) - 1

    def face(self, indices, cls):
        if len(set(indices)) == len(indices):
            self.faces.append(tuple(indices))
            self.face_classes.append(cls)

    def make_object(self):
        mesh = bpy.data.meshes.new(self.name + '_mesh')
        mesh.from_pydata(self.verts, [], self.faces)
        mesh.update(calc_edges=True)
        mesh.materials.append(self.mat)
        obj = bpy.data.objects.new(self.name, mesh)
        bpy.context.collection.objects.link(obj)
        add_projected_uvs(obj)
        for p in obj.data.polygons:
            p.use_smooth = False
        obj.modifiers.new('weighted_normals_clean_hard_surface', 'WEIGHTED_NORMAL')
        return obj


def add_projected_uvs(obj):
    mesh = obj.data
    uv_layer = mesh.uv_layers.new(name='uv_textureable_f07')
    for poly in mesh.polygons:
        n = poly.normal
        coords = [mesh.vertices[i].co for i in poly.vertices]
        for li, co in zip(poly.loop_indices, coords):
            if abs(n.z) >= abs(n.x) and abs(n.z) >= abs(n.y):
                uv = (co.x * 3.0, co.y * 3.0)
            elif abs(n.x) >= abs(n.y):
                uv = (co.y * 3.0, co.z * 8.0)
            else:
                uv = (co.x * 3.0, co.z * 8.0)
            uv_layer.data[li].uv = uv


def make_main_shell(classification, zfunc, mat):
    b = classification['source_bounds']
    ring = classification['ring']
    hull = classification.get('outer_hull') or [(b['min_x'], b['min_y']), (b['max_x'], b['min_y']), (b['max_x'], b['max_y']), (b['min_x'], b['max_y'])]
    cx, cy = ring['center']
    rx_o = ring['rx_outer'] * 1.035
    ry_o = ring['ry_outer'] * 1.035
    rx_i = max(ring['rx_outer'] * ring['inner_ratio'] * 0.92, rx_o * 0.52)
    ry_i = max(ring['ry_outer'] * ring['inner_ratio'] * 0.92, ry_o * 0.52)
    thickness = max(0.030, min(0.055, (b['max_z'] - b['min_z']) * 0.34))
    n = chord_segments(rx_o, ry_o)
    mb = MeshBuilder(ASSET_ID + '_main_armor_shell', mat)
    top_outer = []; bot_outer = []; top_inner = []; bot_inner = []
    for i in range(n):
        a = 2.0 * math.pi * i / n
        ox, oy = ray_polygon_intersection(cx, cy, a, hull)
        ix = cx + rx_i * math.cos(a)
        iy = cy + ry_i * math.sin(a)
        oz = zfunc(ox, oy)
        iz = zfunc(ix, iy)
        top_outer.append(mb.v((ox, oy, oz)))
        bot_outer.append(mb.v((ox, oy, oz - thickness)))
        top_inner.append(mb.v((ix, iy, iz + 0.002)))
        bot_inner.append(mb.v((ix, iy, iz - thickness)))
    for i in range(n):
        j = (i + 1) % n
        mb.face([top_outer[i], top_outer[j], top_inner[j], top_inner[i]], 'smooth_plate_source_silhouette_deck_frame')
        mb.face([bot_outer[j], bot_outer[i], bot_inner[i], bot_inner[j]], 'underside_closed_shell')
        mb.face([top_outer[j], top_outer[i], bot_outer[i], bot_outer[j]], 'outer_source_silhouette_return_wall')
        mb.face([top_inner[i], top_inner[j], bot_inner[j], bot_inner[i]], 'turret_socket_wall')
    obj = mb.make_object()
    obj['surface_class'] = 'smooth_plate_main_armor_shell_source_silhouette'
    return obj, {
        'kind': 'closed_radial_plate_shell_with_source_convex_silhouette_and_socket_wall',
        'segments': n,
        'outer_hull_points': len(hull),
        'outer_hull': hull,
        'inner_aperture_rx': rx_i,
        'inner_aperture_ry': ry_i,
        'thickness': thickness,
        'surface_classes': sorted(set(mb.face_classes)),
    }

def make_annular_shell(classification, zfunc, mat):
    ring = classification['ring']
    cx, cy = ring['center']
    rx_o = ring['rx_outer'] * 1.02
    ry_o = ring['ry_outer'] * 1.02
    rx_i = max(ring['rx_outer'] * ring['inner_ratio'] * 0.96, rx_o * 0.56)
    ry_i = max(ring['ry_outer'] * ring['inner_ratio'] * 0.96, ry_o * 0.56)
    h = max(0.014, min(0.028, ring['z_max'] - ring['z_min'] + 0.006))
    n = chord_segments(rx_o, ry_o)
    mb = MeshBuilder(ASSET_ID + '_turret_ring_annular_shell', mat)
    o0=[]; o1=[]; i0=[]; i1=[]
    for k in range(n):
        a = 2.0 * math.pi * k / n
        oz = zfunc(cx + rx_o * math.cos(a), cy + ry_o * math.sin(a)) + 0.004
        iz = zfunc(cx + rx_i * math.cos(a), cy + ry_i * math.sin(a)) + 0.004
        o0.append(mb.v((cx + rx_o * math.cos(a), cy + ry_o * math.sin(a), oz)))
        o1.append(mb.v((cx + rx_o * math.cos(a), cy + ry_o * math.sin(a), oz + h)))
        i0.append(mb.v((cx + rx_i * math.cos(a), cy + ry_i * math.sin(a), iz)))
        i1.append(mb.v((cx + rx_i * math.cos(a), cy + ry_i * math.sin(a), iz + h)))
    for k in range(n):
        j = (k + 1) % n
        mb.face([o1[k], o1[j], i1[j], i1[k]], 'cylindrical_annular_top')
        mb.face([o0[j], o0[k], o1[k], o1[j]], 'cylindrical_outer_wall')
        mb.face([i0[k], i0[j], i1[j], i1[k]], 'cylindrical_inner_wall')
        mb.face([o0[k], i0[k], i0[j], o0[j]], 'annular_underside_contact')
    obj = mb.make_object()
    obj['surface_class'] = 'cylindrical_turret_ring_shell'
    return obj, {'kind': 'closed_annular_cylindrical_shell', 'segments': n, 'rx_outer': rx_o, 'ry_outer': ry_o, 'rx_inner': rx_i, 'ry_inner': ry_i, 'height': h}


def rounded_rect_points(cx, cy, sx, sy, corner):
    corner = min(corner, sx * 0.45, sy * 0.45)
    pts = []
    centers = [(cx + sx/2 - corner, cy + sy/2 - corner), (cx - sx/2 + corner, cy + sy/2 - corner), (cx - sx/2 + corner, cy - sy/2 + corner), (cx + sx/2 - corner, cy - sy/2 + corner)]
    angle_sets = [(0, math.pi/2), (math.pi/2, math.pi), (math.pi, math.pi*1.5), (math.pi*1.5, math.pi*2)]
    for (ccx, ccy), (a0, a1) in zip(centers, angle_sets):
        for step in range(4):
            a = a0 + (a1 - a0) * step / 3
            pts.append((ccx + corner * math.cos(a), ccy + corner * math.sin(a)))
    return pts


def make_rounded_cuboid(name, cx, cy, sx, sy, base_z, height, mat, surface_class):
    pts = rounded_rect_points(cx, cy, sx, sy, min(sx, sy) * 0.16)
    mb = MeshBuilder(ASSET_ID + '_' + name, mat)
    low=[]; high=[]
    for x, y in pts:
        low.append(mb.v((x, y, base_z - 0.004)))
        high.append(mb.v((x, y, base_z + height)))
    mb.face(high, surface_class + '_top')
    mb.face(list(reversed(low)), surface_class + '_underside_contact')
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        mb.face([low[i], low[j], high[j], high[i]], surface_class + '_sidewall')
    obj = mb.make_object()
    obj['surface_class'] = surface_class
    return obj, {'kind': 'closed_rounded_cuboid_shell', 'center': [cx, cy], 'size': [sx, sy], 'base_z': base_z, 'height': height, 'corner_points': len(pts)}


def make_cylinder(name, cx, cy, radius, base_z, height, mat, surface_class):
    n = max(18, min(32, chord_segments(radius, radius)))
    mb = MeshBuilder(ASSET_ID + '_' + name, mat)
    low=[]; high=[]
    for i in range(n):
        a = 2.0 * math.pi * i / n
        x = cx + radius * math.cos(a); y = cy + radius * math.sin(a)
        low.append(mb.v((x, y, base_z - 0.003)))
        high.append(mb.v((x, y, base_z + height)))
    mb.face(high, surface_class + '_cap')
    mb.face(list(reversed(low)), surface_class + '_underside_contact')
    for i in range(n):
        j = (i + 1) % n
        mb.face([low[i], low[j], high[j], high[i]], surface_class + '_cylindrical_side')
    obj = mb.make_object()
    obj['surface_class'] = surface_class
    return obj, {'kind': 'closed_cylindrical_shell', 'center': [cx, cy], 'radius': radius, 'base_z': base_z, 'height': height, 'segments': n}


def make_detail_shells(classification, zfunc, mat):
    details = []
    primitives = []
    ring = classification['ring']
    rx = ring['rx_outer']; ry = ring['ry_outer']; rcx, rcy = ring['center']
    # Keep details low and deliberate. The prior pass made vertical blocks from source fragments.
    flat = []
    roundish = []
    for cand in classification['detail_candidates']:
        sx, sy, sz = cand['size']
        cx, cy, cz = cand['center']
        dist = math.sqrt(((cx - rcx) / max(rx, 1e-4)) ** 2 + ((cy - rcy) / max(ry, 1e-4)) ** 2)
        if sz > max(sx, sy) * 0.85:
            continue
        if dist < 0.82:
            continue
        if sx > 0.045 and sy > 0.035:
            flat.append(cand)
        elif 0.012 < sx < 0.055 and 0.012 < sy < 0.055:
            roundish.append(cand)
    flat = sorted(flat, key=lambda c: c['size'][0] * c['size'][1], reverse=True)
    roundish = sorted(roundish, key=lambda c: c['tris'], reverse=True)
    used = 0
    if flat:
        cand = flat[0]
        sx, sy, sz = cand['size']; cx, cy, cz = cand['center']
        base_z = zfunc(cx, cy) + 0.005
        obj, prim = make_rounded_cuboid('source_measured_hatch', cx, cy, min(max(sx, 0.055), 0.125), min(max(sy, 0.040), 0.100), base_z, 0.014, mat, 'cuboid_or_rounded_cuboid_hatch_detail')
        prim['source_candidate'] = cand
        details.append(obj); primitives.append(prim); used += 1
    for cand in roundish[:3]:
        sx, sy, sz = cand['size']; cx, cy, cz = cand['center']
        base_z = zfunc(cx, cy) + 0.005
        radius = min(max(max(sx, sy) * 0.42, 0.010), 0.024)
        obj, prim = make_cylinder('low_round_boss_%02d' % used, cx, cy, radius, base_z, 0.010, mat, 'cylindrical_low_round_boss')
        prim['source_candidate'] = cand
        details.append(obj); primitives.append(prim); used += 1
        if used >= 4:
            break
    if not details:
        b = classification['source_bounds']
        x = b['min_x'] + (b['max_x'] - b['min_x']) * 0.77
        y = b['min_y'] + (b['max_y'] - b['min_y']) * 0.72
        base_z = zfunc(x, y) + 0.005
        obj, prim = make_rounded_cuboid('measured_fallback_hatch', x, y, (b['max_x']-b['min_x'])*0.11, (b['max_y']-b['min_y'])*0.075, base_z, 0.014, mat, 'cuboid_or_rounded_cuboid_hatch_detail')
        details.append(obj); primitives.append(prim)
    return details, primitives

def mesh_boundary_report(obj):
    mesh = obj.data
    mesh.update(calc_edges=True)
    edge_faces = defaultdict(int)
    for p in mesh.polygons:
        vs = list(p.vertices)
        for i, a in enumerate(vs):
            b = vs[(i + 1) % len(vs)]
            edge_faces[tuple(sorted((a, b)))] += 1
    boundary = sum(1 for c in edge_faces.values() if c == 1)
    nonmanifold = sum(1 for c in edge_faces.values() if c != 2)
    return {'object': obj.name, 'vertices': len(mesh.vertices), 'polygons': len(mesh.polygons), 'triangles': tri_count(mesh), 'boundary_edges': boundary, 'nonmanifold_edges': nonmanifold, 'uv_layers': [uv.name for uv in mesh.uv_layers]}


def provenance_for_objects(source_bvh, objs, source_name):
    rows = []
    for obj in objs:
        mw = obj.matrix_world.copy()
        for i, v in enumerate(obj.data.vertices):
            wp = mw @ v.co
            loc, normal, face_index, dist = source_bvh.find_nearest(wp, 2.0)
            rows.append({
                'output_object': obj.name,
                'output_vertex': int(i),
                'support': {'kind': 'nearest_source_surface_to_analytic_vertex', 'source_object': source_name, 'source_face': int(face_index) if face_index is not None else -1, 'distance': float(dist) if dist is not None else None},
                'world': [float(wp.x), float(wp.y), float(wp.z)],
            })
    return rows


def camera_basis(points):
    center = Vector((0, 0, 0))
    for p in points:
        center += p
    center /= len(points)
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
    vals=[]; mask=[]
    for y in range(h):
        for x in range(w):
            origin, direction = ray_for_uv(cam, x + 0.5, y + 0.5, w, h)
            loc, normal, face_index, dist = bvh.ray_cast(origin, direction, 20.0)
            vals.append(float(dist) if loc is not None else None)
            mask.append(loc is not None)
    return vals, mask


def save_gray_png(path, values, mask, w, h, lo=None, hi=None):
    present = [v for v, m in zip(values, mask) if m and v is not None] or [0.0]
    if lo is None: lo = min(present)
    if hi is None: hi = max(present)
    if abs(hi - lo) < 1e-8: hi = lo + 1.0
    img = bpy.data.images.new(path.stem, width=w, height=h, alpha=True, float_buffer=False)
    pix = [0.0] * (w * h * 4)
    for y in range(h):
        for x in range(w):
            i = y * w + x; j = i * 4
            if mask[i] and values[i] is not None:
                g = max(0.0, min(1.0, (values[i] - lo) / (hi - lo)))
                pix[j:j+4] = [g, g, g, 1.0]
            else:
                pix[j:j+4] = [0.0, 0.0, 0.0, 0.0]
    img.pixels.foreach_set(pix)
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def depth_compare(source_bvh, retopo_objs, cam):
    deps = bpy.context.evaluated_depsgraph_get()
    all_verts=[]; all_polys=[]
    for obj in retopo_objs:
        eo = obj.evaluated_get(deps); mesh = eo.to_mesh()
        try:
            base = len(all_verts)
            mw = obj.matrix_world.copy()
            all_verts.extend([mw @ v.co for v in mesh.vertices])
            all_polys.extend([tuple(base + i for i in p.vertices) for p in mesh.polygons])
        finally:
            eo.to_mesh_clear()
    retopo_bvh = BVHTree.FromPolygons(all_verts, all_polys, all_triangles=False)
    src_vals, src_mask = sample_depth_image(source_bvh, cam, DEPTH_W, DEPTH_H)
    ret_vals, ret_mask = sample_depth_image(retopo_bvh, cam, DEPTH_W, DEPTH_H)
    shared = [a and b for a, b in zip(src_mask, ret_mask)]
    union = [a or b for a, b in zip(src_mask, ret_mask)]
    errors=[]; err_vals=[]
    for sv, rv, m in zip(src_vals, ret_vals, shared):
        if m:
            e = abs(sv - rv); errors.append(e); err_vals.append(e)
        else:
            err_vals.append(None)
    errors_sorted = sorted(errors)
    def pct(qv):
        if not errors_sorted: return None
        return errors_sorted[min(len(errors_sorted)-1, int(qv * (len(errors_sorted)-1)))]
    report = {'depth_resolution': [DEPTH_W, DEPTH_H], 'shared_pixels': int(sum(shared)), 'source_pixels': int(sum(src_mask)), 'retopo_pixels': int(sum(ret_mask)), 'silhouette_iou': float(sum(shared) / max(1, sum(union))), 'mean_abs_depth_error': float(sum(errors) / max(1, len(errors))), 'p50_abs_depth_error': pct(0.50), 'p95_abs_depth_error': pct(0.95), 'max_abs_depth_error': max(errors) if errors else None}
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
    center = cam_basis['center']; view_dir = cam_basis['view_dir']
    bpy.ops.object.camera_add(location=center - view_dir * 3.2)
    cam = bpy.context.object
    cam.name = ASSET_ID + '_depth_parity_camera'
    look_at(cam, center)
    cam.data.type = 'ORTHO'
    span_r = cam_basis['max_r'] - cam_basis['min_r']; span_u = cam_basis['max_u'] - cam_basis['min_u']
    cam.data.ortho_scale = max(span_u, span_r * 0.68)
    return cam


def render_shaded(source_obj, retopo_objs, cam):
    bpy.ops.object.light_add(type='AREA', location=cam.location + Vector((0, -1.0, 2.2)))
    light = bpy.context.object
    light.name = ASSET_ID + '_softbox'
    light.data.energy = 700; light.data.size = 4.0
    engine_items = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
    if hasattr(bpy.context.scene, 'eevee'):
        bpy.context.scene.eevee.taa_render_samples = 48
    bpy.context.scene.render.resolution_x = 1280; bpy.context.scene.render.resolution_y = 840
    bpy.context.scene.camera = cam
    for obj_set, fn in [([source_obj], 'source_shaded_same_angle.png'), (retopo_objs, 'retopo_shaded_same_angle.png')]:
        source_obj.hide_render = source_obj not in obj_set
        for obj in retopo_objs:
            obj.hide_render = obj not in obj_set
        bpy.context.scene.render.filepath = str(RENDER_DIR / fn)
        bpy.ops.render.render(write_still=True)
    source_obj.hide_render = True
    for obj in retopo_objs:
        obj.hide_render = False


def main():
    ensure_dirs(); reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_obj = find_source_object()
    source_obj.name = ASSET_ID + '_hidden_source_upper_glacis'
    source_mat = make_mat(ASSET_ID + '_source_gray', (0.66, 0.67, 0.62, 1), 0.9)
    armor_mat = make_mat(ASSET_ID + '_smooth_plate_armor', (0.58, 0.61, 0.54, 1), 0.92)
    ring_mat = make_mat(ASSET_ID + '_cylindrical_ring', (0.62, 0.64, 0.56, 1), 0.9)
    detail_mat = make_mat(ASSET_ID + '_raised_detail_shells', (0.56, 0.59, 0.52, 1), 0.92)
    source_obj.data.materials.clear(); source_obj.data.materials.append(source_mat)
    source_verts, source_polys, source_normals = world_mesh_data(source_obj)
    source_bvh = build_bvh_from_data(source_verts, source_polys)
    classification = classify_source(source_verts, source_polys, source_normals)
    zfunc = fit_top_plane(source_verts, source_bvh, classification['source_bounds'])
    main_obj, main_prim = make_main_shell(classification, zfunc, armor_mat)
    ring_obj, ring_prim = make_annular_shell(classification, zfunc, ring_mat)
    details, detail_prims = make_detail_shells(classification, zfunc, detail_mat)
    retopo_objs = [main_obj, ring_obj] + details
    for obj in retopo_objs:
        obj['asset_id'] = ASSET_ID
        obj['scratch_mode'] = True
        obj['revision'] = REVISION
        obj['role'] = ROLE
        obj['source_object'] = source_obj.name
        obj['authoring_policy'] = 'Source-measured analytic primitive-fused shells: clean plates, cylindrical ring/socket, rounded cuboid/cylindrical details, closed shells, UVs.'
    reports = [mesh_boundary_report(obj) for obj in retopo_objs]
    stats = {'vertices': sum(r['vertices'] for r in reports), 'polygons': sum(r['polygons'] for r in reports), 'triangles': sum(r['triangles'] for r in reports), 'objects': len(retopo_objs)}
    cam_basis = camera_basis(source_verts)
    depth_report = depth_compare(source_bvh, retopo_objs, cam_basis)
    cam = add_camera_from_basis(cam_basis)
    render_shaded(source_obj, retopo_objs, cam)
    source_obj.hide_viewport = True; source_obj.hide_render = True
    blend_path = BLEND_DIR / (ASSET_ID + '.blend')
    glb_path = MODEL_DIR / (ASSET_ID + '.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in retopo_objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = main_obj
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    surface_path = MODEL_DIR / 'surface_classification.json'
    primitive_path = MODEL_DIR / 'analytic_primitives.json'
    provenance_path = MODEL_DIR / 'retopo_vertex_provenance.json'
    classification_out = dict(classification)
    surface_path.write_text(json.dumps(classification_out, indent=2) + '\n')
    primitive_path.write_text(json.dumps({'asset_id': ASSET_ID, 'main_shell': main_prim, 'turret_ring_shell': ring_prim, 'detail_shells': detail_prims, 'mesh_boundary_report': reports}, indent=2) + '\n')
    provenance = provenance_for_objects(source_bvh, retopo_objs, source_obj.name)
    provenance_path.write_text(json.dumps({'asset_id': ASSET_ID, 'vertices': provenance}, indent=2) + '\n')
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'scratch_one_piece_analytic_primitive_fused_upper_glacis',
        'revision': REVISION,
        'source_glb': str(SOURCE_GLB.relative_to(ROOT)),
        'source_component': ROLE,
        'authoring_policy': 'Measured analytic shells, not noisy source topology: smooth plates, cylindrical ring/socket, rounded cuboid/cylinder details, clean UVs.',
        'statistics_primary_piece': stats,
        'primary_object_count': len(retopo_objs),
        'surface_classification': str(surface_path.relative_to(ROOT)),
        'analytic_primitives': str(primitive_path.relative_to(ROOT)),
        'provenance': {'path': str(provenance_path.relative_to(ROOT)), 'output_vertices': len(provenance)},
        'mesh_boundary_report': reports,
        'depth_parity': {'path': str((MODEL_DIR / 'depth_error_report.json').relative_to(ROOT)), **depth_report},
        'outputs': {
            'blend': str(blend_path.relative_to(ROOT)),
            'glb': str(glb_path.relative_to(ROOT)),
            'source_depth': str((RENDER_DIR / 'source_depth.png').relative_to(ROOT)),
            'retopo_depth': str((RENDER_DIR / 'retopo_depth.png').relative_to(ROOT)),
            'depth_abs_error': str((RENDER_DIR / 'depth_abs_error.png').relative_to(ROOT)),
            'source_shaded_same_angle': str((RENDER_DIR / 'source_shaded_same_angle.png').relative_to(ROOT)),
            'retopo_shaded_same_angle': str((RENDER_DIR / 'retopo_shaded_same_angle.png').relative_to(ROOT)),
        }
    }
    (MODEL_DIR / 'model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    note = '# ' + ASSET_ID + '\n\nSource-silhouette analytic primitive-fused upper glacis scratch pass. Not cloud accepted.\n\n- Stats: ' + str(stats) + '\n- Depth report: ' + str(depth_report) + '\n- Mesh boundary report: ' + str(reports) + '\n'
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    print(json.dumps({'asset_id': ASSET_ID, 'stats': stats, 'depth_report': depth_report, 'glb': str(glb_path), 'boundary_report': reports}, indent=2))


main()
