
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
SOURCE_GLB = SCRATCH / 'models' / 'real_sherman_chassis_reference_kit_scratch_v1' / 'real_sherman_chassis_reference_kit_scratch_v1.glb'
ASSET_ID = 'real_sherman_upper_glacis_surgical_hybrid_scratch_f09'
REVISION = 'f09-f05-source-faithful-local-analytic-surgery'
MODEL_DIR = SCRATCH / 'models' / ASSET_ID
BLEND_DIR = SCRATCH / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH / 'notes'

SOURCE_NEEDLE = 'source_component_0_upper_front_glacis'
ROLE = 'source_component_0_upper_front_glacis_assembly'
GRID_W = 64
GRID_H = 48
DEPTH_W = 160
DEPTH_H = 112
PLANE_TOL = 0.026
JUMP_LIMIT = 0.20
MIN_CELL = 1


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


def world_mesh_data(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    mesh = eo.to_mesh()
    try:
        mw = obj.matrix_world.copy()
        verts = [mw @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
        tri_centers = []
        for poly in mesh.polygons:
            c = Vector((0, 0, 0))
            for idx in poly.vertices:
                c += verts[idx]
            tri_centers.append(c / len(poly.vertices))
        return verts, polys, tri_centers
    finally:
        eo.to_mesh_clear()


def find_source_object():
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and SOURCE_NEEDLE in obj.name:
            return obj
    raise RuntimeError('upper glacis source object not found')


def build_bvh(obj):
    verts, polys, centers = world_mesh_data(obj)
    return BVHTree.FromPolygons(verts, polys, all_triangles=False), verts, polys, centers


def camera_basis(points):
    center = Vector((0, 0, 0))
    for p in points:
        center += p
    center /= len(points)
    view_dir = Vector((0.08, 1.0, -0.12)).normalized()
    right = Vector((1, 0, 0))
    up = right.cross(view_dir).normalized()
    right = view_dir.cross(up).normalized()
    coords = []
    for p in points:
        r = (p - center).dot(right)
        u = (p - center).dot(up)
        coords.append((r, u))
    min_r = min(c[0] for c in coords); max_r = max(c[0] for c in coords)
    min_u = min(c[1] for c in coords); max_u = max(c[1] for c in coords)
    span_r = max_r - min_r
    span_u = max_u - min_u
    margin = 0.14
    min_r -= span_r * margin; max_r += span_r * margin
    min_u -= span_u * margin; max_u += span_u * margin
    origin_base = center - view_dir * 5.0
    return {'center': center, 'view_dir': view_dir, 'right': right, 'up': up, 'min_r': min_r, 'max_r': max_r, 'min_u': min_u, 'max_u': max_u, 'origin_base': origin_base}


def ray_for_uv(cam, ix, iy, w, h):
    r = cam['min_r'] + (cam['max_r'] - cam['min_r']) * (ix / w)
    u = cam['min_u'] + (cam['max_u'] - cam['min_u']) * (iy / h)
    origin = cam['origin_base'] + cam['right'] * r + cam['up'] * u
    return origin, cam['view_dir']


def sample_grid(bvh, cam, w, h):
    hits = {}
    for y in range(h + 1):
        for x in range(w + 1):
            origin, direction = ray_for_uv(cam, x, y, w, h)
            hit = bvh.ray_cast(origin, direction, 20.0)
            loc, normal, face_index, dist = hit
            if loc is not None:
                hits[(x, y)] = {'point': loc, 'depth': dist, 'normal': normal, 'face': int(face_index)}
    return hits


def fit_error(hits, x0, y0, x1, y1):
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if any(c not in hits for c in corners):
        return None
    d00 = hits[(x0, y0)]['depth']; d10 = hits[(x1, y0)]['depth']
    d11 = hits[(x1, y1)]['depth']; d01 = hits[(x0, y1)]['depth']
    max_jump = max(d00, d10, d11, d01) - min(d00, d10, d11, d01)
    max_err = 0.0
    samples = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if (x, y) not in hits:
                return None
            tx = 0 if x1 == x0 else (x - x0) / (x1 - x0)
            ty = 0 if y1 == y0 else (y - y0) / (y1 - y0)
            est = (d00 * (1 - tx) * (1 - ty) + d10 * tx * (1 - ty) + d11 * tx * ty + d01 * (1 - tx) * ty)
            max_err = max(max_err, abs(hits[(x, y)]['depth'] - est))
            samples += 1
    return max_err, max_jump, samples


def split_cells(hits, x0, y0, x1, y1, out):
    if x1 <= x0 or y1 <= y0:
        return
    fit = fit_error(hits, x0, y0, x1, y1)
    width = x1 - x0
    height = y1 - y0
    if fit is not None:
        err, jump, _samples = fit
        if (err <= PLANE_TOL and jump <= JUMP_LIMIT) or (width <= MIN_CELL and height <= MIN_CELL):
            out.append((x0, y0, x1, y1, err, jump))
            return
    if width <= MIN_CELL and height <= MIN_CELL:
        return
    if width >= height and width > MIN_CELL:
        xm = (x0 + x1) // 2
        split_cells(hits, x0, y0, xm, y1, out)
        split_cells(hits, xm, y0, x1, y1, out)
    else:
        ym = (y0 + y1) // 2
        split_cells(hits, x0, y0, x1, ym, out)
        split_cells(hits, x0, ym, x1, y1, out)


def make_retopo_mesh(hits, cells, material, source_name):
    vertex_map = {}
    verts = []
    provenance = []
    def add_v(key, semantic):
        if key in vertex_map:
            return vertex_map[key]
        h = hits[key]
        idx = len(verts)
        vertex_map[key] = idx
        verts.append(tuple(h['point']))
        provenance.append({
            'output_vertex': idx,
            'grid': [int(key[0]), int(key[1])],
            'support': {'kind': 'source_face_ray_hit', 'source_object': source_name, 'source_face': int(h['face']), 'depth': float(h['depth'])},
            'semantic_patch': semantic,
            'world': [float(h['point'].x), float(h['point'].y), float(h['point'].z)]
        })
        return idx
    faces = []
    landmarks = []
    for x0, y0, x1, y1, err, jump in cells:
        if all(k in hits for k in [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]):
            semantic = 'depth_carrying_patch'
            if jump > 0.08:
                semantic = 'silhouette_or_plane_break_patch'
            f = (add_v((x0,y0), semantic), add_v((x1,y0), semantic), add_v((x1,y1), semantic), add_v((x0,y1), semantic))
            if len(set(f)) == 4:
                faces.append(f)
                landmarks.append({'cell': [x0,y0,x1,y1], 'fit_error': float(err), 'depth_jump': float(jump), 'semantic_patch': semantic})
    mesh = bpy.data.meshes.new(ASSET_ID + '_mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(material)
    for p in mesh.polygons:
        p.use_smooth = False
    obj = bpy.data.objects.new(ASSET_ID + '_upper_front_glacis_retopo', mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = ROLE
    obj['source_object'] = source_name
    obj['primary_retopo_piece'] = True
    obj['authoring_policy'] = 'Adaptive source-depth retopo: vertices come from ray hits on the source component and are retained where they carry silhouette or depth structure.'
    obj.modifiers.new('weighted_normals_depth_retopo', 'WEIGHTED_NORMAL')
    return obj, provenance, landmarks


def sample_depth_image(bvh, cam, w, h):
    vals = []
    mask = []
    for y in range(h):
        for x in range(w):
            origin, direction = ray_for_uv(cam, x + 0.5, y + 0.5, w, h)
            loc, normal, face_index, dist = bvh.ray_cast(origin, direction, 20.0)
            if loc is None:
                vals.append(None); mask.append(False)
            else:
                vals.append(float(dist)); mask.append(True)
    return vals, mask


def save_gray_png(path, values, mask, w, h, lo=None, hi=None):
    present = [v for v, m in zip(values, mask) if m and v is not None]
    if not present:
        present = [0.0]
    if lo is None: lo = min(present)
    if hi is None: hi = max(present)
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
                pix[j:j+4] = [0.0, 0.0, 0.0, 0.0]
    img.pixels.foreach_set(pix)
    img.filepath_raw = str(path)
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def depth_compare(source_bvh, retopo_obj, cam):
    retopo_bvh, _verts, _polys, _centers = build_bvh(retopo_obj)
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
    def pct(q):
        if not errors_sorted:
            return None
        return errors_sorted[min(len(errors_sorted)-1, int(q * (len(errors_sorted)-1)))]
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
    err_hi = max(errors) if errors else 1.0
    save_gray_png(RENDER_DIR / 'depth_abs_error.png', err_vals, shared, DEPTH_W, DEPTH_H, 0.0, err_hi)
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
    light.data.energy = 650
    light.data.size = 4.2
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





def q(vals, t):
    vals = sorted(vals)
    return vals[int((len(vals) - 1) * t)]


def measured_ring(source_verts):
    xs=[p.x for p in source_verts]; ys=[p.y for p in source_verts]; zs=[p.z for p in source_verts]
    z_hi=q(zs,0.86)
    pts=[p for p in source_verts if p.z >= z_hi - 0.012]
    # The turret ring is the broad, near-center high circular/elliptic structure.
    cx=q([p.x for p in pts],0.43)
    cy=q([p.y for p in pts],0.52)
    local=[p for p in pts if abs(p.x-cx)<0.24 and abs(p.y-cy)<0.24]
    if local:
        cx=(min(p.x for p in local)+max(p.x for p in local))*0.5
        cy=(min(p.y for p in local)+max(p.y for p in local))*0.5
        rx=(max(p.x for p in local)-min(p.x for p in local))*0.42
        ry=(max(p.y for p in local)-min(p.y for p in local))*0.42
    else:
        rx=(max(xs)-min(xs))*0.20; ry=(max(ys)-min(ys))*0.20
    return {'cx':cx,'cy':cy,'rx_outer':rx,'ry_outer':ry,'rx_inner':rx*0.68,'ry_inner':ry*0.68,'z':q(zs,0.90)}


def z_at_xy(source_bvh, x, y, fallback):
    loc, normal, face_index, dist = source_bvh.ray_cast(Vector((x,y,fallback+1.0)), Vector((0,0,-1)), 3.0)
    return loc.z if loc is not None else fallback


def make_mat_local(name, color):
    mat=bpy.data.materials.new(name); mat.diffuse_color=color; mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF'); bsdf.inputs['Base Color'].default_value=color; bsdf.inputs['Roughness'].default_value=0.9
    return mat


def add_annular_ring(ring, source_bvh, material):
    n=40; h=0.018
    verts=[]; faces=[]
    for i in range(n):
        a=2*math.pi*i/n; ca=math.cos(a); sa=math.sin(a)
        for rx,ry,zoff in [(ring['rx_outer'],ring['ry_outer'],0),(ring['rx_outer'],ring['ry_outer'],h),(ring['rx_inner'],ring['ry_inner'],h),(ring['rx_inner'],ring['ry_inner'],0)]:
            x=ring['cx']+rx*ca; y=ring['cy']+ry*sa; z=z_at_xy(source_bvh,x,y,ring['z'])+0.004+zoff
            verts.append((x,y,z))
    for i in range(n):
        j=(i+1)%n
        o0=i*4; o1=j*4
        faces.append((o0+1,o1+1,o1+2,o0+2))
        faces.append((o1,o0,o0+1,o1+1))
        faces.append((o0+3,o1+3,o1+2,o0+2))
        faces.append((o0,o1,o1+3,o0+3))
    mesh=bpy.data.meshes.new(ASSET_ID+'_clean_ring_mesh'); mesh.from_pydata(verts,[],faces); mesh.update(calc_edges=True)
    mesh.materials.append(material)
    obj=bpy.data.objects.new(ASSET_ID+'_clean_measured_turret_ring',mesh); bpy.context.collection.objects.link(obj)
    obj.modifiers.new('weighted_normals_clean_ring','WEIGHTED_NORMAL')
    return obj


def rounded_rect(cx,cy,sx,sy,r):
    pts=[]
    centers=[(cx+sx/2-r,cy+sy/2-r),(cx-sx/2+r,cy+sy/2-r),(cx-sx/2+r,cy-sy/2+r),(cx+sx/2-r,cy-sy/2+r)]
    arcs=[(0,math.pi/2),(math.pi/2,math.pi),(math.pi,1.5*math.pi),(1.5*math.pi,2*math.pi)]
    for (ccx,ccy),(a0,a1) in zip(centers,arcs):
        for k in range(4):
            a=a0+(a1-a0)*k/3; pts.append((ccx+r*math.cos(a),ccy+r*math.sin(a)))
    return pts


def add_hatch(name,cx,cy,sx,sy,source_bvh,zbase,material):
    pts=rounded_rect(cx,cy,sx,sy,min(sx,sy)*0.18); low=[]; high=[]; verts=[]; faces=[]; h=0.014
    for x,y in pts:
        z=z_at_xy(source_bvh,x,y,zbase)+0.006
        low.append(len(verts)); verts.append((x,y,z-0.003)); high.append(len(verts)); verts.append((x,y,z+h))
    faces.append(tuple(high)); faces.append(tuple(reversed(low)))
    n=len(pts)
    for i in range(n): faces.append((low[i],low[(i+1)%n],high[(i+1)%n],high[i]))
    mesh=bpy.data.meshes.new(ASSET_ID+'_'+name+'_mesh'); mesh.from_pydata(verts,[],faces); mesh.update(calc_edges=True); mesh.materials.append(material)
    obj=bpy.data.objects.new(ASSET_ID+'_'+name,mesh); bpy.context.collection.objects.link(obj); obj.modifiers.new('weighted_normals_'+name,'WEIGHTED_NORMAL')
    return obj


def delete_artifact_faces(obj, ring, source_bvh):
    # Delete only local ragged feature zones from the f05 source-faithful mesh; keep the broad hull untouched.
    bpy.context.view_layer.objects.active=obj; obj.select_set(True)
    mesh=obj.data
    remove=[]
    for poly in mesh.polygons:
        c=obj.matrix_world @ poly.center
        rr=((c.x-ring['cx'])/max(ring['rx_outer']*1.10,1e-4))**2 + ((c.y-ring['cy'])/max(ring['ry_outer']*1.10,1e-4))**2
        inner=((c.x-ring['cx'])/max(ring['rx_inner']*0.88,1e-4))**2 + ((c.y-ring['cy'])/max(ring['ry_inner']*0.88,1e-4))**2
        hatch_zone=(ring['cx']+ring['rx_outer']*0.88 < c.x < ring['cx']+ring['rx_outer']*1.85 and ring['cy']-ring['ry_outer']*0.18 < c.y < ring['cy']+ring['ry_outer']*0.55)
        # ring annulus and right hatch ragged zone
        if (rr < 1.22 and inner > 0.72) or hatch_zone:
            remove.append(poly.index)
    for p in mesh.polygons: p.select=False
    for idx in remove: mesh.polygons[idx].select=True
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.delete(type='FACE')
    bpy.ops.object.mode_set(mode='OBJECT')
    return len(remove)


def make_quadriflow_retopo(source_obj, material):
    source_bvh, source_verts, source_polys, source_centers = build_bvh(source_obj)
    ring=measured_ring(source_verts)
    bpy.ops.object.select_all(action='DESELECT')
    source_obj.select_set(True)
    bpy.context.view_layer.objects.active = source_obj
    bpy.ops.object.duplicate()
    obj = bpy.context.object
    obj.name = ASSET_ID + '_upper_front_glacis_f05_base_surgery'
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.dissolve_limited(angle_limit=math.radians(35.0), use_dissolve_boundaries=False, delimit={'NORMAL'})
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.data.materials.clear(); obj.data.materials.append(material)
    removed=delete_artifact_faces(obj, ring, source_bvh)
    clean_mat=make_mat_local(ASSET_ID+'_clean_feature_shells',(0.61,0.63,0.55,1))
    ring_obj=add_annular_ring(ring, source_bvh, clean_mat)
    hatch=add_hatch('clean_right_hatch', ring['cx']+ring['rx_outer']*1.23, ring['cy']+ring['ry_outer']*0.18, ring['rx_outer']*0.48, ring['ry_outer']*0.30, source_bvh, ring['z'], clean_mat)
    # join to one export object, but topology remains disconnected feature shells over source-faithful base
    bpy.ops.object.select_all(action='DESELECT')
    for part in (obj, ring_obj, hatch): part.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.join()
    obj=bpy.context.object
    obj.name=ASSET_ID+'_upper_front_glacis_surgical_hybrid'
    for p in obj.data.polygons: p.use_smooth=False
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = ROLE
    obj['source_object'] = source_obj.name
    obj['primary_retopo_piece'] = True
    obj['authoring_policy'] = 'Surgical hybrid: preserve f05 source-faithful broad hull, delete only local ragged ring/hatch faces, join clean measured annular/hatch shells. Reject f07 box-disk abstraction and f08 bad decimation.'
    obj['surgical_report_json']=json.dumps({'deleted_local_artifact_faces':removed,'ring':ring})
    obj.modifiers.new('weighted_normals_surgical_hybrid','WEIGHTED_NORMAL')
    return obj

def provenance_for_retopo(source_bvh, retopo_obj, source_name):
    deps = bpy.context.evaluated_depsgraph_get()
    eo = retopo_obj.evaluated_get(deps)
    mesh = eo.to_mesh()
    rows = []
    try:
        mw = retopo_obj.matrix_world.copy()
        for i, v in enumerate(mesh.vertices):
            wp = mw @ v.co
            loc, normal, face_index, dist = source_bvh.find_nearest(wp, 1.0)
            rows.append({
                'output_vertex': int(i),
                'support': {
                    'kind': 'nearest_source_surface_after_quadriflow',
                    'source_object': source_name,
                    'source_face': int(face_index) if face_index is not None else -1,
                    'distance': float(dist) if dist is not None else None,
                },
                'semantic_patch': 'quadriflow_preserve_sharp_retopo_vertex',
                'world': [float(wp.x), float(wp.y), float(wp.z)],
            })
    finally:
        eo.to_mesh_clear()
    return rows


def main():
    ensure_dirs()
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
    source_obj = find_source_object()
    source_obj.name = ASSET_ID + '_hidden_source_upper_glacis'
    source_mat = make_mat(ASSET_ID + '_source_gray', (0.66, 0.67, 0.62, 1), 0.9)
    retopo_mat = make_mat(ASSET_ID + '_retopo_clay', (0.60, 0.63, 0.54, 1), 0.92)
    source_obj.data.materials.clear(); source_obj.data.materials.append(source_mat)
    source_bvh, source_verts, source_polys, source_centers = build_bvh(source_obj)
    retopo_obj = make_quadriflow_retopo(source_obj, retopo_mat)
    cam_basis = camera_basis(source_verts)
    depth_report = depth_compare(source_bvh, retopo_obj, cam_basis)
    cam = add_camera_from_basis(cam_basis)
    render_shaded(source_obj, retopo_obj, cam)
    source_obj.hide_viewport = True
    source_obj.hide_render = True
    deps = bpy.context.evaluated_depsgraph_get()
    eo = retopo_obj.evaluated_get(deps)
    mesh = eo.to_mesh()
    try:
        stats = {'triangles': tri_count(mesh), 'polygons': len(mesh.polygons), 'vertices': len(mesh.vertices)}
    finally:
        eo.to_mesh_clear()
    blend_path = BLEND_DIR / (ASSET_ID + '.blend')
    glb_path = MODEL_DIR / (ASSET_ID + '.glb')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT')
    retopo_obj.select_set(True)
    bpy.context.view_layer.objects.active = retopo_obj
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    provenance = provenance_for_retopo(source_bvh, retopo_obj, source_obj.name)
    provenance_path = MODEL_DIR / 'retopo_vertex_provenance.json'
    provenance_path.write_text(json.dumps({'asset_id': ASSET_ID, 'vertices': provenance}, indent=2) + '\n')
    landmarks_path = MODEL_DIR / 'retopo_landmarks.json'
    landmarks = {
        'asset_id': ASSET_ID,
        'dissolve_angle_degrees': 35.0,
        'local_surgery': 'delete ragged f05 ring/hatch faces and replace with measured clean shells',
        'retopo_engine': 'f05 source dissolve plus local analytic ring/hatch replacement',
        'preserve_source_boundaries': True,
        'source_component': ROLE,
        'lesson_from_f01_f08': 'f05 was closest but seamed; f07 was box/disk abstraction; f08 looked like bad decimation. f09 preserves f05 broad hull and surgically replaces only ragged feature zones.'
    }
    landmarks_path.write_text(json.dumps(landmarks, indent=2) + '\n')
    manifest = {
        'asset_id': ASSET_ID,
        'scratch_mode': True,
        'artifact_type': 'scratch_one_piece_quadriflow_retopo',
        'revision': REVISION,
        'source_glb': str(SOURCE_GLB.relative_to(ROOT)),
        'source_component': ROLE,
        'authoring_policy': retopo_obj['authoring_policy'],
        'statistics_primary_piece': stats,
        'primary_piece_count': 1,
        'provenance': {'path': str(provenance_path.relative_to(ROOT)), 'output_vertices': len(provenance)},
        'landmarks': {'path': str(landmarks_path.relative_to(ROOT)), 'dissolve_angle_degrees': 35.0},
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
    note = '# ' + ASSET_ID + '\n\nSurgical hybrid source-faithful retopo pass. Scratch diagnostic only; not cloud accepted.\n\n- Source component: ' + ROLE + '\n- Stats: ' + str(stats) + '\n- Depth report: ' + str(depth_report) + '\n- Intended to preserve f05 source identity while replacing only the ugly ring/hatch seams with clean measured shells.\n'
    (NOTES_DIR / (ASSET_ID + '.md')).write_text(note)
    print(json.dumps({'asset_id': ASSET_ID, 'stats': stats, 'depth_report': depth_report, 'glb': str(glb_path)}, indent=2))

main()
