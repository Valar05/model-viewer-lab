import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH_ROOT = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
SERIES_ID = 'real_sherman_chassis_castbudget_scratch'
REVISION = 'castbudget-three-attempts-bevels-seams-guided-hard-surface'

ATTEMPTS = [
    {'suffix': 'b01', 'label': 'controlled bevel hull kit', 'bevel': 0.018, 'segments': 2, 'seams': 8, 'cast_panels': 1, 'crown': 0.035, 'spacing': 0.48},
    {'suffix': 'b02', 'label': 'budget target cast surfaces and crease seams', 'bevel': 0.026, 'segments': 3, 'seams': 14, 'cast_panels': 2, 'crown': 0.055, 'spacing': 0.44},
    {'suffix': 'b03', 'label': 'upper-budget guided cast metal hull kit', 'bevel': 0.032, 'segments': 4, 'seams': 20, 'cast_panels': 3, 'crown': 0.070, 'spacing': 0.42},
]

SOURCE_POLICY = 'Authored guided hard-surface scratch geometry. No Meshy/source topology copy. No decimation. Triangles must buy bevels, cast crowns, crease seams, or silhouette.'
HULL_BUDGET = {'target_min_triangles': 2500, 'target_max_triangles': 3500, 'hard_cap_triangles': 4500}

def P(x, y, z):
    return (x, -z, y)

def reset_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for datablock in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for item in list(datablock):
            if item.users == 0:
                datablock.remove(item)

def material(name, color, rough=0.9):
    m = bpy.data.materials.new(name)
    m.diffuse_color = color
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = 0.0
    return m

def bbox(points):
    xs=[p[0] for p in points]; ys=[p[1] for p in points]; zs=[p[2] for p in points]
    return {'min':[min(xs),min(ys),min(zs)], 'max':[max(xs),max(ys),max(zs)], 'center':[(min(xs)+max(xs))*0.5,(min(ys)+max(ys))*0.5,(min(zs)+max(zs))*0.5], 'size':[max(xs)-min(xs),max(ys)-min(ys),max(zs)-min(zs)]}

def tri_count_for_mesh(mesh):
    return sum(max(0, len(p.vertices)-2) for p in mesh.polygons)

def evaluated_counts(obj, depsgraph):
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        return {'triangles': tri_count_for_mesh(mesh), 'polygons': len(mesh.polygons), 'vertices': len(mesh.vertices)}
    finally:
        eval_obj.to_mesh_clear()

def add_bevel(obj, width, segments):
    if width <= 0:
        return
    mod = obj.modifiers.new('purposeful_edge_bevel_cast_armor', 'BEVEL')
    mod.width = width
    mod.segments = segments
    mod.profile = 0.55
    mod.affect = 'EDGES'
    obj.modifiers.new('weighted_normals_hard_surface_read', 'WEIGHTED_NORMAL')

def mesh_obj(name, verts, faces, mat, role, note, created, bevel=0, segments=1, purpose='plate'):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata([P(*v) for v in verts], [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj['role'] = role
    obj['note'] = note
    obj['purpose'] = purpose
    obj['source_policy'] = SOURCE_POLICY
    obj['authored_lowpoly'] = True
    obj['decimated'] = False
    obj['runtime_bbox'] = json.dumps(bbox(verts))
    add_bevel(obj, bevel, segments)
    created.append(obj)
    return obj

def prism(name, outer, inner, mat, role, note, created, bevel=0, segments=1, purpose='plate'):
    n=len(outer)
    verts=outer+inner
    faces=[tuple(range(n)), tuple(range(2*n-1,n-1,-1))]
    for i in range(n):
        faces.append((i,(i+1)%n,n+(i+1)%n,n+i))
    return mesh_obj(name, verts, faces, mat, role, note, created, bevel, segments, purpose)

def offset(points, dx=0, dy=0, dz=0):
    return [(x+dx,y+dy,z+dz) for x,y,z in points]

def crowned_plate(name, center, sx, sz, y, thickness, crown, mat, role, note, created, nx, nz, bevel, segments):
    # Grid only where curvature/cast crown is visible; not used on flat rectangular plates.
    cx, cz = center
    verts_top=[]
    for iz in range(nz+1):
        z = cz - sz/2 + sz*iz/nz
        for ix in range(nx+1):
            x = cx - sx/2 + sx*ix/nx
            u = (ix/nx - 0.5)*2
            v = (iz/nz - 0.5)*2
            dome = crown * max(0, 1 - 0.55*u*u - 0.65*v*v)
            verts_top.append((x, y + dome, z))
    verts_bot=[(x, y-thickness, z) for x,_,z in verts_top]
    verts=verts_top+verts_bot
    def idx(ix,iz): return iz*(nx+1)+ix
    bot=(nx+1)*(nz+1)
    faces=[]
    for iz in range(nz):
        for ix in range(nx):
            faces.append((idx(ix,iz), idx(ix+1,iz), idx(ix+1,iz+1), idx(ix,iz+1)))
    # bottom simplified as matching grid so normals/edge export stays sane
    for iz in range(nz):
        for ix in range(nx):
            faces.append((bot+idx(ix,iz+1), bot+idx(ix+1,iz+1), bot+idx(ix+1,iz), bot+idx(ix,iz)))
    for ix in range(nx):
        faces.append((idx(ix,0), bot+idx(ix,0), bot+idx(ix+1,0), idx(ix+1,0)))
        faces.append((idx(ix,nz), idx(ix+1,nz), bot+idx(ix+1,nz), bot+idx(ix,nz)))
    for iz in range(nz):
        faces.append((idx(0,iz), idx(0,iz+1), bot+idx(0,iz+1), bot+idx(0,iz)))
        faces.append((idx(nx,iz), bot+idx(nx,iz), bot+idx(nx,iz+1), idx(nx,iz+1)))
    return mesh_obj(name, verts, faces, mat, role, note, created, bevel, segments, 'cast_crowned_surface')

def seam_strip(name, x0, x1, y, z, width, mat, role, created, bevel, segments, vertical=False):
    if vertical:
        outer=[(x0,y,z-width/2),(x0,y,z+width/2),(x1,y,z+width/2),(x1,y,z-width/2)]
    else:
        outer=[(x0,y,z-width/2),(x1,y,z-width/2),(x1,y,z+width/2),(x0,y,z+width/2)]
    inner=[(x,y-0.012,z) for x,y,z in outer]
    return prism(name, outer, inner, mat, role, 'purposeful raised/creased seam strip; buys material edge catch, not density', created, bevel, segments, 'crease_seam')

def make_attempt(attempt):
    reset_scene()
    asset_id=f'{SERIES_ID}_{attempt["suffix"]}'
    model_dir=SCRATCH_ROOT/'models'/asset_id
    blend_dir=SCRATCH_ROOT/'source_blends'/asset_id
    render_dir=SCRATCH_ROOT/'renders'/asset_id
    notes_dir=SCRATCH_ROOT/'notes'
    for d in (model_dir, blend_dir, render_dir, notes_dir):
        d.mkdir(parents=True, exist_ok=True)
    armor=material(asset_id+'_cast_olive_clay', (0.51,0.55,0.46,1), 0.93)
    dark=material(asset_id+'_shadowed_undercut', (0.07,0.075,0.065,1), 0.96)
    seam_mat=material(asset_id+'_edge_catch_seams', (0.62,0.65,0.55,1), 0.88)
    created=[]
    s=attempt['spacing']; bevel=attempt['bevel']; seg=attempt['segments']; crown=attempt['crown']
    # Reference/exploded kit arrangement: close enough to inspect relationships, not assembled as a tank.
    crowned_plate(asset_id+'_lower_cast_tub_crowned_shell', (0,0), 3.05, 1.72, 0.18, 0.18, crown*0.7, armor, 'lower_tub_cast_shell', 'broad lower hull tub with subtle cast crown and bevel returns', created, 8, 5, bevel*0.7, seg)
    crowned_plate(asset_id+'_upper_glacis_cast_plate', (0.78,0), 1.70, 1.82, 0.64+s, 0.12, crown*0.85, armor, 'upper_glacis_cast_plate', 'sloped front glacis spends triangles on cast crown rather than flat primitive face', created, 7, 5, bevel, seg)
    crowned_plate(asset_id+'_front_transmission_cast_cover', (1.18,0), 1.10, 1.35, -0.30-s*0.5, 0.18, crown, armor, 'front_transmission_cast_cover', 'rounded cast transmission cover; triangle spend belongs here', created, 7, 5, bevel*1.1, seg)
    crowned_plate(asset_id+'_rear_bulkhead_with_return', (-1.38,0), 0.85, 1.55, -0.24-s*0.55, 0.15, crown*0.35, armor, 'rear_bulkhead_return', 'rear hull plate with bevel/return edges', created, 5, 5, bevel, seg)
    crowned_plate(asset_id+'_engine_deck_broad_plate', (-0.85,0), 1.30, 1.55, 0.88+s, 0.08, crown*0.2, armor, 'engine_deck_plate', 'engine deck remains mostly flat but gains useful bevel catch', created, 5, 4, bevel*0.75, seg)
    # Side armor and sponson shelves remain simple but bevel-rich.
    left=[(-1.42,0.08,-1.05),(-0.35,0.45,-1.10),(1.35,0.28,-1.02),(1.22,-0.02,-0.82),(-1.35,-0.02,-0.82)]
    right=[(x,y,-z) for x,y,z in left]
    prism(asset_id+'_left_side_armor_beveled_plate', left, [(x,y,z+0.16) for x,y,z in left], armor, 'left_side_armor', 'side armor is still authored, now bevel-weighted instead of primitive-thin', created, bevel, seg)
    prism(asset_id+'_right_side_armor_beveled_plate', right, [(x,y,z-0.16) for x,y,z in right], armor, 'right_side_armor', 'mirrored side armor with same topology budget', created, bevel, seg)
    shelf=[(-1.38,-0.08,-1.18),(1.34,-0.08,-1.18),(1.28,-0.18,-0.86),(-1.32,-0.18,-0.86)]
    rshelf=[(x,y,-z) for x,y,z in shelf]
    prism(asset_id+'_left_sponson_shelf_beveled_return', shelf, offset(shelf, dy=-0.08), dark, 'left_sponson_shelf', 'track socket shelf uses bevel/return thickness, not a paper slab', created, bevel*0.65, max(1,seg-1))
    prism(asset_id+'_right_sponson_shelf_beveled_return', rshelf, offset(rshelf, dy=-0.08), dark, 'right_sponson_shelf', 'right track socket shelf uses matching bevel/return thickness', created, bevel*0.65, max(1,seg-1))
    # Purposeful crease seams. These are small low-profile surfaces that catch light and define welded/cast plate boundaries.
    seam_count=attempt['seams']
    for i in range(seam_count):
        t=i/max(1,seam_count-1)
        if i % 4 == 0:
            seam_strip(asset_id+f'_glacis_horizontal_crease_{i:02d}', 0.05, 1.48, 0.685+s+0.002*i/seam_count, -0.68+1.36*t, 0.018, seam_mat, 'glacis_crease_seam', created, bevel*0.25, 1)
        elif i % 4 == 1:
            seam_strip(asset_id+f'_engine_deck_crease_{i:02d}', -1.42, -0.28, 0.925+s+0.002*i/seam_count, -0.70+1.40*t, 0.014, seam_mat, 'engine_deck_crease_seam', created, bevel*0.2, 1)
        elif i % 4 == 2:
            seam_strip(asset_id+f'_left_side_weld_crease_{i:02d}', -1.25+2.25*t, -1.02+2.25*t, 0.18, -1.145, 0.014, seam_mat, 'left_side_weld_crease', created, bevel*0.22, 1)
        else:
            seam_strip(asset_id+f'_right_side_weld_crease_{i:02d}', -1.25+2.25*t, -1.02+2.25*t, 0.18, 1.145, 0.014, seam_mat, 'right_side_weld_crease', created, bevel*0.22, 1)
    # Small cast edge pads only in later attempts, not random greeble.
    for j in range(attempt['cast_panels']):
        x=-0.95+j*0.55
        crowned_plate(asset_id+f'_cast_access_lip_{j:02d}', (x, -0.42+0.42*j), 0.34, 0.22, 1.02+s, 0.035, crown*0.18, seam_mat, 'cast_access_lip', 'small raised cast/access lip: silhouette-critical light catch, not decorative density', created, 3, 2, bevel*0.35, 1)
    # Lighting and cameras.
    bpy.ops.object.light_add(type='AREA', location=(0,-5.5,4.8))
    light=bpy.context.object; light.name=asset_id+'_softbox'; light.data.energy=660; light.data.size=5.4
    bpy.ops.object.camera_add(location=P(5.8,3.7,4.7)); front=bpy.context.object; front.name=asset_id+'_front_review_camera'
    bpy.ops.object.camera_add(location=P(-5.7,3.65,4.55)); rear=bpy.context.object; rear.name=asset_id+'_rear_review_camera'
    def look_at(obj,target):
        direction=Vector(target)-obj.location
        obj.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
    for cam in (front,rear):
        look_at(cam, Vector(P(0,0.38,0)))
        cam.data.lens=34
    depsgraph=bpy.context.evaluated_depsgraph_get()
    part_stats=[]
    for obj in created:
        counts=evaluated_counts(obj, depsgraph)
        part_stats.append({'object': obj.name, 'role': obj.get('role'), 'purpose': obj.get('purpose'), **counts, 'bbox_runtime': json.loads(obj['runtime_bbox'])})
    totals={'triangles': sum(p['triangles'] for p in part_stats), 'polygons': sum(p['polygons'] for p in part_stats), 'vertices': sum(p['vertices'] for p in part_stats)}
    in_budget=HULL_BUDGET['target_min_triangles'] <= totals['triangles'] <= HULL_BUDGET['target_max_triangles']
    blend_path=blend_dir/f'{asset_id}.blend'; glb_path=model_dir/f'{asset_id}.glb'; manifest_path=model_dir/'model_manifest.json'; notes_path=notes_dir/f'{asset_id}.md'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action='DESELECT')
    for obj in created:
        obj.select_set(True)
    bpy.context.view_layer.objects.active=created[0]
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)
    engine_items=[item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    bpy.context.scene.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
    if hasattr(bpy.context.scene,'eevee'):
        bpy.context.scene.eevee.taa_render_samples=32
    bpy.context.scene.render.resolution_x=1280; bpy.context.scene.render.resolution_y=840
    for cam,filename in ((front,'front_three_quarter.png'),(rear,'rear_three_quarter.png')):
        bpy.context.scene.camera=cam
        bpy.context.scene.render.filepath=str(render_dir/filename)
        bpy.ops.render.render(write_still=True)
    manifest={
        'asset_id': asset_id,
        'series_id': SERIES_ID,
        'attempt': attempt['suffix'],
        'attempt_label': attempt['label'],
        'scratch_mode': True,
        'artifact_type': 'scratch_guided_hard_surface_cast_hull_kit',
        'revision': REVISION,
        'source_policy': SOURCE_POLICY,
        'budget_source': 'docs/doctrine/mobile-tank-asset-budget-manifest.md hull subsystem: 2.5k-3.5k target, 4.5k hard cap',
        'hull_budget': HULL_BUDGET,
        'configuration_policy': 'Exploded/reference hull kit, not assembled tank pose.',
        'triangle_policy': 'Reject triangles for density. Accept triangles that buy bevels, cast crowns, crease seams, silhouette, or material edge catch.',
        'statistics': totals,
        'in_target_hull_budget': in_budget,
        'object_count': len(created),
        'outputs': {'blend': str(blend_path.relative_to(ROOT)), 'glb': str(glb_path.relative_to(ROOT)), 'front_render': str((render_dir/'front_three_quarter.png').relative_to(ROOT)), 'rear_render': str((render_dir/'rear_three_quarter.png').relative_to(ROOT))},
        'parts': part_stats,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf8')
    notes_path.write_text(f"""# {asset_id}\n\nScratch guided hard-surface cast hull attempt.\n\n- Attempt: {attempt['suffix']} - {attempt['label']}\n- Triangles: {totals['triangles']}\n- Polygons: {totals['polygons']}\n- Vertices: {totals['vertices']}\n- Objects: {len(created)}\n- In 2.5k-3.5k hull target: {in_budget}\n- Triangle policy: bevels, crease seams, cast crowns, silhouette, material edge catch only.\n- No decimation. No source topology copy.\n- Scratch only; Blender renders are diagnostics, not acceptance.\n""", encoding='utf8')
    return manifest

all_manifests=[]
for attempt in ATTEMPTS:
    all_manifests.append(make_attempt(attempt))
summary=SCRATCH_ROOT/'notes'/f'{SERIES_ID}_summary.md'
summary.write_text('# real_sherman_chassis_castbudget_scratch summary\n\n' + '\n'.join(f"- {m['asset_id']}: {m['statistics']['triangles']} tris, {m['statistics']['polygons']} polys, {m['statistics']['vertices']} verts, objects={m['object_count']}, in_budget={m['in_target_hull_budget']}" for m in all_manifests) + '\n', encoding='utf8')
print(json.dumps({'series_id': SERIES_ID, 'attempts': [{'asset_id': m['asset_id'], **m['statistics'], 'objects': m['object_count'], 'in_budget': m['in_target_hull_budget']} for m in all_manifests]}, indent=2))
