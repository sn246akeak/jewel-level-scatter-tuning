#!/usr/bin/env python3
"""Validate a candidate board and emit the complete R1-R11 report."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from board_common import (
    DIR4, are_near_families, board_from, board_sha256, boundary_cells,
    color_counts, color_family, component_cells, hsv, luminance, palette_map,
    read_json, write_json,
)
from build_priority_profile import build

AI_CHECK_KEYS = (
    "subject_silhouette_readable",
    "containment_and_feature_hierarchy",
    "face_and_expression",
    "composition_and_player_comfort",
    "boundary_quality",
)


def edge_pairs(board: list[list[int]]):
    height = len(board)
    width = len(board[0]) if height else 0
    for y in range(height):
        for x in range(width):
            if board[y][x] <= 0:
                continue
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if nx < width and ny < height and board[ny][nx] > 0:
                    yield board[y][x], board[ny][nx]


def restricted_components(cells: set[tuple[int, int]]) -> list[int]:
    seen: set[tuple[int, int]] = set()
    sizes = []
    for cell in cells:
        if cell in seen:
            continue
        queue = [cell]
        seen.add(cell)
        for x, y in queue:
            for dx, dy in DIR4:
                neighbor = (x + dx, y + dy)
                if neighbor in cells and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        sizes.append(len(queue))
    return sorted(sizes, reverse=True)


def visual_results(path: Path | None, candidate_hash: str, has_face: bool) -> tuple[dict[str, Any], bool]:
    if path is None:
        return {key: {"status": "pending", "evidence": "AI visual review not supplied"} for key in AI_CHECK_KEYS}, False
    raw = read_json(path)
    if raw.get("candidate_sha256") != candidate_hash:
        return {key: {"status": "pending", "evidence": "Review is not bound to this candidate hash"}
                for key in AI_CHECK_KEYS}, False
    raw = raw.get("ai_visual_checks", raw)
    unknown = set(raw) - set(AI_CHECK_KEYS)
    if unknown:
        raise ValueError(f"unknown AI visual check keys: {sorted(unknown)}")
    result = {}
    complete = True
    for key in AI_CHECK_KEYS:
        item = raw.get(key, {})
        status = item.get("status") if isinstance(item, dict) else None
        if status not in {"pass", "fail", "not_applicable"}:
            status = "pending"
        if status == "not_applicable" and (key != "face_and_expression" or has_face):
            status = "fail"
        evidence = item.get("evidence", "") if isinstance(item, dict) else ""
        result[key] = {"status": status, "evidence": evidence}
        complete = complete and status in {"pass", "not_applicable"} and bool(evidence)
    return result, complete


def validate(path: Path, profile_path: Path | None = None, analysis_path: Path | None = None,
             visual_review_path: Path | None = None) -> tuple[dict[str, Any], bool]:
    data = read_json(path)
    base = board_from(data, "completeBoard", "base")
    initial = board_from(data, "initialBoard", "initial")
    height = len(base)
    width = len(base[0]) if height else 0
    colors = data.get("colors", [])
    palette = palette_map(colors)
    canonical_ids = set(palette)
    base_counts = color_counts(base)
    initial_counts = color_counts(initial)
    errors: list[str] = []
    warnings: list[str] = []

    dimensions_ok = len(initial) == height and all(len(row) == width for row in initial)
    if not dimensions_ok:
        raise ValueError("E_BOARD_SHAPE: initial board dimensions do not match base board")
    if data.get("candidate_sha256") != board_sha256(initial):
        errors.append("candidate hash mismatch; regenerate through run_level.py")
    if "initial" in data and data["initial"] != initial:
        errors.append("initial and initialBoard aliases disagree")
    if "base" in data and data["base"] != base:
        errors.append("base and completeBoard aliases disagree")
    same_base, unfilled, overflow, unknown_ids = [], [], [], []
    for y in range(height):
        for x in range(width):
            base_id, target_id = base[y][x], initial[y][x]
            if base_id > 0 and target_id <= 0:
                unfilled.append([x, y])
            if base_id <= 0 and target_id > 0:
                overflow.append([x, y, target_id])
            if base_id > 0 and target_id == base_id:
                same_base.append([x, y, target_id])
            if target_id > 0 and target_id not in canonical_ids:
                unknown_ids.append([x, y, target_id])
    inventory_ok = base_counts == initial_counts
    if not inventory_ok:
        errors.append(f"color totals mismatch: base={dict(base_counts)} initial={dict(initial_counts)}")
    if unfilled:
        errors.append(f"unfilled art cells: {len(unfilled)}")
    if overflow:
        errors.append(f"filled transparent cells: {len(overflow)}")
    if unknown_ids:
        raise ValueError(f"E_PALETTE: unknown canonical color ids: {len(unknown_ids)}")
    if same_base:
        errors.append(f"same-base conflicts: {len(same_base)}")

    families = {color_id: color_family(palette[color_id]) for color_id in canonical_ids}
    source_regions = component_cells(base)
    total_art = sum(base_counts.values())
    large_threshold = max(8, round(total_art * 0.015))
    region_metrics = []
    target_to_regions: dict[int, set[int]] = defaultdict(set)
    for region in source_regions:
        targets = Counter(initial[y][x] for x, y in region["cells"] if initial[y][x] > 0)
        for target_id in targets:
            target_to_regions[target_id].add(region["id"])
        if region["size"] >= large_threshold:
            region_metrics.append({
                "region_id": region["id"], "source_color_id": region["color"], "size": region["size"],
                "target_counts": {str(key): value for key, value in sorted(targets.items())},
                "target_color_count": len(targets),
            })

    near_coverage: Counter[str] = Counter()
    value_matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for y in range(height):
        for x in range(width):
            source_id, target_id = base[y][x], initial[y][x]
            if source_id <= 0 or target_id <= 0:
                continue
            if are_near_families(families[source_id], families[target_id]):
                near_coverage[f"{target_id} on {source_id}"] += 1
            difference = abs(luminance(palette[source_id]) - luminance(palette[target_id]))
            bucket = "low" if difference < 0.12 else "medium" if difference < 0.3 else "high"
            value_matrix[str(source_id)][bucket] += 1

    saturated_edges = pale_bright_edges = near_adjacency_edges = 0
    for left, right in edge_pairs(initial):
        if left == right:
            continue
        left_hsv, right_hsv = hsv(palette[left]), hsv(palette[right])
        if all(item[1] >= 0.65 and item[2] >= 0.75 for item in (left_hsv, right_hsv)):
            saturated_edges += 1
        if ((families[left] == "pale" and right_hsv[2] >= 0.85)
                or (families[right] == "pale" and left_hsv[2] >= 0.85)):
            pale_bright_edges += 1
        if are_near_families(families[left], families[right]):
            near_adjacency_edges += 1

    boundary = set(boundary_cells(base))
    boundary_by_color = {
        color_id: {cell for cell in boundary if initial[cell[1]][cell[0]] == color_id}
        for color_id in initial_counts
    }
    boundary_count_map = Counter(initial[y][x] for x, y in boundary if initial[y][x] > 0)
    boundary_segments = {
        str(color_id): restricted_components(cells) for color_id, cells in boundary_by_color.items() if cells
    }
    meaningful_boundary_colors = sum(1 for count in boundary_count_map.values() if count >= 2)
    continuous_boundary_segments = sum(len(sizes) for sizes in boundary_segments.values())

    regions4 = component_cells(initial)
    regions8 = component_cells(initial, diagonal=True)
    component_metrics = {}
    total_true_flying = 0
    for color_id in sorted(initial_counts):
        four = sorted([r["size"] for r in regions4 if r["color"] == color_id], reverse=True)
        eight = sorted([r["size"] for r in regions8 if r["color"] == color_id], reverse=True)
        flying = [size for size in eight if size <= 2]
        total_true_flying += sum(flying)
        component_metrics[str(color_id)] = {
            "total": initial_counts[color_id], "components4": four, "components8": eight,
            "true_flying_components": len(flying), "true_flying_points": sum(flying),
        }

    analysis = read_json(analysis_path) if analysis_path else None
    symmetric_expected = bool(analysis and analysis.get("ai_semantics", {}).get("exact_pixel_symmetry"))
    pair_count = symmetry_mismatch = 0
    for y in range(height):
        for x in range(width // 2):
            mirror = width - 1 - x
            if base[y][x] > 0 or base[y][mirror] > 0:
                pair_count += 1
                if initial[y][x] != initial[y][mirror]:
                    symmetry_mismatch += 1
    symmetry_ratio = symmetry_mismatch / pair_count if pair_count else 0.0

    dominant_warning = max(base_counts.values()) / total_art > 0.5
    rare_colors = {str(key): value for key, value in base_counts.items() if value <= 12}
    near_total = sum(near_coverage.values())
    low_contrast_total = sum(row.get("low", 0) for row in value_matrix.values())
    statuses = {
        "R1": "pass" if dimensions_ok and inventory_ok and not unfilled and not overflow and not unknown_ids else "fail",
        "R2": "pass" if not same_base else "fail",
        "R3": "warning" if any(item["target_color_count"] > 3 for item in region_metrics) else "pass",
        "R4": "warning" if any(len(item["components8"]) > 5 for item in component_metrics.values()) else "pass",
        "R5": "warning" if total_art and low_contrast_total / total_art >= 0.15 else "pass",
        "R6": "warning" if total_art and near_total / total_art >= 0.12 else "pass",
        "R7": "warning" if saturated_edges > total_art * 0.2 or pale_bright_edges > total_art * 0.08 else "pass",
        "R8": "warning" if meaningful_boundary_colors > 3 or continuous_boundary_segments > 8 else "pass",
        "R9": "fail" if symmetric_expected and symmetry_mismatch else "pass",
        "R10": "warning" if total_true_flying else "pass",
        "R11": "warning" if dominant_warning or rare_colors else "pass",
    }

    profile = read_json(profile_path) if profile_path else None
    if profile:
        if not analysis or analysis.get("source_revision") != data.get("source_revision") or analysis.get("level_id") != data.get("level_id"):
            errors.append("missing or mismatched source analysis")
        else:
            expected_profile = build(analysis, profile.get("primary_class"))
            if profile != expected_profile:
                errors.append("profile differs from the fixed classification table or measured evidence")
        if profile.get("level_id") != data.get("level_id") or profile.get("source_revision") != data.get("source_revision"):
            errors.append("profile identity or source revision mismatch")
            statuses["R1"] = "fail"
        order = profile["priority_order"]
        profile_summary = {"path": str(profile_path), "primary_class": profile["primary_class"], "priority_order": order}
    else:
        order = [f"R{index}" for index in range(1, 12)]
        profile_summary = {"path": None, "primary_class": None, "priority_order": order}
        errors.append("priority profile not supplied")
    if set(order) != {f"R{index}" for index in range(1, 12)} or len(order) != 11:
        raise ValueError("profile priority order must contain R1-R11 exactly once")
    has_face = bool(analysis and analysis.get("ai_semantics", {}).get("contains_face_or_expression"))
    candidate_hash = board_sha256(initial)
    ai_checks, ai_complete = visual_results(visual_review_path, candidate_hash, has_face)
    raw_review = read_json(visual_review_path) if visual_review_path else {}
    reviews = raw_review.get("warning_reviews", {}) if raw_review.get("candidate_sha256") == candidate_hash else {}
    pending_warnings = [rule for rule, status in statuses.items() if status == "warning"
                        and (reviews.get(rule, {}).get("status") != "pass"
                             or not str(reviews.get(rule, {}).get("evidence", "")).strip())]
    rule_results = {rule_id: {"status": statuses[rule_id], "position": index + 1}
                    for index, rule_id in enumerate(order)}
    for rule in reviews:
        if rule in rule_results and statuses[rule] == "warning":
            rule_results[rule]["visual_review"] = reviews[rule]
    hard_gates = statuses["R1"] == statuses["R2"] == "pass"
    mechanical_ok = all(value != "fail" for value in statuses.values()) and not errors
    warnings.extend([f"{key} requires review" for key, value in statuses.items() if value == "warning"])
    report = {
        "level_id": data.get("level_id"), "source_revision": data.get("source_revision"),
        "candidate_revision": data.get("candidate_revision"),
        "candidate_sha256": candidate_hash,
        "profile": profile_summary, "hard_gates_passed": hard_gates,
        "mechanical_validation_passed": mechanical_ok, "rule_results": rule_results,
        "metrics": {
            "dimensions": {"width": width, "height": height},
            "counts": {str(key): value for key, value in sorted(initial_counts.items())},
            "same_base_conflict_count": len(same_base), "same_base_conflicts": same_base[:50],
            "unfilled_art_cells": len(unfilled), "transparent_overflow_cells": len(overflow),
            "unknown_color_ids": unknown_ids[:50], "large_source_regions": region_metrics,
            "target_groups_spanning_source_regions": {str(k): len(v) for k, v in sorted(target_to_regions.items())},
            "value_contrast_matrix": {key: dict(value) for key, value in value_matrix.items()},
            "near_hue_coverage": dict(near_coverage), "near_hue_coverage_area": near_total,
            "near_hue_jewel_adjacency_edges": near_adjacency_edges,
            "saturated_color_adjacency_edges": saturated_edges,
            "pale_to_bright_adjacency_edges": pale_bright_edges,
            "boundary": {
                "counts": {str(k): v for k, v in boundary_count_map.most_common()},
                "meaningful_color_count": meaningful_boundary_colors,
                "continuous_segment_count": continuous_boundary_segments,
                "segments_by_color": boundary_segments,
            },
            "components": component_metrics, "true_flying_points": total_true_flying,
            "symmetry": {"expected": symmetric_expected, "compared_pairs": pair_count,
                         "different_pairs": symmetry_mismatch, "difference_ratio": round(symmetry_ratio, 6)},
            "dominant_color_over_50_percent": dominant_warning, "rare_colors": rare_colors,
        },
        "ai_visual_checks": ai_checks, "editor_verification": {"status": "not_run"},
        "errors": errors, "warnings": list(dict.fromkeys(warnings)),
        "unresolved_warning_rules": pending_warnings,
        "accepted": mechanical_ok and ai_complete and not pending_warnings,
    }
    return report, mechanical_ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board_json", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--source-analysis", type=Path)
    parser.add_argument("--visual-review", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report, mechanically_ok = validate(args.board_json, args.profile, args.source_analysis, args.visual_review)
    if args.output:
        write_json(args.output, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("OK" if mechanically_ok else "FAIL", args.board_json)
        print(f"  hard gates: {'pass' if report['hard_gates_passed'] else 'fail'}")
        print(f"  visual review: {'pass' if report['accepted'] else 'pending/fail'}")
        print(f"  warnings: {len(report['warnings'])}")
    return 0 if mechanically_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
