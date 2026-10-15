#!/usr/bin/env python3
"""Review-only A/B image evidence verification; not a visual-quality pass."""
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

BASE = Path(__file__).resolve().parents[1] / "web" / "polo-ii-040-evidence"

def main():
    report = json.loads((BASE / "coimbra-040-ab.json").read_text())
    assert report["verify_restore_outside_polo_ii"] is True
    before = report["baseline"]["qa"]
    after = report["candidate"]["qa"]
    assert before["spot"] == after["spot"] == "polo-ii"
    assert abs(before["measured_eye_height_m"] - 1.7) < 0.12
    assert abs(after["measured_eye_height_m"] - 1.7) < 0.12
    assert report["candidate"]["visual"]["facadeTriangles"] >= 10
    assert report["candidate"]["visual"]["roadStrips"] >= 1
    assert report["candidate"]["visual"]["originalSceneGeometryChanged"] is False
    assert report["pageErrors"] == []

    with Image.open(BASE / "coimbra-040-polo-ii-before.png") as b, Image.open(BASE / "coimbra-040-polo-ii-after.png") as a:
        b = b.convert("RGB")
        a = a.convert("RGB")
        assert b.size == a.size == (1280, 800)
        # The HUD occupies upper-left; check actual 3D content below/right.
        box = (480, 110, 1220, 720)
        crop_a, crop_b = a.crop(box), b.crop(box)
        delta = ImageChops.difference(crop_a, crop_b)
        changed = delta.convert("L").point(lambda x: 255 if x > 15 else 0)
        changed_ratio = sum(1 for value in changed.getdata() if value > 0) / (
            changed.width * changed.height
        )
        baseline_variation = max(ImageStat.Stat(crop_b).stddev)
        candidate_variation = max(ImageStat.Stat(crop_a).stddev)
        assert changed_ratio > 0.08, "Images differ only in labels; scene look unchanged"
        assert candidate_variation > 3.0, "Candidate looks blank"
        side = Image.new("RGB", (2560, 800))
        side.paste(b, (0, 0))
        side.paste(a, (1280, 0))
        side.save(BASE / "coimbra-040-polo-ii-side-by-side.jpg", quality=88, optimize=True)

    receipt = {
        "lane": "coimbra-040-polo-ii-visual-ab",
        "actual_scene_pixel_changed_ratio_in_3d_crop": round(changed_ratio, 4),
        "baseline_rgb_stddev": round(baseline_variation, 3),
        "candidate_rgb_stddev": round(candidate_variation, 3),
        "camera_equal": before["camera_world_xyz"] == after["camera_world_xyz"],
        "facade_triangles": report["candidate"]["visual"]["facadeTriangles"],
        "osm_road_strips": report["candidate"]["visual"]["roadStrips"],
        "visual_quality_accepted": False,
        "mac_fps_verified": False,
    }
    assert receipt["camera_equal"]
    (BASE / "coimbra-040-visual-verification.json").write_text(
        json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))

if __name__ == "__main__":
    main()
