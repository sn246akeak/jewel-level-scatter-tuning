#!/usr/bin/env python3
"""Build a fixed F1-F10 priority profile without allowing rule-order drift."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from board_common import read_json, write_json


PROFILES = {
    "F1": (["balanced_structure"], ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11"]),
    "F2": (["fragment_heavy", "small_components"], ["R1", "R2", "R3", "R10", "R9", "R4", "R8", "R5", "R6", "R7", "R11"]),
    "F3": (["near_hue", "low_color_separation"], ["R1", "R2", "R6", "R5", "R3", "R9", "R7", "R4", "R8", "R10", "R11"]),
    "F4": (["high_brightness", "high_saturation"], ["R1", "R2", "R7", "R5", "R6", "R3", "R9", "R4", "R8", "R10", "R11"]),
    "F5": (["symmetry", "paired_regions"], ["R1", "R2", "R9", "R3", "R4", "R8", "R5", "R6", "R7", "R10", "R11"]),
    "F6": (["complex_boundary", "contour_fragments"], ["R1", "R2", "R8", "R3", "R9", "R4", "R5", "R6", "R7", "R10", "R11"]),
    "F7": (["rare_color_tail", "small_inventory"], ["R1", "R2", "R3", "R4", "R10", "R9", "R8", "R5", "R6", "R7", "R11"]),
    "F8": (["dominant_region", "low_color_count"], ["R1", "R2", "R3", "R9", "R5", "R4", "R8", "R6", "R7", "R10", "R11"]),
    "F9": (["face_expression", "feature_hierarchy"], ["R1", "R2", "R9", "R5", "R7", "R6", "R3", "R4", "R8", "R10", "R11"]),
    "F10": (["containment", "outline_linework"], ["R1", "R2", "R9", "R4", "R3", "R8", "R5", "R6", "R7", "R10", "R11"]),
}


def build(analysis: dict[str, Any], primary: str, secondary: list[str] | None = None) -> dict[str, Any]:
    matched = list(analysis["matched_classes"])
    if primary not in PROFILES:
        raise ValueError(f"unknown primary class: {primary}")
    if primary not in matched:
        raise ValueError(f"primary class {primary} is not in matched_classes {matched}")
    expected_secondary = [item for item in matched if item != primary]
    chosen_secondary = secondary if secondary is not None else expected_secondary
    if chosen_secondary != expected_secondary:
        raise ValueError(f"secondary_classes must exactly equal matched non-primary classes: {expected_secondary}")
    risk_tags: list[str] = []
    for profile_id in [primary, *chosen_secondary]:
        for tag in PROFILES[profile_id][0]:
            if tag not in risk_tags:
                risk_tags.append(tag)
    metrics = analysis["objective_metrics"]
    semantics = analysis["ai_semantics"]
    evidence = {key: value for key, value in metrics.items() if key != "color_count"}
    evidence.update({key: semantics[key] for key in semantics if key != "notes"})
    return {
        "level_id": analysis["level_id"],
        "source_revision": analysis["source_revision"],
        "primary_class": primary,
        "secondary_classes": chosen_secondary,
        "risk_tags": risk_tags,
        "priority_order": PROFILES[primary][1],
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_analysis", type=Path)
    parser.add_argument("--primary", required=True, choices=sorted(PROFILES))
    parser.add_argument("--secondary", nargs="*")
    parser.add_argument("--output", type=Path, default=Path("priority_profile.json"))
    args = parser.parse_args()
    profile = build(read_json(args.source_analysis), args.primary, args.secondary)
    write_json(args.output, profile)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
