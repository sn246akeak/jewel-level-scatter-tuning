---
name: jewel-level-scatter-tuning
description: Design, restore, and validate playable pre-fill boards for pixel-art jewel sorting levels in KStage. Use for source-board classification, structural recoloring, scatter-quality review, editor painting, and restoring an accepted board after state loss.
---

# Jewel Level Scatter Tuning

## Purpose and boundaries

Create an initial jewel board that is legal, readable, clustered, and faithful to the completed pixel art's visual structure. Treat the result as a structural recolor rather than random scatter.

Use the KStage editor as the final source of truth. The skill may analyze, plan, validate, paint, restore, and visually review a board. Use the fixed finish sequence in [references/kstage-editor-workflow.md](references/kstage-editor-workflow.md) and stop immediately at its confirmed-save point unless the user explicitly requests additional work.

Do not replace this workflow with the retired local-editor, automatic-scatter, or manual-adjust paths. A restore request reuses the latest accepted artifacts for that level; it does not trigger a redesign unless the user asks for one.

## Single source of rules

[references/priority-rules.md](references/priority-rules.md) is the only source that defines R1-R11. Other files may reference rule IDs but must not rename, redefine, paraphrase, or create additional priority rules.

R1 and R2 are absolute gates and always remain first. Later rules may change order only through an exact F1-F10 profile defined in [references/classification-profiles.md](references/classification-profiles.md). Never invent a rule ID, profile ID, label, or priority order.

## Required execution order

Run Module A before every new Module B design. Module B must not begin until both Module A artifacts exist and contain all required fields.

```text
read source
-> Module A: analyze and classify
-> source_analysis.json
-> priority_profile.json
-> Module B: design initial board
-> initial_board.json
-> validate
-> validation_report.json
-> AI visual review
-> revise until accepted
-> write to KStage
-> fixed finish sequence
-> report actual results and stop
```

For restoration, reuse the four artifacts from the accepted version. If any artifact is missing or belongs to another source board, rebuild Module A before painting.

## Module A: analysis and classification

1. Read [references/classification-profiles.md](references/classification-profiles.md) and [references/priority-rules.md](references/priority-rules.md).
2. Obtain the completed/source board and palette using `scripts/run_level.py prepare` and [references/kstage-editor-workflow.md](references/kstage-editor-workflow.md).
3. Record AI-observed art semantics and the F-profile decision in `design_spec.json` using [references/design-spec.md](references/design-spec.md). Do not write a per-level Python script.
4. Run `scripts/run_level.py analyze`; it computes objective measurements and writes `source_analysis.json`. Select the primary profile, then `design` writes both Module A artifacts before Module B.
5. The pipeline writes `priority_profile.json` from the fixed table. It rejects unknown profile IDs, missing matched classes, changed risk tags, and reordered rules.
6. Confirm the two files describe the same source board and evidence. Only then start Module B.

Normal runs use only `scripts/run_level.py` for local generation and `scripts/kstage_executor.mjs` for browser execution. The detailed commands are in [references/design-spec.md](references/design-spec.md). Standalone helper CLIs are for maintenance.

## Module B: board design

1. Read [references/design-method.md](references/design-method.md) and [references/design-spec.md](references/design-spec.md). Read [references/approved-patterns.md](references/approved-patterns.md) only when its listed patterns match the source art.
2. Run `scripts/run_level.py design` with `design_spec.json`. Its allocator proposes a legal candidate; inspect the art rules in the exact profile order. It does not prove visual optimality.
   When `design.optimizer.enabled` is explicitly true, first read [references/candidate-optimizer.md](references/candidate-optimizer.md). Generation pauses at candidate selection; a machine recommendation cannot approve the board. The option is off by default.
3. Use optional `region_targets` data only for visually meaningful face, outline, centerline, paired, or contained regions. Do not create `classify.py`, `allocate.py`, `design.py`, `accept.py`, or an equivalent per-level program.
4. The pipeline writes `initial_board.json`, `initial_board.svg`, and the mechanical `validation_report.json`.
5. Inspect the preview, write `visual_review.json`, and run `scripts/run_level.py review`. Script success alone is insufficient.
6. If any hard gate fails or the visual review rejects the board, revise the candidate and repeat validation before entering KStage.
7. Paint or commit only the accepted candidate using [references/kstage-editor-workflow.md](references/kstage-editor-workflow.md).
8. Use the editor workflow reference for inventory checks during painting and the fixed finish sequence. Do not report completion from local files alone; post-save restore tests and pixel comparisons are not routine requirements.

## Normal runs and maintenance

AI authors only `design_spec.json` and `visual_review.json` per level. All other artifacts are script-generated and hash-checked. Do not create per-level programs, duplicate semantic input files, edit generated JSON, or modify the skill while executing a level.

Execution requires real server blocks, a complete simulated plan, a fresh single editor context, and successful pre-write block checks. Use the fixed executor's `runStep` entrypoint; it owns the session, bounded batches, and timestamped logs. Do not improvise coordinates or session wrappers.

A runtime or UI failure ends that execution attempt with a generated report. Preserve the known tab and last verified state. Script fixes belong to maintenance and require `scripts/test_skill.py` before use; its certificate states which tests actually ran. Never describe offline tests as a successful live KStage save.

## Required artifacts

Keep these four artifacts together for each level and accepted revision:

```text
source_analysis.json
priority_profile.json
initial_board.json
validation_report.json
```

Each artifact must identify the level/source and revision so a restore cannot mix versions. A later revision replaces the accepted set only after local validation, AI review, and the routine editor completion checks pass. Record optional restore or pixel tests only when performed.

## Reference routing

- Always read [references/priority-rules.md](references/priority-rules.md) and [references/classification-profiles.md](references/classification-profiles.md) for a new design.
- Read [references/design-method.md](references/design-method.md) when creating or revising an initial board.
- Read [references/design-spec.md](references/design-spec.md) for the per-level JSON input and generic pipeline commands.
- Read [references/validation-rules.md](references/validation-rules.md) before accepting a candidate or export.
- Read [references/kstage-editor-workflow.md](references/kstage-editor-workflow.md) for any KStage read, paint, restore, or final-state check.
- When an execution blocker occurs, first match its stage and error text in [references/execution-troubleshooting.md](references/execution-troubleshooting.md), then use the matching verified procedure within the current execution/maintenance boundary.
- Read [references/approved-patterns.md](references/approved-patterns.md) only for matching symmetric, contour, reciprocal-area, or small-accent cases.

## Completion and stopping point

Completion requires all of the following:

- The four required artifacts exist and refer to the same source and revision.
- R1 and R2 pass.
- The remaining rules have been checked in the profile's fixed order.
- The validation report has no unresolved failure.
- The AI visual checks pass.
- KStage accepts the board, the painting inventory checks pass, and the fixed finish sequence reaches its confirmed-save point.

The exact final clicks and stopping condition are defined only in [references/kstage-editor-workflow.md](references/kstage-editor-workflow.md#fixed-finish-sequence). Do not extend normal execution with additional post-save checks. Export, packaging, and server upload require an explicit request.

If JSON or ZIP will be handed to Unity, run `scripts/validate_color_ids.py` and require `OK` before handoff.

## Completion report

Report observed values, not a generic claim that the skill was followed. Include at least:

```text
主分类：F*
辅助分类：F*、F*
实际顺序：R1 > R2 > ... > R11
硬门槛：通过 / 未通过
近色覆盖面积：<actual cell count>
高饱和相邻边：<actual edge count>
真实飞点：<actual value>
边界颜色：<actual value>
视觉检查：通过 / 未通过
剩余风险或例外：<none or details>
```

Never report completion while candidate validation, a required visual check, or the fixed finish sequence has an unresolved failure. Optional tests that were not requested do not block completion; do not claim they passed.

## User boundaries

- If the user requests review only, do not operate the editor.
- If the user asks to execute, use their Chrome KStage tab by default and leave it at the saved completed state; follow the browser selection details in the editor workflow reference.
- If browser access, login, or the exact editor tab is unavailable, identify the blocked step precisely.
