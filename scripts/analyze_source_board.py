#!/usr/bin/env python3
"""Create source_analysis.json from a KStage source-state artifact."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from board_common import (
    are_near_families,
    boundary_cells,
    color_counts,
    color_family,
    component_cells,
    hsv,
    palette_map,
    read_json,
    source_payload,
    write_json,
)


SEMANTIC_DEFAULTS = {
    "visual_pairing": False,
    "exact_pixel_symmetry": False,
    "contains_face_or_expression": False,
    "containment_structure": False,
    "outline_or_linework_dominant": False,
    "notes": [],
}


def analyze(source_path: Path, semantics: dict[str, Any] | None = None) -> dict[str, Any]:
    data = read_json(source_path)
    level_id, revision, board, colors = source_payload(data)
    palette = palette_map(colors)
    counts = color_counts(board)
    total = sum(counts.values())
    regions = component_cells(board)
    boundary = boundary_cells(board)
    families = {color_id: color_family(palette[color_id]) for color_id in counts}
    near_groups = sorted(
        {
            "-".join(sorted((families[left], families[right])))
            for index, left in enumerate(sorted(counts))
            for right in sorted(counts)[index + 1 :]
            if are_near_families(families[left], families[right])
        }
    )
    objective = {
        "left_right_mask_symmetric": all((row[x] > 0) == (row[-1-x] > 0)
                                         for row in board for x in range(len(row) // 2)),
        "bright_color_ratio": round(sum(counts[c] for c in counts if hsv(palette[c])[2] >= 0.85) / total, 6),
        "high_saturation_ratio": round(
            sum(counts[c] for c in counts if hsv(palette[c])[1] >= 0.65 and hsv(palette[c])[2] >= 0.75) / total,
            6,
        ),
        "small_component_ratio": round(sum(r["size"] for r in regions if r["size"] <= 3) / total, 6),
        "small_component_count": sum(1 for r in regions if r["size"] <= 3),
        "rare_color_count": sum(1 for count in counts.values() if count <= 12),
        "boundary_color_count": len({board[y][x] for x, y in boundary}),
        "dominant_color_ratio": round(max(counts.values()) / total, 6),
        "near_hue_groups": near_groups,
        "color_count": len(counts),
    }
    ai_semantics = dict(SEMANTIC_DEFAULTS)
    if semantics:
        semantics = dict(semantics)
        # Legacy 'symmetric' means visual pairing, never a demand for exact mirroring.
        if "symmetric" in semantics:
            semantics.setdefault("visual_pairing", semantics.pop("symmetric"))
        unknown = set(semantics) - set(SEMANTIC_DEFAULTS)
        if unknown:
            raise ValueError(f"unknown ai_semantics keys: {sorted(unknown)}")
        ai_semantics.update(semantics)
    for key, value in ai_semantics.items():
        if key != "notes" and type(value) is not bool:
            raise ValueError(f"ai_semantics.{key} must be boolean")
    if ai_semantics["exact_pixel_symmetry"] and not objective["left_right_mask_symmetric"]:
        raise ValueError("E_SYMMETRY: exact_pixel_symmetry requires a mirrored silhouette; visual_pairing does not")
    matched: list[str] = []
    if objective["small_component_ratio"] >= 0.08 or objective["small_component_count"] >= 8:
        matched.append("F2")
    if near_groups:
        matched.append("F3")
    if objective["bright_color_ratio"] >= 0.45 or objective["high_saturation_ratio"] >= 0.45:
        matched.append("F4")
    if ai_semantics["visual_pairing"] or ai_semantics["exact_pixel_symmetry"]:
        matched.append("F5")
    if objective["boundary_color_count"] >= 5:
        matched.append("F6")
    if objective["rare_color_count"]:
        matched.append("F7")
    if objective["dominant_color_ratio"] > 0.5 or objective["color_count"] <= 3:
        matched.append("F8")
    if ai_semantics["contains_face_or_expression"]:
        matched.append("F9")
    if ai_semantics["containment_structure"] or ai_semantics["outline_or_linework_dominant"]:
        matched.append("F10")
    if not matched:
        matched = ["F1"]
    return {
        "level_id": level_id,
        "source_revision": revision,
        "dimensions": {"width": len(board[0]), "height": len(board), "art_cells": total},
        "objective_metrics": objective,
        "ai_semantics": ai_semantics,
        "matched_classes": matched,
        "regions": [
            {"id": r["id"], "source_color_id": r["color"], "size": r["size"], "cells": r["cells"]}
            for r in regions
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_state", type=Path)
    parser.add_argument("--spec", type=Path, required=True, help="design_spec.json containing ai_semantics")
    parser.add_argument("--output", type=Path, default=Path("source_analysis.json"))
    args = parser.parse_args()
    semantics = read_json(args.spec).get("ai_semantics", {})
    result = analyze(args.source_state, semantics)
    write_json(args.output, result)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
