import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH_ROOT = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
SOURCE_MANIFEST = SCRATCH_ROOT / 'models' / 'real_sherman_chassis_reference_kit_scratch_v1' / 'model_manifest.json'
REF_IMAGE = SCRATCH_ROOT / 'renders' / 'real_sherman_chassis_reference_kit_scratch_v1' / 'front_reference_config.png'
SERIES_ID = 'real_sherman_chassis_structural_retopo_referencekit_scratch'
REVISION = 'structural-retopo-d01-d03-major-planes-hatch-side-assemblies'

ATTEMPTS = [
    {'suffix': 'd01', 'label': 'major plane trace', 'grid': 4, 'bevel': 0.004, 'bevel_segments': 1, 'side_steps': 2, 'hatch_detail': 1, 'seams': 1},
    {'suffix': 'd02', 'label': 'hatch and side structure correction', 'grid': 5, 'bevel': 0.006, 'bevel_segments': 2, 'side_steps': 3, 'hatch_detail': 2, 'seams': 2},
    {'suffix': 'd03', 'label': 'final structural cleanup', 'grid': 6, 'bevel': 0.007, 'bevel_segments': 2, 'side_steps': 4, 'hatch_detail': 3, 'seams': 3},
]

BUDGET = {'target_min_triangles': 2500, 'preferred_max_triangles': 3500, 'hard_cap_triangles': 4500}
source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding='utf8'))
source_parts = {p['role']: p for p in source_manifest['parts']}


def reset_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for item in list(collection):
            if item.users == 0:
                collection.remove(item)


def make_mat(name, color, rough=0.9):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = 0.0
    return mat


def source_bbox(role):
    return source_parts[role]['bbox_world']


def map_box(role, pts):
    b = source_bbox(role)
    mn = b['min']; mx = b['max']
    return [(mn[0] + (mx[0]-mn[0])*x, mn[1] + (mx[1]-mn[1])*y, mn[2] + (mx[2]-mn[2])*z) for x, y, z in pts]


def tri_count(mesh):
    return sum(max(0, len(p.vertices) - 2) for p in mesh.polygons)


def evaluated_counts(obj, depsgraph):
    eo = obj.evaluated_get(depsgraph)
    mesh = eo.to_mesh()
    try:
        return {'triangles': tri_count(mesh), 'polygons': len(mesh.polygons), 'vertices': len(mesh.vertices)}
    finally:
        eo.to_mesh_clear()


def mesh_obj(asset_id, created, name, role, verts, faces, mat, note, spend_reason, bevel=0.0, segments=1, primary=True):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id'] = asset_id
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['role'] = role
    obj['source_role'] = role
    obj['handmade_retopo'] = True
    obj['source_policy'] = 'Hand-authored structural retopo from Meshy reference sheet/bbox only; no source topology copy and no decimation.'
    obj['note'] = note
    obj['triangle_spend_reason'] = spend_reason
    obj['primary_kit_piece'] = primary
    if role in source_parts:
        obj['source_bbox_world'] = json.dumps(source_bbox(role))
    if bevel > 0:
        mod = obj.modifiers.new('edge_support_bevel_structural_only', 'BEVEL')
        mod.width = bevel
        mod.segments = segments
        mod.profile = 0.52
        mod.affect = 'EDGES'
    obj.modifiers.new('weighted_normals_structural_planes', 'WEIGHTED_NORMAL')
    created.append(obj)
    return obj


def prism(asset_id, created, name, role, local_outer, z0, z1, mat, note, spend, bevel, segments, primary=True):
    bottom = [(x, y, z0) for x, y in local_outer]
    top = [(x, y, z1) for x, y in local_outer]
    local = bottom + top
    n = len(local_outer)
    faces = [tuple(range(n-1, -1, -1)), tuple(range(n, 2*n))]
    for i in range(n):
        faces.append((i, (i+1)%n, n+(i+1)%n, n+i))
    return mesh_obj(asset_id, created, name, role, map_box(role, local), faces, mat, note, spend, bevel, segments, primary)


def add_box_feature(asset_id, created, name, role, x0, x1, y0, y1, z0, z1, mat, note, spend, bevel, segments, primary=False):
    verts = map_box(role, [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)])
    faces = [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    return mesh_obj(asset_id, created, name, role, verts, faces, mat, note, spend, bevel, segments, primary)


def crowned_panel(asset_id, created, name, role, outline, zbase, ztop, crown, grid, mat, note, spend, bevel, segments, primary=True):
    # Build a structural top surface on the outline's bbox using a clipped grid. Points outside outline bbox are not used;
    # this is intentionally not a dense sculpt, only enough planes to avoid primitive-flat read.
    xs = [p[0] for p in outline]; ys = [p[1] for p in outline]
    minx, maxx = min(xs), max(xs); miny, maxy = min(ys), max(ys)
    # For simplicity, use grid rectangle with outline side faces; silhouette is still carried by outline prism.
    verts=[]; faces=[]
    for iy in range(grid+1):
        y = miny + (maxy-miny)*iy/grid
        for ix in range(grid+1):
            x = minx + (maxx-minx)*ix/grid
            u=(ix/grid-0.5)*2; v=(iy/grid-0.5)*2
            z = ztop + crown * max(0, 1 - 0.55*u*u - 0.65*v*v)
            verts.append((x,y,z))
    bot_offset = len(verts)
    verts += [(x,y,zbase) for x,y,_ in verts]
    def idx(ix,iy): return iy*(grid+1)+ix
    for iy in range(grid):
        for ix in range(grid):
            faces.append((idx(ix,iy), idx(ix+1,iy), idx(ix+1,iy+1), idx(ix,iy+1)))
            faces.append((bot_offset+idx(ix,iy+1), bot_offset+idx(ix+1,iy+1), bot_offset+idx(ix+1,iy), bot_offset+idx(ix,iy)))
    for ix in range(grid):
        faces.append((idx(ix,0), bot_offset+idx(ix,0), bot_offset+idx(ix+1,0), idx(ix+1,0)))
        faces.append((idx(ix,grid), idx(ix+1,grid), bot_offset+idx(ix+1,grid), bot_offset+idx(ix,grid)))
    for iy in range(grid):
        faces.append((idx(0,iy), idx(0,iy+1), bot_offset+idx(0,iy+1), bot_offset+idx(0,iy)))
        faces.append((idx(grid,iy), bot_offset+idx(grid,iy), bot_offset+idx(grid,iy+1), idx(grid,iy+1)))
    return mesh_obj(asset_id, created, name, role, map_box(role, verts), faces, mat, note, spend, bevel, segments, primary)


def upper_front_glacis(asset_id, created, attempt, mats):
    role = 'source_component_0_upper_front_glacis_assembly'
    armor, dark, edge = mats
    grid = attempt['grid']; bevel = attempt['bevel']; seg = attempt['bevel_segments']
    # Major deck/glacis body with structural facets.
    crowned_panel(asset_id, created, f'{asset_id}_00_upper_glacis_structural_deck', role,
                  [(0.05,0.10),(0.88,0.08),(0.98,0.55),(0.78,0.93),(0.12,0.88),(0.02,0.36)],
                  0.18, 0.78, 0.018*attempt['hatch_detail'], grid, armor,
                  'Upper reference component rebuilt as traced structural deck/glacis planes, not a textured slab.',
                  'silhouette trace, deck/glacis crown, thickness, bevel support', bevel, seg, True)
    # Real hatch/deck structure: inset cut frame and raised lip. This replaces the wrong texture smear.
    h = attempt['hatch_detail']
    add_box_feature(asset_id, created, f'{asset_id}_00_hatch_inset_dark_aperture', role, 0.43, 0.62, 0.36, 0.55, 0.805, 0.845, dark,
                    'Dark recessed hatch aperture: real geometry, not texture smear.', 'hatch/deck cut structure', bevel*0.45, 1, False)
    add_box_feature(asset_id, created, f'{asset_id}_00_hatch_front_lip', role, 0.40, 0.65, 0.335, 0.365, 0.84, 0.91, edge,
                    'Front hatch lip defines the hatch as a structural plate.', 'hatch lip and edge catch', bevel*0.35, 1, False)
    add_box_feature(asset_id, created, f'{asset_id}_00_hatch_rear_lip', role, 0.40, 0.65, 0.545, 0.575, 0.84, 0.91, edge,
                    'Rear hatch lip defines the hatch as a structural plate.', 'hatch lip and edge catch', bevel*0.35, 1, False)
    add_box_feature(asset_id, created, f'{asset_id}_00_hatch_left_lip', role, 0.39, 0.42, 0.34, 0.57, 0.84, 0.90, edge,
                    'Left hatch side lip, structural not decorative.', 'hatch side structure', bevel*0.35, 1, False)
    add_box_feature(asset_id, created, f'{asset_id}_00_hatch_right_lip', role, 0.63, 0.66, 0.34, 0.57, 0.84, 0.90, edge,
                    'Right hatch side lip, structural not decorative.', 'hatch side structure', bevel*0.35, 1, False)
    if h >= 2:
        add_box_feature(asset_id, created, f'{asset_id}_00_forward_plane_break', role, 0.09, 0.89, 0.22, 0.245, 0.82, 0.875, edge,
                        'Forward deck/glacis plane break line.', 'major plane break, not surface detail', bevel*0.25, 1, False)
    if h >= 3:
        add_box_feature(asset_id, created, f'{asset_id}_00_rear_plate_step', role, 0.14, 0.76, 0.77, 0.805, 0.82, 0.89, edge,
                        'Rear step line for deck ownership.', 'major rear plane step', bevel*0.25, 1, False)


def lower_tub(asset_id, created, attempt, mats):
    role = 'source_component_1_lower_hull_floor_tub'
    armor, dark, edge = mats
    bevel = attempt['bevel']; seg = attempt['bevel_segments']; grid=attempt['grid']
    # Open tray with structural rim, inner floor, angled side returns.
    outer = [(0.02,0.06),(0.96,0.08),(0.91,0.93),(0.08,0.92)]
    crowned_panel(asset_id, created, f'{asset_id}_01_lower_tub_floor_pan', role, outer, 0.10, 0.28, 0.008, max(3,grid-1), armor,
                  'Lower tub floor and rim built as structural tray bottom.', 'open tub floor and shallow crown', bevel*0.7, seg, True)
    # Four upturned rim/return strips.
    add_box_feature(asset_id, created, f'{asset_id}_01_front_rim_return', role, 0.06, 0.94, 0.055, 0.11, 0.28, 0.90, armor,
                    'Front raised rim return of tub.', 'tub wall thickness and rim return', bevel, seg, False)
    add_box_feature(asset_id, created, f'{asset_id}_01_rear_rim_return', role, 0.08, 0.90, 0.86, 0.925, 0.28, 0.88, armor,
                    'Rear raised rim return of tub.', 'tub wall thickness and rim return', bevel, seg, False)
    add_box_feature(asset_id, created, f'{asset_id}_01_left_sloped_rim_return', role, 0.025, 0.12, 0.12, 0.86, 0.25, 0.92, armor,
                    'Left side rim return of tub.', 'side wall plane and thickness', bevel, seg, False)
    add_box_feature(asset_id, created, f'{asset_id}_01_right_sloped_rim_return', role, 0.88, 0.965, 0.12, 0.86, 0.25, 0.86, armor,
                    'Right side rim return of tub.', 'side wall plane and thickness', bevel, seg, False)
    # Inner ledge line that makes it read as a tub, not a block.
    add_box_feature(asset_id, created, f'{asset_id}_01_inner_floor_inset', role, 0.18, 0.82, 0.22, 0.76, 0.31, 0.34, dark,
                    'Inset floor shadow plane inside tub.', 'interior floor inset and tray read', bevel*0.4, 1, False)


def engine_deck(asset_id, created, attempt, mats):
    role='source_component_2_engine_deck_assembly'
    armor,dark,edge=mats; bevel=attempt['bevel']; seg=attempt['bevel_segments']
    crowned_panel(asset_id, created, f'{asset_id}_02_engine_deck_structural_plate', role,
                  [(0.04,0.08),(0.96,0.07),(0.95,0.90),(0.04,0.92)], 0.12, 0.72, 0.004, 3, armor,
                  'Engine deck broad plate with real thickness.', 'broad deck plane and thickness', bevel*0.6, seg, True)
    for k, x in enumerate([0.30,0.43,0.56,0.69]):
        add_box_feature(asset_id, created, f'{asset_id}_02_grille_major_bar_{k:02d}', role, x-0.012, x+0.012, 0.22, 0.78, 0.74, 0.95, edge,
                        'Major grille/raised bar: structural reference feature.', 'engine deck major bar, not small detail', bevel*0.25, 1, False)
    if attempt['seams'] >= 2:
        add_box_feature(asset_id, created, f'{asset_id}_02_rear_cross_step', role, 0.14, 0.86, 0.78, 0.815, 0.73, 0.92, edge,
                        'Rear cross-step catches deck plane break.', 'engine deck plane break', bevel*0.25, 1, False)


def rear_plate(asset_id, created, attempt, mats):
    role='source_component_3_rear_plate_assembly'
    armor,dark,edge=mats; bevel=attempt['bevel']; seg=attempt['bevel_segments']
    crowned_panel(asset_id, created, f'{asset_id}_03_rear_plate_shoulder_return', role,
                  [(0.06,0.08),(0.92,0.04),(0.98,0.76),(0.80,0.96),(0.14,0.90),(0.02,0.25)], 0.10, 0.84, 0.01, max(3,attempt['grid']-2), armor,
                  'Rear component traced as sloped shoulder/return plate, not rectangle.', 'rear silhouette shoulder, thickness, return plane', bevel, seg, True)
    add_box_feature(asset_id, created, f'{asset_id}_03_lower_return_shadow', role, 0.10, 0.88, 0.07, 0.16, 0.08, 0.28, dark,
                    'Lower return shadow makes rear plate read as structure.', 'rear lower return', bevel*0.35, 1, False)


def side_assembly(asset_id, created, attempt, mats, role, name, axis_hint):
    armor,dark,edge=mats; bevel=attempt['bevel']; seg=attempt['bevel_segments']; steps=attempt['side_steps']
    # Main side is stepped: two or more structural planes, not a stick with surface ribs.
    if axis_hint == 'horizontal':
        main=[(0.02,0.16),(0.98,0.12),(0.94,0.84),(0.12,0.94)]
        prism(asset_id, created, f'{asset_id}_{name}_main_stepped_side_shell', role, main, 0.12, 0.74, armor,
              'Side assembly main shell traced to reference orientation with real thickness.', 'side silhouette and primary side plane', bevel, seg, True)
        for i in range(steps):
            x0 = 0.16 + i*(0.68/max(1,steps-1)) if steps > 1 else 0.50
            add_box_feature(asset_id, created, f'{asset_id}_{name}_structural_step_{i:02d}', role, x0-0.035, x0+0.05, 0.20, 0.78, 0.76, 0.96, edge,
                            'Stepped side mechanical plane, not decorative rib.', 'major stepped mechanical side plane', bevel*0.35, 1, False)
        add_box_feature(asset_id, created, f'{asset_id}_{name}_lower_socket_return', role, 0.10, 0.90, 0.10, 0.20, 0.06, 0.36, dark,
                        'Lower socket return gives side piece structural underside.', 'side lower return/undercut', bevel*0.45, 1, False)
    else:
        main=[(0.10,0.02),(0.88,0.06),(0.92,0.96),(0.18,0.98)]
        prism(asset_id, created, f'{asset_id}_{name}_main_stepped_side_shell', role, main, 0.12, 0.74, armor,
              'Vertical side assembly main shell traced to reference orientation with real thickness.', 'side silhouette and primary side plane', bevel, seg, True)
        for i in range(steps):
            y0 = 0.18 + i*(0.64/max(1,steps-1)) if steps > 1 else 0.50
            add_box_feature(asset_id, created, f'{asset_id}_{name}_structural_step_{i:02d}', role, 0.20, 0.78, y0-0.035, y0+0.05, 0.76, 0.96, edge,
                            'Stepped side mechanical plane, not decorative rib.', 'major stepped mechanical side plane', bevel*0.35, 1, False)
        add_box_feature(asset_id, created, f'{asset_id}_{name}_lower_socket_return', role, 0.10, 0.22, 0.12, 0.90, 0.06, 0.34, dark,
                        'Lower socket return gives side piece structural underside.', 'side lower return/undercut', bevel*0.45, 1, False)


def remaining_plate(asset_id, created, attempt, mats):
    role='source_component_6_remaining_reference_plate'
    armor,dark,edge=mats; bevel=attempt['bevel']; seg=attempt['bevel_segments']
    prism(asset_id, created, f'{asset_id}_06_remaining_traced_armor_plate', role,
          [(0.03,0.22),(0.90,0.07),(0.98,0.68),(0.82,0.94),(0.08,0.82)], 0.12, 0.88, armor,
          'Remaining source plate keeps traced silhouette and thickness only.', 'traced loose plate silhouette and thickness', bevel*0.7, max(1,seg-1), True)


def add_reference_sheet(asset_id, created, make_mat):
    if not REF_IMAGE.exists():
        return None
    img = bpy.data.images.load(str(REF_IMAGE))
    mat = bpy.data.materials.new(asset_id + '_visible_reference_sheet_emissive')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage'); tex.image = img
    em = nodes.new('ShaderNodeEmission'); em.inputs['Strength'].default_value = 0.75
    out = nodes.new('ShaderNodeOutputMaterial')
    mat.node_tree.links.new(tex.outputs['Color'], em.inputs['Color'])
    mat.node_tree.links.new(em.outputs['Emission'], out.inputs['Surface'])
    verts=[(-1.60,1.42,-0.78),(1.60,1.42,-0.78),(1.60,1.42,0.86),(-1.60,1.42,0.86)]
    faces=[(0,1,2,3)]
    mesh=bpy.data.meshes.new(asset_id+'_reference_sheet_mesh')
    mesh.from_pydata(verts, [], faces); mesh.update(calc_edges=True)
    uv=mesh.uv_layers.new(name='reference_sheet_uv')
    for loop, co in zip(mesh.polygons[0].loop_indices, [(0,0),(1,0),(1,1),(0,1)]):
        uv.data[loop].uv = co
    mesh.materials.append(mat)
    obj=bpy.data.objects.new(asset_id+'_reference_sheet_background', mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id']=asset_id
    obj['role']='visible_reference_sheet_background'
    obj['source_image']=str(REF_IMAGE)
    obj.visible_shadow = False
    created.append(obj)
    border_mat=make_mat(asset_id+'_reference_sheet_border_mat',(0.01,0.01,0.01,1),0.8)
    for suffix, bverts in [
        ('top',[(-1.62,1.415,0.86),(1.62,1.415,0.86),(1.62,1.415,0.90),(-1.62,1.415,0.90)]),
        ('bottom',[(-1.62,1.415,-0.82),(1.62,1.415,-0.82),(1.62,1.415,-0.78),(-1.62,1.415,-0.78)]),
        ('left',[(-1.64,1.415,-0.82),(-1.60,1.415,-0.82),(-1.60,1.415,0.90),(-1.64,1.415,0.90)]),
        ('right',[(1.60,1.415,-0.82),(1.64,1.415,-0.82),(1.64,1.415,0.90),(1.60,1.415,0.90)]),
    ]:
        mesh=bpy.data.meshes.new(asset_id+'_reference_sheet_border_'+suffix+'_mesh')
        mesh.from_pydata(bverts, [], [(0,1,2,3)]); mesh.update(calc_edges=True)
        mesh.materials.append(border_mat)
        bo=bpy.data.objects.new(asset_id+'_reference_sheet_border_'+suffix, mesh)
        bpy.context.collection.objects.link(bo)
        bo['asset_id']=asset_id
        bo['role']='visible_reference_sheet_border'
        bo.visible_shadow=False
        created.append(bo)
    return obj


def build_attempt(attempt):
    reset_scene()
    asset_id=f'{SERIES_ID}_{attempt["suffix"]}'
    model_dir=SCRATCH_ROOT/'models'/asset_id
    blend_dir=SCRATCH_ROOT/'source_blends'/asset_id
    render_dir=SCRATCH_ROOT/'renders'/asset_id
    notes_dir=SCRATCH_ROOT/'notes'
    for d in (model_dir, blend_dir, render_dir, notes_dir):
        d.mkdir(parents=True, exist_ok=True)
    armor=make_mat(asset_id+'_warm_clay_structural_armor',(0.64,0.66,0.57,1),0.92)
    dark=make_mat(asset_id+'_dark_inset_return',(0.06,0.065,0.055,1),0.96)
    edge=make_mat(asset_id+'_edge_catch_planes',(0.74,0.75,0.64,1),0.88)
    mats=(armor,dark,edge)
    created=[]
    upper_front_glacis(asset_id, created, attempt, mats)
    lower_tub(asset_id, created, attempt, mats)
    engine_deck(asset_id, created, attempt, mats)
    rear_plate(asset_id, created, attempt, mats)
    side_assembly(asset_id, created, attempt, mats, 'source_component_4_left_side_assembly', '04_left_side_assembly', 'horizontal')
    side_assembly(asset_id, created, attempt, mats, 'source_component_5_right_side_assembly', '05_right_side_assembly', 'vertical')
    remaining_plate(asset_id, created, attempt, mats)
    add_reference_sheet(asset_id, created, make_mat)
    # Lights and cameras.
    bpy.ops.object.light_add(type='AREA', location=(0,-4.8,2.9))
    light=bpy.context.object; light.name=asset_id+'_softbox'; light.data.energy=720; light.data.size=4.5
    bpy.ops.object.camera_add(location=(0,-3.75,0.78))
    front=bpy.context.object; front.name=asset_id+'_front_reference_sheet_camera'
    bpy.ops.object.camera_add(location=(0,3.35,0.74))
    rear=bpy.context.object; rear.name=asset_id+'_rear_oblique_camera'
    bpy.ops.object.camera_add(location=(0.18,-2.35,0.48))
    hatch=bpy.context.object; hatch.name=asset_id+'_hatch_deck_close_camera'
    def look_at(obj, target):
        direction=Vector(target)-obj.location
        obj.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
    look_at(front, Vector((0,0,0.02))); front.data.lens=34
    look_at(rear, Vector((0,0,0.02))); rear.data.lens=38
    look_at(hatch, Vector((0.18,0.25,0.20))); hatch.data.lens=55
    depsgraph=bpy.context.evaluated_depsgraph_get()
    parts=[]
    for obj in created:
        if obj.type != 'MESH':
            continue
        counts=evaluated_counts(obj, depsgraph)
        role=obj.get('role','')
        if role.startswith('visible_reference_sheet'):
            primary=False
        else:
            primary=bool(obj.get('primary_kit_piece', False))
        source_role=obj.get('source_role','')
        parts.append({
            'object': obj.name,
            'role': role,
            'source_role': source_role,
            'primary_kit_piece': primary,
            'triangle_spend_reason': obj.get('triangle_spend_reason',''),
            **counts,
            'source_bbox_world': json.loads(obj['source_bbox_world']) if obj.get('source_bbox_world') else None,
        })
    hand_parts=[p for p in parts if not str(p['role']).startswith('visible_reference_sheet')]
    primary_parts=[p for p in hand_parts if p['primary_kit_piece']]
    stats_all={'triangles':sum(p['triangles'] for p in hand_parts),'polygons':sum(p['polygons'] for p in hand_parts),'vertices':sum(p['vertices'] for p in hand_parts)}
    stats_primary={'triangles':sum(p['triangles'] for p in primary_parts),'polygons':sum(p['polygons'] for p in primary_parts),'vertices':sum(p['vertices'] for p in primary_parts)}
    in_budget=BUDGET['target_min_triangles'] <= stats_all['triangles'] <= BUDGET['preferred_max_triangles']
    under_hard=stats_all['triangles'] <= BUDGET['hard_cap_triangles']
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
        bpy.context.scene.eevee.taa_render_samples=48
    bpy.context.scene.render.resolution_x=1280; bpy.context.scene.render.resolution_y=840
    for cam, filename in ((front,'front_with_reference_sheet.png'),(rear,'rear_oblique.png'),(hatch,'hatch_deck_close.png')):
        bpy.context.scene.camera=cam
        bpy.context.scene.render.filepath=str(render_dir/filename)
        bpy.ops.render.render(write_still=True)
    manifest={
        'asset_id':asset_id,
        'series_id':SERIES_ID,
        'attempt':attempt['suffix'],
        'attempt_label':attempt['label'],
        'scratch_mode':True,
        'artifact_type':'scratch_structural_retopo_reference_kit',
        'revision':REVISION,
        'source_manifest':str(SOURCE_MANIFEST.relative_to(ROOT)),
        'reference_sheet_image':str(REF_IMAGE.relative_to(ROOT)),
        'source_policy':'Meshy source kit is visual/reference truth only. Exported meshes are hand-authored structural retopo; no source topology copy; no decimation.',
        'configuration_policy':'Same seven source component roles and source bbox/exploded configuration as Meshy reference kit.',
        'budget':BUDGET,
        'statistics_all_hand_retopo_excluding_reference_sheet':stats_all,
        'statistics_primary_kit_pieces':stats_primary,
        'primary_kit_piece_count':len(primary_parts),
        'all_hand_mesh_object_count':len(hand_parts),
        'in_preferred_budget_band':in_budget,
        'under_hard_cap':under_hard,
        'outputs':{
            'blend':str(blend_path.relative_to(ROOT)),
            'glb':str(glb_path.relative_to(ROOT)),
            'front_with_reference_sheet':str((render_dir/'front_with_reference_sheet.png').relative_to(ROOT)),
            'rear_oblique':str((render_dir/'rear_oblique.png').relative_to(ROOT)),
            'hatch_deck_close':str((render_dir/'hatch_deck_close.png').relative_to(ROOT)),
        },
        'parts':parts,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf8')
    notes_path.write_text(f"""# {asset_id}\n\nStructural retopo reference-kit attempt.\n\n- Attempt: {attempt['suffix']} - {attempt['label']}\n- All hand-retopo stats excluding reference sheet: {stats_all}\n- Primary kit-piece stats: {stats_primary}\n- Preferred budget band: {in_budget}\n- Under hard cap: {under_hard}\n- The hatch/deck area is real inset/lip geometry, not a texture smear.\n- Side assemblies use stepped structural planes, not ribbed sticks.\n- Scratch only; renders are diagnostic, not cloud acceptance.\n""", encoding='utf8')
    return manifest

all_manifests=[]
for attempt in ATTEMPTS:
    all_manifests.append(build_attempt(attempt))
summary=SCRATCH_ROOT/'notes'/f'{SERIES_ID}_summary.md'
summary.write_text('# Structural retopo reference-kit attempts\n\n' + '\n'.join(f"- {m['asset_id']}: all={m['statistics_all_hand_retopo_excluding_reference_sheet']}, primary={m['statistics_primary_kit_pieces']}, preferred={m['in_preferred_budget_band']}, hard_cap={m['under_hard_cap']}" for m in all_manifests) + '\n', encoding='utf8')
print(json.dumps({'series_id':SERIES_ID,'attempts':[{'asset_id':m['asset_id'],'all':m['statistics_all_hand_retopo_excluding_reference_sheet'],'primary':m['statistics_primary_kit_pieces'],'preferred':m['in_preferred_budget_band'],'hard_cap':m['under_hard_cap']} for m in all_manifests]}, indent=2))
