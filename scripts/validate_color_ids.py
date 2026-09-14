#!/usr/bin/env python3
"""Validate and optionally repair Jewel level color IDs.

The web editor can render colors from hex values, but Unity resolves jewel
materials by numeric color id. Any generated JSON must therefore use the
project's canonical palette IDs in colors[], completeBoard, and initialBoard.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


CANONICAL = {
    "#F1EDE2": 1,
    "#F15294": 2,
    "#954716": 3,
    "#363739": 4,
    "#EB271B": 5,
    "#F6CB0B": 6,
    "#ED6100": 7,
    "#4B4ECF": 8,
    "#057205": 9,
    "#9ECE20": 10,
    "#EBDEA7": 11,
    "#1DA9DC": 12,
    "#C23BFF": 13,
    "#ECB3B9": 14,
    "#8B8B8B": 15,
    "#FF9505": 18,
    "#4DEBEA": 19,
    "#383880": 20,
    "#39A92B": 21,
    "#D78B6A": 22,
    "#7A2E3A": 23,
    "#7221BC": 26,
    "#F9F110": 27,
}


BOARDS = ("completeBoard", "initialBoard")


def level_object(data: dict[str, Any]) -> dict[str, Any]:
    if "level" in data and isinstance(data["level"], dict):
        return data["level"]
    return data


def collect_used_ids(level: dict[str, Any]) -> set[int]:
    used: set[int] = set()
    for board_name in BOARDS:
        board = level.get(board_name)
        if not isinstance(board, list):
            continue
        for row in board:
            for cell in row:
                if cell != -1:
                    used.add(cell)
    return used


def validate_or_repair_data(data: dict[str, Any], *, fix: bool) -> tuple[dict[str, Any], list[str], bool]:
    level = level_object(data)
    colors = level.get("colors")
    if not isinstance(colors, list):
        return data, ["missing colors[]"], False

    errors: list[str] = []
    old_to_new: dict[int, int] = {}
    seen_ids: set[int] = set()

    for color in colors:
        if not isinstance(color, dict):
            errors.append(f"invalid color entry: {color!r}")
            continue
        hex_value = str(color.get("hex", "")).upper()
        if hex_value not in CANONICAL:
            errors.append(f"unknown color hex {hex_value}")
            continue
        old_id = color.get("id")
        canonical_id = CANONICAL[hex_value]
        if old_id != canonical_id:
            errors.append(f"{hex_value}: id {old_id} should be {canonical_id}")
        if isinstance(old_id, int):
            old_to_new[old_id] = canonical_id
        seen_ids.add(canonical_id)
        if fix:
            color["id"] = canonical_id

    used_ids = collect_used_ids(level)
    missing_from_colors = used_ids - set(old_to_new)
    if missing_from_colors:
        errors.append(f"board uses IDs not present in colors[]: {sorted(missing_from_colors)}")

    changed = False
    if fix and errors and not missing_from_colors:
        for board_name in BOARDS:
            board = level.get(board_name)
            if not isinstance(board, list):
                continue
            for y, row in enumerate(board):
                for x, cell in enumerate(row):
                    if cell != -1:
                        board[y][x] = old_to_new[cell]
        colors.sort(key=lambda item: item["id"])
        changed = True

        post_errors = []
        for color in colors:
            hex_value = str(color.get("hex", "")).upper()
            if color.get("id") != CANONICAL.get(hex_value):
                post_errors.append(f"{hex_value}: still wrong after fix")
        errors = post_errors

    unknown_after = collect_used_ids(level) - seen_ids
    if unknown_after:
        errors.append(f"board uses IDs outside canonical colors[] after validation: {sorted(unknown_after)}")

    return data, errors, changed


def validate_json_file(path: Path, *, fix: bool) -> bool:
    data = json.loads(path.read_text())
    data, errors, changed = validate_or_repair_data(data, fix=fix)
    if changed:
        backup = path.with_suffix(path.suffix + ".bak-wrong-color-ids")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    if errors:
        print(f"FAIL {path}")
        for error in errors:
            print(f"  - {error}")
        return False
    print(f"OK {path}" + (" (fixed)" if changed else ""))
    return True


def validate_zip_file(path: Path, *, fix: bool) -> bool:
    with zipfile.ZipFile(path, "r") as zin:
        names = zin.namelist()
        json_names = [name for name in names if name.endswith("level.json")]
        if not json_names:
            print(f"FAIL {path}\n  - no level.json in zip")
            return False
        level_name = json_names[0]
        data = json.loads(zin.read(level_name))
        data, errors, changed = validate_or_repair_data(data, fix=fix)
        if errors:
            print(f"FAIL {path}:{level_name}")
            for error in errors:
                print(f"  - {error}")
            return False
        if changed:
            backup = path.with_suffix(path.suffix + ".bak-wrong-color-ids")
            if not backup.exists():
                shutil.copy2(path, backup)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp_path = Path(tmp.name)
            try:
                with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                    for item in zin.infolist():
                        payload = zin.read(item.filename)
                        if item.filename == level_name:
                            payload = json.dumps(data, ensure_ascii=False, indent=2).encode()
                        zout.writestr(item, payload)
                shutil.move(tmp_path, path)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
    print(f"OK {path}" + (" (fixed)" if changed else ""))
    return True


def expand_targets(target: Path) -> list[Path]:
    if target.is_dir():
        nested = target / "level.json"
        if nested.exists():
            return [nested]
        return sorted(target.rglob("level.json"))
    return [target]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="level.json, level zip, or directory containing level.json")
    parser.add_argument("--fix", action="store_true", help="repair temporary IDs and create a backup")
    args = parser.parse_args()

    ok = True
    for raw_path in args.paths:
        for path in expand_targets(Path(raw_path)):
            if path.suffix.lower() == ".zip":
                ok = validate_zip_file(path, fix=args.fix) and ok
            elif path.name == "level.json" or path.suffix.lower() == ".json":
                ok = validate_json_file(path, fix=args.fix) and ok
            else:
                print(f"SKIP {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
