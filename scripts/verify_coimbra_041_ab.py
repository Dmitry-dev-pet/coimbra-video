#!/usr/bin/env python3
"""Coimbra 041 A/B/A screenshot integrity checks; human review still required."""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
from PIL import Image, ImageChops, ImageStat, ImageDraw

HERE = Path(__file__).resolve().parents[1] / "web" / "polo-ii-041-evidence"
SHOTS = ["baseline-040", "candidate-041", "restored-040"]
REGIONS = [(0, 410, 550, 745), (430, 110, 1190, 690)]

def fraction_changed(image1: Image.Image, image2: Image.Image, threshold=16):
    return sum(1 for pixel in ImageChops.difference(image1, image2).convert("L").getdata()
               if pixel > threshold) / (image1.width * image1.height)


def main():
    report = json.loads((HERE / "coimbra-041-ab.json").read_text())
    if not report.get("successful"):
        raise RuntimeError("Browser A/B/A did not finish")
    before, after, restored = (report[k] for k in ("before", "candidate", "restored"))
    assert before["street"]["spot"] == after["street"]["spot"] == restored["street"]["spot"] == "polo-ii"
    assert before["cameraXYZ"] == after["cameraXYZ"] == restored["cameraXYZ"]
    assert before["cameraRotation"] == after["cameraRotation"] == restored["cameraRotation"]
    assert abs(before["street"]["measured_eye_height_m"] - 1.7) < 0.12
    assert before["visual040"]["active"] and after["visual040"]["active"]
    v=after["vegetation041"]
    assert v["active"] and v["selectedCrowns"] >= 15
    assert v["lobeInstances"] == 5 * v["selectedCrowns"]
    assert v["hiddenSourceTriangles"] > 200
    assert v["retainedSourceTriangles"] > v["hiddenSourceTriangles"]
    assert v["originalGeometryRestored"]
    assert v["originalGLBModified"] is False
    assert v["crop_m"] == [220, 220] and v["margin_m"] == 12
    assert restored["vegetation041"]["originalGeometryRestored"]
    assert not restored["vegetation041"]["active"]
    assert report["outsideSpot"]["vegetation041"]["originalGeometryRestored"]
    assert not report["outsideSpot"]["vegetation041"]["active"]
    assert not report["errors"]

    images=[]
    for shot in SHOTS:
        file=HERE / ("coimbra-041-" + shot + ".png")
        with Image.open(file) as png:
            assert png.format=="PNG" and png.size==(1280,800)
            images.append(png.convert("RGB"))
    original,candidate,back=images
    baseline_changes=[];restored_changes=[]
    for rect in REGIONS:
        before_crop=original.crop(rect)
        after_crop=candidate.crop(rect)
        back_crop=back.crop(rect)
        assert max(ImageStat.Stat(after_crop).stddev)>3.0, "Candidate is a blank render"
        baseline_changes.append(fraction_changed(before_crop,after_crop))
        restored_changes.append(fraction_changed(before_crop,back_crop))
    changed_ratio=sum(baseline_changes)/len(baseline_changes)
    restored_ratio=sum(restored_changes)/len(restored_changes)
    assert changed_ratio>0.025, f"Vegetation is not visibly different: {changed_ratio:.3f}"
    assert restored_ratio<0.09, f"Cannot visually restore baseline: {restored_ratio:.3f}"

    contact=Image.new("RGB",(1280*3,800),"white")
    for i,img in enumerate(images):
        contact.paste(img,(i*1280,0))
    pen=ImageDraw.Draw(contact)
    for i,title in enumerate(("Baseline 040","Vegetation 041","Restored 040")):
        pen.rectangle((i*1280+440,0,i*1280+700,33),fill=(27,35,36))
        pen.text((i*1280+452,11),title,fill=(245,245,242))
    contact.save(HERE/"coimbra-041-polo-ii-contact.jpg",quality=88,optimize=True)

    receipt={
        "lane":"coimbra-041-polo-ii-vegetation-ab",
        "same_camera":True,
        "camera_height_m":before["street"]["measured_eye_height_m"],
        "selected_accepted_crowns":v["selectedCrowns"],
        "source_triangle_count_hidden_in_patch":v["hiddenSourceTriangles"],
        "source_triangle_count_retained":v["retainedSourceTriangles"],
        "smoothed_foliage_lobe_instances":v["lobeInstances"],
        "candidate_changed_scene_pixel_fraction":round(changed_ratio,4),
        "restored_changed_scene_pixel_fraction":round(restored_ratio,4),
        "original_GLTF_buffers_untouched":True,
        "accepted_blend_unchanged":True,
        "human_approved":False,
        "Mac_M4_FPS_measured":False,
    }
    (HERE/"coimbra-041-visual-verification.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt,indent=2))

if __name__=="__main__":
    main()
