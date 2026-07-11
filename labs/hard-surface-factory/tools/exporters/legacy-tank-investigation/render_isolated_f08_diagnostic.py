
import bpy
from mathutils import Vector
from pathlib import Path
ROOT=Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
ASSET='real_sherman_upper_glacis_clean_source_islands_scratch_f08'
GLB=ROOT/'archive/scratch/20260708-real-sherman-chassis-scratch/models'/ASSET/(ASSET+'.glb')
OUT=ROOT/'archive/scratch/20260708-real-sherman-chassis-scratch/renders'/ASSET/'isolated_glb_view.png'
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
bpy.ops.import_scene.gltf(filepath=str(GLB))
objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
pts=[]
for o in objs:
    pts += [o.matrix_world@v.co for v in o.data.vertices]
center=Vector((0,0,0))
for p in pts: center+=p
center/=len(pts)
minx=min(p.x for p in pts); maxx=max(p.x for p in pts); miny=min(p.y for p in pts); maxy=max(p.y for p in pts); minz=min(p.z for p in pts); maxz=max(p.z for p in pts)
bpy.ops.object.light_add(type='AREA', location=(center.x, center.y-2.0, center.z+1.8)); l=bpy.context.object; l.data.energy=600; l.data.size=4
bpy.ops.object.camera_add(location=(center.x+0.08, center.y-1.8, center.z+0.18)); cam=bpy.context.object
direction=center-cam.location; cam.rotation_euler=direction.to_track_quat('-Z','Y').to_euler(); cam.data.type='ORTHO'; cam.data.ortho_scale=max(maxx-minx, maxy-miny, maxz-minz)*1.25
bpy.context.scene.camera=cam
engine_items=[item.identifier for item in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
bpy.context.scene.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_items else 'BLENDER_EEVEE'
if hasattr(bpy.context.scene,'eevee'): bpy.context.scene.eevee.taa_render_samples=48
bpy.context.scene.render.resolution_x=1280; bpy.context.scene.render.resolution_y=840; bpy.context.scene.render.filepath=str(OUT)
bpy.ops.render.render(write_still=True)
print(OUT)
