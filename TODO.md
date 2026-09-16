# Jewel Level Scatter Tuning Roadmap

## Completed

- [x] Phase 1: split the monolithic `SKILL.md` into rule, classification, design, validation, KStage workflow, and approved-pattern references.
- [x] Phase 1: remove the retired local-editor and automatic/manual scatter workflow from the active skill.
- [x] Phase 2: define stable R1-R11 rules in one source.
- [x] Phase 2: define fixed F1-F10 classifications, risk tags, artifact schemas, and deterministic primary-profile orders.
- [x] Phase 2: make `source_analysis.json` and `priority_profile.json` mandatory before a new Module B design.

## Phase 3: script enforcement

- [x] Add `scripts/analyze_source_board.py` to produce objective `source_analysis.json` metrics while leaving art semantics for AI input.
- [x] Add `scripts/build_priority_profile.py` to validate F IDs and risk tags, choose/copy the fixed primary order, and reject AI-defined names or reordering.
- [x] Add a declarative `design_spec.json` contract and generic `scripts/design_initial_board.py` allocator.
- [x] Add `scripts/run_design_pipeline.py` so one command generates all four required artifacts and a preview.
- [x] Add `--profile`, `--source-analysis`, `--visual-review`, and report-output support to `scripts/validate_initial_board.py`.
- [x] Add target-color counts per large source region.
- [x] Add saturated-color adjacency edge length.
- [x] Add white/cream-to-bright long-edge contact.
- [x] Add near-hue coverage and near-hue jewel adjacency area.
- [x] Add boundary color and continuous-segment counts.
- [x] Preserve per-color four/eight-direction components and refine true-flying-point detection.
- [x] Add symmetry difference metrics.
- [x] Add dominant-color-over-50% and rare-color shortage warnings.
- [x] Emit a complete `validation_report.json` tied to source, candidate, and profile revisions.

## Phase 4: historical regression

- [x] Asset 2748 regression fixture: actual 19 KStage blocks versus 57 analysis regions; exact 796-cell execution simulation.
- [x] Replace inferred-block and partial-resume helpers with a guarded executor and terminal failure reports.
- [x] Require pre-write selection checks and an initial no-paint probe of every server block.
- [x] Use one normal CLI, two authored inputs, generated artifact hashes, and a runtime regression certificate.
- [x] Separate visual pairing from exact pixel symmetry; bind visual reviews to candidate hashes and resolve each warning explicitly.
- [ ] Run the new browser adapter on a separately authorized clean KStage acceptance level; offline fixtures and mock UI tests do not establish a live save/restore result.

- [ ] Select 2-3 representative historical images for each F1-F10 profile.
- [ ] Save expected primary/secondary classification evidence for each image.
- [ ] Compare fixed priority order, board metrics, editor result, and AI visual review.
- [ ] Record only patterns supported by repeated accepted cases; do not add duplicate rule prose.
