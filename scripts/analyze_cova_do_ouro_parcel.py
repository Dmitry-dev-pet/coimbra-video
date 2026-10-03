from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio
import requests
from PIL import Image
from pyproj import Transformer
from rasterio.transform import rowcol
from shapely import affinity
from shapely.geometry import Point, Polygon, box, mapping, shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "cova_do_ouro_site.json"
SITE = ROOT / "site_output_cova_do_ouro"
MDT = SITE / "cova_do_ouro_mdt_50cm.tif"
OUT = ROOT / "site_output_cova_do_ouro_parcel"
CADASTRO_URL = "https://ogcapi.dgterritorio.gov.pt/collections/cadastro/items"
WMS = "https://cartografia.dgterritorio.gov.pt/wms/ortos2025"
WMS_LAYER = "Ortos2025-RGB"
TARGET_AREA = 1061.0


def fetch_cadastro(bbox_wgs84):
    r = requests.get(
        CADASTRO_URL,
        params={
            "bbox": ",".join(str(x) for x in bbox_wgs84),
            "limit": 1000,
            "f": "json",
        },
        timeout=90,
    )
    r.raise_for_status()
    return r.json()


def fetch_ortho(bounds_3763, resolution=0.25):
    minx, miny, maxx, maxy = bounds_3763
    width = int(round((maxx - minx) / resolution))
    height = int(round((maxy - miny) / resolution))
    r = requests.get(
        WMS,
        params={
            "service": "WMS",
            "request": "GetMap",
            "version": "1.3.0",
            "layers": WMS_LAYER,
            "styles": "",
            "crs": "EPSG:3763",
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "width": width,
            "height": height,
            "format": "image/jpeg",
            "transparent": "false",
        },
        timeout=120,
    )
    r.raise_for_status()
    ctype = r.headers.get("content-type", "").lower()
    if "image" not in ctype:
        raise RuntimeError(f"Orthophoto WMS did not return image: {ctype}")
    from io import BytesIO
    return Image.open(BytesIO(r.content)).convert("RGB")


def get_area(props, geom):
    for key in ("areavalue", "areaValue", "area"):
        try:
            if props.get(key) is not None:
                return float(props[key])
        except Exception:
            pass
    return float(geom.area)


def choose_candidates(features, point_wgs, to_3763):
    pxy = shp_transform(to_3763.transform, point_wgs)
    rows = []
    for f in features:
        if not f.get("geometry"):
            continue
        g_wgs = shape(f["geometry"])
        g_xy = shp_transform(to_3763.transform, g_wgs)
        props = f.get("properties", {})
        area = get_area(props, g_xy)
        dist = float(g_xy.distance(pxy))
        contains = bool(g_xy.contains(pxy) or g_xy.touches(pxy))
        score = dist * 4.0 + abs(area - TARGET_AREA) / 8.0
        if contains:
            score -= 1000.0
        rows.append({
            "feature": f,
            "geom_wgs": g_wgs,
            "geom_xy": g_xy,
            "area_m2": area,
            "distance_to_listing_point_m": dist,
            "contains_listing_point": contains,
            "score": score,
            "label": props.get("label") or f.get("id"),
            "id": f.get("id"),
            "properties": props,
        })
    rows.sort(key=lambda x: x["score"])
    return rows


def bilinear(src, x, y):
    inv = ~src.transform
    colc, rowc = inv * (x, y)
    col = colc - 0.5
    row = rowc - 0.5
    c0, r0 = int(math.floor(col)), int(math.floor(row))
    dc, dr = col - c0, row - r0
    if r0 < 0 or c0 < 0 or r0 + 1 >= src.height or c0 + 1 >= src.width:
        return float("nan")
    win = src.read(1, window=((r0, r0+2), (c0, c0+2))).astype(float)
    nd = src.nodata
    if nd is not None:
        win[win == nd] = np.nan
    if not np.isfinite(win).all():
        return float("nan")
    q00, q10 = win[0,0], win[0,1]
    q01, q11 = win[1,0], win[1,1]
    return float(q00*(1-dc)*(1-dr)+q10*dc*(1-dr)+q01*(1-dc)*dr+q11*dc*dr)


def rectangle(center_x, center_y, angle_deg, width=7.0, height=6.0):
    r = box(-width/2, -height/2, width/2, height/2)
    r = affinity.rotate(r, angle_deg, origin=(0,0), use_radians=False)
    return affinity.translate(r, center_x, center_y)


def sample_rect(src, rect):
    minx, miny, maxx, maxy = rect.bounds
    xs = np.linspace(minx, maxx, 9)
    ys = np.linspace(miny, maxy, 9)
    pts = []
    for y in ys:
        for x in xs:
            p = Point(x,y)
            if rect.covers(p):
                z = bilinear(src, x, y)
                if np.isfinite(z):
                    pts.append((x,y,z))
    if len(pts) < 20:
        return None
    arr = np.asarray(pts, dtype=float)
    z = arr[:,2]
    A = np.column_stack([arr[:,0]-arr[:,0].mean(), arr[:,1]-arr[:,1].mean(), np.ones(len(arr))])
    coef = np.linalg.lstsq(A, z, rcond=None)[0]
    pred = A @ coef
    rmse = float(np.sqrt(np.mean((z-pred)**2)))
    zrange = float(z.max()-z.min())
    slope = float(math.hypot(coef[0],coef[1]))
    return {
        "elevation_min_m": float(z.min()),
        "elevation_max_m": float(z.max()),
        "elevation_range_m": zrange,
        "best_fit_slope_percent": slope*100.0,
        "best_fit_slope_degrees": math.degrees(math.atan(slope)),
        "plane_rmse_m": rmse,
        "score": zrange + rmse*2.0,
    }


def optimize_footprint(parcel, mdt_path):
    search_poly = parcel.buffer(-0.75)
    if search_poly.is_empty:
        search_poly = parcel
    minx,miny,maxx,maxy = search_poly.bounds
    best = None
    with rasterio.open(mdt_path) as src:
        for y in np.arange(miny, maxy+0.001, 0.75):
            for x in np.arange(minx, maxx+0.001, 0.75):
                if not search_poly.contains(Point(x,y)):
                    continue
                for angle in range(0, 180, 5):
                    r = rectangle(x,y,angle)
                    if not search_poly.covers(r):
                        continue
                    stats = sample_rect(src,r)
                    if stats is None:
                        continue
                    rec = {"center_epsg3763":[float(x),float(y)],"angle_deg":angle,"geometry":r,**stats}
                    if best is None or rec["score"] < best["score"]:
                        best = rec
    return best


def main():
    cfg = json.loads(CONFIG.read_text())
    lon, lat = cfg["center_wgs84"]
    to_3763 = Transformer.from_crs("EPSG:4326","EPSG:3763",always_xy=True)
    to_wgs = Transformer.from_crs("EPSG:3763","EPSG:4326",always_xy=True)
    cx,cy = to_3763.transform(lon,lat)
    radius = 180.0
    west,south = to_wgs.transform(cx-radius,cy-radius)
    east,north = to_wgs.transform(cx+radius,cy+radius)
    bbox = [west,south,east,north]

    OUT.mkdir(parents=True, exist_ok=True)
    raw = fetch_cadastro(bbox)
    (OUT/"cadastro_raw.geojson").write_text(json.dumps(raw,indent=2)+"\n")

    candidates = choose_candidates(raw.get("features",[]), Point(lon,lat), to_3763)
    top = candidates[:12]
    candidate = top[0] if top else None

    ortho_bounds = (cx-90,cy-90,cx+90,cy+90)
    ortho = fetch_ortho(ortho_bounds)
    ortho.save(OUT/"ortho_2025.jpg",quality=94)

    placement = None
    if candidate is not None and MDT.exists():
        placement = optimize_footprint(candidate["geom_xy"], MDT)

    fig,ax=plt.subplots(figsize=(9,9))
    ax.imshow(np.asarray(ortho),extent=[ortho_bounds[0],ortho_bounds[2],ortho_bounds[1],ortho_bounds[3]],origin="upper")
    for i,row in enumerate(top):
        g=row["geom_xy"]
        geoms=[g] if g.geom_type=="Polygon" else list(g.geoms)
        for poly in geoms:
            x,y=poly.exterior.xy
            ax.plot(x,y,linewidth=1.0 if i else 2.6)
        rp=g.representative_point()
        ax.text(rp.x,rp.y,f'{row["area_m2"]:.0f} m²',fontsize=7)
    ax.scatter([cx],[cy],marker="x",s=70)
    if placement:
        x,y=placement["geometry"].exterior.xy
        ax.plot(x,y,linewidth=3)
    ax.set_xlim(ortho_bounds[0],ortho_bounds[2]); ax.set_ylim(ortho_bounds[1],ortho_bounds[3])
    ax.set_aspect("equal")
    ax.set_title("Cova do Ouro — DGT Cadastro + Orthophoto 2025")
    ax.set_xlabel("PT-TM06 X (m)"); ax.set_ylabel("PT-TM06 Y (m)")
    fig.tight_layout(); fig.savefig(OUT/"parcel_overlay.png",dpi=200); plt.close(fig)

    summary_top=[]
    for row in top:
        summary_top.append({
            "id":row["id"],"label":row["label"],"area_m2":row["area_m2"],
            "distance_to_listing_point_m":row["distance_to_listing_point_m"],
            "contains_listing_point":row["contains_listing_point"],
            "administrativeunit":row["properties"].get("administrativeunit"),
        })

    out = {
        "listing_point_wgs84":[lon,lat],
        "cadastro_source":"DGT Cadastro Predial (Continente) OGC API",
        "feature_count_in_360m_box":len(candidates),
        "target_advertised_area_m2":TARGET_AREA,
        "top_candidates":summary_top,
        "selected_candidate":None,
        "optimized_6x7_placement":None,
        "warning":"Selection is automated from cadastral geometry, advertised area and agency point. Verify NIC/parcel identity against seller documents before treating it as the legal property.",
    }
    if candidate:
        g=candidate["geom_xy"]
        out["selected_candidate"]={
            "id":candidate["id"],"label":candidate["label"],"area_m2":candidate["area_m2"],
            "distance_to_listing_point_m":candidate["distance_to_listing_point_m"],
            "contains_listing_point":candidate["contains_listing_point"],
            "bounds_epsg3763":list(g.bounds),
            "centroid_epsg3763":[g.centroid.x,g.centroid.y],
            "centroid_wgs84":list(to_wgs.transform(g.centroid.x,g.centroid.y)),
            "geometry_geojson_wgs84":mapping(candidate["geom_wgs"]),
        }
    if placement:
        center_wgs=to_wgs.transform(*placement["center_epsg3763"])
        out["optimized_6x7_placement"]={
            k:v for k,v in placement.items() if k!="geometry"
        }
        out["optimized_6x7_placement"]["center_wgs84"]=list(center_wgs)
        out["optimized_6x7_placement"]["geometry_geojson_wgs84"]=mapping(shp_transform(to_wgs.transform,placement["geometry"]))

    (OUT/"parcel_summary.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))


if __name__=="__main__":
    main()
