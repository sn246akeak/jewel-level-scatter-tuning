# Experimental candidate optimization

Use only when `design.optimizer.enabled` is explicitly true. Absence or false preserves the existing generator. This experiment adds local candidates after the existing initial board; it does not replace browser operations or alter F1–F10 orders.

## Inputs and limits

Keep the same two authored files. In `design_spec.json`:

```json
{
  "design": {
    "optimizer": {
      "enabled": true,
      "max_evaluations": 96,
      "max_proposals": 4096,
      "max_seconds": 8,
      "max_rounds": 2,
      "max_candidates": 3,
      "preserve_regions": []
    }
  }
}
```

`preserve_regions` uses analysis region IDs. Each listed region retains its initial candidate cells exactly during optimization. Regions with existing `region_targets` constraints are also frozen. This preserves the supplied draft structure; it does not prove that the draft is visually correct. Broader role-based face, containment, and outline constraints are not implemented in this experiment. Unknown configuration fields fail rather than being silently ignored.

The proposal and evaluation limits count attempted transformations and unique legal evaluations respectively; baseline validation is separate. The time budget is checked between bounded moves, so an in-progress move/validation may finish after the deadline. With a nonbinding time limit, identical inputs and budgets reproduce the same boards. A time-limited prefix may differ across machines; the report records the stop reason. There is no global optimum guarantee.

## Search and comparison

The available operations are equal-sized uniform region swaps, equal-inventory whole-color swaps, alternative continuous-order region partitions, and equal-sized compact small-patch swaps. All preserve inventory and source mask and are rejected if they violate R1/R2, preserved regions, or mechanical validation. Unequal-sized whole-block swaps require compensation and are not silently allowed.

Metrics come from the existing validator. `optimize_candidates.rule_values` is the machine adapter; the meanings of rules remain in [priority-rules.md](priority-rules.md). Compare rules in the exact primary order. Within one rule, existing validation severity and measured dimensions are compared componentwise: all non-worse with at least one better is an improvement; mixed gains and losses are an unresolved tradeoff. Lower rules cannot resolve an earlier tradeoff. No weighted total, invented risk buckets, or AI changes to the profile order are used. R9 is measured only for explicitly requested exact symmetry; its other semantics and R11 are not scored. The output must not describe this proxy ordering as a complete artistic judgment.

The first changed rule determines improvement, regression or unresolved tradeoff. Retain the original board plus up to two unique alternatives, including unresolved tradeoffs. A deterministic tuple order schedules exploration and limits the shortlist; it does not establish a unique winner among incomparable boards. Only strict improvements advance the search. The recommendation is a search suggestion; the original remains selectable. Every worsened dimension is logged, including losses in lower-priority rules. Three outputs are a maximum, not a quota.

## Selection checkpoint

`run_level.py design` writes the usual initial artifacts plus:

- `candidate_set.json`: immutable candidate boards and their mechanical reports.
- `candidate_comparison.json`: operations, changed metrics, decisive rule, limits and actual stop reason.
- `candidate_preview.svg`: source, original candidate and alternatives together.

The run stops at `awaiting_candidate_selection`, always unaccepted. `review`, `check`, and `browser-code` cannot bypass this checkpoint. Compare the actual previews and warnings, then add the selection to the existing `visual_review.json`:

```json
{
  "candidate_selection": {
    "candidate_set_sha256": "<generated set hash>",
    "candidate_id": "<listed candidate ID or baseline>",
    "reason": "<observed visual reason, including rejected machine tradeoffs>",
    "tradeoff_reviews": {
      "R8": {"status": "pass", "evidence": "<actual observation justifying this candidate's boundary change>"}
    }
  },
  "candidate_sha256": "<selected board hash>",
  "ai_visual_checks": {},
  "warning_reviews": {}
}
```

Fill the five visual checks and every required warning review as defined in [design-spec.md](design-spec.md). In addition, selection requires a passing, nonempty `tradeoff_reviews` entry for every rule in the chosen candidate's `comparison_to_baseline.tradeoff_rules`, even if the existing validator does not warn. The R8 entry above is illustrative; use the actual reported IDs. A machine recommendation never supplies this evidence. AI can reject a machine improvement when the proxy missed an artistic problem; record that problem explicitly. If no candidate is visually acceptable, revise `design_spec.json` and generate a new set. Do not fabricate a passing review to reach the next stage.

Run `run_level.py select --run <run>` to materialize the chosen candidate, then `review` and `check`. Selection alone leaves the run unaccepted. A changed design or candidate set requires a new selection and review, even if its board happens to be identical. Generated candidates and comparisons are included in the usual artifact hashes.

## Stable-version boundary

This implementation is maintained in an isolated experimental worktree. The installed Skill, its validation certificate, old runs, and editor helpers remain unchanged. To leave the experiment, use the installed Skill and a normal run. Do not transplant an experimental manifest into an old run. Installing or merging this experiment is a separate release step after evaluating its results.
