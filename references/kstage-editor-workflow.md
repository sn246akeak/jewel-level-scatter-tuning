# KStage Editor Workflow

Use this reference for reading, painting, restoring, and verifying a KStage pre-level. Apply R1-R11 from [priority-rules.md](priority-rules.md); this file only defines editor control.

## Browser and tab gate

- Use the Codex in-app browser for KStage.
- Maintain one editor instance for one exact pre-level URL.
- Search for an existing exact-URL tab before creating one. Reuse it when present.
- If multiple exact-URL tabs exist, stop and resolve the duplicate instead of choosing one arbitrarily.
- Keep the same tab through source reading, painting, final verification, and delivery.
- Do not use the retired local editor, external browser, automatic-scatter preview, or manual-adjust flow.

Use `scripts/kstage_prefill_helpers.mjs` for repeated mechanics. It reads and writes editor state; it does not classify the source or design the board.

## Read the source

For a `pixel-beads-editor-v2` or token link:

```js
const kstage = await import("/Users/admin/.codex/skills/jewel-level-scatter-tuning/scripts/kstage_prefill_helpers.mjs");
const boot = await kstage.bootstrapKStageV2("<kstage-editor-url>");
```

Build Module A inputs from `boot.state.source.completeBoard`, `boot.state.source.colors`, and `boot.state.source.grid`. Treat the returned source revision or token identity as part of every artifact.

## Pre-paint gate

Before painting:

- Confirm all four required artifacts exist and share the same level/source revision.
- Confirm `validation_report.json.accepted` is true for the exact candidate revision.
- Claim the existing exact KStage tab or create exactly one visible tab if none exists.
- Collapse the left `展开面板` panel and preserve a wide layout.
- Confirm `#tuneCanvas` is fully visible and its rectangle is stable across two reads.
- Confirm every planned click coordinate lies inside the canvas.
- Read the visible color inventory and map brushes by row order; do not assume canonical-ID order.

After entering pre-fill, inspect whether KStage reports `当前编辑：分片 i/n（w×h）`. For a fragment, use artifacts and counts for that exact fragment. Never apply an unsliced full-board candidate to a fragment canvas.

## Commit or paint

For v2 links, prefer the helper API after local acceptance:

```js
await kstage.applyPreFillBoardKStageV2("<kstage-editor-url>", board);
```

When direct canvas painting is required:

```js
await kstage.prepareStableKStagePainting(tab, board);
await kstage.paintInitialBoardSingleCell(tab, board);
const state = await kstage.finishPreFill(tab);
```

Use single cells or short verified runs. Re-read inventory after each color batch; stop if the used count does not increase by the planned amount. Scroll an off-screen color button into view before selecting it.

## Final editor verification

1. Require every row to show `已用 == 总` and `剩:0` via `kstage.verifyRowsComplete(tab)`.
2. Save the visible final canvas with `kstage.saveTuneCanvasImage(tab, outputPath)`.
3. Compare the saved canvas with the accepted `initial_board.json` at cell level and visually.
4. Accept the completion JavaScript dialog so KStage runs its sync path.
5. Stop at the export modal or current completed editor state.
6. Mark the same tab deliverable. Do not reopen the URL merely to show the result.

Do not enter a level ID, click `确认导出`, click `导出关卡`, or click `上传服务器` unless the user explicitly requests that action.

## Restoration after state loss

Treat requests such as `复原`, `恢复`, `填回刚刚那版`, server restart, `Not found`, or lost state as restoration.

Use the most recent accepted four-artifact set for the exact pre-level. Do not redesign, rerun classification, use manual adjust, or open a duplicate tab when the artifacts still match the source revision.

```js
const kstage = await import("/Users/admin/.codex/skills/jewel-level-scatter-tuning/scripts/kstage_prefill_helpers.mjs");
const result = await kstage.restoreKStageBoardFromSavedPlan(
  "https://kstage.kiwifun.games/products/1/pixel/pre-levels/<pre-level-id>/editor/",
  "/path/to/accepted/initial_board.json"
);
```

The restore is complete only after the same final editor verification used for a new design.

## Failure handling

Report the exact failed gate. Do not silently switch to a retired editor path, JSON import shortcut, duplicate page, screenshot-only reconstruction, or backend exploration. If the existing exact tab cannot be surfaced safely, state that the editor verification remains incomplete.
