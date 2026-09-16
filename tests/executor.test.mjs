import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {buildHybridPaintPlan,simulatePlan,validateSourceBlocks,verifySelectedBlock,sha256,startPreFillKStageV2,postKStageV2} from '../scripts/kstage_prefill_helpers.mjs';
import {createExecutionSession,createExecutionRunner} from '../scripts/kstage_executor.mjs';
const f=JSON.parse(fs.readFileSync(new URL('./fixtures/asset-2748.json',import.meta.url)));
const board=f.candidate,blocks=f.blocks.blocks;
const clone=value=>structuredClone(value);

test('V2 prefill request includes the actual required occurredAt field',async t=>{
  const before=Date.now();
  t.mock.method(globalThis,'fetch',async(url,options)=>{
    assert.equal(url,'https://example.test/api/v2/prefill/start');
    const body=JSON.parse(options.body);
    assert.equal(body.expectedRevision,f.state.revision);
    assert.deepEqual(body.state,f.state);
    assert.ok(Date.parse(body.operation.occurredAt)>=before);
    assert.ok(Date.parse(body.operation.occurredAt)<=Date.now());
    assert.match(body.requestId,/^[0-9a-f-]{36}$/);
    return new Response(JSON.stringify({ok:true,result:{blocks}}));
  });
  const result=await startPreFillKStageV2({state:f.state,contextToken:'private-context'}, {baseUrl:'https://example.test'});
  assert.deepEqual(result.result.blocks,blocks);
});

test('V2 errors preserve server reason and redact credentials',async t=>{
  t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify({
    ok:false,code:'operation_invalid',error:'operation.occurredAt 不能为空。 private-context'
  }),{status:400}));
  await assert.rejects(postKStageV2('prefill/start',{contextToken:'private-context'}),error=>{
    assert.equal(error.code,'E_API');
    assert.match(error.message,/HTTP 400 operation_invalid: operation.occurredAt/);
    assert.ok(!error.message.includes('private-context'));
    return true;
  });
});

function mockPort(options={}) {
  const used=Object.fromEntries(board.colors.map(c=>[c.id,0]));
  if(options.partial)used[11]=1;
  let selected=null,mode='cell',brush=null,painting=0;
  const actual=board.completeBoard.map(row=>row.map(()=>-1));
  const port={started:0,colorClicks:0,paintClicks:0,saves:0,
    async assertContext(){if(options.duplicate)throw Object.assign(new Error('duplicate tab'),{code:'E_DUPLICATE_TAB'});},
    async read(){return {status:options.lock?'错误：该草稿正在另一个标签页编辑。':'',inPreFill:true,
      rows:board.colors.map(c=>({id:c.id,total:c.count,used:used[c.id],remaining:c.count-used[c.id]})),selected};},
    async start(){port.started++;},async fit(){},
    async mode(m){mode=m;selected=null;},
    async select(p){
      const block=blocks.find(b=>b.pixels.some(q=>q.r===p.y&&q.c===p.x));
      const unfilled=block.pixels.filter(q=>actual[q.r][q.c]===-1).length;
      selected={blockId:block.blockId,hex:block.hex,total:block.pixelCount,unfilled};
      if(options.wrongProbe) selected.blockId+=100;
      if(options.wrongAfterSingles&&painting)selected.unfilled++;
    },
    async choose(id){
      port.colorClicks++;brush=id;
      if(mode==='block') {
        const block=blocks.find(b=>b.blockId===selected.blockId);
        for(const p of block.pixels) if(actual[p.r][p.c]===-1){actual[p.r][p.c]=id;used[id]++;painting++;}
      }
    },
    async paint(p){port.paintClicks++;painting++;actual[p.y][p.x]=brush;used[brush]++;if(options.inventoryError)used[brush]++;},
    async preview(){assert.deepEqual(actual,board.initialBoard);},
    async finish(){if(options.saveError)throw Object.assign(new Error('save failed'),{code:'E_SAVE'});port.saves++;},
  };
  return port;
}
async function advanceAll(session) {
  let result;
  for(let i=0;i<100;i++) {
    result=await session.advance({maxActions:20});
    if(result.status==='awaiting_visual_review')return result;
  }
  throw new Error('session did not complete');
}
test('real server 19-block fixture exactly reconstructs all 796 cells',()=>{
  assert.equal(blocks.length,19);
  const plan=buildHybridPaintPlan(board,{sourceBlocks:blocks});
  assert.equal(plan.totalCells,796);
  assert.equal(plan.singleCellCount,71);
  assert.equal(plan.fillOps.length,17);
  assert.deepEqual(simulatePlan(board,blocks,plan),board.initialBoard);
});
test('no local inferred-block fallback',()=>assert.throws(()=>buildHybridPaintPlan(board),{code:'E_BLOCKS_MISSING'}));
test('reject duplicate ID, wrong pixelCount, overlap, omitted pixels, and wrong source color',()=>{
  for(const mutate of [b=>b[1].blockId=b[0].blockId,b=>b[0].pixelCount++,
    b=>b[1].pixels[0]=b[0].pixels[0],b=>b.pop(),b=>b[0].colorId=5]) {
    const bad=clone(blocks);mutate(bad);assert.throws(()=>validateSourceBlocks(board,bad));
  }
});
test('a selected 93-cell KStage block cannot be mistaken for a six-cell local region',()=>{
  assert.throws(()=>verifySelectedBlock({blockId:10,total:93,unfilled:91,hex:'#7A2E3A'},
    {blockId:0,total:6,count:6,sourceColorId:23},board.colors),{code:'E_SELECTED_BLOCK'});
});
test('every real block is probed before first board mutation',async()=>{
  const port=mockPort(),session=await createExecutionSession({board,sourceBlocks:blocks,port});
  const state=await session.advance({maxActions:19});
  assert.equal(state.completed,19);assert.equal(port.colorClicks,0);assert.equal(port.paintClicks,0);
  await advanceAll(session);assert.equal(port.saves,0);
  await session.finish({visualMatches:true});assert.equal(port.saves,1);
  assert.equal((await session.advance()).status,'saved');
});
test('wrong selected block aborts before any color click and cannot resume',async()=>{
  const port=mockPort({wrongProbe:true}),reports=[];
  const session=await createExecutionSession({board,sourceBlocks:blocks,port,persist:r=>reports.push(r)});
  await assert.rejects(session.advance(),{code:'E_SELECTED_BLOCK'});
  assert.equal(port.colorClicks,0);assert.equal(port.paintClicks,0);
  await assert.rejects(session.advance(),{code:'E_TERMINAL'});
  assert.equal(reports.at(-1).status,'failed');
});
test('block unfilled count is checked again after minority single cells',async()=>{
  const port=mockPort({wrongAfterSingles:true}),session=await createExecutionSession({board,sourceBlocks:blocks,port});
  await assert.rejects(advanceAll(session),{code:'E_SELECTED_BLOCK'});
  assert.equal(port.paintClicks,71); // no majority block has been filled
  assert.equal(port.saves,0);
});
test('partial board, duplicate tab, and edit lock stop before any cell write',async()=>{
  for(const options of [{partial:true},{duplicate:true},{lock:true}]) {
    const port=mockPort(options);
    await assert.rejects(createExecutionSession({board,sourceBlocks:blocks,port}));
    assert.equal(port.started,0);assert.equal(port.paintClicks,0);
  }
});
test('inventory mismatch stops after the offending cell with no recovery',async()=>{
  const port=mockPort({inventoryError:true}),session=await createExecutionSession({board,sourceBlocks:blocks,port});
  await assert.rejects(advanceAll(session),{code:'E_INVENTORY'});
  assert.equal(port.paintClicks,1);assert.equal(port.saves,0);
});
test('failed visual review or save cannot report completion',async()=>{
  for(const saveError of [false,true]){
    const port=mockPort({saveError}),reports=[];
    const session=await createExecutionSession({board,sourceBlocks:blocks,port,persist:r=>reports.push(r)});
    await advanceAll(session);
    await assert.rejects(session.finish({visualMatches:saveError}));
    assert.equal(reports.at(-1).saved,false);
    assert.equal(port.saves,0);
  }
});
test('candidate mutation, alias disagreement, invalid inventory rejected',()=>{
  const modified=clone(board);modified.initialBoard[0][4]=4;
  assert.throws(()=>buildHybridPaintPlan(modified,{sourceBlocks:blocks}));
  const hashWrong=clone(board);hashWrong.candidate_sha256=sha256([]);
  assert.throws(()=>buildHybridPaintPlan(hashWrong,{sourceBlocks:blocks}),{code:'E_ARTIFACT'});
});

test('tiny boards still finish with a block operation',()=>{
  const b={completeBoard:[[1,2]],initialBoard:[[2,1]],colors:[{id:1,hex:'#000000',count:1},{id:2,hex:'#ffffff',count:1}],candidate_sha256:sha256([[2,1]])};
  const bs=[{blockId:7,colorId:1,pixelCount:1,pixels:[{r:0,c:0}]},{blockId:9,colorId:2,pixelCount:1,pixels:[{r:0,c:1}]}];
  const p=buildHybridPaintPlan(b,{sourceBlocks:bs});
  assert.equal(p.singleCellCount,0);assert.equal(p.fillOps.length,2);
});
test('runtime change stops a session between batches before further writes',async()=>{
  const port=mockPort();let changed=false;
  const session=await createExecutionSession({board,sourceBlocks:blocks,port,verifyFiles:()=>{
    if(changed)throw Object.assign(new Error('runtime changed'),{code:'E_HELPER_CHANGED'});
  }});
  await session.advance({maxActions:19});changed=true;
  await assert.rejects(session.advance(),{code:'E_HELPER_CHANGED'});
  assert.equal(port.paintClicks,0);
});

// Exercise the real DOM/coordinate adapter without a live browser or network.
import vm from 'node:vm';
import {createBrowserPort} from '../scripts/kstage_executor.mjs';
test('browser adapter reads actual selection text and rejects covered cells before clicking',async()=>{
  let clicks=0,covered=false;
  const canvas={id:'tuneCanvas',offsetWidth:310,offsetHeight:350,getClientRects:()=>[1],getBoundingClientRect:()=>({x:10,y:20,width:310,height:350})};
  const doc={body:{innerText:'颜色放置区（预填充）'},
    querySelector:selector=>selector==='#statusMsg'?{textContent:'选中色块 #10（原色 #7A2E3A，总93格，未填91格）→ 请在右侧选择填充颜色'}:
      selector==='#tuneCanvas'?canvas:selector==='#preFillModeBar'?canvas:null,
    querySelectorAll:()=>[],elementFromPoint:()=>covered?{id:'overlay'}:canvas};
  const page={evaluate:(fn,arg)=>vm.runInNewContext(`(${fn.toString()})(arg)`,{document:doc,arg,innerWidth:1000,innerHeight:800}),
    getByLabel:()=>({count:async()=>0})};
  const tab={id:'tab',url:async()=>'https://example.test/editor',playwright:page,click:async()=>clicks++};
  const port=createBrowserPort(tab,{url:'https://example.test/editor',listTabs:async()=>[{id:'tab',url:'https://example.test/editor'}],runDir:'/unused'});
  const state=await port.read();
  assert.equal(state.selected.blockId,10);assert.equal(state.selected.total,93);assert.equal(state.selected.unfilled,91);
  await port.point({x:1,y:1},{width:31,height:35});assert.equal(clicks,1);
  covered=true;await assert.rejects(port.point({x:1,y:1},{width:31,height:35}),{code:'E_CANVAS'});assert.equal(clicks,1);
});

test('real browser adapter handles the last-fill confirm, cancels export, then saves once',async()=>{
  const actions=[];let status='',dialogOpen=false,modal=false;
  const query={body:{innerText:''},querySelector:selector=>selector==='#statusMsg'?{textContent:status}:null,querySelectorAll:()=>[]};
  const locator=(name)=>({filter(){return this;},count:async()=>name==='取消'&&modal?1:0,
    click:async()=>{
      actions.push(name);
      if(name.includes('data-prefill-cid'))dialogOpen=true;
      if(name==='取消')modal=false;
      if(name==='保存进度')status='已保存浏览器进度。';
    }});
  const tab={playwright:{getByRole:(_role,{name})=>locator(name),locator,waitForTimeout:async()=>{},
    evaluate:(fn,arg)=>vm.runInNewContext(`(${fn.toString()})(arg)`,{document:query,arg,innerWidth:1000,innerHeight:800})},
    getJsDialog:async()=>dialogOpen?{type:'confirm',accept:async()=>{actions.push('确认完成');dialogOpen=false;modal=true;status='已完成确认。';}}:null,
    markDeliverable:async()=>actions.push('保留页面')};
  const port=createBrowserPort(tab,{url:'fixture',listTabs:async()=>[],runDir:'/unused'});
  await port.mode('block');await port.choose(11,{completesBoard:true});
  assert.deepEqual(actions.slice(-2),['确认完成','取消']);
  assert.equal(actions.includes('保存进度'),false);
  await port.finish();
  assert.deepEqual(actions.slice(-2),['保存进度','保留页面']);
  assert.equal(actions.includes('完成填充'),false);
});

test('fixed entrypoint survives disposable caller scopes without restarting or repeating cells',async()=>{
  const port=mockPort();let starts=0;
  const step=createExecutionRunner(async()=>{starts++;return createExecutionSession({board,sourceBlocks:blocks,port});});
  const options={runDir:'/fixture/scoped',listTabs:async()=>[]},tab={id:'one'};
  // Each invocation discards all of its local variables, as separate REPL cells can do.
  async function invoke(action='advance') {
    try {const localOnly=await step(tab,{...options,action});return localOnly;}
    catch(error){throw error;}
  }
  const first=await invoke();assert.equal(first.completed,0);assert.equal(port.paintClicks,0);
  const second=await invoke();assert.equal(second.completed,20);
  assert.equal(port.paintClicks,1); // Nineteen probes followed by the first cell.
  const third=await invoke();assert.equal(third.completed,40);assert.equal(starts,1);
  assert.equal(port.paintClicks,21);
  assert.equal((await invoke('status')).completed,40);assert.equal(port.paintClicks,21);
});

test('fixed entrypoint excludes overlapping initialization and different tabs',async()=>{
  let release,starts=0;
  const gate=new Promise(resolve=>release=resolve),port=mockPort();
  const step=createExecutionRunner(async()=>{starts++;await gate;return createExecutionSession({board,sourceBlocks:blocks,port});});
  const options={runDir:'/fixture/concurrent'},tab={id:'one'};
  const pending=step(tab,options);
  await assert.rejects(step(tab,options),{code:'E_BUSY'});
  await assert.rejects(step({id:'two'},options),{code:'E_TAB_CHANGED'});
  release();await pending;assert.equal(starts,1);
  assert.equal((await step(tab,{...options,action:'status'})).completed,0);
});

test('fixed entrypoint remembers initialization failure and never automatically retries',async()=>{
  let starts=0;
  const step=createExecutionRunner(async()=>{starts++;throw Object.assign(new Error('existing record'),{code:'E_EXISTING_EXECUTION'});});
  const options={runDir:'/fixture/failed-init'},tab={id:'one'};
  await assert.rejects(step(tab,options),{code:'E_EXISTING_EXECUTION'});
  await assert.rejects(step(tab,options),{code:'E_TERMINAL'});
  assert.equal(starts,1);
});

test('operation log retains timed attempted cell when inventory verification fails',async()=>{
  const port=mockPort({inventoryError:true}),reports=[];
  const step=createExecutionRunner(()=>createExecutionSession({board,sourceBlocks:blocks,port,persist:r=>reports.push(r)}));
  const options={runDir:'/fixture/failed-write'},tab={id:'one'};
  await step(tab,options);
  await assert.rejects(step(tab,options),{code:'E_INVENTORY'});
  const failed=reports.at(-1);
  assert.equal(failed.events.length,19);assert.equal(failed.current_action.type,'cell');
  assert.ok(Number.isFinite(Date.parse(failed.current_action.started_at)));
  assert.ok(failed.events.every(e=>e.elapsed_ms>=0&&Date.parse(e.finished_at)>=Date.parse(e.started_at)));
  await assert.rejects(step(tab,options),{code:'E_TERMINAL'});assert.equal(port.paintClicks,1);
});

test('fixed entrypoint completes once and repeated saved calls perform no browser actions',async()=>{
  const port=mockPort();let starts=0;
  const step=createExecutionRunner(()=>{starts++;return createExecutionSession({board,sourceBlocks:blocks,port});});
  const options={runDir:'/fixture/saved'},tab={id:'one'};
  let result=await step(tab,options);
  for(let i=0;i<100&&result.status!=='awaiting_visual_review';i++)result=await step(tab,options);
  assert.equal(result.status,'awaiting_visual_review');assert.equal(port.saves,0);
  assert.equal((await step(tab,{...options,action:'finish',visualMatches:true})).status,'saved');
  const clicks=port.colorClicks+port.paintClicks;
  for(const action of ['advance','finish','status'])assert.equal((await step(tab,{...options,action,visualMatches:true})).status,'saved');
  assert.equal(port.saves,1);assert.equal(port.colorClicks+port.paintClicks,clicks);assert.equal(starts,1);
});

test('finish before initialization and unsupported actions do not initialize anything',async()=>{
  let starts=0;
  const step=createExecutionRunner(()=>starts++),tab={id:'one'},options={runDir:'/fixture/invalid'};
  await assert.rejects(step(tab,{...options,action:'finish',visualMatches:true}),{code:'E_PHASE'});
  await assert.rejects(step(tab,{...options,action:'retry'}),{code:'E_ACTION'});
  assert.equal(starts,0);
});

test('final preview scrolls the actual clipped image into view before one screenshot',async()=>{
  const runDir=fs.mkdtempSync(path.join(os.tmpdir(),'jewel-preview-'));
  const box={x:784,y:157,width:620,height:700},moves=[];let captures=0;
  const img={getBoundingClientRect:()=>box};
  const tab={playwright:{getByRole:(role,{name})=>{
    assert.equal(role,'img');assert.equal(name,'打散后预览');
    return {evaluate:fn=>vm.runInNewContext(`(${fn.toString()})(img)`,{img,innerWidth:1299,innerHeight:790})};
  }},scroll:async(_point,direction)=>{
    moves.push(direction);if(direction==='right')box.x=660;else if(direction==='down')box.y=47;
  },screenshot:async()=>{
    assert.ok(box.x+box.width<=1299&&box.y+box.height<=790);captures++;return Buffer.from('entire observed image');
  }};
  try {
    await createBrowserPort(tab,{runDir}).preview();
    assert.deepEqual(moves,['right','down']);assert.equal(captures,1);
    assert.equal(fs.readFileSync(path.join(runDir,'editor_preview.png'),'utf8'),'entire observed image');
  } finally {fs.rmSync(runDir,{recursive:true,force:true});}
});
