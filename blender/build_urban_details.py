from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "bridge_output_008c" / "coimbra-highres-terrain-visual-dev.blend"
OSM_LOCAL = ROOT / "data" / "processed" / "bridge_osm_oss_local.json"
TERRAIN = ROOT / "bridge_output_008b" / "bridge_terrain_highres_2m.npz"
OUT = ROOT / "bridge_output_009d"
OUT_BLEND = OUT / "coimbra-urban-details-base.blend"
MANIFEST = OUT / "urban-details-manifest.json"

MOSAIQ_PARENT = ROOT / "_mosaiq"
if str(MOSAIQ_PARENT) not in sys.path:
    sys.path.insert(0, str(MOSAIQ_PARENT))

from mosaiq_osm_vr.src import addon_core as mos_core  # type: ignore
from mosaiq_osm_vr.src import addon_ui as mos_ui  # type: ignore

VERSION = "coimbra-urban-details-v1"
SIDEWALK_WIDTH = 1.75


class TerrainSampler:
    def __init__(self, path: Path):
        data = np.load(path)
        self.z = data["z"].astype(np.float32)
        self.xs = data["xs"].astype(np.float32)
        self.ys = data["ys"].astype(np.float32)
        self.z0 = float(data["z0"])

    def sample(self, x: float, y: float) -> float | None:
        if x < float(self.xs[0]) or x > float(self.xs[-1]):
            return None
        if y > float(self.ys[0]) or y < float(self.ys[-1]):
            return None
        fx = (x - float(self.xs[0])) / (float(self.xs[-1]) - float(self.xs[0])) * (len(self.xs) - 1)
        fy = (float(self.ys[0]) - y) / (float(self.ys[0]) - float(self.ys[-1])) * (len(self.ys) - 1)
        x0 = int(np.floor(fx)); y0 = int(np.floor(fy))
        x1 = min(x0 + 1, len(self.xs) - 1)
        y1 = min(y0 + 1, len(self.ys) - 1)
        tx = fx - x0; ty = fy - y0
        a = float(self.z[y0, x0]); b = float(self.z[y0, x1])
        c = float(self.z[y1, x0]); d = float(self.z[y1, x1])
        return ((a * (1-tx) + b*tx) * (1-ty) + (c*(1-tx) + d*tx)*ty) - self.z0


def stable_unit(token: str, channel: int = 0) -> float:
    d = hashlib.sha256(f"{token}:{channel}".encode()).digest()
    return int.from_bytes(d[:8], "big") / float((1 << 64) - 1)


def material(name, color, rough=0.65, metallic=0.0, emission=None):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metallic
        if emission is not None:
            key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = emission
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = 0.5
    return mat


def add_box(v, f, mi, cx, cy, z0, sx, sy, sz, angle, mat_index):
    ax = Vector((math.cos(angle), math.sin(angle), 0.0))
    ay = Vector((-math.sin(angle), math.cos(angle), 0.0))
    c = Vector((cx, cy, z0 + sz * 0.5))
    hx, hy, hz = ax * (sx * 0.5), ay * (sy * 0.5), Vector((0,0,sz*0.5))
    base=len(v)
    for dz in (-hz, hz):
        v.extend([
            tuple(c-hx-hy+dz), tuple(c+hx-hy+dz),
            tuple(c+hx+hy+dz), tuple(c-hx+hy+dz)
        ])
    f.extend([
        (base,base+1,base+2,base+3),(base+4,base+7,base+6,base+5),
        (base,base+4,base+5,base+1),(base+1,base+5,base+6,base+2),
        (base+2,base+6,base+7,base+3),(base+3,base+7,base+4,base)
    ])
    mi.extend([mat_index]*6)


def add_prism(v, f, mi, cx, cy, z0, radius, height, sides, mat_index):
    base=len(v)
    for z in (z0,z0+height):
        for i in range(sides):
            a=math.tau*i/sides
            v.append((cx+math.cos(a)*radius,cy+math.sin(a)*radius,z))
    for i in range(sides):
        j=(i+1)%sides
        f.append((base+i,base+j,base+sides+j,base+sides+i)); mi.append(mat_index)
    f.append(tuple(base+i for i in reversed(range(sides)))); mi.append(mat_index)
    f.append(tuple(base+sides+i for i in range(sides))); mi.append(mat_index)


def finalize(name, vertices, faces, indices, materials):
    if not faces:
        return None
    mesh=bpy.data.meshes.new(name+"_Mesh")
    mesh.from_pydata(vertices,[],faces); mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    for mat in materials: mesh.materials.append(mat)
    for poly,idx in zip(mesh.polygons,indices): poly.material_index=idx
    obj["urban_version"]=VERSION
    return obj


def line_for_way(way, nodes):
    result=[]
    for nid in way.get("nodes") or []:
        node=nodes.get(str(nid))
        if node:
            x,y=node["xy"]; result.append((float(x),float(y)))
    return result


def drape(obj, terrain):
    shifted=skipped=0
    if not obj: return shifted, skipped
    for vertex in obj.data.vertices:
        z=terrain.sample(float(vertex.co.x),float(vertex.co.y))
        if z is None:
            skipped+=1; continue
        vertex.co.z += z
        shifted+=1
    obj.data.update()
    return shifted, skipped


def join_objects(objects, name):
    objects=[o for o in objects if o and o.name in bpy.data.objects]
    if not objects: return None
    # MOSAIQ geometry creators intentionally return unlinked Blender objects.
    # Link them before selection/join so they belong to the active ViewLayer.
    for o in objects:
        if not o.users_collection:
            bpy.context.collection.objects.link(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects: o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.ops.object.join()
    objects[0].name=name; objects[0].data.name=name+"_Mesh"
    return objects[0]


def heading(tags, token):
    raw=str(tags.get("direction") or "").strip()
    try:
        return math.radians(float(raw))
    except Exception:
        return stable_unit(token,0)*math.tau


def main():
    for p in (BASE,OSM_LOCAL,TERRAIN):
        if not p.is_file(): raise SystemExit(f"Missing input: {p}")
    bpy.ops.wm.open_mainfile(filepath=str(BASE))
    data=json.loads(OSM_LOCAL.read_text())
    nodes=data["nodes"]; ways=data["ways"]
    terrain=TerrainSampler(TERRAIN)

    sidewalks=[]; parking=[]; crossings=[]
    smat=mos_core.ensure_sidewalk_slab_material()
    pmat=mos_core.ensure_parking_material()
    cmat=mos_core.ensure_crosswalk_material()

    counts={"sidewalk_strips":0,"parking_strips":0,"crosswalks":0}
    for way in ways:
        tags=way.get("tags") or {}
        if "highway" not in tags: continue
        line=line_for_way(way,nodes)
        if len(line)<2: continue
        road_width=mos_core.highway_width_m(tags)
        park=mos_ui.parse_parking_lanes(tags)
        walks=mos_ui.parse_sidewalks(tags)
        for side in walks:
            sign=1.0 if side=="left" else -1.0
            pw=float((park.get(side) or {}).get("width",0.0))
            offset=sign*(road_width*0.5+pw+0.18+SIDEWALK_WIDTH*0.5)
            obj=mos_core.create_offset_strip(
                f"urban_sidewalk_{way['id']}_{side}",line,SIDEWALK_WIDTH,offset,0.045,smat
            )
            if obj: sidewalks.append(obj); counts["sidewalk_strips"]+=1
        for side,spec in park.items():
            sign=1.0 if side=="left" else -1.0
            width=float(spec.get("width",2.4))
            offset=sign*(road_width*0.5+width*0.5+0.06)
            obj=mos_core.create_offset_strip(
                f"urban_parking_{way['id']}_{side}",line,width,offset,0.035,pmat
            )
            if obj: parking.append(obj); counts["parking_strips"]+=1

    # Exact tagged crossing nodes. Find nearest road segment containing each node.
    ways_by_node={}
    for way in ways:
        if "highway" not in (way.get("tags") or {}): continue
        for nid in way.get("nodes") or []: ways_by_node.setdefault(int(nid),[]).append(way)
    for nid_s,node in nodes.items():
        tags=node.get("tags") or {}
        if (tags.get("highway") or "").lower()!="crossing" and not tags.get("crossing"):
            continue
        nid=int(nid_s); candidates=ways_by_node.get(nid,[])
        if not candidates: continue
        way=candidates[0]; ids=way.get("nodes") or []; idx=ids.index(nid)
        neighbor=None
        if idx+1<len(ids): neighbor=nodes.get(str(ids[idx+1]))
        elif idx>0: neighbor=nodes.get(str(ids[idx-1]))
        if not neighbor: continue
        x,y=map(float,node["xy"]); nx,ny=map(float,neighbor["xy"])
        tangent=(nx-x,ny-y)
        obj=mos_core.create_crosswalk_mesh(
            f"urban_crossing_{nid}",(x,y),tangent,
            mos_core.highway_width_m(way.get("tags") or {}),
            stripe_length=2.5,stripe_width=0.34,stripe_gap=0.30,z=0.06,mat=cmat
        )
        if obj: crossings.append(obj); counts["crosswalks"]+=1

    drape_stats={}
    for group_name,objects in (("sidewalks",sidewalks),("parking",parking),("crossings",crossings)):
        shifted=skipped=0
        for obj in objects:
            a,b=drape(obj,terrain); shifted+=a; skipped+=b
        drape_stats[group_name]={"shifted":shifted,"skipped":skipped}
    joined=[
        join_objects(sidewalks,"Urban_Sidewalks"),
        join_objects(parking,"Urban_Parking"),
        join_objects(crossings,"Urban_Crosswalks"),
    ]

    mats=[
        material("Urban_Metal",(0.12,0.13,0.14,1),0.4,0.45),
        material("Urban_LampHead",(0.78,0.70,0.48,1),0.28,0.05,(0.78,0.62,0.28,1)),
        material("Urban_Wood",(0.28,0.12,0.045,1),0.72),
        material("Urban_Bin",(0.10,0.16,0.12,1),0.65),
        material("Urban_SignalDark",(0.025,0.03,0.03,1),0.4),
        material("Urban_Red",(0.45,0.015,0.008,1),0.35,0.0,(0.5,0.01,0.005,1)),
        material("Urban_Amber",(0.5,0.18,0.005,1),0.35,0.0,(0.55,0.16,0.005,1)),
        material("Urban_Green",(0.005,0.30,0.05,1),0.35,0.0,(0.005,0.38,0.04,1)),
        material("Urban_Sign",(0.65,0.06,0.035,1),0.45),
    ]
    v=[];f=[];mi=[]
    fixture_counts={"street_lamps":0,"benches":0,"waste":0,"bicycle_parking":0,"traffic_signals":0,"road_signs":0}
    skipped_points=0
    for nid,node in nodes.items():
        tags=node.get("tags") or {}; x,y=map(float,node["xy"])
        z=terrain.sample(x,y)
        if z is None: skipped_points+=1; continue
        ang=heading(tags,f"node:{nid}")
        hw=(tags.get("highway") or "").lower(); am=(tags.get("amenity") or "").lower()
        if hw=="street_lamp":
            add_prism(v,f,mi,x,y,z+0.02,0.065,5.4,6,0)
            add_box(v,f,mi,x+math.cos(ang)*0.18,y+math.sin(ang)*0.18,z+5.33,0.55,0.18,0.18,ang,1)
            fixture_counts["street_lamps"]+=1
        elif am=="bench":
            add_box(v,f,mi,x,y,z+0.42,1.7,0.46,0.16,ang,2)
            add_box(v,f,mi,x-math.sin(ang)*0.19,y+math.cos(ang)*0.19,z+0.58,1.7,0.10,0.58,ang,2)
            for s in (-0.55,0.55):
                px=x+math.cos(ang)*s; py=y+math.sin(ang)*s
                add_box(v,f,mi,px,py,z+0.03,0.09,0.36,0.42,ang,0)
            fixture_counts["benches"]+=1
        elif am in {"waste_basket","waste_disposal","recycling"}:
            large=am!="waste_basket"
            add_box(v,f,mi,x,y,z+0.03,1.15 if large else 0.48,0.72 if large else 0.48,1.05 if large else 0.85,ang,3)
            fixture_counts["waste"]+=1
        elif am=="bicycle_parking":
            for off in (-0.65,0.0,0.65):
                px=x+math.cos(ang)*off; py=y+math.sin(ang)*off
                add_prism(v,f,mi,px,py,z+0.02,0.035,0.82,6,0)
            fixture_counts["bicycle_parking"]+=1
        elif hw=="traffic_signals":
            add_prism(v,f,mi,x,y,z+0.02,0.065,3.5,6,0)
            add_box(v,f,mi,x,y,z+2.55,0.32,0.28,0.92,ang,4)
            # three readable coloured pips represented as small protruding boxes.
            for zz,idx in ((3.25,5),(2.96,6),(2.67,7)):
                add_box(v,f,mi,x+math.cos(ang)*0.16,y+math.sin(ang)*0.16,zz,0.13,0.08,0.13,ang,idx)
            fixture_counts["traffic_signals"]+=1
        elif hw in {"stop","give_way"}:
            add_prism(v,f,mi,x,y,z+0.02,0.045,2.3,6,0)
            add_box(v,f,mi,x,y,z+1.85,0.62,0.08,0.55,ang,8)
            fixture_counts["road_signs"]+=1

    fixtures=finalize("Urban_Fixtures",v,f,mi,mats)
    if fixtures: joined.append(fixtures)

    for obj in joined:
        if obj:
            obj["source"]="OpenStreetMap + MOSAIQ semantics"
            obj["mosaiq_commit"]="f73d030aecd3289007472a887d78aae2e74b6ea0"
            obj["mosaiq_license"]="Apache-2.0"

    scene=bpy.context.scene
    scene["city_urban_version"]=VERSION
    scene["city_urban_source"]="OpenStreetMap + MOSAIQ semantics"
    scene["city_urban_mosaiq_commit"]="f73d030aecd3289007472a887d78aae2e74b6ea0"
    scene["city_urban_sidewalk_count"]=counts["sidewalk_strips"]
    scene["city_urban_crosswalk_count"]=counts["crosswalks"]
    scene["city_urban_fixture_count"]=sum(fixture_counts.values())

    OUT.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    result={
        "version":VERSION,
        "base":BASE.relative_to(ROOT).as_posix(),
        "output":OUT_BLEND.relative_to(ROOT).as_posix(),
        "mosaiq":{"commit":"f73d030aecd3289007472a887d78aae2e74b6ea0","license":"Apache-2.0"},
        "linear_details":counts,
        "fixtures":fixture_counts,
        "fixture_geometry":{"vertices":len(v),"faces":len(f)},
        "drape":drape_stats,
        "point_skipped":skipped_points,
    }
    MANIFEST.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
