# Module B Design Method

Use this procedure only after `source_analysis.json` and `priority_profile.json` are complete. Load R1-R11 from [priority-rules.md](priority-rules.md) and apply them in the exact profile order. This file describes the work sequence; it does not define or reorder rules.

## Inputs

Require:

- Completed/base board, dimensions, palette, and exact inventory.
- `design_spec.json` for AI semantics, the F-profile decision, and optional protected-region counts.
- `source_analysis.json` for measured features and AI semantics.
- `priority_profile.json` for the selected profiles and fixed order.
- A stable revision identifier shared by all artifacts.

## Build the structural map

1. Extract four-direction and eight-direction components for each source color.
2. Mark large regions, small details, outer boundary cells, holes, narrow links, centerlines, paired regions, and containment relations.
3. Record visually meaningful regions that do not align exactly with raw color components.
4. Create a region-capacity table and a target-color inventory table.
5. Mark every illegal target/base pairing under R2 before proposing assignments.

## Allocate target colors

1. Walk the exact profile order and record the decision made for each rule ID.
2. Propose assignments for the largest and most structurally important regions first.
3. Compare assignments by legal capacity, component count, source-region crossings, value difference, hue-family relation, boundary effect, and symmetry effect.
4. Use whole regions first. When a split is required, use one continuous band, block, nested area, or contour-following segment.
5. Recompute remaining inventory after every major assignment. Do not postpone a known count mismatch to the final pass.

## Resolve small remainders

Use this sequence and stop at the first legal fit:

1. Extend an existing same-color group through a neighboring legal cell.
2. Fill a matching small source detail or paired detail.
3. Complete a short structural line or contour segment.
4. Place a compact edge-following repair beside the nearest group.

For each repair, record the affected rule IDs and why earlier options did not fit. Do not create an unrecorded exception.

## Candidate review loop

After a complete candidate exists:

1. Re-evaluate every rule in the exact profile order.
2. Compare four-direction and eight-direction component maps.
3. Inspect the boundary as an ordered contour rather than only as color totals.
4. Inspect left-right or top-bottom correspondence when `source_analysis.json` marks symmetry.
5. Compare the candidate against the source at full view and at pixel scale.
6. Run an optimization challenge: attempt one legal region swap or local repair that could improve a higher-priority failed or weak rule.
7. Keep the change only when it improves the earliest affected rule without breaking an earlier rule.

Save the accepted candidate as `initial_board.json`; never paint an unvalidated draft into KStage.

Use `scripts/run_level.py design` for this procedure. Per-level changes belong in `design_spec.json`, not in a new Python program or a hand-edited candidate.

## Initial-board artifact

The artifact must contain:

```json
{
  "level_id": "<level or pre-level id>",
  "source_revision": "<same revision as Module A>",
  "candidate_revision": 1,
  "profile_path": "priority_profile.json",
  "width": 0,
  "height": 0,
  "colors": [],
  "completeBoard": [],
  "initialBoard": [],
  "rule_decisions": {
    "R1": {"status": "pass", "notes": []},
    "R2": {"status": "pass", "notes": []}
  },
  "exceptions": []
}
```

Include one decision entry for every R1-R11 ID. Exceptions must name an existing rule ID, affected cells or regions, and the evidence that made the exception necessary.
