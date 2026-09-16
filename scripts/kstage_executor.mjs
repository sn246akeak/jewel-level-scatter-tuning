/** Bounded, fail-closed UI execution. Invoke through cua_repl with the selected user tab. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {createHash} from 'node:crypto';
import {fail, same, counts, assertCounts, validateBoard, buildHybridPaintPlan,
  verifySelectedBlock, bootstrapKStageV2} from './kstage_prefill_helpers.mjs';
const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const readJSON = file => JSON.parse(fs.readFileSync(file,'utf8'));
const fileHash = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const writeJSON = (file,data) => fs.writeFileSync(file,JSON.stringify(data,null,2)+'\n');

export function loadAcceptedRun(runDir) {
  const certificate = readJSON(path.join(ROOT,'.runtime-validation.json'));
  const manifest = readJSON(path.join(runDir,'run_manifest.json'));
  const allowed = new Set(['design_spec.json','visual_review.json','run_manifest.json',
    ...Object.keys(manifest.generated_hashes||{}),'editor_execution_plan.json','editor_execution_report.json','editor_preview.png','.DS_Store']);
  if(fs.readdirSync(runDir).some(name=>!allowed.has(name)))fail('E_RUN_FILES','Unexpected per-level file');
  if (certificate.status !== 'passed' || !same(certificate.tool_hashes,manifest.tool_hashes)) fail('E_HELPER_CHANGED','Runtime was not tested for this run');
  for (const [name,hash] of Object.entries(manifest.tool_hashes)) if (fileHash(path.join(ROOT,name)) !== hash) fail('E_HELPER_CHANGED',name);
  for (const [name,hash] of Object.entries({...manifest.generated_hashes,...manifest.input_hashes})) {
    if (fileHash(path.join(runDir,name)) !== hash) fail('E_ARTIFACT_CHANGED',name);
  }
  const board = readJSON(path.join(runDir,'initial_board.json'));
  const report = readJSON(path.join(runDir,'validation_report.json'));
  const source = readJSON(path.join(runDir,'kstage_blocks.json'));
  validateBoard(board);
  if (!manifest.accepted || manifest.phase !== 'accepted' || report.accepted !== true ||
      report.candidate_sha256 !== board.candidate_sha256 || manifest.candidate_sha256 !== board.candidate_sha256 ||
      source.source_revision !== board.source_revision || !same(source.completeBoard,board.completeBoard) ||
      !same(source.identity,manifest.identity)) fail('E_NOT_ACCEPTED','Artifacts are not accepted for this source and candidate');
  return {board,source,manifest};
}

function assertRows(rows, totals, used) {
  if (!Array.isArray(rows) || rows.length !== Object.keys(totals).length || new Set(rows.map(r=>r.id)).size !== rows.length) fail('E_INVENTORY','Missing or duplicate palette row');
  for (const row of rows) if (row.total !== totals[row.id] || row.used !== (used[row.id]||0) ||
      row.remaining !== row.total-row.used) fail('E_INVENTORY',`Unexpected state for color ${row.id}`);
}
function statusGate(state) {
  if (/另一个标签页|another tab/i.test(state.status||'')) fail('E_EDIT_LOCK','The draft is locked by another tab');
  if (/错误[:：]|error[:：]/i.test(state.status||'')) fail('E_EDITOR',state.status);
  if (state.fragment) fail('E_FRAGMENT','This executor requires an unsliced source');
}

/** A session can advance in bounded batches. Any error makes it terminal: no reset, reload, or resume. */
export async function createExecutionSession({board, sourceBlocks, port, persist = ()=>{}, verifyFiles = ()=>{}}) {
  board=structuredClone(board); sourceBlocks=structuredClone(sourceBlocks);
  const plan = buildHybridPaintPlan(board,{sourceBlocks});
  const used = Object.fromEntries(Object.keys(plan.totals).map(id=>[id,0]));
  const log = {schema:'kstage-execution-report-v2',candidate_sha256:board.candidate_sha256,
    source_revision:board.source_revision,status:'preflight',events:[],saved:false,
    started_at:new Date().toISOString(),current_action:null,
    pixel_comparison:'not_run',restore_test:'not_run'};
  let cursor = 0, busy = false;
  const ops = [];
  for (const block of sourceBlocks) ops.push({type:'probe',blockId:block.blockId,sourceColorId:block.colorId,
    total:block.pixelCount,count:block.pixelCount,anchor:{x:block.pixels[0].c,y:block.pixels[0].r}});
  for (const [id,cells] of Object.entries(plan.singleCellsByColor)) for (const cell of cells) ops.push({type:'cell',id:Number(id),cell});
  for (const op of plan.fillOps) ops.push({type:'fill',...op});
  function record() {
    log.updated_at=new Date().toISOString();
    persist(structuredClone(log));
  }
  function failed(error) {
    log.status='failed'; log.error={code:error.code||'E_UI',message:String(error.message||error)};
    record(); throw error;
  }
  async function observe() { const state=await port.read(); statusGate(state); return state; }
  try {
    verifyFiles();
    await port.assertContext();
    const before=await port.read();
    // A lock is actionable; stale unrelated status text is not used to authorize any action.
    if (/另一个标签页/.test(before.status||'')) fail('E_EDIT_LOCK','The draft is locked by another tab');
    if (before.fragment) fail('E_FRAGMENT','Unsliced source required');
    if (before.inPreFill) assertRows(before.rows,plan.totals,used);
    else {
      if (!before.hasStart) fail('E_CAPABILITY','Fresh source preview required');
      await port.start();
    }
    const ready=await observe();
    if (!ready.inPreFill) fail('E_CAPABILITY','Pre-fill initialization did not produce visible controls');
    assertRows(ready.rows,plan.totals,used);
    await port.fit(plan);
    record();
  } catch(error) { failed(error); }
  return {
    plan:structuredClone(plan),
    snapshot() {return {status:log.status,completed:cursor,total:ops.length,used:{...used},
      singleCellCount:plan.singleCellCount,blockFillOps:plan.fillOps.length};},
    async advance({maxActions=20}={}) {
      if (busy || log.status==='failed') fail('E_TERMINAL','Session is busy or failed; no retry is allowed');
      if (log.status==='awaiting_visual_review' || log.status==='saved') return {status:log.status};
      if (!Number.isInteger(maxActions) || maxActions < 1 || maxActions > 30) fail('E_BATCH','Use 1–30 actions');
      busy=true;
      try {
        verifyFiles(); await port.assertContext();
        const deadline=Date.now()+20000;
        for (let n=0;cursor<ops.length && n<maxActions && Date.now()<deadline;n++,cursor++) {
          const op=ops[cursor];
          const startedAt=Date.now();
          log.current_action={index:cursor,type:op.type,blockId:op.blockId,
            colorId:op.id||op.targetColorId,cell:op.cell,started_at:new Date(startedAt).toISOString()};
          record(); // Preserve the attempted operation even if its outcome is uncertain.
          const before=await observe(); assertRows(before.rows,plan.totals,used);
          if (op.type==='probe' || op.type==='fill') {
            await port.mode('block'); await port.select(op.anchor,plan);
            const selectedState=await observe();
            verifySelectedBlock(selectedState.selected,op,board.colors);
            if (op.type==='probe') {
              await port.mode('cell'); // deselect without writing any board cell
            } else {
              if (plan.totals[op.targetColorId]-used[op.targetColorId] < op.count) fail('E_INVENTORY','Not enough remaining for selected block');
              const completesBoard=Object.values(used).reduce((a,b)=>a+b,0)+op.count===plan.totalCells;
              await port.choose(op.targetColorId,{completesBoard});
              used[op.targetColorId]+=op.count;
            }
          } else {
            await port.mode('cell'); await port.choose(op.id); await port.paint(op.cell,plan);
            used[op.id]++;
          }
          const after=await observe(); assertRows(after.rows,plan.totals,used);
          log.events.push({...log.current_action,count:op.count||1,
            finished_at:new Date().toISOString(),elapsed_ms:Date.now()-startedAt});
          log.current_action=null;
          log.status=op.type==='probe'?'preflight':'painting';
          record();
        }
        if (cursor===ops.length) {
          assertCounts(used,plan.totals);
          await port.preview();
          log.status='awaiting_visual_review'; record();
        }
        return {status:log.status,completed:cursor,total:ops.length,used:{...used}};
      } catch(error) { return failed(error); } finally {busy=false;}
    },
    async finish({visualMatches=false}={}) {
      if (busy || log.status!=='awaiting_visual_review') fail('E_PHASE','Painting and editor review must precede finish');
      if (!visualMatches) return failed(Object.assign(new Error('Editor preview did not match accepted candidate'),{code:'E_VISUAL'}));
      busy=true;
      try {
        log.current_action={type:'finish',started_at:new Date().toISOString()};record();
        verifyFiles(); await port.assertContext();
        assertRows((await observe()).rows,plan.totals,used);
        await port.finish();
        log.editor_visual_review='pass'; log.status='saved'; log.saved=true;
        log.current_action=null;
        log.save_confirmation='已保存浏览器进度。'; record();
        return {status:'saved',singleCellCount:plan.singleCellCount,blockFillOps:plan.fillOps.length};
      } catch(error) {return failed(error);} finally {busy=false;}
    },
  };
}

/** All interactions use the existing CUA tab. evaluate reads visible DOM/geometry only. */
export function createBrowserPort(tab,{url,listTabs,runDir}) {
  let mode=null, brush=null, completed=false;
  const page=tab.playwright;
  const button=name=>page.getByRole('button',{name,exact:true});
  const port={
    async assertContext() {
      const tabs=await listTabs();
      const matches=tabs.filter(item=>item.url===url);
      if (matches.length!==1 || String(matches[0].id)!==String(tab.id)) fail('E_DUPLICATE_TAB','Use exactly one existing tab for this URL');
      if (await tab.url()!==url) fail('E_TAB_CHANGED','Selected tab navigated away');
    },
    async read() {
      return page.evaluate(()=>{
        const visible=e=>!!e && !!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
        const status=document.querySelector('#statusMsg')?.textContent?.trim()||'';
        const text=document.body.innerText;
        const match=status.match(/选中色块\s*#(\d+)（原色\s*(#[A-Fa-f0-9]{6})，总\s*(\d+)格，未填\s*(\d+)格）/);
        const canvas=document.querySelector('#tuneCanvas'); const r=canvas?.getBoundingClientRect();
        return {status,selected:match?{blockId:Number(match[1]),hex:match[2],total:Number(match[3]),unfilled:Number(match[4])}:null,
          inPreFill:visible(document.querySelector('#preFillModeBar')),
          hasStart:Array.from(document.querySelectorAll('button')).some(b=>visible(b)&&b.textContent.trim()==='开始预填充'),
          fragment:/当前编辑：分片/.test(text),
          rows:Array.from(document.querySelectorAll('#placementRows .pre-fill-placement-row')).map(row=>({
            id:Number(row.getAttribute('data-color-id')),
            total:Number(row.querySelector('.count-total')?.textContent.match(/\d+/)?.[0]),
            used:Number(row.querySelector('.count-used')?.textContent.match(/\d+/)?.[0]),
            remaining:Number(row.querySelector('.count-remain')?.textContent.match(/\d+/)?.[0])})),
          canvas:r?{x:r.x,y:r.y,width:r.width,height:r.height}:null,
          viewport:{width:innerWidth,height:innerHeight}};
      });
    },
    async start() {
      await button('开始预填充').click({timeoutMs:5000});
      for(let n=0;n<12;n++) {
        const state=await port.read(); statusGate(state);
        if(state.inPreFill) return;
        await page.waitForTimeout(250);
      }
      fail('E_CAPABILITY','Pre-fill start did not initialize');
    },
    async fit(plan) {
      const hide=page.getByLabel('隐藏完成状态',{exact:true});
      if(await hide.count()) await hide.setChecked(true,{timeoutMs:2000});
      for(let i=0;i<10;i++) {
        const s=await port.read(),r=s.canvas;
        if(!r?.width) fail('E_CANVAS','No visible canvas');
        if(r.width/plan.width<7 || r.height/plan.height<7) fail('E_CANVAS','Cells too small');
        if(r.x>=0&&r.y>=0&&r.x+r.width<=s.viewport.width&&r.y+r.height<=s.viewport.height) return;
        if(r.height>s.viewport.height-80 || r.width>s.viewport.width-80) {
          await page.locator('#zoomOutBtn').click({timeoutMs:2000});
        } else {
          await tab.scroll([Math.max(1,Math.min(s.viewport.width-1,r.x+r.width/2)),s.viewport.height/2],
            r.y<0?'up':'down',0.3);
        }
      }
      fail('E_CANVAS','Could not fit canvas using bounded layout adjustments');
    },
    async mode(value) {
      if(mode===value) return;
      await page.locator(value==='block'?'#preFillModeFillBtn':'#preFillModeCellBtn').click({timeoutMs:2000});
      mode=value; brush=null;
    },
    async point(cell,plan) {
      await port.fit(plan);
      const a=await port.read(),b=await port.read(),r=b.canvas;
      if(!same(a.canvas,r)||!r?.width) fail('E_CANVAS','Canvas moved before click');
      const x=r.x+(cell.x+0.5)*r.width/plan.width,y=r.y+(cell.y+0.5)*r.height/plan.height;
      if(x<0||y<0||x>=b.viewport.width||y>=b.viewport.height) fail('E_CANVAS','Cell lies outside viewport');
      const hit=await page.evaluate(({x,y})=>document.elementFromPoint(x,y)?.id==='tuneCanvas',{x,y});
      if(!hit) fail('E_CANVAS','Canvas cell is covered by another control');
      await tab.click([x,y]);
    },
    async select(cell,plan) {await port.point(cell,plan);},
    async paint(cell,plan) {await port.point(cell,plan);},
    async choose(id,{completesBoard=false}={}) {
      if(mode==='cell'&&brush===id) return;
      try {await page.locator(`button.pre-fill-btn[data-prefill-cid="${id}"]`).click({timeoutMs:3000});}
      catch(error) {
        // Only the known last write can legitimately be interrupted by completion.
        if(!completesBoard || !(await tab.getJsDialog()))throw error;
      }
      brush=id;
      if(completesBoard) {await port.complete();return;}
      if(mode==='block') {
        for(let n=0;n<16;n++) {
          const s=await port.read();statusGate(s);
          if(/^已将色块/.test(s.status))return;
          await page.waitForTimeout(200);
        }
        fail('E_TIMEOUT','Block fill response did not arrive; do not retry');
      }
    },
    async preview() {
      // Completion replaces the canvas with a larger image inside scrollable panes.
      // Fit that observed image before capturing it; fullPage alone can still crop panes.
      const preview=page.getByRole('img',{name:'打散后预览',exact:true});
      for(let i=0;i<8;i++) {
        const s=await preview.evaluate(img=>{
          const r=img.getBoundingClientRect();
          return {x:r.x,y:r.y,width:r.width,height:r.height,vw:innerWidth,vh:innerHeight};
        });
        if(s.x>=0&&s.y>=0&&s.x+s.width<=s.vw&&s.y+s.height<=s.vh) {
          fs.writeFileSync(path.join(runDir,'editor_preview.png'),Buffer.from(await tab.screenshot()));
          return;
        }
        if(i===7||s.width>s.vw||s.height>s.vh)fail('E_CANVAS','Final preview cannot fit the current viewport');
        const point=[Math.max(1,Math.min(s.vw-2,s.x+s.width/2)),Math.max(1,Math.min(s.vh-2,s.y+s.height/2))];
        const direction=s.x<0?'left':s.x+s.width>s.vw?'right':s.y<0?'up':'down';
        await tab.scroll(point,direction,0.3);
      }
    },
    async complete() {
      // updatePreFillPlacementUI schedules the confirmation after the fill response.
      // Read dialogs before DOM: an open native confirm can block DOM/CDP operations.
      let confirmed=false;
      for(let i=0;i<20;i++) {
        const dialog=await tab.getJsDialog();
        if(dialog) {
          if(dialog.type!=='confirm')fail('E_DIALOG','Unexpected completion dialog');
          await dialog.accept();confirmed=true;break;
        }
        await page.waitForTimeout(200);
      }
      if(!confirmed) {
        const direct=button('完成并导出（跳过打散）').filter({visible:true});
        if(await direct.count()!==1)fail('E_FINISH','No completion prompt or direct completion control');
        await direct.click({timeoutMs:3000});
      }
      for(let i=0;i<16;i++) {
        const cancel=button('取消').filter({visible:true});
        if(await cancel.count()===1) {await cancel.click({timeoutMs:2000});completed=true;break;}
        if(i===15)fail('E_FINISH','Expected export modal was not reached');
        await page.waitForTimeout(200);
      }
    },
    async finish() {
      if(!completed)fail('E_FINISH','Completion and export cancellation must precede save');
      await button('保存进度').click({timeoutMs:3000});
      for(let i=0;i<16;i++) {
        const s=await port.read(); statusGate(s);
        if(s.status.includes('已保存浏览器进度。')) {await tab.markDeliverable();return;}
        await page.waitForTimeout(200);
      }
      fail('E_SAVE','Save confirmation missing');
    },
  };
  return port;
}

export async function startExecution(tab,{runDir,listTabs}) {
  const executionReport=path.join(runDir,'editor_execution_report.json');
  if(fs.existsSync(executionReport)) fail('E_EXISTING_EXECUTION','This run already has an execution record; no automatic replay');
  const {board,source,manifest}=loadAcceptedRun(runDir);
  const startedManifestHash=fileHash(path.join(runDir,'run_manifest.json'));
  const url=await tab.url();
  const port=createBrowserPort(tab,{url,listTabs,runDir});
  const persist=report=>writeJSON(executionReport,report);
  try {
    await port.assertContext();
    const boot=await bootstrapKStageV2(url);
    if(!same(boot.state.identity,manifest.identity)||boot.state.source.sourceSha256!==source.source_revision||
       !same(boot.state.source.completeBoard,board.completeBoard)||
       !same(boot.state.source.colors,board.colors)) fail('E_SOURCE','Live tab does not identify the accepted source');
    const session=await createExecutionSession({board,sourceBlocks:source.blocks,port,persist,
      verifyFiles:()=>{
        if(fileHash(path.join(runDir,'run_manifest.json'))!==startedManifestHash) fail('E_ARTIFACT_CHANGED','Run regenerated during execution');
        return loadAcceptedRun(runDir);
      }});
    writeJSON(path.join(runDir,'editor_execution_plan.json'),session.plan);
    return session;
  } catch(error) {
    if(!fs.existsSync(executionReport))persist({status:'failed',saved:false,error:{code:error.code||'E_UI',message:error.message}});
    throw error;
  }
}

/** Own sessions in the imported module, never in caller/REPL-local variables. */
export function createExecutionRunner(open=startExecution) {
  const runs=new Map();
  return async function runStep(tab,options) {
    const {runDir,action='advance',visualMatches,maxActions=20}=options;
    if(!['advance','status','finish'].includes(action))fail('E_ACTION','Use advance, status, or finish');
    if(!Number.isInteger(maxActions)||maxActions<1||maxActions>30)fail('E_BATCH','Use 1–30 actions');
    const key=path.resolve(runDir);
    let entry=runs.get(key);
    if(!entry) {
      if(action!=='advance')fail('E_PHASE','Initialize with advance before status or finish');
      entry={tabId:String(tab.id),busy:false,failure:null,session:null};
      // Register before awaiting initialization so concurrent calls cannot start twice.
      runs.set(key,entry);
    }
    if(entry.tabId!==String(tab.id))fail('E_TAB_CHANGED','Keep the original tab for this run');
    if(entry.busy)fail('E_BUSY','The previous operation is still running; do not overlap calls');
    if(entry.failure)fail('E_TERMINAL',`This run has stopped: ${entry.failure.message}`);
    entry.busy=true;
    try {
      if(!entry.session) {
        entry.session=await open(tab,{...options,runDir:key});
        // Initialization is its own checkpoint; no painting on the first call.
        return entry.session.snapshot();
      }
      const state=entry.session.snapshot();
      if(action==='status'||state.status==='saved')return state;
      if(action==='finish')return await entry.session.finish({visualMatches});
      return await entry.session.advance({maxActions});
    } catch(error) {
      entry.failure=error;
      throw error;
    } finally {entry.busy=false;}
  };
}

// Retain this module namespace in the CUA top-level binding printed by browser-code.
// CUA can reload repeated imports across cells; native Node's ESM cache is not a guarantee.
// A runtime reset loses the registry; the on-disk execution guard still prevents replay.
export const runStep=createExecutionRunner();
