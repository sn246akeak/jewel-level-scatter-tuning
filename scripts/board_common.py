#!/usr/bin/env python3
"""Shared, dependency-free board utilities for the jewel tuning skill."""

from __future__ import annotations

import colorsys
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


DIR4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIR8 = DIR4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_cell(value: Any) -> int:
    return -1 if value in (None, 0, -1, "") else int(value)


def normalize_board(board: list[list[Any]]) -> list[list[int]]:
    return [[normalize_cell(cell) for cell in row] for row in board]


def board_from(data: dict[str, Any], *names: str) -> list[list[int]]:
    for holder in (data, data.get("source", {}), data.get("level", {}), data.get("workspace", {})):
        for name in names:
            board = holder.get(name) if isinstance(holder, dict) else None
            if isinstance(board, list) and board:
                return normalize_board(board)
    raise ValueError(f"missing board: one of {', '.join(names)}")


def source_payload(data: dict[str, Any]) -> tuple[str, str, list[list[int]], list[dict[str, Any]]]:
    source = data.get("source", data)
    identity = data.get("identity", {})
    if data.get("level_id"):
        level_id = str(data["level_id"])
    elif identity.get("assetId"):
        level_id = f"asset_{identity['assetId']}"
    else:
        level_id = str(identity.get("levelId") or source.get("levelId") or "unknown")
    board = board_from(data, "completeBoard", "base")
    colors = source.get("colors") or data.get("colors") or []
    if not colors:
        counts = color_counts(board)
        colors = [{"id": color_id, "count": count, "hex": None} for color_id, count in sorted(counts.items())]
    revision = str(
        data.get("source_revision")
        or source.get("sourceSha256")
        or hashlib.sha256(json.dumps(board, separators=(",", ":")).encode()).hexdigest()
    )
    return level_id, revision, board, colors


def color_counts(board: list[list[int]]) -> Counter[int]:
    return Counter(cell for row in board for cell in row if cell > 0)


def palette_map(colors: Iterable[dict[str, Any]]) -> dict[int, str]:
    return {int(color["id"]): color.get("hex") or "#808080" for color in colors}


def rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def hsv(hex_color: str) -> tuple[float, float, float]:
    return colorsys.rgb_to_hsv(*rgb(hex_color))


def luminance(hex_color: str) -> float:
    channels = []
    for channel in rgb(hex_color):
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def color_family(hex_color: str) -> str:
    hue, saturation, value = hsv(hex_color)
    degrees = hue * 360
    if saturation < 0.12 and value >= 0.78:
        return "pale"
    if saturation < 0.15:
        return "gray"
    if value < 0.28:
        return "dark"
    if degrees < 15 or degrees >= 345:
        return "red"
    if degrees < 45:
        return "orange_brown" if value < 0.68 else "orange"
    if degrees < 70:
        return "yellow"
    if degrees < 165:
        return "green"
    if degrees < 205:
        return "cyan"
    if degrees < 255:
        return "blue"
    if degrees < 295:
        return "purple"
    return "pink"


NEAR_FAMILIES = {
    frozenset(("red", "orange")),
    frozenset(("orange", "orange_brown")),
    frozenset(("orange_brown", "yellow")),
    frozenset(("orange", "yellow")),
    frozenset(("yellow", "green")),
    frozenset(("green", "cyan")),
    frozenset(("cyan", "blue")),
    frozenset(("blue", "purple")),
    frozenset(("purple", "pink")),
    frozenset(("pink", "red")),
    frozenset(("pale", "yellow")),
    frozenset(("pale", "pink")),
}


def are_near_families(left: str, right: str) -> bool:
    return left == right or frozenset((left, right)) in NEAR_FAMILIES


def component_cells(
    board: list[list[int]], *, diagonal: bool = False, restrict_color: int | None = None
) -> list[dict[str, Any]]:
    height = len(board)
    width = len(board[0]) if height else 0
    dirs = DIR8 if diagonal else DIR4
    seen: set[tuple[int, int]] = set()
    output: list[dict[str, Any]] = []
    for y in range(height):
        for x in range(width):
            color_id = board[y][x]
            if color_id <= 0 or (restrict_color is not None and color_id != restrict_color) or (x, y) in seen:
                continue
            cells = [(x, y)]
            seen.add((x, y))
            for cx, cy in cells:
                for dx, dy in dirs:
                    nx, ny = cx + dx, cy + dy
                    if (
                        0 <= nx < width
                        and 0 <= ny < height
                        and (nx, ny) not in seen
                        and board[ny][nx] == color_id
                    ):
                        seen.add((nx, ny))
                        cells.append((nx, ny))
            output.append({"color": color_id, "size": len(cells), "cells": sorted(cells, key=lambda p: (p[1], p[0]))})
    output.sort(key=lambda item: (-item["size"], item["color"], item["cells"][0][1], item["cells"][0][0]))
    for region_id, item in enumerate(output):
        item["id"] = region_id
    return output


def boundary_cells(mask_board: list[list[int]]) -> list[tuple[int, int]]:
    height = len(mask_board)
    width = len(mask_board[0]) if height else 0
    result = []
    for y in range(height):
        for x in range(width):
            if mask_board[y][x] <= 0:
                continue
            if any(
                not (0 <= x + dx < width and 0 <= y + dy < height)
                or mask_board[y + dy][x + dx] <= 0
                for dx, dy in DIR4
            ):
                result.append((x, y))
    return result


def board_sha256(board: list[list[int]]) -> str:
    return hashlib.sha256(json.dumps(board, separators=(",", ":")).encode()).hexdigest()


def assert_rectangular(board: list[list[int]]) -> tuple[int, int]:
    if not board or not board[0]:
        raise ValueError("board is empty")
    width = len(board[0])
    if any(len(row) != width for row in board):
        raise ValueError("board is not rectangular")
    return width, len(board)
