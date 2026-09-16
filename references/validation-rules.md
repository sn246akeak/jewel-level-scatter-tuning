# Validation Contract

Validate the exact candidate that will be written to KStage. Load rule definitions from [priority-rules.md](priority-rules.md) and the fixed order from the candidate's `priority_profile.json`.

## Commands

For normal runs use `python3 scripts/run_level.py review --run /path/to/run`, followed by `check`. The standalone validator is for maintenance. Unity export validation still uses `scripts/validate_color_ids.py` when an export is requested.

## Required report fields

The report must identify `level_id`, `source_revision`, `candidate_revision`, and the profile used. It must include a result for every R1-R11 ID in the exact profile order.

Record these machine or mathematical checks:

| Check | Rule IDs |
|---|---|
| Dimensions, filled art cells, transparent-cell overflow, color totals, canonical IDs | R1 |
| Same-base conflict count and coordinates | R2 |
| Target colors per large source region and target groups spanning source regions | R3 |
| Structural-color component summary | R4 |
| Value-contrast coverage matrix | R5 |
| Near-hue coverage area and near-hue jewel adjacency area | R6 |
| Saturated adjacency edge length and white/cream-to-bright long-edge contact | R7 |
| Boundary color count and continuous segment count | R8 |
| Symmetry difference score | R9 |
| Per-color four-direction components, eight-direction components, and true flying points | R10 |
| Dominant-color-over-50% and rare-color shortage warnings | R11 |

`validate_initial_board.py` emits every metric in this table. Warning thresholds identify items for AI review; they do not pretend to decide visual quality.

## AI-only checks

Scripts do not decide:

- Whether the subject, silhouette, and feature hierarchy remain readable under R9.
- Whether containment and source-region crossings still make visual sense under R9.
- Whether faces and expressions remain appealing and recognizable under R9.
- Whether the cleanup entry, overall composition, and player comfort pass R11.

Record each as `pass` or `fail` with short evidence. Do not label a script heuristic as an AI visual result.

## Acceptance logic

1. Reject immediately if R1 or R2 fails.
2. Evaluate R3-R11 in the exact profile order.
3. A failure at an earlier position cannot be offset by a later result.
4. Revise `design_spec.json` and run `run_level.py design`; it increments the revision and regenerates the candidate and report.
5. Accept only when the visual review names the computed candidate hash, all five visual checks pass, and each warning has its own passing review with evidence. Face N/A is forbidden for face-bearing sources. The R8 check cannot be skipped. See [design-spec.md](design-spec.md) for the single review input. Exact symmetry requests fail mechanically if the output differs.
6. During KStage painting or commit, record the observed inventory checks and any visible errors. Finish according to [kstage-editor-workflow.md](kstage-editor-workflow.md#fixed-finish-sequence); do not add routine post-save screenshots, pixel comparisons, or refresh/restore tests. Distinguish browser-save confirmation from optional tests: record unperformed tests as `not_run` and do not let them block normal completion.

## Report skeleton

```json
{
  "level_id": "<id>",
  "source_revision": "<revision>",
  "candidate_revision": 1,
  "profile": {
    "primary_class": "F4",
    "priority_order": ["R1", "R2", "R7", "R5", "R6", "R3", "R9", "R4", "R8", "R10", "R11"]
  },
  "hard_gates_passed": false,
  "rule_results": {},
  "metrics": {},
  "ai_visual_checks": {},
  "editor_verification": {},
  "accepted": false
}
```
