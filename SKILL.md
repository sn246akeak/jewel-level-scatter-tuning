---
name: jewel-level-scatter-tuning
description: Design, restore, and validate playable pre-fill boards for pixel-art jewel sorting levels in KStage. Use for source-board classification, structural recoloring, scatter-quality review, editor painting, and restoring an accepted board after state loss.
---

# Jewel Level Scatter Tuning

## Purpose and boundaries

Create an initial jewel board that is legal, readable, clustered, and faithful to the completed pixel art's visual structure. Treat the result as a structural recolor rather than random scatter.

Use the KStage editor as the final source of truth. The skill may analyze, plan, validate, paint, restore, and visually review a board. Stop at the completed editor state or export modal unless the user explicitly asks to export, package, or upload.

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
-> compare final editor state
-> report actual results
```

For restoration, reuse the four artifacts from the accepted version. If any artifact is missing or belongs to another source board, rebuild Module A before painting.

## Module A: analysis and classification

1. Read [references/classification-profiles.md](references/classification-profiles.md) and [references/priority-rules.md](references/priority-rules.md).
2. Obtain the completed/source board and palette using [references/kstage-editor-workflow.md](references/kstage-editor-workflow.md).
3. Record objective measurements and AI-observed art semantics in `source_analysis.json` using the schema in the classification reference.
4. Select exactly one primary F profile and every applicable secondary profile. Use the primary profile's priority order verbatim.
5. Write `priority_profile.json`. Copy profile IDs, risk tags, and the priority order exactly; do not translate, rename, add, omit, or reorder entries.
6. Confirm the two files describe the same source board and evidence. Only then start Module B.

Until `analyze_source_board.py` and `build_priority_profile.py` are implemented, create these two artifacts explicitly from the source data and fixed tables. This temporary manual step does not permit changing the tables.

## Module B: board design

1. Read [references/design-method.md](references/design-method.md). Read [references/approved-patterns.md](references/approved-patterns.md) only when its listed patterns match the source art.
2. Design with the exact `priority_order` from `priority_profile.json`. R1 and R2 may never be traded for a later rule.
3. Save the candidate as `initial_board.json`, including the completed/base board, initial board, dimensions, palette, and a reference to the profile artifact.
4. Validate according to [references/validation-rules.md](references/validation-rules.md) and save the full result as `validation_report.json`.
5. Perform the required AI checks recorded in that reference. Script success alone is insufficient.
6. If any hard gate fails or the visual review rejects the board, revise the candidate and repeat validation before entering KStage.
7. Paint or commit only the accepted candidate using [references/kstage-editor-workflow.md](references/kstage-editor-workflow.md).
8. Compare the actual editor canvas and inventory with the accepted candidate. Do not report completion from local files alone.

## Required artifacts

Keep these four artifacts together for each level and accepted revision:

```text
source_analysis.json
priority_profile.json
initial_board.json
validation_report.json
```

Each artifact must identify the level/source and revision so a restore cannot mix versions. A later revision replaces the accepted set only after local validation, AI review, and editor verification all pass.

## Reference routing

- Always read [references/priority-rules.md](references/priority-rules.md) and [references/classification-profiles.md](references/classification-profiles.md) for a new design.
- Read [references/design-method.md](references/design-method.md) when creating or revising an initial board.
- Read [references/validation-rules.md](references/validation-rules.md) before accepting a candidate or export.
- Read [references/kstage-editor-workflow.md](references/kstage-editor-workflow.md) for any KStage read, paint, restore, or final-state check.
- Read [references/approved-patterns.md](references/approved-patterns.md) only for matching symmetric, contour, reciprocal-area, or small-accent cases.

## Completion and stopping point

Completion requires all of the following:

- The four required artifacts exist and refer to the same source and revision.
- R1 and R2 pass.
- The remaining rules have been checked in the profile's fixed order.
- The validation report has no unresolved failure.
- The AI visual checks pass.
- KStage accepts the board, every inventory row is complete, and the visible final canvas matches the accepted candidate.

After accepting KStage's completion dialog, stop at the export modal or current completed editor state. Do not enter a level ID, confirm export, export the level, or upload to the server without an explicit request.

If JSON or ZIP will be handed to Unity, run `scripts/validate_color_ids.py` and require `OK` before handoff.

## Completion report

Report observed values, not a generic claim that the skill was followed. Include at least:

```text
主分类：F*
辅助分类：F*、F*
实际顺序：R1 > R2 > ... > R11
硬门槛：通过 / 未通过
近色主交换：<actual value>
高饱和长边：<actual value>
真实飞点：<actual value>
边界颜色：<actual value>
视觉检查：通过 / 未通过
剩余风险或例外：<none or details>
```

Never report completion while validation, editor verification, or a required visual check remains unresolved.

## User boundaries

- If the user requests review only, do not operate the editor.
- If the user asks to execute, keep the current exact KStage tab visible at the final accepted state.
- If browser access, login, or the exact editor tab is unavailable, identify the blocked step precisely.
