from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PARCEL = ROOT / "site_output_cova_do_ouro_parcel"
ORTHO = PARCEL / "ortho_2025.jpg"
OUT = ROOT / "site_output_cova_do_ouro_listing_georef"
LISTING_URL = "https://images.century21.pt/b27472e0-660a-40af-bf5a-0d77016aa932/2.png?height=1536&quality=100&width=2048"
ORTHO_BOUNDS = [-20411.96603710206, 62053.59232631121, -20231.96603710206, 62233.59232631121]


def download_listing():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "listing_plot_outline.png"
    r = requests.get(LISTING_URL, timeout=90, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    path.write_bytes(r.content)
    return path


def normalize(gray):
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    return clahe.apply(gray)


def match_homography(listing_bgr, ortho_bgr):
    a = normalize(cv2.cvtColor(listing_bgr, cv2.COLOR_BGR2GRAY))
    b = normalize(cv2.cvtColor(ortho_bgr, cv2.COLOR_BGR2GRAY))
    sift = cv2.SIFT_create(nfeatures=12000, contrastThreshold=0.02, edgeThreshold=15)
    ka, da = sift.detectAndCompute(a, None)
    kb, db = sift.detectAndCompute(b, None)
    if da is None or db is None:
        raise RuntimeError("SIFT descriptors unavailable")
    bf = cv2.BFMatcher(cv2.NORM_L2)
    knn = bf.knnMatch(da, db, k=2)
    good = [m for m,n in knn if m.distance < 0.74*n.distance]
    if len(good) < 8:
        raise RuntimeError(f"Too few good matches: {len(good)}")
    src = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1,1,2)
    dst = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1,1,2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0, maxIters=10000, confidence=0.999)
    if H is None:
        raise RuntimeError("Homography failed")
    inliers = mask.ravel().astype(bool)
    proj = cv2.perspectiveTransform(src[inliers], H)
    err = np.linalg.norm(proj[:,0,:] - dst[inliers,0,:], axis=1)
    return H, {
        "keypoints_listing":len(ka),
        "keypoints_ortho":len(kb),
        "good_matches":len(good),
        "inliers":int(inliers.sum()),
        "inlier_ratio":float(inliers.mean()),
        "median_reprojection_error_px":float(np.median(err)) if len(err) else None,
        "p90_reprojection_error_px":float(np.percentile(err,90)) if len(err) else None,
    }


def yellow_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Century21 parcel outline is bright yellow.
    lo = np.array([18, 130, 120], np.uint8)
    hi = np.array([42, 255, 255], np.uint8)
    m = cv2.inRange(hsv, lo, hi)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5,5),np.uint8))
    return m


def px_to_xy(u,v,w,h):
    minx,miny,maxx,maxy = ORTHO_BOUNDS
    x = minx + (u / w) * (maxx-minx)
    y = maxy - (v / h) * (maxy-miny)
    return x,y


def main():
    listing_path = download_listing()
    listing = cv2.imread(str(listing_path), cv2.IMREAD_COLOR)
    ortho = cv2.imread(str(ORTHO), cv2.IMREAD_COLOR)
    if listing is None or ortho is None:
        raise RuntimeError("Could not read listing/ortho image")

    H, metrics = match_homography(listing, ortho)
    h,w = ortho.shape[:2]
    warped = cv2.warpPerspective(listing, H, (w,h))

    mask = yellow_mask(listing)
    warped_mask = cv2.warpPerspective(mask, H, (w,h), flags=cv2.INTER_NEAREST)
    ys,xs = np.where(warped_mask > 0)
    if len(xs) < 20:
        raise RuntimeError("Yellow outline did not survive georeference")

    overlay = ortho.copy()
    yellow = np.zeros_like(overlay)
    yellow[:,:,1] = 255
    yellow[:,:,2] = 255
    sel = warped_mask > 0
    overlay[sel] = (0.25*overlay[sel] + 0.75*yellow[sel]).astype(np.uint8)

    # Agency map point at center of our 180m ortho crop.
    cv2.drawMarker(overlay,(w//2,h//2),(255,0,0),cv2.MARKER_CROSS,24,2)
    cv2.imwrite(str(OUT/"listing_outline_on_dgt_ortho.png"),overlay)
    cv2.imwrite(str(OUT/"listing_warped_to_dgt.png"),warped)
    cv2.imwrite(str(OUT/"listing_yellow_mask_georef.png"),warped_mask)

    xys = np.array([px_to_xy(float(u),float(v),w,h) for u,v in zip(xs,ys)])
    outline_bounds = [float(xys[:,0].min()),float(xys[:,1].min()),float(xys[:,0].max()),float(xys[:,1].max())]

    # Find contour(s) of transformed yellow line for compact vector evidence.
    contours,_=cv2.findContours(warped_mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contours=sorted(contours,key=cv2.contourArea,reverse=True)
    lines=[]
    for c in contours[:20]:
        if len(c)<3:
            continue
        eps=1.5
        c2=cv2.approxPolyDP(c,eps,False)
        coords=[]
        for p in c2[:,0,:]:
            coords.append(list(px_to_xy(float(p[0]),float(p[1]),w,h)))
        lines.append(coords)
    (OUT/"outline_lines_epsg3763.json").write_text(json.dumps(lines,indent=2)+"\n")

    payload={
        "listing_image_url":LISTING_URL,
        "orthophoto_source":"DGT Orthophotos 2025, 0.25m",
        "orthophoto_bounds_epsg3763":ORTHO_BOUNDS,
        "registration":metrics,
        "yellow_pixel_count":int(len(xs)),
        "outline_bounds_epsg3763":outline_bounds,
        "outline_span_m":[outline_bounds[2]-outline_bounds[0],outline_bounds[3]-outline_bounds[1]],
        "outputs":{
            "overlay":"site_output_cova_do_ouro_listing_georef/listing_outline_on_dgt_ortho.png",
            "warped_listing":"site_output_cova_do_ouro_listing_georef/listing_warped_to_dgt.png",
            "warped_mask":"site_output_cova_do_ouro_listing_georef/listing_yellow_mask_georef.png",
            "outline_lines":"site_output_cova_do_ouro_listing_georef/outline_lines_epsg3763.json",
        },
        "warning":"The yellow line is an advertising graphic, not an official cadastral survey. Registration quality must be reviewed visually.",
    }
    (OUT/"listing_georef_summary.json").write_text(json.dumps(payload,indent=2)+"\n")
    print(json.dumps(payload,indent=2))


if __name__=="__main__":
    main()
