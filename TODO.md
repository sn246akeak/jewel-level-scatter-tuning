# Jewel Level Scatter Tuning Roadmap

## Completed

- [x] Phase 1: split the monolithic `SKILL.md` into rule, classification, design, validation, KStage workflow, and approved-pattern references.
- [x] Phase 1: remove the retired local-editor and automatic/manual scatter workflow from the active skill.
- [x] Phase 2: define stable R1-R11 rules in one source.
- [x] Phase 2: define fixed F1-F10 classifications, risk tags, artifact schemas, and deterministic primary-profile orders.
- [x] Phase 2: make `source_analysis.json` and `priority_profile.json` mandatory before a new Module B design.

## Phase 3: script enforcement

- [ ] Add `scripts/analyze_source_board.py` to produce objective `source_analysis.json` metrics while leaving art semantics for AI input.
- [ ] Add `scripts/build_priority_profile.py` to validate F IDs and risk tags, choose/copy the fixed primary order, and reject AI-defined names or reordering.
- [ ] Add `--profile` and report-output support to `scripts/validate_initial_board.py`.
- [ ] Add target-color counts per large source region.
- [ ] Add saturated-color adjacency edge length.
- [ ] Add white/cream-to-bright long-edge contact.
- [ ] Add near-hue coverage and near-hue jewel adjacency area.
- [ ] Add boundary color and continuous-segment counts.
- [ ] Preserve per-color four/eight-direction components and refine true-flying-point detection.
- [ ] Add symmetry difference metrics.
- [ ] Add dominant-color-over-50% and rare-color shortage warnings.
- [ ] Emit a complete `validation_report.json` tied to source, candidate, and profile revisions.

## Phase 4: historical regression

- [ ] Select 2-3 representative historical images for each F1-F10 profile.
- [ ] Save expected primary/secondary classification evidence for each image.
- [ ] Compare fixed priority order, board metrics, editor result, and AI visual review.
- [ ] Record only patterns supported by repeated accepted cases; do not add duplicate rule prose.
