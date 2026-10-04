#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor in {path}, got {text.count(old)}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    args = p.parse_args()
    root = args.source

    hpp = root / "src/script/api/script_town.hpp"
    cpp = root / "src/script/api/script_town.cpp"
    town = root / "src/town_cmd.cpp"

    hpp_anchor = """\tstatic bool ExpandTown(TownID town_id, SQInteger houses);\n\n"""
    hpp_insert = hpp_anchor + """\t/**\n\t * Place one completed house without expanding roads. Coimbra editor-only bridge.\n\t * @param tile Buildable tile where the house should be placed.\n\t * @param house_id Base HouseID to place.\n\t * @pre ScriptCompanyMode::IsDeity().\n\t * @return True if the house was placed.\n\t * @api -ai\n\t */\n\tstatic bool PlaceHouse(TileIndex tile, SQInteger house_id);\n\n"""
    replace_once(hpp, hpp_anchor, hpp_insert, "script_town.hpp PlaceHouse export")

    cpp_anchor = """\treturn ScriptObject::Command<CMD_EXPAND_TOWN>::Do(town_id, houses, {TownExpandMode::Buildings, TownExpandMode::Roads});\n}\n\n"""
    cpp_insert = cpp_anchor + """/* static */ bool ScriptTown::PlaceHouse(TileIndex tile, SQInteger house_id)\n{\n\tEnforceDeityMode(false);\n\tEnforcePrecondition(false, ::IsValidTile(tile));\n\tEnforcePrecondition(false, house_id >= 0 && house_id <= UINT16_MAX);\n\n\treturn ScriptObject::Command<CMD_PLACE_HOUSE>::Do(tile, (HouseID)house_id, true, false);\n}\n\n"""
    replace_once(cpp, cpp_anchor, cpp_insert, "script_town.cpp PlaceHouse implementation")

    replace_once(
        town,
        """\tif (_game_mode != GM_EDITOR && _settings_game.economy.place_houses == PH_FORBIDDEN) return CMD_ERROR;\n""",
        """\tif (_game_mode != GM_EDITOR && _current_company != OWNER_DEITY && _settings_game.economy.place_houses == PH_FORBIDDEN) return CMD_ERROR;\n""",
        "town_cmd deity permission",
    )
    replace_once(
        town,
        """\t\tbool house_completed = _settings_game.economy.place_houses == PH_ALLOWED_CONSTRUCTED;\n""",
        """\t\tbool house_completed = _current_company == OWNER_DEITY || _settings_game.economy.place_houses == PH_ALLOWED_CONSTRUCTED;\n""",
        "town_cmd completed deity house",
    )

    checks = {
        "script_town.hpp": "static bool PlaceHouse(TileIndex tile, SQInteger house_id);",
        "script_town.cpp": "ScriptTown::PlaceHouse(TileIndex tile, SQInteger house_id)",
        "town_cmd.cpp": "_current_company != OWNER_DEITY",
    }
    for rel, needle in checks.items():
        text = (root / ("src/script/api/" + rel if rel.startswith("script_") else "src/" + rel)).read_text(encoding="utf-8")
        if needle not in text:
            raise RuntimeError(f"post-patch check failed: {rel}: {needle}")

    print("OpenTTD 15.3 Coimbra house-editor patch applied")


if __name__ == "__main__":
    main()
