#!/usr/bin/env python3
"""Run Module A, Module B generation, and mechanical validation in one command."""

from __future__ import annotations

import argparse
from pathlib import Path

from analyze_source_board import analyze
from board_common import read_json, write_json
from build_priority_profile import PROFILES, build
from design_initial_board import design, render_svg
from validate_initial_board import validate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_state", type=Path)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--visual-review", type=Path)
    parser.add_argument("--candidate-revision", type=int, default=1)
    args = parser.parse_args()

    spec = read_json(args.spec)
    primary = spec.get("primary_class")
    if primary not in PROFILES:
        raise ValueError("design_spec.json must contain a valid primary_class F1-F10")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = args.out_dir / "source_analysis.json"
    profile_path = args.out_dir / "priority_profile.json"
    board_path = args.out_dir / "initial_board.json"
    preview_path = args.out_dir / "initial_board.svg"
    report_path = args.out_dir / "validation_report.json"

    analysis = analyze(args.source_state, spec.get("ai_semantics"))
    if "matched_classes" in spec:
        matched = spec["matched_classes"]
        if not isinstance(matched, list) or not matched or any(item not in PROFILES for item in matched):
            raise ValueError("matched_classes must be a non-empty list containing only F1-F10")
        if matched != analysis["matched_classes"]:
            raise ValueError("matched_classes must match measured features and ai_semantics; omit it to derive automatically")
    write_json(analysis_path, analysis)
    profile = build(analysis, primary, spec.get("secondary_classes"))
    write_json(profile_path, profile)
    artifact = design(args.source_state, profile_path, spec, args.candidate_revision)
    artifact["ai_semantics"] = analysis["ai_semantics"]
    write_json(board_path, artifact)
    render_svg(artifact, preview_path)
    report, mechanically_ok = validate(board_path, profile_path, analysis_path, args.visual_review)
    write_json(report_path, report)

    print(f"source_analysis={analysis_path}")
    print(f"priority_profile={profile_path}")
    print(f"initial_board={board_path}")
    print(f"preview={preview_path}")
    print(f"validation_report={report_path}")
    print(f"mechanical_validation={'pass' if mechanically_ok else 'fail'}")
    print(f"ai_visual_review={'pass' if report['accepted'] else 'pending/fail'}")
    return 0 if mechanically_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
