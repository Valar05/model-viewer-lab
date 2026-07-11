
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
ASSET_ID = 'real_sherman_upper_glacis_f05_revamp_scratch_f10'
REVISION = 'f10-f05-visual-target-local-ring-hatch-cleanup'
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


def build_bvh(obj):
    verts, polys, _normals = world_mesh_data(obj)
    return BVHTree.FromPolygons(verts, polys, all_triangles=False), verts, polys


def q(vals, t):
    vals = sorted(vals)
    return vals[int((len(vals) - 1) * t)]


def connected_components(verts, polys, normals):
    v2f = defaultdict(list)
    for fi, face in enumerate(polys):
        for v in face:
            v2f[v].append(fi)
    seen = set(); comps = []
    for fi in range(len(polys)):
        if fi in seen:
            continue
        stack = [fi]; seen.add(fi); faces = []; vidx = set()
        while stack:
            f = stack.pop(); faces.append(f)
            for v in polys[f]:
                vidx.add(v)
                for nf in v2f[v]:
                    if nf not in seen:
                        seen.add(nf); stack.append(nf)
        pts = [verts[i] for i in vidx]
        ns = [normals[i] for i in faces]
        avg = Vector((0, 0, 0))
        for n in ns:
            avg += n
        if ns:
            avg.normalize()
        comps.append({
            'faces': len(faces),
            'tris': sum(max(0, len(polys[i]) - 2) for i in faces),
            'verts': len(vidx),
            'min': [min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)],
            'max': [max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)],
            'center': [sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts), sum(p.z for p in pts) / len(pts)],
            'normal': [avg.x, avg.y, avg.z],
        })
    return sorted(comps, key=lambda c: c['tris'], reverse=True)


def measure_features(source_obj):
    verts, polys, normals = world_mesh_data(source_obj)
    comps = connected_components(verts, polys, normals)
    zmax = max(p.z for p in verts)
    ring_candidates = []
    for c in comps:
        sx = c['max'][0] - c['min'][0]; sy = c['max'][1] - c['min'][1]; sz = c['max'][2] - c['min'][2]
        if c['tris'] >= 250 and c['normal'][2] > 0.75 and c['center'][2] > zmax - 0.035 and 0.22 <= sx <= 0.48 and 0.22 <= sy <= 0.48 and sz < 0.035:
            ring_candidates.append(c)
    ring_comp = ring_candidates[0] if ring_candidates else comps[3]
    rcx = (ring_comp['min'][0] + ring_comp['max'][0]) * 0.5
    rcy = (ring_comp['min'][1] + ring_comp['max'][1]) * 0.5
    rx_outer = (ring_comp['max'][0] - ring_comp['min'][0]) * 0.5 * 1.01
    ry_outer = (ring_comp['max'][1] - ring_comp['min'][1]) * 0.5 * 1.01
    ring = {
        'source_component': ring_comp,
        'cx': rcx,
        'cy': rcy,
        'rx_outer': rx_outer,
        'ry_outer': ry_outer,
        'rx_inner': rx_outer * 0.66,
        'ry_inner': ry_outer * 0.66,
        'z': ring_comp['max'][2],
    }
    hatch_parts = []
    for c in comps:
        sx = c['max'][0] - c['min'][0]; sy = c['max'][1] - c['min'][1]; sz = c['max'][2] - c['min'][2]
        if c['tris'] >= 80 and c['center'][1] > rcy + ry_outer * 0.62 and c['center'][0] > rcx - rx_outer * 0.15 and sx < 0.16 and sy < 0.16 and sz > 0.006:
            hatch_parts.append(c)
    if hatch_parts:
        hmin = [min(c['min'][i] for c in hatch_parts) for i in range(3)]
        hmax = [max(c['max'][i] for c in hatch_parts) for i in range(3)]
        hx = (hmin[0] + hmax[0]) * 0.5; hy = (hmin[1] + hmax[1]) * 0.5
        hsx = max(0.070, min(0.18, (hmax[0] - hmin[0]) * 0.75))
        hsy = max(0.045, min(0.13, (hmax[1] - hmin[1]) * 0.75))
        hz = hmax[2]
    else:
        hx = rcx + rx_outer * 1.18; hy = rcy + ry_outer * 1.10; hsx = rx_outer * 0.70; hsy = ry_outer * 0.38; hz = ring['z']
    hatch = {'source_components': hatch_parts, 'cx': hx, 'cy': hy, 'sx': hsx, 'sy': hsy, 'z': hz}
    return {'ring': ring, 'hatch': hatch, 'top_components': comps[:18]}


def z_at(source_bvh, x, y, fallback):
    loc, normal, face_index, dist = source_bvh.ray_cast(Vector((x, y, fallback + 1.0)), Vector((0, 0, -1)), 3.0)
    return loc.z if loc is not None else fallback


def add_uvs(obj):
    mesh = obj.data
    if not mesh.uv_layers:
        uv_layer = mesh.uv_layers.new(name='uv_f05_revamp_f10')
    else:
        uv_layer = mesh.uv_layers.active
    for poly in mesh.polygons:
        n = poly.normal
        for li in poly.loop_indices:
            co = mesh.vertices[mesh.loops[li].vertex_index].co
            if abs(n.z) >= abs(n.x) and abs(n.z) >= abs(n.y):
                uv_layer.data[li].uv = (co.x * 3.0, co.y * 3.0)
            elif abs(n.x) >= abs(n.y):
                uv_layer.data[li].uv = (co.y * 3.0, co.z * 8.0)
            else:
                uv_layer.data[li].uv = (co.x * 3.0, co.z * 8.0)


def make_annular_ring(feature, source_bvh, mat_index=1):
    ring = feature['ring']
    n = 40; h = 0.016
    verts = []; faces = []
    for i in range(n):
        a = 2 * math.pi * i / n
        ca = math.cos(a); sa = math.sin(a)
        points = [
            (ring['rx_outer'], ring['ry_outer'], 0.000),
            (ring['rx_outer'], ring['ry_outer'], h),
            (ring['rx_inner'], ring['ry_inner'], h + 0.002),
            (ring['rx_inner'], ring['ry_inner'], 0.000),
        ]
        for rx, ry, dz in points:
            x = ring['cx'] + rx * ca; y = ring['cy'] + ry * sa
            z = z_at(source_bvh, x, y, ring['z']) + 0.004 + dz
            verts.append((x, y, z))
    face_classes = []
    for i in range(n):
        j = (i + 1) % n; a = i * 4; b = j * 4
        faces.append((a+1, b+1, b+2, a+2)); face_classes.append('turret_ring_top')
        faces.append((b, a, a+1, b+1)); face_classes.append('turret_ring_outer_wall')
        faces.append((a+3, b+3, b+2, a+2)); face_classes.append('socket_wall')
        faces.append((a, b, b+3, a+3)); face_classes.append('turret_ring_contact')
    mesh = bpy.data.meshes.new(ASSET_ID + '_clean_turret_ring_mesh')
    mesh.from_pydata(verts, [], faces); mesh.update(calc_edges=True)
    for poly in mesh.polygons:
        poly.material_index = mat_index
    obj = bpy.data.objects.new(ASSET_ID + '_clean_turret_ring_shell', mesh)
    bpy.context.collection.objects.link(obj)
    obj.modifiers.new('weighted_normals_clean_ring', 'WEIGHTED_NORMAL')
    return obj, {'kind': 'local_annular_shell_overlay', 'segments': n, **ring, 'face_classes': sorted(set(face_classes))}


def rounded_rect(cx, cy, sx, sy, r):
    pts = []
    centers = [(cx+sx/2-r, cy+sy/2-r), (cx-sx/2+r, cy+sy/2-r), (cx-sx/2+r, cy-sy/2+r), (cx+sx/2-r, cy-sy/2+r)]
    arcs = [(0, math.pi/2), (math.pi/2, math.pi), (math.pi, 1.5*math.pi), (1.5*math.pi, 2*math.pi)]
    for (ccx, ccy), (a0, a1) in zip(centers, arcs):
        for k in range(4):
            a = a0 + (a1 - a0) * k / 3
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def make_hatch(feature, source_bvh, mat_index=2):
    h = feature['hatch']; pts = rounded_rect(h['cx'], h['cy'], h['sx'], h['sy'], min(h['sx'], h['sy']) * 0.18)
    verts = []; low = []; high = []; height = 0.014
    for x, y in pts:
        z = z_at(source_bvh, x, y, h['z']) + 0.006
        low.append(len(verts)); verts.append((x, y, z - 0.003))
        high.append(len(verts)); verts.append((x, y, z + height))
    faces = [tuple(high), tuple(reversed(low))]
    n = len(pts)
    for i in range(n):
        faces.append((low[i], low[(i+1)%n], high[(i+1)%n], high[i]))
    mesh = bpy.data.meshes.new(ASSET_ID + '_clean_hatch_mesh')
    mesh.from_pydata(verts, [], faces); mesh.update(calc_edges=True)
    for poly in mesh.polygons:
        poly.material_index = mat_index
    obj = bpy.data.objects.new(ASSET_ID + '_clean_hatch_shell', mesh)
    bpy.context.collection.objects.link(obj)
    obj.modifiers.new('weighted_normals_clean_hatch', 'WEIGHTED_NORMAL')
    return obj, {'kind': 'local_rounded_cuboid_overlay', 'corner_points': n, **{k:v for k,v in h.items() if k != 'source_components'}}


def mesh_boundary_report(obj):
    mesh = obj.data; mesh.update(calc_edges=True)
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


def make_f05_revamp(source_obj, armor_mat, ring_mat, hatch_mat):
    source_bvh, source_verts, source_polys = build_bvh(source_obj)
    feature = measure_features(source_obj)
    bpy.ops.object.select_all(action='DESELECT')
    source_obj.select_set(True); bpy.context.view_layer.objects.active = source_obj
    bpy.ops.object.duplicate()
    base = bpy.context.object
    base.name = ASSET_ID + '_f05_base_preserved'
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.dissolve_limited(angle_limit=math.radians(35.0), use_dissolve_boundaries=False, delimit={'NORMAL'})
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    base.data.materials.clear(); base.data.materials.append(armor_mat); base.data.materials.append(ring_mat); base.data.materials.append(hatch_mat)
    for p in base.data.polygons:
        p.use_smooth = False
        p.material_index = 0
    ring_obj, ring_prim = make_annular_ring(feature, source_bvh, 1)
    hatch_obj, hatch_prim = make_hatch(feature, source_bvh, 2)
    for obj in (ring_obj, hatch_obj):
        obj.data.materials.clear(); obj.data.materials.append(armor_mat); obj.data.materials.append(ring_mat); obj.data.materials.append(hatch_mat)
        add_uvs(obj)
    add_uvs(base)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in (base, ring_obj, hatch_obj):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = base
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = ASSET_ID + '_upper_front_glacis_f05_revamp'
    add_uvs(obj)
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = ROLE
    obj['source_object'] = source_obj.name
    obj['primary_retopo_piece'] = True
    obj['authoring_policy'] = 'f05 visual target preserved; local measured ring and hatch shells overlay f05 seam zones for texture readiness. No analytic hull restart, no broad deletion.'
    obj.modifiers.new('weighted_normals_f05_revamp', 'WEIGHTED_NORMAL')
    primitive_report = {'ring_overlay': ring_prim, 'hatch_overlay': hatch_prim, 'feature_measurement': feature}
    return obj, primitive_report


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
                pix[j:j+4] = [0, 0, 0, 0]
    img.pixels.foreach_set(pix); img.filepath_raw = str(path); img.file_format = 'PNG'; img.save(); bpy.data.images.remove(img)


def depth_compare(source_bvh, retopo_obj, cam):
    retopo_bvh, _verts, _polys = build_bvh(retopo_obj)
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
    cam = bpy.context.object; cam.name = ASSET_ID + '_depth_parity_camera'; look_at(cam, center); cam.data.type = 'ORTHO'
    span_r = cam_basis['max_r'] - cam_basis['min_r']; span_u = cam_basis['max_u'] - cam_basis['min_u']
    cam.data.ortho_scale = max(span_u, span_r * 0.68)
    return cam


def render_shaded(source_obj, retopo_obj, cam):
    bpy.ops.object.light_add(type='AREA', location=cam.location + Vector((0, -1.0, 2.2)))
    light = bpy.context.object; light.name = ASSET_ID + '_softbox'; light.data.energy = 700; light.data.size = 4.0
    engine_items = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
    if hasattr(bpy.context.scene, 'eevee'):
        bpy.context.scene.eevee.taa_render_samples = 48
    bpy.context.scene.render.resolution_x = 1280; bpy.context.scene.render.resolution_y = 840; bpy.context.scene.camera = cam
    all_meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    for obj, fn in [(source_obj, 'source_shaded_same_angle.png'), (retopo_obj, 'retopo_shaded_same_angle.png')]:
        for m in all_meshes:
            m.hide_render = m != obj
        bpy.context.scene.render.filepath = str(RENDER_DIR / fn)
        bpy.ops.render.render(write_still=True)
    for m in all_meshes:
        m.hide_render = m != retopo_obj


def provenance_for_retopo(source_bvh, retopo_obj, source_name):
    rows=[]
    for i, v in enumerate(retopo_obj.data.vertices):
        wp = retopo_obj.matrix_world @ v.co
        loc, normal, face_index, dist = source_bvh.find_nearest(wp, 1.0)
        rows.append({'output_vertex': i, 'support': {'kind': 'nearest_source_surface_after_f05_revamp', 'source_object': source_name, 'source_face': int(face_index) if face_index is not None else -1, 'distance': float(dist) if dist is not None else None}, 'world': [float(wp.x), float(wp.y), float(wp.z)]})
    return rows


def main():
    ensure_dirs(); reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_obj = find_source_object(); source_obj.name = ASSET_ID + '_hidden_source_upper_glacis'
    source_mat = make_mat(ASSET_ID + '_source_gray', (0.66, 0.67, 0.62, 1), 0.9)
    armor_mat = make_mat('armor_plate', (0.58, 0.61, 0.54, 1), 0.92)
    ring_mat = make_mat('turret_ring', (0.62, 0.64, 0.56, 1), 0.90)
    hatch_mat = make_mat('hatch_detail', (0.56, 0.59, 0.52, 1), 0.92)
    source_obj.data.materials.clear(); source_obj.data.materials.append(source_mat)
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj != source_obj:
            obj.hide_viewport = True; obj.hide_render = True
    source_bvh, source_verts, source_polys = build_bvh(source_obj)
    retopo_obj, primitive_report = make_f05_revamp(source_obj, armor_mat, ring_mat, hatch_mat)
    cam_basis = camera_basis(source_verts)
    depth_report = depth_compare(source_bvh, retopo_obj, cam_basis)
    cam = add_camera_from_basis(cam_basis)
    render_shaded(source_obj, retopo_obj, cam)
    source_obj.hide_viewport = True; source_obj.hide_render = True; retopo_obj.hide_render = False
    deps = bpy.context.evaluated_depsgraph_get(); eo = retopo_obj.evaluated_get(deps); mesh = eo.to_mesh()
    try:
        stats = {'triangles': tri_count(mesh), 'polygons': len(mesh.polygons), 'vertices': len(mesh.vertices)}
    finally:
        eo.to_mesh_clear()
    blend_path = BLEND_DIR / (ASSET_ID + '.blend'); glb_path = MODEL_DIR / (ASSET_ID + '.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT'); retopo_obj.select_set(True); bpy.context.view_layer.objects.active = retopo_obj
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    primitive_path = MODEL_DIR / 'local_repair_primitives.json'
    primitive_path.write_text(json.dumps({'asset_id': ASSET_ID, **primitive_report}, indent=2) + '\n')
    provenance_path = MODEL_DIR / 'retopo_vertex_provenance.json'
    provenance = provenance_for_retopo(source_bvh, retopo_obj, source_obj.name)
    provenance_path.write_text(json.dumps({'asset_id': ASSET_ID, 'vertices': provenance}, indent=2) + '\n')
    boundary = mesh_boundary_report(retopo_obj)
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'scratch_f05_revamp_local_ring_hatch_cleanup',
        'revision': REVISION,
        'source_glb': str(SOURCE_GLB.relative_to(ROOT)),
        'source_component': ROLE,
        'authoring_policy': retopo_obj['authoring_policy'],
        'statistics_primary_piece': stats,
        'material_slots': [m.name for m in retopo_obj.data.materials],
        'mesh_boundary_report': boundary,
        'local_repair_primitives': str(primitive_path.relative_to(ROOT)),
        'provenance': {'path': str(provenance_path.relative_to(ROOT)), 'output_vertices': len(provenance)},
        'depth_parity': {'path': str((MODEL_DIR / 'depth_error_report.json').relative_to(ROOT)), **depth_report},
        'outputs': {'blend': str(blend_path.relative_to(ROOT)), 'glb': str(glb_path.relative_to(ROOT)), 'source_shaded_same_angle': str((RENDER_DIR / 'source_shaded_same_angle.png').relative_to(ROOT)), 'retopo_shaded_same_angle': str((RENDER_DIR / 'retopo_shaded_same_angle.png').relative_to(ROOT)), 'source_depth': str((RENDER_DIR / 'source_depth.png').relative_to(ROOT)), 'retopo_depth': str((RENDER_DIR / 'retopo_depth.png').relative_to(ROOT)), 'depth_abs_error': str((RENDER_DIR / 'depth_abs_error.png').relative_to(ROOT))}
    }
    (MODEL_DIR / 'model_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    note = '# ' + ASSET_ID + '\n\nf05 revamp pass: preserve f05 broad hull and overlay measured local ring/hatch shells. Scratch diagnostic only.\n\n- Stats: ' + str(stats) + '\n- Depth report: ' + str(depth_report) + '\n- Boundary report: ' + str(boundary) + '\n'
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    print(json.dumps({'asset_id': ASSET_ID, 'stats': stats, 'depth_report': depth_report, 'boundary': boundary, 'glb': str(glb_path)}, indent=2))


main()
