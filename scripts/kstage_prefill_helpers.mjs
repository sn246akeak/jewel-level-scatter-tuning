/** Pure plan/compiler helpers. UI execution lives in kstage_executor.mjs. */
import { createHash, randomUUID } from 'node:crypto';

export function fail(code, message) {
  const error = new Error(`${code}: ${message}`);
  error.code = code;
  throw error;
}
export const sha256 = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
export const counts = board => {
  const result = {};
  for (const row of board) for (const id of row) if (id > 0) result[id] = (result[id] || 0) + 1;
  return result;
};
export function assertCounts(actual, expected, code = 'E_INVENTORY') {
  const ids = [...new Set([...Object.keys(actual), ...Object.keys(expected)])];
  if (ids.some(id => actual[id] !== expected[id])) fail(code, 'Color totals differ');
}
export function getKStageV2OpenToken(url) {
  const token = new URL(url).searchParams.get('open_token');
  if (!token) fail('E_SOURCE', 'KStage URL has no open_token');
  return token;
}
export async function postKStageV2(endpoint, body, options = {}) {
  const base = options.baseUrl || 'https://kstage.kiwifun.games/pixel-beads-editor-v2';
  const response = await fetch(`${base.replace(/\/+$/, '')}/api/v2/${endpoint}`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  });
  const result = await response.json().catch(()=>null);
  if (!response.ok || !result || result.ok === false) {
    let detail=`KStage ${endpoint}: HTTP ${response.status} ${result?.code||'request_failed'}: ${result?.error||'Invalid response'}`;
    for (const secret of [body.openToken,body.contextToken]) if(secret) detail=detail.replaceAll(secret,'<redacted>');
    fail('E_API', detail);
  }
  return result;
}
export async function bootstrapKStageV2(url) {
  const parsed = new URL(url);
  return postKStageV2('bootstrap', {openToken: getKStageV2OpenToken(url)},
    {baseUrl: `${parsed.origin}${parsed.pathname.replace(/\/+$/, '')}`});
}
export async function startPreFillKStageV2(boot, options = {}) {
  return postKStageV2('prefill/start', {contextToken: boot.contextToken, requestId: randomUUID(),
    expectedRevision: boot.state.revision, state: boot.state, operation: {occurredAt:new Date().toISOString()}}, options);
}

export function validateBoard(board) {
  const base = board.completeBoard;
  const initial = board.initialBoard;
  const height = base?.length, width = base?.[0]?.length;
  if (!height || !width || !Array.isArray(initial) || initial.length !== height ||
      base.some(row => row.length !== width) || initial.some(row => row.length !== width)) {
    fail('E_BOARD_SHAPE', 'Board matrices must be matching rectangles');
  }
  if ((board.initial && !same(board.initial, initial)) || (board.base && !same(board.base, base))) {
    fail('E_ARTIFACT', 'Board aliases disagree');
  }
  const palette = new Set(board.colors.map(color => color.id));
  if (palette.size !== board.colors.length) fail('E_PALETTE', 'Duplicate color IDs');
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const source = base[y][x], target = initial[y][x];
    if (source === -1 ? target !== -1 : (!Number.isInteger(source) || !Number.isInteger(target) ||
        !palette.has(source) || !palette.has(target) || target <= 0 || target === source)) {
      fail('E_BOARD_CELL', `Illegal cell (${x},${y})`);
    }
  }
  assertCounts(counts(initial), counts(base));
  if (board.candidate_sha256 !== sha256(initial)) fail('E_ARTIFACT', 'Candidate hash mismatch');
  return {width, height, totals: counts(base)};
}

export function validateSourceBlocks(board, sourceBlocks) {
  const {width, height} = validateBoard(board);
  if (!Array.isArray(sourceBlocks) || !sourceBlocks.length) {
    fail('E_BLOCKS_MISSING', 'Real prefill/start blocks are required; there is no inferred fallback');
  }
  const covered = new Set(), ids = new Set();
  for (const block of sourceBlocks) {
    if (!Number.isInteger(block.blockId) || ids.has(block.blockId) ||
        !Number.isInteger(block.colorId) || !Array.isArray(block.pixels) ||
        !block.pixels.length || block.pixelCount !== block.pixels.length) {
      fail('E_BLOCK_SCHEMA', 'Invalid ID, duplicate ID, pixels, or pixelCount');
    }
    ids.add(block.blockId);
    for (const p of block.pixels) {
      const key = `${p.r},${p.c}`;
      if (!Number.isInteger(p.r) || !Number.isInteger(p.c) || p.r < 0 || p.c < 0 ||
          p.r >= height || p.c >= width || board.completeBoard[p.r][p.c] !== block.colorId ||
          block.colorId <= 0 || covered.has(key)) fail('E_BLOCK_COVERAGE', 'Wrong, overlapping, or transparent block cell');
      covered.add(key);
    }
  }
  const total = Object.values(counts(board.completeBoard)).reduce((a,b) => a+b, 0);
  if (covered.size !== total) fail('E_BLOCK_COVERAGE', 'Blocks do not cover every source art cell exactly once');
}

export function buildHybridPaintPlan(board, {sourceBlocks, minBlockFillCells = 3} = {}) {
  validateSourceBlocks(board, sourceBlocks);
  if (!Number.isInteger(minBlockFillCells) || minBlockFillCells < 1) fail('E_PLAN', 'Invalid fill threshold');
  const singleCellsByColor = {}, fillOps = [];
  const add = (id, p) => (singleCellsByColor[id] ||= []).push({x:p.c, y:p.r});
  for (const block of sourceBlocks) {
    const groups = new Map();
    for (const p of block.pixels) {
      const id = board.initialBoard[p.r][p.c];
      if (!groups.has(id)) groups.set(id, []);
      groups.get(id).push(p);
    }
    const [id, cells] = [...groups].sort((a,b) => b[1].length-a[1].length || a[0]-b[0])[0];
    if (cells.length >= minBlockFillCells) {
      fillOps.push({blockId: block.blockId, sourceColorId:block.colorId, total:block.pixelCount,
        targetColorId:id, count:cells.length, anchor:{x:cells[0].c,y:cells[0].r}});
      for (const [other, points] of groups) if (other !== id) for (const p of points) add(other,p);
    } else for (const [other, points] of groups) for (const p of points) add(other,p);
  }
  const geometry = validateBoard(board);
  // Always end in a block operation; cell-mode mouseup may open a blocking completion dialog.
  if (!fillOps.length && minBlockFillCells > 1) return buildHybridPaintPlan(board,{sourceBlocks,minBlockFillCells:1});
  const plan = {schema:'kstage-execution-plan-v2', candidate_sha256:board.candidate_sha256,
    source_revision:board.source_revision, blocks_sha256:sha256(sourceBlocks), ...geometry,
    totalCells:Object.values(geometry.totals).reduce((a,b)=>a+b,0), singleCellsByColor, fillOps,
    singleCellCount:Object.values(singleCellsByColor).reduce((sum,cells)=>sum+cells.length,0),
    blockFillCellCount:fillOps.reduce((sum,op)=>sum+op.count,0)};
  simulatePlan(board, sourceBlocks, plan);
  return plan;
}

export function simulatePlan(board, blocks, plan) {
  const result = board.completeBoard.map(row => row.map(() => -1));
  const remaining = {...counts(board.completeBoard)};
  const put = (x,y,id) => {
    if (result[y]?.[x] !== -1 || board.completeBoard[y]?.[x] <= 0 ||
        id !== board.initialBoard[y][x] || !(remaining[id] > 0)) fail('E_SIMULATION','Invalid or duplicate planned placement');
    result[y][x] = id; remaining[id]--;
  };
  for (const [id,cells] of Object.entries(plan.singleCellsByColor)) for (const p of cells) put(p.x,p.y,Number(id));
  for (const op of plan.fillOps) {
    const block = blocks.find(b => b.blockId === op.blockId);
    if (!block) fail('E_SIMULATION','Unknown planned block');
    const empty = block.pixels.filter(p=>result[p.r][p.c]===-1);
    if (empty.length !== op.count || empty.length > remaining[op.targetColorId]) fail('E_SIMULATION','Fill condition failed');
    for (const p of empty) put(p.c,p.r,op.targetColorId);
  }
  if (!same(result,board.initialBoard) || Object.values(remaining).some(n=>n)) fail('E_SIMULATION','Final board mismatch');
  return result;
}

export function verifySelectedBlock(selected, operation, colors, unfilled = operation.count) {
  const hex = colors.find(c=>c.id===operation.sourceColorId)?.hex;
  if (!selected || selected.blockId !== operation.blockId || selected.total !== operation.total ||
      selected.unfilled !== unfilled || selected.hex?.toUpperCase() !== hex?.toUpperCase()) {
    fail('E_SELECTED_BLOCK', 'Selected block ID, source color, total, or unfilled count differs; no color clicked');
  }
}

export function createPreFillPlanKStageV2(boot, board) {
  validateBoard(board);
  if (boot.state.source.sourceSha256 !== board.source_revision ||
      !same(boot.state.source.completeBoard,board.completeBoard)) fail('E_SOURCE','Source differs');
  return {schema:'kstage-prefill-plan',version:1,identity:boot.state.identity,
    sourceSha256:board.source_revision,fullBoard:board.initialBoard};
}

// Fail closed for callers of the retired unguarded entrypoints.
export async function paintInitialBoardHybrid() { fail('E_ENTRYPOINT','Use startExecution(tab, {runDir, listTabs}) from kstage_executor.mjs'); }
export const paintInitialBoard = paintInitialBoardHybrid;
export const paintInitialBoardSingleCell = paintInitialBoardHybrid;
export const restoreKStageBoardFromSavedPlan = paintInitialBoardHybrid;
