# KStage Editor Workflow

This reference specifies execution only. Classification and recoloring are completed before this workflow.

## One tab, one accepted run

Use the user's existing Chrome tab unless they explicitly select another browser. Discover tabs through the available CUA API, select the exact requested editor, and keep that handle through save. If none exists, open one visible tab. Never create a second copy to recover from an error.

The executor requires one tab for the URL, matching live source identity, source revision, board matrices, palette, a tested runtime, and an accepted immutable run. A split canvas or partly filled board returns a specific error before painting. Restore requests first use the editor's own saved progress. If that fails, repaint an accepted plan only into a confirmed empty board using this same executor; do not reconstruct a partial board from inventory totals.

## Region identity contract

`source_analysis.json.regions` describes art regions for design. These IDs are never KStage fill IDs.

`kstage_blocks.json.blocks` comes from the actual `prefill/start` response. Preserve its `blockId`, `colorId`, `pixelCount`, and `pixels` verbatim. Check unique IDs, exact pixel counts, integer in-bounds coordinates, source-color agreement, no overlap, and full art-cell coverage. Do not infer the operation partition from four-way or eight-way connectivity. Asset 2748 had 57 analysis regions and 19 actual operation blocks.

`prepare` calls the stateless V2 endpoints to obtain source and blocks; this does not paint or save anything in the browser. The executor separately enters pre-fill through the selected tab.

The V2 mutation envelope includes `operation.occurredAt` in UTC, alongside `requestId`, `expectedRevision`, `contextToken`, and `state`. `prepare_report.json` records each request's stage, duration, HTTP status, and sanitized error response, including failures before source artifacts exist. This report is generated automatically; it contains neither opening nor context tokens.

Before writing any cell, the executor probes every server block in the live UI. Selection must display the expected block ID, original hex, total count, and unfilled count. It then paints minority assignments first and checks each color's inventory; immediately before each bulk fill it rechecks the selected block and the remaining inventory. A block fill consumes only currently unfilled cells and preserves the earlier single-cell assignments. The planner simulates the entire result and requires exact agreement with the candidate before UI work.

## Normal invocation

All local commands and authored inputs are defined in [design-spec.md](design-spec.md). Run `run_level.py check` before the browser stage.

Select the existing tab as `tab`, then obtain the exact setup code from the normal CLI:

```bash
python3 scripts/run_level.py browser-code --run /absolute/path/to/run --browser-id 1 --browser-action setup
```

Use the actual browser ID returned by discovery. Paste the generated setup into CUA unchanged, at top level, once. It retains `kstageRuntime` and `kstageOptions`; the runtime owns the execution session and timestamped logs. CUA does not reliably preserve repeated imports across calls or declarations inside a try/function block, so do not wrap the generated code or reimport on each step. `startExecution` is an internal/maintenance API.

The first call initializes without painting. Use `browser-code --browser-action advance` to obtain the repeatable expression for later calls; each performs at most 20 actions and continues the stored cursor. Repeat it until `awaiting_visual_review`. `--browser-action status` returns a read-only checkpoint. Overlapping calls and switching tabs are rejected. An executor failure or runtime reset still stops the run; do not delete its report or replay a partial session.

The last fill handles the automatic completion confirmation and cancels the export modal before yielding. The program scrolls the observed final image into view and generates `editor_execution_plan.json`, `editor_execution_report.json`, and one complete `editor_preview.png`; it rejects a viewport too small to show the image. Compare that preview with the accepted candidate, paying attention to R8/R9. If it matches, invoke:

```bash
python3 scripts/run_level.py browser-code --run /absolute/path/to/run --browser-action finish --visual-matches true
```

If it does not match, use `action: "finish", visualMatches: false`; this records a terminal failure. A repeated call after confirmed save returns the saved status without more browser actions. Do not hand-edit the execution report. Inventory and operation checks are recorded separately from a pixel-by-pixel comparison; the latter is not claimed when unavailable.

## Fixed finish sequence

1. Fill the last block.
2. Confirm the automatic completion prompt. If it does not appear, use the visible `完成并导出（跳过打散）` control. `完成填充` alone only synchronizes/exits pre-fill on the inspected editor and is not an equivalent finish operation.
3. Cancel the export modal.
4. After the one final preview comparison, the `finish` action clicks `保存进度` in the same tab.
5. Observe `已保存浏览器进度。`, keep the tab available, and return the final reply immediately.

The executor owns these operations and records whether the save confirmation was observed. No refresh, restore test, extra screenshot, or redesign follows a successful save. Report browser-local saving only. Export or server upload requires a user request.

## Terminal errors

For observed failure scenarios, matching conditions, established fixes, and their verification limits, consult [the execution troubleshooting table](execution-troubleshooting.md) before improvising a recovery. The response boundaries below still apply.

| Code | Meaning | Normal-run response |
|---|---|---|
| E_HELPER_UNTESTED / E_HELPER_CHANGED | Runtime lacks matching regression results or changed mid-run | Stop; repair/test in maintenance |
| E_ARTIFACT_CHANGED / E_INPUT_CHANGED / E_NOT_ACCEPTED | Candidate, inputs, or review are stale | Regenerate/review through the pipeline before any UI write |
| E_BLOCKS_MISSING / E_BLOCK_SCHEMA / E_BLOCK_COVERAGE | Missing or invalid server partition | Stop before opening pre-fill |
| E_DUPLICATE_TAB / E_TAB_CHANGED / E_EDIT_LOCK | Conflicting editor context | Stop; retain the known tab |
| E_FRAGMENT / E_CAPABILITY | Unsupported editor mode or missing expected controls | Stop before painting |
| E_SELECTED_BLOCK | Selected block differs from the plan | Do not click a color |
| E_CANVAS | Target moved, is obscured, or is outside the viewport | Do not click a cell |
| E_INVENTORY / E_EDITOR / E_TIMEOUT | Unexpected write result | Record last verified step and stop |
| E_VISUAL / E_FINISH / E_SAVE | Final review or saving failed | Report incomplete; never claim saved |

There is no automatic retry after a failed write, reset, undo loop, duplicate tab, backend exploration, or runtime patch during normal drawing. Bounded waits for a pending response are part of one operation, not retries. A helper failure is a maintenance task; preserve its report and raw contract data for regression.

## Maintenance and capability limits

Before using changed scripts, run `python3 scripts/test_skill.py` (supply `--node` when Node is not on PATH). It tests the captured server partition, full plan reconstruction, pre-write rejection, inventory errors, failure stopping, and artifact/visual-review gates. The generated `.runtime-validation.json` records the exact scripts, tests, and reference hashes. A change invalidates the certificate and existing runs.

The certificate explicitly distinguishes offline regression from a live browser acceptance test. Passing the former does not prove a changed site's UI still matches. The initial UI probes provide a no-paint capability check on each run; production release confidence still benefits from a separately authorized clean test level.

The local editor patch's `载入预填充方案` capability is not assumed deployed. Normal execution has one supported path above. Add batch import as a separately tested adapter only after that capability is verified in the target editor. Never treat an HTTP response or an internal file as a browser save.
