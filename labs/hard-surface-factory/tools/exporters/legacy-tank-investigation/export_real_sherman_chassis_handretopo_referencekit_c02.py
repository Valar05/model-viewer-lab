import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH_ROOT = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
SOURCE_MANIFEST = SCRATCH_ROOT / 'models' / 'real_sherman_chassis_reference_kit_scratch_v1' / 'model_manifest.json'
REF_IMAGE = SCRATCH_ROOT / 'renders' / 'real_sherman_chassis_reference_kit_scratch_v1' / 'front_reference_config.png'
ASSET_ID = 'real_sherman_chassis_handretopo_referencekit_scratch_c02'
REVISION = 'hand-retopo-source-reference-parts-same-config-readable-reference-sheet-c02'
MODEL_DIR = SCRATCH_ROOT / 'models' / ASSET_ID
BLEND_DIR = SCRATCH_ROOT / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH_ROOT / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH_ROOT / 'notes'
for d in (MODEL_DIR, BLEND_DIR, RENDER_DIR, NOTES_DIR):
    d.mkdir(parents=True, exist_ok=True)
GLB_PATH = MODEL_DIR / f'{ASSET_ID}.glb'
BLEND_PATH = BLEND_DIR / f'{ASSET_ID}.blend'
MANIFEST_PATH = MODEL_DIR / 'model_manifest.json'
NOTES_PATH = NOTES_DIR / f'{ASSET_ID}.md'

source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding='utf8'))
source_parts = {p['role']: p for p in source_manifest['parts']}

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Clay material: geometry only. Reference sheet is image textured.
def make_mat(name, color, rough=0.9):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = rough
    return mat

armor = make_mat('handretopo_warm_cast_armor_clay', (0.62, 0.65, 0.56, 1), 0.92)
dark = make_mat('handretopo_shadowed_cut_faces', (0.10, 0.11, 0.095, 1), 0.96)
edge = make_mat('handretopo_edge_weld_light_catch', (0.72, 0.73, 0.62, 1), 0.88)

created = []
kit_objects = []

def bbox(role):
    return source_parts[role]['bbox_world']

def map_box(role, pts):
    b = bbox(role); mn=b['min']; mx=b['max']
    return [(mn[0]+(mx[0]-mn[0])*x, mn[1]+(mx[1]-mn[1])*y, mn[2]+(mx[2]-mn[2])*z) for x,y,z in pts]

def tri_count(mesh):
    return sum(max(0, len(p.vertices)-2) for p in mesh.polygons)

def world_bbox(pts):
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]; zs=[p[2] for p in pts]
    return {'min':[min(xs),min(ys),min(zs)], 'max':[max(xs),max(ys),max(zs)], 'size':[max(xs)-min(xs),max(ys)-min(ys),max(zs)-min(zs)]}

def mesh_obj(name, role, verts, faces, mat, note, bevel=0.004, segments=1, include=True):
    mesh=bpy.data.meshes.new(name+'_mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = False
    obj=bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj['asset_id']=ASSET_ID
    obj['role']=role
    obj['source_role']=role
    obj['scratch_mode']=True
    obj['revision']=REVISION
    obj['source_policy']='Hand-authored retopo mesh using Meshy source part bbox/reference sheet as guide; no source topology copy, no decimation.'
    obj['note']=note
    obj['source_bbox_world']=json.dumps(bbox(role)) if role in source_parts else ''
    obj['handmade_retopo']=True
    if bevel:
        be=obj.modifiers.new('small_hard_surface_bevel_edges_that_matter','BEVEL')
        be.width=bevel
        be.segments=segments
        be.profile=0.55
        be.affect='EDGES'
    obj.modifiers.new('weighted_normals_for_cast_plate_read','WEIGHTED_NORMAL')
    created.append(obj)
    if include:
        kit_objects.append(obj)
    return obj

def prism_from_role(name, role, outer2d, z0=0.08, z1=0.92, mat=armor, note='', bevel=0.004, segments=1):
    bottom=[(x,y,z0) for x,y in outer2d]
    top=[(x,y,z1) for x,y in outer2d]
    local=bottom+top
    n=len(outer2d)
    faces=[tuple(range(n-1,-1,-1)), tuple(range(n,2*n))]
    for i in range(n):
        faces.append((i,(i+1)%n,n+(i+1)%n,n+i))
    return mesh_obj(name, role, map_box(role, local), faces, mat, note, bevel, segments)

def deck_with_hole(name, role, mat=armor):
    seg=24
    verts=[]; faces=[]
    # top/bottom outer rectangle with faceted circular turret opening.
    outer=[(0.08,0.09),(0.92,0.09),(0.96,0.68),(0.74,0.92),(0.12,0.88),(0.04,0.36)]
    center=(0.48,0.47); r=0.165
    ztop=0.86; zbot=0.18
    top_outer=[(x,y,ztop) for x,y in outer]
    bot_outer=[(x,y,zbot) for x,y in outer]
    ring_top=[]; ring_bot=[]
    for i in range(seg):
        a=math.tau*i/seg
        ring_top.append((center[0]+math.cos(a)*r, center[1]+math.sin(a)*r, ztop))
        ring_bot.append((center[0]+math.cos(a)*r, center[1]+math.sin(a)*r, zbot))
    verts=top_outer+ring_top+bot_outer+ring_bot
    n=len(outer); top_ring=n; bot_outer_start=n+seg; bot_ring=bot_outer_start+n
    # Top face: six broad sectors to ring. Purposefully low-poly fan around actual hole.
    for i in range(seg):
        j=(i+1)%seg
        side=int((i/seg)*n)%n
        faces.append((side,(side+1)%n,top_ring+j,top_ring+i))
    # bottom sectors
    for i in range(seg):
        j=(i+1)%seg
        side=int((i/seg)*n)%n
        faces.append((bot_outer_start+(side+1)%n,bot_outer_start+side,bot_ring+i,bot_ring+j))
    # outer wall and inner wall
    for i in range(n):
        faces.append((i,bot_outer_start+i,bot_outer_start+(i+1)%n,(i+1)%n))
    for i in range(seg):
        j=(i+1)%seg
        faces.append((top_ring+i,top_ring+j,bot_ring+j,bot_ring+i))
    obj=mesh_obj(name, role, map_box(role, verts), faces, mat, 'hand-retopo upper hull/glacis assembly matching source component 0: faceted turret aperture, broad deck, sloped irregular outline', 0.006, 2)
    return obj

def tub_open(name, role):
    # Open tray / tub: bottom panel plus upturned walls and sloped lips.
    verts=[]; faces=[]
    bottom=[(0.04,0.10,0.18),(0.96,0.10,0.18),(0.92,0.88,0.18),(0.08,0.88,0.18)]
    rim=[(0.00,0.02,0.88),(1.00,0.04,0.80),(0.96,0.96,0.86),(0.05,0.94,0.92)]
    inner=[(0.12,0.18,0.38),(0.86,0.18,0.34),(0.82,0.78,0.36),(0.16,0.80,0.38)]
    verts=bottom+rim+inner
    faces += [(0,1,2,3)]
    # side walls between rim and bottom/inner shelves
    for i in range(4):
        faces.append((4+i,4+(i+1)%4,8+(i+1)%4,8+i))
        faces.append((i,(i+1)%4,4+(i+1)%4,4+i))
    # floor ledge from bottom to inner
    for i in range(4):
        faces.append((i,8+i,8+(i+1)%4,(i+1)%4))
    return mesh_obj(name, role, map_box(role, verts), faces, armor, 'hand-retopo lower hull floor tub: open tray with sloped rim and interior floor, same source location', 0.005, 2)

def engine_deck(name, role):
    base=[(0.04,0.05),(0.96,0.05),(0.96,0.90),(0.04,0.92)]
    obj=prism_from_role(name, role, base, 0.20, 0.78, armor, 'hand-retopo engine deck assembly: thin plate with authored grille bars added as owned subfeatures', 0.004, 1)
    # add grille bars within same bbox as separate light-catch strips but still owned to source role
    for k,x in enumerate([0.34,0.50,0.66]):
        w=0.025
        verts=map_box(role, [(x-w,0.20,0.80),(x+w,0.20,0.80),(x+w,0.72,0.80),(x-w,0.72,0.80),(x-w,0.20,0.94),(x+w,0.20,0.94),(x+w,0.72,0.94),(x-w,0.72,0.94)])
        faces=[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        mesh_obj(name+f'_grille_bar_{k:02d}', role, verts, faces, edge, 'owned handmade engine-deck grille bar matched to reference sheet, not random density', 0.002, 1, include=False)
    return obj

def rear_plate(name, role):
    poly=[(0.08,0.08),(0.92,0.04),(0.96,0.78),(0.82,0.96),(0.15,0.90),(0.02,0.25)]
    return prism_from_role(name, role, poly, 0.08, 0.92, armor, 'hand-retopo rear plate assembly with sloped upper shoulder and lower return, same source component', 0.005, 2)

def side_component(name, role, long_axis='x'):
    # Low-poly sidewall with vertical ribs/divisions like reference side pieces.
    poly=[(0.02,0.10),(0.98,0.08),(0.95,0.88),(0.08,0.94)]
    obj=prism_from_role(name, role, poly, 0.08, 0.88, armor, f'hand-retopo {role}: long side armor panel with authored thickness and reference-like divisions', 0.005, 2)
    for k,t in enumerate([0.18,0.36,0.54,0.72]):
        if long_axis=='x':
            strip=[(t-0.010,0.18,0.90),(t+0.010,0.18,0.90),(t+0.010,0.82,0.90),(t-0.010,0.82,0.90),(t-0.010,0.18,1.00),(t+0.010,0.18,1.00),(t+0.010,0.82,1.00),(t-0.010,0.82,1.00)]
        else:
            strip=[(0.18,t-0.010,0.90),(0.82,t-0.010,0.90),(0.82,t+0.010,0.90),(0.18,t+0.010,0.90),(0.18,t-0.010,1.00),(0.82,t-0.010,1.00),(0.82,t+0.010,1.00),(0.18,t+0.010,1.00)]
        verts=map_box(role, strip)
        faces=[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        mesh_obj(name+f'_owned_rib_{k:02d}', role, verts, faces, edge, 'owned side-panel rib from hand retopo, used to match reference part silhouette', 0.0015, 1, include=False)
    return obj

def remaining_plate(name, role):
    poly=[(0.03,0.20),(0.92,0.08),(0.98,0.72),(0.82,0.94),(0.08,0.80)]
    return prism_from_role(name, role, poly, 0.12, 0.90, armor, 'hand-retopo remaining reference plate: long loose armor plate in exact source slot', 0.004, 1)

# Seven exported kit pieces. Additional owned ribs/grille bars are marked include=False in manifest, but exported so the hand retopo matches the reference read.
deck_with_hole('handretopo_c01_00_upper_front_glacis_assembly', 'source_component_0_upper_front_glacis_assembly')
tub_open('handretopo_c01_01_lower_hull_floor_tub', 'source_component_1_lower_hull_floor_tub')
engine_deck('handretopo_c01_02_engine_deck_assembly', 'source_component_2_engine_deck_assembly')
rear_plate('handretopo_c01_03_rear_plate_assembly', 'source_component_3_rear_plate_assembly')
side_component('handretopo_c01_04_left_side_assembly', 'source_component_4_left_side_assembly', 'x')
side_component('handretopo_c01_05_right_side_assembly', 'source_component_5_right_side_assembly', 'y')
remaining_plate('handretopo_c01_06_remaining_reference_plate', 'source_component_6_remaining_reference_plate')

# Reference sheet backdrop: visible in renders and model viewer, behind the hand-retopo kit.
if REF_IMAGE.exists():
    img = bpy.data.images.load(str(REF_IMAGE))
    mat = bpy.data.materials.new('visible_reference_sheet_front_background')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = img
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 0.85
    out = nodes.new('ShaderNodeOutputMaterial')
    mat.node_tree.links.new(tex.outputs['Color'], emission.inputs['Color'])
    mat.node_tree.links.new(emission.outputs['Emission'], out.inputs['Surface'])
    verts=[(-1.48,1.18,-0.70),(1.48,1.18,-0.70),(1.48,1.18,0.78),(-1.48,1.18,0.78)]
    faces=[(0,1,2,3)]
    mesh=bpy.data.meshes.new('reference_sheet_background_mesh')
    mesh.from_pydata(verts, [], faces); mesh.update(calc_edges=True)
    mesh.materials.append(mat)
    bg=bpy.data.objects.new('reference_sheet_background__source_front_render', mesh)
    bpy.context.collection.objects.link(bg)
    bg['asset_id']=ASSET_ID
    bg['role']='visible_reference_sheet_background'
    bg['source_image']=str(REF_IMAGE)
    created.append(bg)
    border_mat = make_mat('reference_sheet_dark_border', (0.015, 0.015, 0.012, 1), 0.8)
    # Four thin border strips make it obvious that this is an image reference board, not a white void.
    border_specs = [
        ('top', [(-1.50,1.175,0.78),(1.50,1.175,0.78),(1.50,1.175,0.81),(-1.50,1.175,0.81)]),
        ('bottom', [(-1.50,1.175,-0.73),(1.50,1.175,-0.73),(1.50,1.175,-0.70),(-1.50,1.175,-0.70)]),
        ('left', [(-1.51,1.175,-0.73),(-1.48,1.175,-0.73),(-1.48,1.175,0.81),(-1.51,1.175,0.81)]),
        ('right', [(1.48,1.175,-0.73),(1.51,1.175,-0.73),(1.51,1.175,0.81),(1.48,1.175,0.81)]),
    ]
    for suffix, bverts in border_specs:
        bm=bpy.data.meshes.new('reference_sheet_border_'+suffix+'_mesh')
        bm.from_pydata(bverts, [], [(0,1,2,3)]); bm.update(calc_edges=True)
        bm.materials.append(border_mat)
        bo=bpy.data.objects.new('reference_sheet_border_'+suffix, bm)
        bpy.context.collection.objects.link(bo)
        bo['asset_id']=ASSET_ID
        bo['role']='visible_reference_sheet_border'
        created.append(bo)

# Lighting/camera.
bpy.ops.object.light_add(type='AREA', location=(0,-4.3,2.8))
light=bpy.context.object; light.name='handretopo_c01_softbox'; light.data.energy=700; light.data.size=4.2
bpy.ops.object.camera_add(location=(0,-3.65,0.78))
front=bpy.context.object; front.name='handretopo_c01_front_review_camera_with_reference_sheet'
bpy.ops.object.camera_add(location=(0,3.10,0.70))
rear=bpy.context.object; rear.name='handretopo_c01_rear_review_camera'
def look_at(obj, target):
    direction=Vector(target)-obj.location
    obj.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
for cam in (front, rear):
    look_at(cam, Vector((0,0,0.02)))
    cam.data.lens=34

# Stats after modifiers.
depsgraph=bpy.context.evaluated_depsgraph_get()
parts=[]
for obj in created:
    if obj.type != 'MESH':
        continue
    eval_obj=obj.evaluated_get(depsgraph)
    mesh=eval_obj.to_mesh()
    try:
        parts.append({
            'object': obj.name,
            'role': obj.get('role',''),
            'source_role': obj.get('source_role',''),
            'included_as_primary_kit_piece': obj in kit_objects,
            'triangles': tri_count(mesh),
            'polygons': len(mesh.polygons),
            'vertices': len(mesh.vertices),
            'source_bbox_world': json.loads(obj['source_bbox_world']) if obj.get('source_bbox_world') else None,
        })
    finally:
        eval_obj.to_mesh_clear()

kit_only=[p for p in parts if p['included_as_primary_kit_piece']]
all_mesh=[p for p in parts if p['role'] != 'visible_reference_sheet_background']

bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
bpy.ops.object.select_all(action='DESELECT')
for obj in created:
    obj.select_set(True)
bpy.context.view_layer.objects.active=created[0]
bpy.ops.export_scene.gltf(filepath=str(GLB_PATH), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)

engine_items=[item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
bpy.context.scene.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
if hasattr(bpy.context.scene,'eevee'):
    bpy.context.scene.eevee.taa_render_samples=48
bpy.context.scene.render.resolution_x=1280
bpy.context.scene.render.resolution_y=840
for cam, name in ((front,'front_with_reference_sheet.png'),(rear,'rear_reference_config.png')):
    bpy.context.scene.camera=cam
    bpy.context.scene.render.filepath=str(RENDER_DIR/name)
    bpy.ops.render.render(write_still=True)

manifest={
    'asset_id': ASSET_ID,
    'scratch_mode': True,
    'artifact_type': 'scratch_hand_retopo_reference_kit_same_configuration',
    'revision': REVISION,
    'source_manifest': str(SOURCE_MANIFEST.relative_to(ROOT)),
    'reference_sheet_image': str(REF_IMAGE.relative_to(ROOT)),
    'source_policy': 'Source Meshy GLB/components used only as reference sheet and bboxes. Exported kit pieces are hand-authored meshes, not source topology and not decimated source mesh.',
    'configuration_policy': 'Same seven source component roles and same source bbox/configuration as Meshy exploded reference kit.',
    'primary_kit_piece_count': len(kit_only),
    'total_exported_mesh_objects_excluding_reference_sheet': len(all_mesh),
    'statistics_primary_kit_pieces': {
        'triangles': sum(p['triangles'] for p in kit_only),
        'polygons': sum(p['polygons'] for p in kit_only),
        'vertices': sum(p['vertices'] for p in kit_only),
    },
    'statistics_all_hand_retopo_meshes_excluding_reference_sheet': {
        'triangles': sum(p['triangles'] for p in all_mesh),
        'polygons': sum(p['polygons'] for p in all_mesh),
        'vertices': sum(p['vertices'] for p in all_mesh),
    },
    'outputs': {
        'blend': str(BLEND_PATH.relative_to(ROOT)),
        'glb': str(GLB_PATH.relative_to(ROOT)),
        'front_with_reference_sheet': str((RENDER_DIR/'front_with_reference_sheet.png').relative_to(ROOT)),
        'rear_reference_config': str((RENDER_DIR/'rear_reference_config.png').relative_to(ROOT)),
    },
    'parts': parts,
}
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf8')
NOTES_PATH.write_text(f'''# {ASSET_ID}\n\nCorrection from user: make the exact Meshy reference parts by hand, in the same configuration, with the reference sheet in the review frame.\n\nWhat this pass does:\n\n- Seven primary hand-authored retopo kit pieces match the seven source component roles.\n- Each primary piece is placed in the source component bbox/configuration from `real_sherman_chassis_reference_kit_scratch_v1`.\n- Source Meshy topology is not exported, copied, or decimated.\n- Owned grille/rib subfeatures are handmade and kept with source roles to improve visual parity.\n- A visible background reference sheet uses the source front render, so review can compare hand-retopo parts against the given kit.\n\nStats:\n\n- Primary kit pieces: {manifest['statistics_primary_kit_pieces']}\n- All hand-retopo meshes excluding reference sheet: {manifest['statistics_all_hand_retopo_meshes_excluding_reference_sheet']}\n\nScratch only. Not cloud accepted.\n''', encoding='utf8')
print(json.dumps({'asset_id': ASSET_ID, 'primary_kit_piece_count': len(kit_only), 'stats_primary': manifest['statistics_primary_kit_pieces'], 'stats_all_hand': manifest['statistics_all_hand_retopo_meshes_excluding_reference_sheet'], 'glb': str(GLB_PATH)}, indent=2))
