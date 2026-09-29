from __future__ import annotations

import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_hero_realism.py <manifest>")

    manifest = json.loads(Path(sys.argv[1]).read_text())
    if manifest.get("version") != "coimbra-hero-realism-v1":
        fail("wrong version")

    buildings = manifest.get("hero_buildings") or []
    if len(buildings) != 4 or len(set(buildings)) != 4:
        fail("expected exactly four unique hero buildings")

    windows = manifest.get("window_stats") or {}
    requested = int(windows.get("requested", 0))
    emitted = int(windows.get("emitted", 0))
    skipped = int(windows.get("skipped", 0))
    mullions = int(windows.get("mullions", 0))
    shifted = int(windows.get("shifted", 0))

    if requested < 100:
        fail("window pass unexpectedly sparse")
    if emitted <= 0 or skipped <= 0:
        fail("window variation did not emit both kept and omitted openings")
    if emitted + skipped != requested:
        fail("window accounting mismatch")
    if mullions < 10:
        fail("too few mullioned windows")
    if shifted < 10:
        fail("window placement variation did not activate")

    realism = manifest.get("realism") or {}
    balconies = int(realism.get("balconies", 0))
    roof_units = int(realism.get("roof_units", 0))
    trims = int(realism.get("trim_pieces", 0))
    downpipes = int(realism.get("downpipes", 0))

    if balconies < 1 or balconies > 4:
        fail("balcony count outside restrained range")
    if roof_units < 1:
        fail("flat-roof technical details missing")
    if trims != 8:
        fail("expected plinth + cornice on four hero buildings")
    if downpipes != 4:
        fail("expected one downpipe per hero building")

    geometry = manifest.get("overlay_geometry") or {}
    if int(geometry.get("faces", 0)) <= 0:
        fail("realism overlay is empty")

    images = manifest.get("images") or []
    if len(images) != 4:
        fail("expected four review photos")

    rules = manifest.get("rules") or {}
    for key in (
        "full_city_unchanged",
        "photo_patch_only",
        "balconies_top_two_facades_only",
        "closeups_from_safe_hero_position",
    ):
        if rules.get(key) is not True:
            fail(f"missing invariant: {key}")

    print(json.dumps({
        "ok": True,
        "windows_requested": requested,
        "windows_emitted": emitted,
        "windows_skipped": skipped,
        "window_mullions": mullions,
        "balconies": balconies,
        "roof_units": roof_units,
        "overlay_faces": geometry.get("faces"),
    }, indent=2))


if __name__ == "__main__":
    main()
