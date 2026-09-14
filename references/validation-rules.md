# Validation Contract

Validate the exact candidate that will be written to KStage. Load rule definitions from [priority-rules.md](priority-rules.md) and the fixed order from the candidate's `priority_profile.json`.

## Current commands

Run board validation:

```bash
python3 scripts/validate_initial_board.py initial_board.json --json
```

Capture the JSON output as `validation_report.json`. Before any Unity-facing import, export, ZIP, or `level.json` handoff, run:

```bash
python3 scripts/validate_color_ids.py /path/to/level.json
```

Use `--fix` only to repair an identified ID mismatch, then validate the repaired file again.

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

The current `validate_initial_board.py` covers only part of this contract: dimensions, totals, same-base conflicts, transparent overflow, boundary color count, near-hue coverage, and four/eight-direction components. Until its Phase 3 upgrade is complete, calculate and record the missing quantitative checks explicitly. Marking them absent or `unknown` blocks completion.

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
4. Revise `initial_board.json`, increment `candidate_revision`, and regenerate the entire report after any board change.
5. Accept locally only when every required result is present and no failure remains.
6. After KStage painting or commit, compare the visible editor inventory and canvas with the accepted candidate. Add editor verification to the same report before final completion.

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
