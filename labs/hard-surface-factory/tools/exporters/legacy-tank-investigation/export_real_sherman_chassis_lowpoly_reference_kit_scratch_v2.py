import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SOURCE_GLB = Path('/storage/emulated/0/Download/Meshy_AI_Exploded_View_of_a_Ta_0708195813_generate.glb')
SCRATCH_ROOT = ROOT / 'archive' / 'scratch' / '20260708-real-sherman-chassis-scratch'
ASSET_ID = 'real_sherman_chassis_lowpoly_reference_kit_scratch_v2'
REVISION = 'lowpoly-reference-kit-v2-aggressive-component-budget'
MODEL_DIR = SCRATCH_ROOT / 'models' / ASSET_ID
BLEND_DIR = SCRATCH_ROOT / 'source_blends' / ASSET_ID
RENDER_DIR = SCRATCH_ROOT / 'renders' / ASSET_ID
NOTES_DIR = SCRATCH_ROOT / 'notes'
GLB_PATH = MODEL_DIR / f'{ASSET_ID}.glb'
BLEND_PATH = BLEND_DIR / f'{ASSET_ID}.blend'
MANIFEST_PATH = MODEL_DIR / 'model_manifest.json'
NOTES_PATH = NOTES_DIR / f'{ASSET_ID}.md'
for d in (MODEL_DIR, BLEND_DIR, RENDER_DIR, NOTES_DIR):
    d.mkdir(parents=True, exist_ok=True)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
if not SOURCE_GLB.exists():
    raise FileNotFoundError(SOURCE_GLB)

bpy.ops.import_scene.gltf(filepath=str(SOURCE_GLB))
imported = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
if not imported:
    raise RuntimeError('source GLB imported no mesh objects')

bpy.ops.object.select_all(action='DESELECT')
for obj in imported:
    obj.select_set(True)
bpy.context.view_layer.objects.active = imported[0]
if len(imported) == 1:
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode='OBJECT')

parts = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
parts.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
role_names = [
    'source_component_0_upper_front_glacis_assembly',
    'source_component_1_lower_hull_floor_tub',
    'source_component_2_engine_deck_assembly',
    'source_component_3_rear_plate_assembly',
    'source_component_4_left_side_assembly',
    'source_component_5_right_side_assembly',
    'source_component_6_remaining_reference_plate',
]

fallback = bpy.data.materials.new('reference_kit_fallback_neutral_only_if_missing')
fallback.diffuse_color = (0.56, 0.57, 0.48, 1)
fallback.use_nodes = True
fallback.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (0.56, 0.57, 0.48, 1)
fallback.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value = 0.86

manifest_parts = []
for idx, obj in enumerate(parts):
    role = role_names[idx] if idx < len(role_names) else f'source_component_{idx}'
    obj.name = f'reference_kit_v1_{idx:02d}_{role}'
    obj.data.name = obj.name + '_mesh'
    obj['asset_id'] = ASSET_ID
    obj['scratch_mode'] = True
    obj['revision'] = REVISION
    obj['kit_policy'] = 'real source mesh component in original exploded reference configuration; no box-bashed substitute geometry; no assembled tank pose'
    obj['reference_source_glb'] = str(SOURCE_GLB)
    if not obj.data.materials:
        obj.data.materials.append(fallback)
    uv_before = len(obj.data.uv_layers)
    if uv_before == 0:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
        bpy.ops.object.mode_set(mode='OBJECT')
    tris_before = sum(max(0, len(poly.vertices) - 2) for poly in obj.data.polygons)
    # Low-poly correction: dissolve coplanar / near-coplanar source tessellation before any collapse.
    # This is the pass that makes broad flat plates become a few faces instead of thousands.
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    try:
        planar = obj.modifiers.new('lowpoly_planar_dissolve_flat_plates', 'DECIMATE')
        planar.decimate_type = 'DISSOLVE'
        planar.angle_limit = math.radians(8.0)
        planar.use_dissolve_boundaries = False
        bpy.ops.object.modifier_apply(modifier=planar.name)
    except Exception:
        try:
            obj.modifiers.remove(planar)
        except Exception:
            pass
    tris_after_planar = sum(max(0, len(poly.vertices) - 2) for poly in obj.data.polygons)
    triangle_budget_by_role = {
        'source_component_0_upper_front_glacis_assembly': 1800,
        'source_component_1_lower_hull_floor_tub': 1800,
        'source_component_2_engine_deck_assembly': 1400,
        'source_component_3_rear_plate_assembly': 1200,
        'source_component_4_left_side_assembly': 1100,
        'source_component_5_right_side_assembly': 1100,
        'source_component_6_remaining_reference_plate': 900,
    }
    triangle_budget = triangle_budget_by_role.get(role, 1200)
    if tris_after_planar > triangle_budget:
        collapse = obj.modifiers.new('lowpoly_component_budget_collapse', 'DECIMATE')
        collapse.ratio = triangle_budget / max(tris_after_planar, 1)
        collapse.use_collapse_triangulate = True
        try:
            bpy.ops.object.modifier_apply(modifier=collapse.name)
        except Exception:
            obj.modifiers.remove(collapse)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    try:
        obj.modifiers.new('reference_kit_weighted_normals', 'WEIGHTED_NORMAL')
    except Exception:
        pass
    world = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mins = [min(v[i] for v in world) for i in range(3)]
    maxs = [max(v[i] for v in world) for i in range(3)]
    tris_after = sum(max(0, len(poly.vertices) - 2) for poly in obj.data.polygons)
    manifest_parts.append({
        'object': obj.name,
        'role': role,
        'vertex_count': len(obj.data.vertices),
        'triangles_before_lowpoly': tris_before,
        'triangle_budget': locals().get('triangle_budget', None),
        'triangles_after_planar_dissolve': locals().get('tris_after_planar', tris_before),
        'triangles_after_lowpoly': tris_after,
        'uv_layers': [uv.name for uv in obj.data.uv_layers],
        'material_slots': [slot.material.name if slot.material else None for slot in obj.material_slots],
        'bbox_world': {'min': mins, 'max': maxs, 'size': [maxs[i] - mins[i] for i in range(3)]},
    })

bpy.ops.object.light_add(type='AREA', location=(0, -4.5, 3.5))
light = bpy.context.object
light.name = 'reference_kit_softbox'
light.data.energy = 650
light.data.size = 5.0
bpy.ops.object.camera_add(location=(0.0, -3.2, 1.4))
front_cam = bpy.context.object
front_cam.name = 'reference_kit_front_camera'
bpy.ops.object.camera_add(location=(0.0, 3.2, 1.4))
rear_cam = bpy.context.object
rear_cam.name = 'reference_kit_rear_camera'

def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
for cam in (front_cam, rear_cam):
    look_at(cam, (0, 0, 0))
    cam.data.lens = 42

bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
bpy.ops.object.select_all(action='DESELECT')
for obj in parts:
    obj.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.export_scene.gltf(filepath=str(GLB_PATH), export_format='GLB', use_selection=True, export_apply=True, export_extras=True)

engine_items = [item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
if hasattr(bpy.context.scene, 'eevee'):
    bpy.context.scene.eevee.taa_render_samples = 48
bpy.context.scene.render.resolution_x = 1280
bpy.context.scene.render.resolution_y = 840
for cam, name in ((front_cam, 'front_reference_config.png'), (rear_cam, 'rear_reference_config.png')):
    bpy.context.scene.camera = cam
    bpy.context.scene.render.filepath = str(RENDER_DIR / name)
    bpy.ops.render.render(write_still=True)

manifest = {
    'asset_id': ASSET_ID,
    'artifact_type': 'scratch_lowpoly_reference_configuration_kit_planar_reduction',
    'revision': REVISION,
    'scratch_mode': True,
    'discarded_prior_artifact': 'real_sherman_chassis_kit_scratch_v1 is red: assembled-tank pose and box-bashed geometry violated kit target',
    'source_glb': str(SOURCE_GLB),
    'output_glb': str(GLB_PATH.relative_to(ROOT)),
    'source_blend': str(BLEND_PATH.relative_to(ROOT)),
    'renders': {
        'front_reference_config': str((RENDER_DIR / 'front_reference_config.png').relative_to(ROOT)),
        'rear_reference_config': str((RENDER_DIR / 'rear_reference_config.png').relative_to(ROOT)),
    },
    'policy': {
        'configuration': 'original exploded reference configuration only',
        'make_tank': False,
        'box_bashing': False,
        'source_mesh_components': True,
        'materials': 'preserve source material slots where present; fallback only when missing',
        'uvs': 'preserve source UVs where present; smart project only when missing',
        'decimation': 'planar hard-surface dissolve first, then aggressive per-component budget; if this loses the machine read, manual hard-surface retopo is required',
    },
    'parts': manifest_parts,
}
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding='utf8')
NOTES_PATH.write_text(f'''# {ASSET_ID}\n\nThis replaces the rejected real_sherman_chassis_kit_scratch_v1 premise.\n\nCorrection applied:\n\n- Kit stays in the original exploded/reference configuration.\n- Meshes are split from the real Meshy source components, not re-authored as boxes.\n- No assembled tank pose.\n- No random helper blockers.\n- Source UVs/materials are preserved where present; generated UVs only if a component lacks them.\n- Planar hard-surface dissolve is applied so flat plates are not thousands of triangles.
- This pass uses aggressive component budgets near 9k total triangles.
- If source relief collapses into mush, the next step is manual hard-surface retopo, not more decimation.\n\nOutputs:\n\n- GLB: {GLB_PATH.relative_to(ROOT)}\n- Blend: {BLEND_PATH.relative_to(ROOT)}\n- Manifest: {MANIFEST_PATH.relative_to(ROOT)}\n- Renders: {(RENDER_DIR / 'front_reference_config.png').relative_to(ROOT)}, {(RENDER_DIR / 'rear_reference_config.png').relative_to(ROOT)}\n''', encoding='utf8')
print(json.dumps({'asset_id': ASSET_ID, 'parts': len(parts), 'glb': str(GLB_PATH)}, indent=2))
