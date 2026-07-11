
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
SOURCE_GLB = SCRATCH / 'models' / 'real_sherman_chassis_reference_kit_scratch_v1' / 'real_sherman_chassis_reference_kit_scratch_v1.glb'
ASSET_ID = 'real_sherman_upper_glacis_feature_retopo_scratch_f02'
REVISION = 'f02-clean-source-supported-feature-loop-reto'
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
        return verts, polys
    finally:
        eo.to_mesh_clear()


def build_bvh(obj):
    verts, polys = world_mesh_data(obj)
    return BVHTree.FromPolygons(verts, polys, all_triangles=False), verts, polys


def bounds(points):
    return {
        'min_x': min(p.x for p in points), 'max_x': max(p.x for p in points),
        'min_y': min(p.y for p in points), 'max_y': max(p.y for p in points),
        'min_z': min(p.z for p in points), 'max_z': max(p.z for p in points),
    }


def q(vals, t):
    vals = sorted(vals)
    return vals[int((len(vals) - 1) * t)]


def xy_sample(source_bvh, b, x, y, fallback_z=None):
    origin = Vector((x, y, b['max_z'] + 1.0))
    loc, normal, face_index, dist = source_bvh.ray_cast(origin, Vector((0, 0, -1)), 3.0)
    if loc is not None:
        return Vector((x, y, loc.z)), int(face_index)
    if fallback_z is None:
        fallback_z = (b['min_z'] + b['max_z']) * 0.5
    return Vector((x, y, fallback_z)), -1


class MeshBuilder:
    def __init__(self, source_bvh, b):
        self.source_bvh = source_bvh
        self.b = b
        self.verts = []
        self.faces = []
        self.provenance = []

    def v(self, x, y, z_offset=0.0, semantic='source_supported_feature_vertex'):
        p, face = xy_sample(self.source_bvh, self.b, x, y)
        p.z += z_offset
        idx = len(self.verts)
        self.verts.append((p.x, p.y, p.z))
        self.provenance.append({
            'output_vertex': idx,
            'semantic': semantic,
            'support': {'kind': 'vertical_source_ray_hit', 'source_face': int(face)},
            'world': [float(p.x), float(p.y), float(p.z)],
        })
        return idx

    def add_face(self, face):
        if len(set(face)) == len(face):
            self.faces.append(tuple(face))

    def add_quad(self, a, b, c, d):
        self.add_face((a, b, c, d))


def add_plate_grid(mb, xs, ys):
    ids = {}
    for yi, y in enumerate(ys):
        for xi, x in enumerate(xs):
            ids[(xi, yi)] = mb.v(x, y, 0.001, 'load_bearing_plate_grid')
    for yi in range(len(ys) - 1):
        for xi in range(len(xs) - 1):
            mb.add_quad(ids[(xi, yi)], ids[(xi + 1, yi)], ids[(xi + 1, yi + 1)], ids[(xi, yi + 1)])


def add_raised_box(mb, cx, cy, sx, sy, h, name):
    x0 = cx - sx * 0.5; x1 = cx + sx * 0.5
    y0 = cy - sy * 0.5; y1 = cy + sy * 0.5
    btm = [mb.v(x0, y0, 0.004, name + '_seat'), mb.v(x1, y0, 0.004, name + '_seat'), mb.v(x1, y1, 0.004, name + '_seat'), mb.v(x0, y1, 0.004, name + '_seat')]
    top = [mb.v(x0, y0, h, name + '_raised_edge'), mb.v(x1, y0, h, name + '_raised_edge'), mb.v(x1, y1, h, name + '_raised_edge'), mb.v(x0, y1, h, name + '_raised_edge')]
    mb.add_quad(*top)
    for i in range(4):
        mb.add_quad(btm[i], btm[(i + 1) % 4], top[(i + 1) % 4], top[i])


def add_ring(mb, cx, cy, rx_outer, ry_outer, rx_inner, ry_inner, h, segments=36):
    outer_low = [] ; outer_top = [] ; inner_low = [] ; inner_top = []
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        co = math.cos(a); si = math.sin(a)
        outer_low.append(mb.v(cx + rx_outer * co, cy + ry_outer * si, 0.004, 'turret_ring_outer_seat'))
        outer_top.append(mb.v(cx + rx_outer * co, cy + ry_outer * si, h, 'turret_ring_outer_lip'))
        inner_low.append(mb.v(cx + rx_inner * co, cy + ry_inner * si, 0.006, 'turret_ring_inner_seat'))
        inner_top.append(mb.v(cx + rx_inner * co, cy + ry_inner * si, h + 0.004, 'turret_ring_inner_lip'))
    for i in range(segments):
        j = (i + 1) % segments
        mb.add_quad(outer_top[i], outer_top[j], inner_top[j], inner_top[i])
        mb.add_quad(outer_low[j], outer_low[i], outer_top[i], outer_top[j])
        mb.add_quad(inner_low[i], inner_low[j], inner_top[j], inner_top[i])


def create_feature_mesh(source_bvh, source_points, material, source_name):
    b = bounds(source_points)
    xs_all = [p.x for p in source_points]; ys_all = [p.y for p in source_points]
    x0 = q(xs_all, 0.02); x1 = q(xs_all, 0.98)
    y0 = q(ys_all, 0.04); y1 = q(ys_all, 0.96)
    xr = x1 - x0; yr = y1 - y0
    mb = MeshBuilder(source_bvh, b)

    xs = [x0, x0 + xr * 0.13, x0 + xr * 0.34, x0 + xr * 0.55, x0 + xr * 0.76, x1]
    ys = [y0, y0 + yr * 0.18, y0 + yr * 0.40, y0 + yr * 0.62, y0 + yr * 0.84, y1]
    add_plate_grid(mb, xs, ys)

    # Source-measured feature placement. These are proportional selectors over the measured component envelope,
    # then every emitted vertex is projected back to the source surface.
    add_ring(mb, x0 + xr * 0.31, y0 + yr * 0.53, xr * 0.225, yr * 0.245, xr * 0.155, yr * 0.168, 0.030, 40)
    add_raised_box(mb, x0 + xr * 0.78, y0 + yr * 0.73, xr * 0.185, yr * 0.155, 0.026, 'right_deck_hatch')
    add_raised_box(mb, x0 + xr * 0.66, y0 + yr * 0.44, xr * 0.105, yr * 0.060, 0.020, 'small_front_periscope')
    add_raised_box(mb, x0 + xr * 0.12, y0 + yr * 0.37, xr * 0.095, yr * 0.080, 0.018, 'left_front_boss')

    # Load-bearing side/front lips; thin but volumetric, not zero-thickness planes.
    add_raised_box(mb, x0 + xr * 0.50, y0 + yr * 0.035, xr * 0.98, yr * 0.045, 0.018, 'front_lower_lip')
    add_raised_box(mb, x0 + xr * 0.975, y0 + yr * 0.50, xr * 0.050, yr * 0.80, 0.016, 'right_side_return')
    add_raised_box(mb, x0 + xr * 0.025, y0 + yr * 0.50, xr * 0.050, yr * 0.82, 0.016, 'left_side_return')

    mesh = bpy.data.meshes.new(ASSET_ID + '_mesh')
    mesh.from_pydata(mb.verts, [], mb.faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(material)
    for p in mesh.polygons:
        p.use_smooth = False
    obj = bpy.data.objects.new(ASSET_ID + '_upper_front_glacis_feature_retopo', mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = ROLE
    obj['source_object'] = source_name
    obj['authoring_policy'] = 'Clean source-supported feature-loop retopo: plate grid, turret-ring lip, hatches, and returns are projected to source surface and kept low-poly.'
    obj.modifiers.new('weighted_normals_feature_retopo', 'WEIGHTED_NORMAL')
    landmarks = {
        'source_bounds': b,
        'feature_policy': 'proportional source envelope selectors with per-vertex source ray support',
        'features': ['load_bearing_plate_grid', 'turret_ring', 'right_deck_hatch', 'small_front_periscope', 'left_front_boss', 'front_lower_lip', 'side_returns'],
    }
    return obj, mb.provenance, landmarks


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
    return {
        'center': center, 'view_dir': view_dir, 'right': right, 'up': up,
        'min_r': min_r - span_r * margin, 'max_r': max_r + span_r * margin,
        'min_u': min_u - span_u * margin, 'max_u': max_u + span_u * margin,
        'origin_base': center - view_dir * 5.0,
    }


def ray_for_uv(cam, ix, iy, w, h):
    r = cam['min_r'] + (cam['max_r'] - cam['min_r']) * (ix / w)
    u = cam['min_u'] + (cam['max_u'] - cam['min_u']) * (iy / h)
    origin = cam['origin_base'] + cam['right'] * r + cam['up'] * u
    return origin, cam['view_dir']


def sample_depth_image(bvh, cam, w, h):
    vals = [] ; mask = []
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


def depth_compare(source_bvh, retopo_obj, cam):
    retopo_bvh, _verts, _polys = build_bvh(retopo_obj)
    src_vals, src_mask = sample_depth_image(source_bvh, cam, DEPTH_W, DEPTH_H)
    ret_vals, ret_mask = sample_depth_image(retopo_bvh, cam, DEPTH_W, DEPTH_H)
    shared = [a and b for a, b in zip(src_mask, ret_mask)]
    union = [a or b for a, b in zip(src_mask, ret_mask)]
    errors = [] ; err_vals = []
    for sv, rv, m in zip(src_vals, ret_vals, shared):
        if m:
            e = abs(sv - rv); errors.append(e); err_vals.append(e)
        else:
            err_vals.append(None)
    errors_sorted = sorted(errors)
    def pct(qv):
        if not errors_sorted: return None
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
    lo = min(present); hi = max(present)
    save_gray_png(RENDER_DIR / 'source_depth.png', src_vals, src_mask, DEPTH_W, DEPTH_H, lo, hi)
    save_gray_png(RENDER_DIR / 'retopo_depth.png', ret_vals, ret_mask, DEPTH_W, DEPTH_H, lo, hi)
    save_gray_png(RENDER_DIR / 'depth_abs_error.png', err_vals, shared, DEPTH_W, DEPTH_H, 0.0, max(errors) if errors else 1.0)
    (MODEL_DIR / 'depth_error_report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def add_camera_from_basis(cam_basis):
    center = cam_basis['center']
    view_dir = cam_basis['view_dir']
    cam_loc = center - view_dir * 3.2
    bpy.ops.object.camera_add(location=cam_loc)
    cam = bpy.context.object
    cam.name = ASSET_ID + '_depth_parity_camera'
    look_at(cam, center)
    cam.data.type = 'ORTHO'
    span_r = cam_basis['max_r'] - cam_basis['min_r']
    span_u = cam_basis['max_u'] - cam_basis['min_u']
    cam.data.ortho_scale = max(span_u, span_r * 0.68)
    return cam


def render_shaded(source_obj, retopo_obj, cam):
    bpy.ops.object.light_add(type='AREA', location=cam.location + Vector((0, -1.0, 2.2)))
    light = bpy.context.object
    light.name = ASSET_ID + '_softbox'
    light.data.energy = 700
    light.data.size = 4.0
    engine_items = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
    if hasattr(bpy.context.scene, 'eevee'):
        bpy.context.scene.eevee.taa_render_samples = 48
    bpy.context.scene.render.resolution_x = 1280
    bpy.context.scene.render.resolution_y = 840
    bpy.context.scene.camera = cam
    for obj, fn in [(source_obj, 'source_shaded_same_angle.png'), (retopo_obj, 'retopo_shaded_same_angle.png')]:
        source_obj.hide_render = obj != source_obj
        retopo_obj.hide_render = obj != retopo_obj
        bpy.context.scene.render.filepath = str(RENDER_DIR / fn)
        bpy.ops.render.render(write_still=True)
    source_obj.hide_render = True
    retopo_obj.hide_render = False


def main():
    ensure_dirs(); reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_obj = find_source_object()
    source_obj.name = ASSET_ID + '_hidden_source_upper_glacis'
    source_mat = make_mat(ASSET_ID + '_source_gray', (0.66, 0.67, 0.62, 1), 0.9)
    retopo_mat = make_mat(ASSET_ID + '_retopo_clay', (0.58, 0.62, 0.54, 1), 0.92)
    source_obj.data.materials.clear(); source_obj.data.materials.append(source_mat)
    source_bvh, source_verts, source_polys = build_bvh(source_obj)
    retopo_obj, provenance, landmarks = create_feature_mesh(source_bvh, source_verts, retopo_mat, source_obj.name)
    cam_basis = camera_basis(source_verts)
    depth_report = depth_compare(source_bvh, retopo_obj, cam_basis)
    cam = add_camera_from_basis(cam_basis)
    render_shaded(source_obj, retopo_obj, cam)
    source_obj.hide_viewport = True; source_obj.hide_render = True
    deps = bpy.context.evaluated_depsgraph_get(); eo = retopo_obj.evaluated_get(deps); mesh = eo.to_mesh()
    try:
        stats = {'triangles': tri_count(mesh), 'polygons': len(mesh.polygons), 'vertices': len(mesh.vertices)}
    finally:
        eo.to_mesh_clear()
    blend_path = BLEND_DIR / (ASSET_ID + '.blend')
    glb_path = MODEL_DIR / (ASSET_ID + '.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT')
    retopo_obj.select_set(True); bpy.context.view_layer.objects.active = retopo_obj
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    provenance_path = MODEL_DIR / 'retopo_vertex_provenance.json'
    landmarks_path = MODEL_DIR / 'retopo_landmarks.json'
    provenance_path.write_text(json.dumps({'asset_id': ASSET_ID, 'vertices': provenance}, indent=2) + '\n')
    landmarks_path.write_text(json.dumps({'asset_id': ASSET_ID, **landmarks}, indent=2) + '\n')
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'scratch_one_piece_feature_loop_retopo',
        'revision': REVISION,
        'source_glb': str(SOURCE_GLB.relative_to(ROOT)),
        'source_component': ROLE,
        'authoring_policy': retopo_obj['authoring_policy'],
        'statistics_primary_piece': stats,
        'primary_piece_count': 1,
        'provenance': {'path': str(provenance_path.relative_to(ROOT)), 'output_vertices': len(provenance)},
        'landmarks': {'path': str(landmarks_path.relative_to(ROOT)), 'features': landmarks['features']},
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
    note = '# ' + ASSET_ID + '\n\nClean source-supported feature-loop retopo pass. Scratch diagnostic only, not cloud accepted.\n\n- Source component: ' + ROLE + '\n- Stats: ' + str(stats) + '\n- Depth report: ' + str(depth_report) + '\n- This pass rejects f01 depth-sheet ugliness by keeping explicit hard-surface feature loops.\n'
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    print(json.dumps({'asset_id': ASSET_ID, 'stats': stats, 'depth_report': depth_report, 'glb': str(glb_path)}, indent=2))


main()
