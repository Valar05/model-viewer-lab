
import json, math
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path('/storage/emulated/0/Documents/GodotProjects/tanks-for-the-memories')
SCRATCH=ROOT/'archive'/'scratch'/'20260708-real-sherman-chassis-scratch'
SRC=SCRATCH/'models'/'real_sherman_chassis_reference_kit_scratch_v1'/'model_manifest.json'
REF=SCRATCH/'renders'/'real_sherman_chassis_reference_kit_scratch_v1'/'front_reference_config.png'
SERIES='real_sherman_chassis_modeled_platekit_scratch'; ASSET=SERIES+'_d04'; REV='d04-continuous-modeled-plates-no-box-feature-assembly'
parts_src={p['role']:p for p in json.loads(SRC.read_text())['parts']}

def reset():
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()

def mat(n,c):
    m=bpy.data.materials.new(n); m.diffuse_color=c; m.use_nodes=True
    bsdf=m.node_tree.nodes.get('Principled BSDF'); bsdf.inputs['Base Color'].default_value=c; bsdf.inputs['Roughness'].default_value=.92
    return m

def bb(role): return parts_src[role]['bbox_world']
def mp(role, pts):
    b=bb(role); mn=b['min']; mx=b['max']
    return [(mn[0]+(mx[0]-mn[0])*x, mn[1]+(mx[1]-mn[1])*y, mn[2]+(mx[2]-mn[2])*z) for x,y,z in pts]
def tris(mesh): return sum(max(0,len(p.vertices)-2) for p in mesh.polygons)
def obj(created,name,role,verts,faces,material,note,primary=True,bevel=.0):
    me=bpy.data.meshes.new(name+'_mesh'); me.from_pydata(mp(role,verts),[],faces); me.update(calc_edges=True); me.materials.append(material)
    for p in me.polygons: p.use_smooth=False
    o=bpy.data.objects.new(name,me); bpy.context.collection.objects.link(o)
    o['asset_id']=ASSET; o['revision']=REV; o['scratch_mode']=True; o['role']=role; o['source_role']=role; o['primary_kit_piece']=primary; o['modeled_not_box_assembled']=True; o['note']=note; o['source_bbox_world']=json.dumps(bb(role))
    if bevel:
        mod=o.modifiers.new('micro_bevel_hard_edges','BEVEL'); mod.width=bevel; mod.segments=1; mod.profile=.45
    o.modifiers.new('weighted_normals','WEIGHTED_NORMAL'); created.append(o); return o

def patch(v,f,x0,x1,y0,y1,z,nx,ny):
    base=len(v)
    for iy in range(ny+1):
        y=y0+(y1-y0)*iy/ny
        for ix in range(nx+1):
            x=x0+(x1-x0)*ix/nx; v.append((x,y,z(x,y)))
    def id(ix,iy): return base+iy*(nx+1)+ix
    for iy in range(ny):
        for ix in range(nx): f.append((id(ix,iy),id(ix+1,iy),id(ix+1,iy+1),id(ix,iy+1)))

def wall(v,f,a,b,zt,zb):
    base=len(v); v += [(a[0],a[1],zt(*a)),(b[0],b[1],zt(*b)),(b[0],b[1],zb),(a[0],a[1],zb)]; f.append((base,base+1,base+2,base+3))

def upper(created,mats):
    role='source_component_0_upper_front_glacis_assembly'; armor,dark,line=mats; v=[]; f=[]; cx=.55; cy=.55; ro=.235; ri=.162
    def z(x,y): return .72+.035*max(0,1-((x-cx)/.55)**2-((y-cy)/.52)**2)-.06*max(0,.34-y)-.025*max(0,y-.78)
    for args in [(.06,.94,.09,cy-ro,9,3),(.07,.91,cy+ro,.91,8,4),(.06,cx-ro,cy-ro,cy+ro,4,5),(cx+ro,.94,cy-ro,cy+ro,4,5)]: patch(v,f,args[0],args[1],args[2],args[3],z,args[4],args[5])
    outline=[(.06,.09),(.90,.08),(.97,.34),(.91,.74),(.78,.92),(.15,.89),(.03,.35)]
    for a,b in zip(outline,outline[1:]+outline[:1]): wall(v,f,a,b,z,.18)
    n=48; ot=[]; it=[]; ib=[]
    for i in range(n):
        a=math.tau*i/n; co=math.cos(a); si=math.sin(a)
        ot.append(len(v)); v.append((cx+ro*co,cy+ro*si,z(cx+ro*co,cy+ro*si)+.048))
        it.append(len(v)); v.append((cx+ri*co,cy+ri*si,z(cx+ri*co,cy+ri*si)+.02))
        ib.append(len(v)); v.append((cx+ri*.86*co,cy+ri*.86*si,.30))
    for i in range(n):
        j=(i+1)%n; f.append((ot[i],ot[j],it[j],it[i])); f.append((it[i],it[j],ib[j],ib[i]))
    obj(created,ASSET+'_00_upper_hull_compound_plate_with_ring_aperture',role,v,f,armor,'Modeled compound upper hull: four plate fields, real ring aperture, inner ring wall, asymmetric outline.',True,.003)
    # shaped hatch inset, secondary plate, not a cuboid
    hv=[]; hf=[]; hx0,hx1,hy0,hy1=.33,.50,.22,.40; patch(hv,hf,hx0,hx1,hy0,hy1,lambda x,y:z(x,y)+.055,4,3)
    for a,b in zip([(hx0,hy0),(hx1,hy0),(hx1,hy1),(hx0,hy1)],[(hx1,hy0),(hx1,hy1),(hx0,hy1),(hx0,hy0)]): wall(hv,hf,a,b,lambda x,y:z(x,y)+.055,.70)
    obj(created,ASSET+'_00_driver_hatch_shaped_inset_plate',role,hv,hf,line,'Shaped hatch inset with top grid and walls.',False,.002)
    dv=[(cx,cy,.295)]+[(cx+ri*.82*math.cos(math.tau*i/n),cy+ri*.82*math.sin(math.tau*i/n),.30) for i in range(n)]; df=[(0,i+1,((i+1)%n)+1) for i in range(n)]
    obj(created,ASSET+'_00_ring_dark_opening',role,dv,df,dark,'Dark aperture under the turret ring.',False,0)

def tray(created,mats):
    role='source_component_1_lower_hull_floor_tub'; armor,dark,line=mats; v=[]; f=[]
    outer=[(.04,.08),(.96,.10),(.93,.90),(.09,.92)]; inner=[(.16,.20),(.84,.22),(.80,.78),(.20,.80)]
    v += [(x,y,.30) for x,y in outer]+[(x,y,.37) for x,y in inner]+[(x,y,.10) for x,y in outer]
    for i in range(4):
        j=(i+1)%4; f.append((i,j,4+j,4+i)); f.append((i,8+i,8+j,j))
    obj(created,ASSET+'_01_open_tray_looped_hull_tub',role,v,f,armor,'Open tray with outer loop, inner loop, and return walls as one mesh.',True,.004)
    v=[]; f=[]; patch(v,f,.18,.82,.24,.76,lambda x,y:.34,6,4); obj(created,ASSET+'_01_recessed_floor_field',role,v,f,dark,'Inset floor field.',False,0)

def deck(created,mats):
    role='source_component_2_engine_deck_assembly'; armor,dark,line=mats; v=[]; f=[]
    def z(x,y): return .70+.012*math.sin(math.pi*x)*math.sin(math.pi*y)
    patch(v,f,.05,.95,.08,.92,z,12,7)
    for a,b in zip([(.05,.08),(.95,.08),(.95,.92),(.05,.92)],[ (.95,.08),(.95,.92),(.05,.92),(.05,.08)]): wall(v,f,a,b,z,.13)
    for x0 in [.22,.34,.46,.58,.70]: patch(v,f,x0,x0+.04,.22,.78,lambda x,y:.79,1,6)
    obj(created,ASSET+'_02_engine_deck_single_mesh_grille_fields',role,v,f,armor,'Single engine deck mesh with integrated raised grille fields and shell thickness.',True,.0025)

def rear(created,mats):
    role='source_component_3_rear_plate_assembly'; armor,dark,line=mats; v=[]; f=[]
    def z(x,y): return .74+.025*(.5-y)+.018*math.sin(math.pi*x)
    patch(v,f,.08,.92,.08,.88,z,8,8)
    outline=[(.08,.08),(.90,.04),(.98,.60),(.80,.94),(.16,.88),(.02,.24)]
    for a,b in zip(outline,outline[1:]+outline[:1]): wall(v,f,a,b,z,.11)
    obj(created,ASSET+'_03_rear_plate_shoulder_modeled_shell',role,v,f,armor,'Modeled rear shoulder shell with asymmetric outline and return walls.',True,.003)

def side(created,mats,role,tag,vertical=False):
    armor,dark,line=mats; v=[]; f=[]; stations=[.04,.14,.26,.40,.56,.72,.86,.96]; sections=[]
    for s in stations:
        c=.04*math.sin(math.pi*s)
        sec=[(s,.14,.15),(s,.18,.58+c),(s,.34,.82+c),(s,.72,.82+c),(s,.88,.54+c),(s,.93,.17)] if not vertical else [(.14,s,.15),(.18,s,.58+c),(.34,s,.82+c),(.72,s,.82+c),(.88,s,.54+c),(.93,s,.17)]
        sections.append([len(v)+i for i in range(len(sec))]); v += sec
    for a,b in zip(sections,sections[1:]):
        for i in range(6): f.append((a[i],b[i],b[(i+1)%6],a[(i+1)%6]))
    f.append(tuple(reversed(sections[0]))); f.append(tuple(sections[-1]))
    for s0 in [.20,.38,.56,.74]:
        base=len(v)
        if not vertical: v += [(s0,.30,.855),(s0+.04,.31,.867),(s0+.04,.78,.867),(s0,.79,.855)]
        else: v += [(.30,s0,.855),(.31,s0+.04,.867),(.78,s0+.04,.867),(.79,s0,.855)]
        f.append((base,base+1,base+2,base+3))
    obj(created,ASSET+'_'+tag+'_swept_multiplane_side_shell',role,v,f,armor,'Swept multi-plane side shell with cross-sections and integrated step fields.',True,.003)

def loose(created,mats):
    role='source_component_6_remaining_reference_plate'; armor,dark,line=mats; v=[]; f=[]; outline=[(.05,.20),(.88,.06),(.98,.62),(.80,.94),(.10,.80)]
    def z(x,y): return .70+.012*math.sin(math.pi*x)-.018*y
    c=(sum(x for x,y in outline)/5,sum(y for x,y in outline)/5); v.append((c[0],c[1],z(*c)))
    for p in outline: v.append((p[0],p[1],z(*p)))
    for i in range(5): f.append((0,i+1,((i+1)%5)+1))
    for a,b in zip(outline,outline[1:]+outline[:1]): wall(v,f,a,b,z,.18)
    obj(created,ASSET+'_06_asymmetric_loose_reference_plate',role,v,f,armor,'Asymmetric loose plate shell with return walls.',True,.0025)

def ref(created):
    if not REF.exists(): return
    img=bpy.data.images.load(str(REF)); m=bpy.data.materials.new(ASSET+'_reference_sheet_emissive'); m.use_nodes=True; ns=m.node_tree.nodes; ns.clear(); t=ns.new('ShaderNodeTexImage'); t.image=img; e=ns.new('ShaderNodeEmission'); e.inputs['Strength'].default_value=.75; o=ns.new('ShaderNodeOutputMaterial'); m.node_tree.links.new(t.outputs['Color'],e.inputs['Color']); m.node_tree.links.new(e.outputs['Emission'],o.inputs['Surface'])
    me=bpy.data.meshes.new(ASSET+'_reference_sheet_mesh'); me.from_pydata([(-1.62,1.42,-.82),(1.62,1.42,-.82),(1.62,1.42,.90),(-1.62,1.42,.90)],[],[(0,1,2,3)]); me.update(calc_edges=True); uv=me.uv_layers.new(name='uv')
    for loop,co in zip(me.polygons[0].loop_indices,[(0,0),(1,0),(1,1),(0,1)]): uv.data[loop].uv=co
    me.materials.append(m); ob=bpy.data.objects.new(ASSET+'_reference_sheet_background',me); bpy.context.collection.objects.link(ob); ob['asset_id']=ASSET; ob['role']='visible_reference_sheet_background'; ob.visible_shadow=False; created.append(ob)

def look(o,t):
    d=Vector(t)-o.location; o.rotation_euler=d.to_track_quat('-Z','Y').to_euler()

def build():
    reset(); model=SCRATCH/'models'/ASSET; blend=SCRATCH/'source_blends'/ASSET; rend=SCRATCH/'renders'/ASSET; notes=SCRATCH/'notes'
    for d in [model,blend,rend,notes]: d.mkdir(parents=True,exist_ok=True)
    mats=(mat(ASSET+'_clay_armor',(.58,.61,.52,1)),mat(ASSET+'_dark_openings',(.035,.04,.035,1)),mat(ASSET+'_edge_lips',(.72,.73,.63,1)))
    created=[]; upper(created,mats); tray(created,mats); deck(created,mats); rear(created,mats); side(created,mats,'source_component_4_left_side_assembly','04_left',False); side(created,mats,'source_component_5_right_side_assembly','05_right',True); loose(created,mats); ref(created)
    bpy.ops.object.light_add(type='AREA', location=(0,-4.5,3.2)); l=bpy.context.object; l.data.energy=780; l.data.size=4
    cams=[]
    for name,loc,tgt,lens in [('front',(0,-3.75,.78),(0,0,.02),34),('hatch',(.18,-2.25,.54),(.15,.24,.18),55),('rear',(0,3.35,.74),(0,0,.02),38)]:
        bpy.ops.object.camera_add(location=loc); c=bpy.context.object; c.name=ASSET+'_'+name+'_camera'; look(c,tgt); c.data.lens=lens; cams.append((c,name))
    deps=bpy.context.evaluated_depsgraph_get(); manifest_parts=[]
    for o in created:
        if o.type!='MESH': continue
        eo=o.evaluated_get(deps); me=eo.to_mesh(); c={'triangles':tris(me),'polygons':len(me.polygons),'vertices':len(me.vertices)}; eo.to_mesh_clear()
        role=o.get('role',''); manifest_parts.append({'object':o.name,'role':role,'source_role':o.get('source_role',''),'primary_kit_piece':bool(o.get('primary_kit_piece',False)),'modeled_not_box_assembled':bool(o.get('modeled_not_box_assembled',False)),**c,'source_bbox_world':json.loads(o['source_bbox_world']) if o.get('source_bbox_world') else None})
    hand=[p for p in manifest_parts if not str(p['role']).startswith('visible_reference_sheet')]; primary=[p for p in hand if p['primary_kit_piece']]
    allstats={k:sum(p[k] for p in hand) for k in ['triangles','polygons','vertices']}; pristats={k:sum(p[k] for p in primary) for k in ['triangles','polygons','vertices']}
    bpy.ops.wm.save_as_mainfile(filepath=str(blend/(ASSET+'.blend'))); bpy.ops.object.select_all(action='DESELECT')
    for o in created: o.select_set(True)
    bpy.context.view_layer.objects.active=created[0]; bpy.ops.export_scene.gltf(filepath=str(model/(ASSET+'.glb')),export_format='GLB',use_selection=True,export_apply=True,export_extras=True)
    items=[i.identifier for i in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]; bpy.context.scene.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in items else 'BLENDER_EEVEE'
    if hasattr(bpy.context.scene,'eevee'): bpy.context.scene.eevee.taa_render_samples=32
    bpy.context.scene.render.resolution_x=1280; bpy.context.scene.render.resolution_y=840
    for c,name in cams: bpy.context.scene.camera=c; bpy.context.scene.render.filepath=str(rend/({'front':'front_with_reference_sheet.png','hatch':'hatch_deck_close.png','rear':'rear_oblique.png'}[name])); bpy.ops.render.render(write_still=True)
    man={'asset_id':ASSET,'series_id':SERIES,'attempt':'d04','scratch_mode':True,'artifact_type':'scratch_modeled_plate_reference_kit','revision':REV,'source_manifest':str(SRC.relative_to(ROOT)),'reference_sheet_image':str(REF.relative_to(ROOT)),'configuration_policy':'Same seven source component roles and exploded/reference configuration as Meshy reference kit.','construction_rule':'Seven primary components are custom continuous meshes; rectangular feature-box assembly is intentionally not used.','budget':{'hard_cap_triangles':9000,'intent':'model enough structure before optimizing'},'statistics_all_hand_mesh_excluding_reference_sheet':allstats,'statistics_primary_kit_pieces':pristats,'primary_kit_piece_count':len(primary),'all_hand_mesh_object_count':len(hand),'under_hard_cap':allstats['triangles']<=9000,'outputs':{'blend':str((blend/(ASSET+'.blend')).relative_to(ROOT)),'glb':str((model/(ASSET+'.glb')).relative_to(ROOT)),'front_with_reference_sheet':str((rend/'front_with_reference_sheet.png').relative_to(ROOT)),'hatch_deck_close':str((rend/'hatch_deck_close.png').relative_to(ROOT)),'rear_oblique':str((rend/'rear_oblique.png').relative_to(ROOT))},'parts':manifest_parts}
    (model/'model_manifest.json').write_text(json.dumps(man,indent=2)+'\n')
    note='# '+ASSET+'\n\nScratch d04 response to box-assembly failure.\n\n- All hand mesh excluding reference sheet: '+str(allstats)+'\n- Primary kit pieces: '+str(pristats)+'\n- Primary piece count: '+str(len(primary))+'\n- Construction rule: continuous modeled plate meshes, not rectangular feature-box assembly.\n- Key change: ring aperture/wall, paneled upper hull topology, open tray loops, swept side shells, rear shoulder mesh, integrated engine deck fields.\n- Scratch diagnostic only; not production/cloud accepted.\n'
    (notes/(ASSET+'.md')).write_text(note)
    print(json.dumps({'asset_id':ASSET,'all':allstats,'primary':pristats,'hand_objects':len(hand),'under_hard_cap':man['under_hard_cap']},indent=2))
build()
