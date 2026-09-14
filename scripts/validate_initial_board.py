#!/usr/bin/env python3
"""Validate a planned Jewel initial board before painting it into KStage."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ID_TO_HEX = {
    1: "#F1EDE2",
    2: "#F15294",
    3: "#954716",
    4: "#363739",
    5: "#EB271B",
    6: "#F6CB0B",
    7: "#ED6100",
    8: "#4B4ECF",
    9: "#057205",
    10: "#9ECE20",
    11: "#EBDEA7",
    12: "#1DA9DC",
    13: "#C23BFF",
    14: "#ECB3B9",
    15: "#8B8B8B",
    18: "#FF9505",
    19: "#4DEBEA",
    20: "#383880",
    21: "#39A92B",
    22: "#D78B6A",
    23: "#7A2E3A",
    26: "#7221BC",
    27: "#F9F110",
}


COLOR_FAMILY = {
    1: "pale",
    2: "pink",
    3: "brown",
    4: "dark",
    5: "red_orange",
    6: "yellow_orange",
    7: "red_orange",
    8: "blue_purple",
    9: "green",
    10: "green",
    11: "pale",
    12: "blue_cyan",
    13: "purple_pink",
    14: "pale",
    15: "gray",
    18: "yellow_orange",
    19: "blue_cyan",
    20: "blue_purple",
    21: "green",
    22: "brown",
    23: "brown",
    26: "blue_purple",
    27: "yellow_orange",
}


PALE_FAMILIES = {"pale", "yellow_orange", "pink"}
NEAR_FAMILY_PAIRS = {
    frozenset(("yellow_orange", "red_orange")),
    frozenset(("blue_cyan", "blue_purple")),
    frozenset(("blue_purple", "purple_pink")),
    frozenset(("purple_pink", "pink")),
    frozenset(("green", "green")),
    frozenset(("brown", "red_orange")),
    frozenset(("brown", "yellow_orange")),
}


def normalize_empty(value: Any) -> int:
    return 0 if value in (None, 0, -1, "") else int(value)


def get_board(data: dict[str, Any], names: tuple[str, ...]) -> list[list[int]]:
    level = data.get("level", data)
    for name in names:
        board = level.get(name)
        if isinstance(board, list):
            return [[normalize_empty(cell) for cell in row] for row in board]
    raise SystemExit(f"missing board: one of {', '.join(names)}")


def connected_components(board: list[list[int]], color_id: int, *, diagonal: bool) -> list[int]:
    height = len(board)
    width = len(board[0]) if height else 0
    dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if diagonal:
        dirs += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    seen: set[tuple[int, int]] = set()
    sizes: list[int] = []
    for y in range(height):
        for x in range(width):
            if board[y][x] != color_id or (x, y) in seen:
                continue
            queue = [(x, y)]
            seen.add((x, y))
            size = 0
            for cx, cy in queue:
                size += 1
                for dx, dy in dirs:
                    nx, ny = cx + dx, cy + dy
                    if (
                        0 <= nx < width
                        and 0 <= ny < height
                        and board[ny][nx] == color_id
                        and (nx, ny) not in seen
                    ):
                        seen.add((nx, ny))
                        queue.append((nx, ny))
            sizes.append(size)
    return sorted(sizes, reverse=True)


def color_counts(board: list[list[int]]) -> Counter[int]:
    return Counter(cell for row in board for cell in row if cell)


def boundary_counts(initial: list[list[int]], base: list[list[int]]) -> Counter[int]:
    height = len(base)
    width = len(base[0]) if height else 0
    boundary: Counter[int] = Counter()
    for y in range(height):
        for x in range(width):
            if not base[y][x]:
                continue
            is_boundary = False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height) or not base[ny][nx]:
                    is_boundary = True
                    break
            if is_boundary and initial[y][x]:
                boundary[initial[y][x]] += 1
    return boundary


def near_hue_pairs(initial: list[list[int]], base: list[list[int]]) -> dict[str, int]:
    pairs: Counter[str] = Counter()
    for y, row in enumerate(base):
        for x, base_id in enumerate(row):
            target_id = initial[y][x]
            if not base_id or not target_id:
                continue
            base_family = COLOR_FAMILY.get(base_id, "unknown")
            target_family = COLOR_FAMILY.get(target_id, "unknown")
            near = base_family == target_family or frozenset((base_family, target_family)) in NEAR_FAMILY_PAIRS
            light_on_light = base_family in PALE_FAMILIES and target_family in PALE_FAMILIES
            if near or light_on_light:
                key = f"{ID_TO_HEX.get(target_id, target_id)} on {ID_TO_HEX.get(base_id, base_id)}"
                pairs[key] += 1
    return dict(sorted(pairs.items(), key=lambda item: item[1], reverse=True))


def validate(path: Path) -> tuple[dict[str, Any], bool]:
    data = json.loads(path.read_text())
    base = get_board(data, ("base", "completeBoard"))
    initial = get_board(data, ("initial", "initialBoard"))
    height = len(base)
    width = len(base[0]) if height else 0
    errors: list[str] = []
    warnings: list[str] = []

    if len(initial) != height or any(len(row) != width for row in initial):
        errors.append("initial board dimensions do not match base board")

    base_counts = color_counts(base)
    initial_counts = color_counts(initial)
    if base_counts != initial_counts:
        errors.append(f"color totals mismatch: base={dict(base_counts)} initial={dict(initial_counts)}")

    same_base = []
    unfilled = []
    overflow = []
    for y in range(height):
        for x in range(width):
            base_id = base[y][x]
            target_id = initial[y][x]
            if base_id and not target_id:
                unfilled.append((x, y))
            if not base_id and target_id:
                overflow.append((x, y, target_id))
            if base_id and target_id and base_id == target_id:
                same_base.append((x, y, target_id))
    if same_base:
        errors.append(f"same-base conflicts: {len(same_base)}")
    if unfilled:
        errors.append(f"unfilled art cells: {len(unfilled)}")
    if overflow:
        errors.append(f"filled transparent cells: {len(overflow)}")

    boundary = boundary_counts(initial, base)
    boundary_major = [item for item in boundary.most_common() if item[1] >= 2]
    if len(boundary_major) > 3:
        warnings.append(f"boundary uses more than 3 meaningful colors: {boundary_major}")

    near_pairs = near_hue_pairs(initial, base)
    if near_pairs:
        top_pair, top_count = next(iter(near_pairs.items()))
        total_art = sum(base_counts.values())
        if top_count / total_art >= 0.08:
            warnings.append(f"large near-hue or pale-on-pale coverage: {top_pair} = {top_count}")

    components = {}
    for color_id in sorted(initial_counts):
        c4 = connected_components(initial, color_id, diagonal=False)
        c8 = connected_components(initial, color_id, diagonal=True)
        components[str(color_id)] = {
            "hex": ID_TO_HEX.get(color_id),
            "total": initial_counts[color_id],
            "components4": c4,
            "components8": c8,
            "trueFlyingPoints4": sum(1 for size in c4 if size <= 2),
            "trueFlyingPoints8": sum(1 for size in c8 if size <= 2),
        }
        if len(c8) > 4 and components[str(color_id)]["trueFlyingPoints8"] > 1:
            warnings.append(f"{ID_TO_HEX.get(color_id, color_id)} has many 8-dir fragments: {c8[:10]}")

    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "width": width,
        "height": height,
        "counts": {str(key): value for key, value in sorted(initial_counts.items())},
        "sameBaseConflicts": same_base[:50],
        "boundary": {
            "counts": {str(key): value for key, value in boundary.most_common()},
            "meaningfulColorCount": len(boundary_major),
        },
        "nearHueOrLightOnLight": near_pairs,
        "components": components,
    }
    return report, not errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board_json", type=Path)
    parser.add_argument("--json", action="store_true", help="emit machine-readable report")
    args = parser.parse_args()

    report, ok = validate(args.board_json)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("OK" if ok else "FAIL", args.board_json)
        for error in report["errors"]:
            print(f"  ERROR: {error}")
        for warning in report["warnings"]:
            print(f"  WARN: {warning}")
        print(f"  boundary colors: {report['boundary']['meaningfulColorCount']}")
        print(f"  near-hue/light pairs: {len(report['nearHueOrLightOnLight'])}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
