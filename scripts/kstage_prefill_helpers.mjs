const BROWSER_CLIENT_PATH =
  "/Users/admin/.codex/plugins/cache/openai-bundled/browser/26.818.31338/scripts/browser-client.mjs";

export async function ensureBrowser() {
  return await ensureInAppBrowser();
}

export async function ensureInAppBrowser() {
  if (globalThis.agent?.browsers == null) {
    const { setupBrowserRuntime } = await import(BROWSER_CLIENT_PATH);
    globalThis.agent = await setupBrowserRuntime();
  }
  if (globalThis.iab == null) {
    globalThis.iab = await globalThis.agent.browsers.get("iab");
  }
  globalThis.browser = globalThis.iab;
  return globalThis.iab;
}

export function getKStageV2OpenToken(url) {
  const parsed = new URL(url);
  const token = parsed.searchParams.get("open_token");
  if (!token) throw new Error("KStage v2 URL is missing open_token.");
  return token;
}

export function isKStageV2Url(url) {
  return String(url || "").includes("/pixel-beads-editor-v2/") ||
    String(url || "").includes("/pixel-beads-editor/?open_token=");
}

export async function postKStageV2(endpoint, body, options = {}) {
  const { baseUrl = "https://kstage.kiwifun.games/pixel-beads-editor-v2" } = options;
  const response = await fetch(`${baseUrl.replace(/\/+$/, "")}/api/v2/${String(endpoint).replace(/^\/+/, "")}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`KStage v2 ${endpoint} failed: HTTP ${response.status} ${text}`);
  }
  return await response.json();
}

export async function bootstrapKStageV2(url, options = {}) {
  const openToken = getKStageV2OpenToken(url);
  return await postKStageV2("bootstrap", { openToken }, options);
}

export function kstageV2Envelope(bootOrState, state, operation = {}) {
  const contextToken = bootOrState.contextToken;
  if (!contextToken) throw new Error("KStage v2 contextToken is missing; bootstrap first.");
  if (!state?.revision && state?.revision !== 0) throw new Error("KStage v2 state revision is missing.");
  return {
    contextToken,
    requestId: crypto.randomUUID(),
    expectedRevision: state.revision,
    state,
    operation: {
      ...operation,
      occurredAt: operation.occurredAt || new Date().toISOString(),
    },
  };
}

export async function startPreFillKStageV2(boot, options = {}) {
  const envelope = kstageV2Envelope(boot, boot.state, {});
  const output = await postKStageV2("prefill/start", envelope, options);
  return { ...output, contextToken: boot.contextToken };
}

export async function commitPreFillKStageV2(boot, state, fullBoard, options = {}) {
  const envelope = kstageV2Envelope(boot, state, { fullBoard });
  return await postKStageV2("prefill/commit", envelope, options);
}

export async function skipScatterKStageV2(boot, state, options = {}) {
  const envelope = kstageV2Envelope(boot, state, {});
  return await postKStageV2("scatter/skip", envelope, options);
}

export async function applyPreFillBoardKStageV2(url, boardData, options = {}) {
  const boot = await bootstrapKStageV2(url, options);
  const started = await startPreFillKStageV2(boot, options);
  const initial = boardData.initial || boardData.initialBoard;
  if (!initial) throw new Error("boardData must contain initial or initialBoard.");
  const committed = await commitPreFillKStageV2(boot, started.state, initial, options);
  return { boot, started, committed };
}

export async function openKStageEditor(url, options = {}) {
  const { newTab = true, waitMs = 2500, requireVisible = true } = options;
  const browser = await ensureInAppBrowser();
  let tab = await findSingleExistingKStageEditorTab(browser, url);

  if (!tab) {
    if (newTab) {
      tab = await browser.tabs.new();
    } else {
      const openTabs = await browser.user.openTabs();
      const editor = openTabs.find(
        (item) =>
          (item.url || "").includes("/products/1/pixel/pre-levels/") &&
          (item.url || "").includes("/editor/")
      );
      tab = editor ? await browser.user.claimTab(editor.id) : await browser.tabs.new();
    }
  }

  await dismissJsDialog(tab, "dismiss").catch(() => {});
  const currentUrl = await tab.playwright.evaluate(() => location.href).catch(() => "");
  if (currentUrl !== url) {
    await tab.goto(url);
  }
  await tab.playwright.waitForLoadState("domcontentloaded");
  await tab.playwright.waitForTimeout(waitMs);
  if (requireVisible) await assertUserVisibleKStageTab(browser, tab, url);
  return { browser, tab, page: tab.playwright, state: await readEditorState(tab) };
}

export async function findSingleExistingKStageEditorTab(browser, url) {
  const matches = (item) => (item.url || "") === url;

  const openTabs = await browser.user.openTabs().catch(() => []);
  const visibleMatches = openTabs.filter(matches);
  if (visibleMatches.length > 1) {
    throw new Error(
      `Multiple visible KStage editor tabs are already open for ${url}. ` +
        "Close the duplicate tabs before automated painting to avoid edit-lock/state conflicts."
    );
  }
  if (visibleMatches.length === 1) {
    return await browser.user.claimTab(visibleMatches[0].id);
  }

  const controlledTabs = await browser.tabs.list().catch(() => []);
  const controlledMatches = controlledTabs.filter(matches);
  if (controlledMatches.length > 1) {
    throw new Error(
      `Multiple controlled KStage editor tabs are already open for ${url}. ` +
        "Refusing to create or choose another editor instance."
    );
  }
  if (controlledMatches.length === 1) {
    return await browser.tabs.get(controlledMatches[0].id);
  }

  return null;
}

export async function openKStageEditorInNewVisibleTab(url, options = {}) {
  return await openKStageEditor(url, { newTab: true, requireVisible: true, ...options });
}

export async function openKStageEditorBackground(url, options = {}) {
  const {
    waitMs = 2500,
    hideBrowser = true,
  } = options;
  const browser = await ensureInAppBrowser();
  if (hideBrowser) {
    await (await browser.capabilities.get("visibility")).set(false).catch(() => {});
  }
  let tab = await findSingleExistingKStageEditorTab(browser, url);
  if (!tab) tab = await browser.tabs.new();
  await dismissJsDialog(tab, "dismiss").catch(() => {});
  const currentUrl = await tab.playwright.evaluate(() => location.href).catch(() => "");
  if (currentUrl !== url) {
    await tab.goto(url);
  }
  await tab.playwright.waitForLoadState("domcontentloaded");
  await tab.playwright.waitForTimeout(waitMs);
  return { browser, tab, page: tab.playwright, state: await readEditorState(tab) };
}

export async function assertUserVisibleKStageTab(browser, tab, url) {
  const visibleTabs = await browser.user.openTabs();
  const state = await readEditorState(tab).catch(() => null);
  const visible = visibleTabs.find((item) => item.url === url);
  if (!visible) {
    throw new Error(
      `KStage tab ${url} is not in the user's visible in-app browser tabs. ` +
        "Refusing to continue on a hidden or external control tab."
    );
  }
  if (state?.url !== url) {
    throw new Error(`KStage visible tab URL mismatch: expected ${url}, got ${state?.url || "unknown"}`);
  }
  return { visible, state };
}

export async function claimVisibleKStageEditor(url, options = {}) {
  const { exact = true } = options;
  const browser = await ensureInAppBrowser();
  const matchesUrl = (item) => {
    const current = item.url || "";
    if (exact) return current === url;
    return current.includes("/products/1/pixel/pre-levels/") && current.includes("/editor/");
  };

  const visibleTabs = await browser.user.openTabs();
  const visible = visibleTabs.find(matchesUrl);
  if (visible) {
    return { browser, tab: await browser.user.claimTab(visible), source: "visible" };
  }

  const controlledTabs = await browser.tabs.list().catch(() => []);
  const controlled = controlledTabs.find(matchesUrl);
  if (controlled) {
    return { browser, tab: await browser.tabs.get(controlled.id), source: "controlled" };
  }

  throw new Error(
    `No existing KStage editor tab found for ${url}. Refusing to open a new page during restore.`
  );
}

export async function restoreKStageBoardFromSavedPlan(url, boardPathOrData, options = {}) {
  const {
    reload = true,
    waitMs = 2000,
    paintOptions = {},
    markDeliverable = true,
  } = options;
  const { tab, source } = await claimVisibleKStageEditor(url, { exact: true });

  await dismissJsDialog(tab, "dismiss").catch(() => {});
  if (reload) {
    await tab.reload();
    await tab.playwright.waitForLoadState({ state: "domcontentloaded", timeoutMs: 15000 }).catch(() => {});
    await tab.playwright.waitForTimeout(waitMs);
  }

  const state = await readEditorState(tab);
  if (state.url !== url) {
    throw new Error(`Restore tab URL mismatch: expected ${url}, got ${state.url}`);
  }
  if (!state.hasPreview || !state.hasStart) {
    throw new Error("KStage editor is not in a clean target-preview state after reload.");
  }

  let boardData = boardPathOrData;
  if (typeof boardPathOrData === "string") {
    const fs = await import("fs");
    boardData = JSON.parse(fs.readFileSync(boardPathOrData, "utf8"));
  }

  const painted = await paintInitialBoard(tab, boardData, {
    pauseMs: 70,
    afterColorPauseMs: 250,
    acceptCompletionDialog: true,
    ...paintOptions,
  });
  const verification = await verifyRowsComplete(tab);
  if (markDeliverable) await tab.markDeliverable().catch(() => {});
  return { tab, source, state: painted, verification };
}

export async function readEditorState(tab) {
  return await tab.playwright.evaluate(() => {
    const text = document.body.innerText || "";
    const fragmentMatch = text.match(/当前编辑：分片\s+(\d+)\/(\d+)（(\d+)×(\d+)）/);
    const buttons = Array.from(document.querySelectorAll("button")).map((button, index) => ({
      index,
      text: button.textContent.trim(),
      visible: Boolean(button.offsetWidth || button.offsetHeight || button.getClientRects().length),
      disabled: button.disabled,
    }));
    const rows = Array.from(document.querySelectorAll("#placementRows .pre-fill-placement-row")).map(
      (row, index) => ({
        index,
        id: Number(row.getAttribute("data-color-id")),
        text: row.innerText.trim().replace(/\s+/g, " "),
        total: Number((row.querySelector(".count-total")?.textContent || "").match(/\d+/)?.[0] || 0),
        used: Number((row.querySelector(".count-used")?.textContent || "").match(/\d+/)?.[0] || 0),
        remaining: Number((row.querySelector(".count-remain")?.textContent || "").match(/\d+/)?.[0] || 0),
      })
    );
    const canvas = document.querySelector("#tuneCanvas");
    const rect = canvas?.getBoundingClientRect();
    return {
      url: location.href,
      title: document.title,
      hasPreview: Boolean(document.querySelector("#completePreviewImg")),
      hasStart: buttons.some((button) => button.visible && button.text.includes("开始预填充")),
      inPreFill: text.includes("颜色放置区（预填充）"),
      hasExportModal: text.includes("确认导出"),
      hasDone: text.includes("已完成确认") || text.includes("打散完成"),
      rows,
      buttons,
      canvas: rect
        ? {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            bitmapWidth: canvas.width,
            bitmapHeight: canvas.height,
            visible: Boolean(rect.width && rect.height),
          }
        : null,
      fragment: fragmentMatch
        ? {
            index: Number(fragmentMatch[1]),
            total: Number(fragmentMatch[2]),
            width: Number(fragmentMatch[3]),
            height: Number(fragmentMatch[4]),
          }
        : null,
      text: text.slice(0, 2500),
    };
  });
}

export async function enterPreFill(tab) {
  const page = tab.playwright;
  let state = await readEditorState(tab);
  if (!state.inPreFill) {
    if (!state.hasStart) {
      throw new Error("KStage editor is not ready: visible 开始预填充 button not found.");
    }
    await page.locator("button").filter({ hasText: "开始预填充" }).first().click();
    await page.waitForTimeout(1500);
  }

  const singleCellButton = page.locator("button").filter({ hasText: "单格模式" }).first();
  if (await singleCellButton.count()) {
    await singleCellButton.click().catch(() => {});
    await page.waitForTimeout(250);
  }

  state = await readEditorState(tab);
  if (!state.inPreFill || !state.canvas?.visible || state.rows.length === 0) {
    throw new Error("KStage pre-fill did not initialize correctly.");
  }
  return state;
}

export async function prepareStableKStagePainting(tab, boardData, options = {}) {
  const {
    minCanvasWidth = 560,
    stableDelta = 1,
    waitMs = 250,
  } = options;
  const state = await enterPreFill(tab);
  const initial = boardData.initial || boardData.initialBoard;
  const width = boardData.width || initial?.[0]?.length;
  const height = boardData.height || initial?.length;
  if (!initial || !width || !height) {
    throw new Error("boardData must contain width, height, and initial/initialBoard.");
  }
  if (state.fragment && (state.fragment.width !== width || state.fragment.height !== height)) {
    throw new Error(
      `Board size ${width}x${height} does not match current KStage fragment ` +
        `${state.fragment.index}/${state.fragment.total} size ${state.fragment.width}x${state.fragment.height}.`
    );
  }
  await tab.playwright.evaluate(() => {
    const expand = Array.from(document.querySelectorAll("button")).find((button) =>
      (button.textContent || "").trim().includes("展开面板")
    );
    if (expand) {
      const rect = expand.getBoundingClientRect();
      if (rect.width && rect.height && rect.x >= 0 && rect.y >= 0) {
        // If the panel is already collapsed this button is usually the only visible handle.
        // Do not click it; just keep the canvas region as-is.
      }
    }
    document.querySelector("#tuneCanvas")?.scrollIntoView({ block: "center", inline: "center" });
  });
  await tab.playwright.waitForTimeout(waitMs);
  const first = await readEditorState(tab);
  await tab.playwright.waitForTimeout(waitMs);
  const second = await readEditorState(tab);
  const a = first.canvas;
  const b = second.canvas;
  if (!a?.visible || !b?.visible) throw new Error("KStage canvas is not visible.");
  const moved =
    Math.abs(a.x - b.x) > stableDelta ||
    Math.abs(a.y - b.y) > stableDelta ||
    Math.abs(a.width - b.width) > stableDelta ||
    Math.abs(a.height - b.height) > stableDelta;
  if (moved) throw new Error("KStage canvas rectangle is not stable; stop before painting.");
  if (b.width < minCanvasWidth || b.height < minCanvasWidth) {
    throw new Error(`KStage canvas is too small for reliable painting: ${b.width}x${b.height}.`);
  }
  return second;
}

export async function saveCompletePreview(tab, outputPath) {
  const src = await tab.playwright.evaluate(() =>
    document.querySelector("#completePreviewImg")?.getAttribute("src")
  );
  if (!src?.startsWith("data:image/")) {
    throw new Error("complete preview data URL not found.");
  }
  const base64 = src.split(",", 2)[1];
  const fs = await import("fs");
  fs.writeFileSync(outputPath, Buffer.from(base64, "base64"));
  return outputPath;
}

export async function screenshotTuneCanvas(tab, outputPath) {
  const bytes = await tab.screenshot();
  const fs = await import("fs");
  fs.writeFileSync(outputPath, Buffer.from(bytes));
  return outputPath;
}

export async function saveTuneCanvasImage(tab, outputPath) {
  const src = await tab.playwright.evaluate(() => {
    const canvas = document.querySelector("#tuneCanvas");
    if (!canvas || typeof canvas.toDataURL !== "function") return null;
    return canvas.toDataURL("image/png");
  });
  if (src?.startsWith("data:image/png;base64,")) {
    const fs = await import("fs");
    fs.writeFileSync(outputPath, Buffer.from(src.split(",", 2)[1], "base64"));
    return outputPath;
  }
  return await screenshotTuneCanvas(tab, outputPath);
}

export async function saveTuneCanvasPng(tab, outputPath) {
  return await saveTuneCanvasImage(tab, outputPath);
}

export async function verifyRowsComplete(tab) {
  const state = await readEditorState(tab);
  return {
    complete: state.rows.length > 0 && state.rows.every((row) => row.remaining === 0 && row.used === row.total),
    rows: state.rows,
    hasDone: state.hasDone,
    hasExportModal: state.hasExportModal,
  };
}

export function buildHorizontalRuns(initialBoard) {
  const runsByColor = {};
  const height = initialBoard.length;
  const width = initialBoard[0]?.length || 0;
  for (let y = 0; y < height; y += 1) {
    let x = 0;
    while (x < width) {
      const colorId = initialBoard[y][x];
      if (!colorId) {
        x += 1;
        continue;
      }
      let x2 = x;
      while (x2 + 1 < width && initialBoard[y][x2 + 1] === colorId) x2 += 1;
      (runsByColor[colorId] ||= []).push({ y, x1: x, x2 });
      x = x2 + 1;
    }
  }
  return runsByColor;
}

export async function paintInitialBoard(tab, boardData, options = {}) {
  const {
    order = null,
    pauseMs = 80,
    afterColorPauseMs = 120,
    acceptCompletionDialog = true,
  } = options;
  const page = tab.playwright;
  const state = await enterPreFill(tab);
  const initial = boardData.initial || boardData.initialBoard;
  const width = boardData.width || initial?.[0]?.length;
  const height = boardData.height || initial?.length;
  if (!initial || !width || !height) {
    throw new Error("boardData must contain width, height, and initial/initialBoard.");
  }
  if (state.fragment && (state.fragment.width !== width || state.fragment.height !== height)) {
    throw new Error(
      `Board size ${width}x${height} does not match current KStage fragment ` +
        `${state.fragment.index}/${state.fragment.total} size ${state.fragment.width}x${state.fragment.height}. ` +
        "Generate and paint a per-fragment board instead of a full-board plan."
    );
  }

  const runsByColor = buildHorizontalRuns(initial);
  const paintOrder = order || state.rows.map((row) => row.id).filter((id) => runsByColor[id]?.length);

  for (const colorId of paintOrder) {
    if (!runsByColor[colorId]?.length) continue;
    const current = await readEditorState(tab);
    const row = current.rows.find((item) => item.id === Number(colorId));
    if (!row || row.remaining === 0) continue;

    await page.evaluate((id) => {
      const button = document.querySelector(`button.pre-fill-btn[data-prefill-cid="${id}"]`);
      if (button) button.scrollIntoView({ block: "center", inline: "nearest" });
    }, colorId);
    await page.waitForTimeout(80);
    await page.locator(`button.pre-fill-btn[data-prefill-cid="${colorId}"]`).click();
    await page.waitForTimeout(pauseMs);

    const rect = await page.evaluate(() => {
      const r = document.querySelector("#tuneCanvas").getBoundingClientRect();
      return { x: r.x, y: r.y, width: r.width, height: r.height };
    });
    const cellW = rect.width / width;
    const cellH = rect.height / height;
    const point = (x, y) => ({
      x: rect.x + (x + 0.5) * cellW,
      y: rect.y + (y + 0.5) * cellH,
    });

    for (const run of runsByColor[colorId]) {
      const path = [];
      for (let x = run.x1; x <= run.x2; x += 1) path.push(point(x, run.y));
      if (path.length === 1) await tab.cua.click(path[0]);
      else await tab.cua.drag({ path });
    }
    await page.waitForTimeout(afterColorPauseMs);
  }

  try {
    return await readEditorState(tab);
  } catch (error) {
    if (!String(error?.message || error).includes("dialog")) throw error;
    if (!acceptCompletionDialog) throw error;
    await dismissJsDialog(tab, "accept");
    await page.waitForTimeout(1200);
    return await readEditorState(tab);
  }
}

export async function paintInitialBoardSingleCell(tab, boardData, options = {}) {
  const {
    order = null,
    pauseMs = 12,
    afterColorPauseMs = 120,
    batchVerify = true,
    minCanvasWidth = 560,
  } = options;
  const page = tab.playwright;
  const state = await prepareStableKStagePainting(tab, boardData, { minCanvasWidth });
  const initial = boardData.initial || boardData.initialBoard;
  const width = boardData.width || initial?.[0]?.length;
  const height = boardData.height || initial?.length;
  const cellsByColor = {};
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const colorId = initial[y][x];
      if (!colorId) continue;
      (cellsByColor[colorId] ||= []).push({ x, y });
    }
  }
  const paintOrder = order || state.rows.map((row) => row.id).filter((id) => cellsByColor[id]?.length);

  for (const colorId of paintOrder) {
    const planned = cellsByColor[colorId] || [];
    if (!planned.length) continue;
    const before = await readEditorState(tab);
    const rowBefore = before.rows.find((item) => item.id === Number(colorId));
    if (!rowBefore || rowBefore.remaining === 0) continue;

    await page.evaluate((id) => {
      const button = document.querySelector(`button.pre-fill-btn[data-prefill-cid="${id}"]`);
      if (!button) throw new Error(`Missing pre-fill button for color ${id}`);
      button.scrollIntoView({ block: "center", inline: "nearest" });
    }, colorId);
    await page.waitForTimeout(60);
    await page.locator(`button.pre-fill-btn[data-prefill-cid="${colorId}"]`).click({ force: true });
    await page.waitForTimeout(pauseMs);

    for (const cell of planned) {
      // Placement-panel scrolling can move the full page after a row selection.
      // Re-read the canvas rectangle for every click so a stale page offset can
      // never spill a bead into an adjacent control or outside the board.
      const rect = await page.evaluate(() => {
        const canvas = document.querySelector("#tuneCanvas");
        canvas.scrollIntoView({ block: "center", inline: "center" });
        const r = canvas.getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width, height: r.height };
      });
      const cellW = rect.width / width;
      const cellH = rect.height / height;
      const point = {
        x: rect.x + (cell.x + 0.5) * cellW,
        y: rect.y + (cell.y + 0.5) * cellH,
      };
      if (
        point.x <= rect.x ||
        point.y <= rect.y ||
        point.x >= rect.x + rect.width ||
        point.y >= rect.y + rect.height
      ) {
        throw new Error(`Planned click is outside the canvas for color ${colorId}: ${JSON.stringify(point)}`);
      }
      await tab.cua.click(point);
    }
    await page.waitForTimeout(afterColorPauseMs);

    if (batchVerify) {
      const after = await readEditorState(tab);
      const rowAfter = after.rows.find((item) => item.id === Number(colorId));
      const expectedUsed = Math.min(rowBefore.used + planned.length, rowBefore.total);
      if (!rowAfter || rowAfter.used < expectedUsed) {
        throw new Error(
          `KStage single-cell paint did not advance color ${colorId} as expected: ` +
            `before ${rowBefore.used}, after ${rowAfter?.used}, planned ${planned.length}.`
        );
      }
    }
  }
  return await readEditorState(tab);
}

export async function finishPreFill(tab, options = {}) {
  const { acceptCompletionDialog = true, waitMs = 3500 } = options;
  const page = tab.playwright;
  let state = await readEditorState(tab);
  if (state.rows.some((row) => row.remaining !== 0)) return state;

  const finishButton = page.locator("button").filter({ hasText: "完成填充" }).first();
  if (await finishButton.count()) await finishButton.click().catch(() => {});
  await page.waitForTimeout(waitMs);

  if (acceptCompletionDialog) {
    await dismissJsDialog(tab, "accept").catch(() => {});
    await page.waitForTimeout(1200);
  }
  return await readEditorState(tab);
}

export async function dismissJsDialog(tab, action = "accept") {
  const dialog = await tab.getJsDialog();
  if (!dialog) return null;
  const message = dialog.message;
  if (action === "dismiss") await dialog.dismiss();
  else await dialog.accept();
  return message;
}
