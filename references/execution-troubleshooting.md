# 执行错误与解决方案对照库

用于读取素材、生成产物、操作编辑器、保存与恢复时的故障检索。`EX01–EX17` 是案例编号，不是配色规则或优先级；配色规则仍只由 [priority-rules.md](priority-rules.md) 定义。

## 使用方法

1. 用**发生阶段 + 完整报错/可见现象**搜索下表，再核对“匹配条件与原因”。同一个 HTTP 状态码或 `E_CANVAS` 可能有不同原因，不能只按编号套方案。
2. 命中后使用表中已有入口，具体操作以链接的工作流或脚本为准。先读当前报告，确认停在哪一步；正常继续同一个未失败的会话，与重新执行一次写入不同。
3. 处理后检查该行的验收信号。解决方案不是重放许可；已失败、已部分写入或结果不确定的运行，按 [终止错误处理](kstage-editor-workflow.md#terminal-errors) 保留现场，不能删除报告、回滚猜测或新开同图来绕过保护。
4. 未命中时记录现象、阶段、源版本、最后确认的动作及错误响应；在维护中定位并验证后补充本库。不要把推测原因写成定论，也不要边画图边改通用脚本。

**验证标记的范围：**“线上”指实际 KStage 页面或接口的指定操作；“本地补丁”指本机测试页面；“回归”指自动化测试；“本机命令”指工具或 CLI。每条只证明明确列出的部分，不代表整条流程或所有后续版本都通过。证据基线为 2026-09-15，历史材料见文末。

## 对照表

| 编号 / 阶段 | 错误类型与检索词 | 匹配条件、已知原因 | 已找到的处理方法 / 入口 | 如何验收；验证程度 |
|---|---|---|---|---|
| EX01 / 色块识别 | 选错区域、填充越界、边界被毁；`E_SELECTED_BLOCK`、`E_BLOCK_COVERAGE` | 把分析用的四向连通区 ID 当成编辑器填充 ID。小狗 asset 2748 有 **57 个分析区、19 个真实操作块**；六格分析区不等于界面选中的大块。 | [区域身份契约](kstage-editor-workflow.md#region-identity-contract)：`prepare` 保存真实 `prefill/start` 分区；`buildHybridPaintPlan` 只用 `kstage_blocks.json`；`runStep` 在任何填色前逐块探测，并在块填充前再次验证 ID、原色、总格数、未填数。实现：[helper](../scripts/kstage_prefill_helpers.mjs)、[executor](../scripts/kstage_executor.mjs)。不再用四向或八向连通性猜操作分区。 | 全盘覆盖无重叠、计划模拟与候选一致、所有选块读数匹配后才可点击颜色。**线上 + 回归**：2748 的 19 块全部核对后完成 796 格；错误分区拒绝测试见 [executor tests](../tests/executor.test.mjs)。 |
| EX02 / 填色效率 | 大量单格输入、填充模式没生效 | 没利用“该选中块未填数量 ≤ 该目标色剩余可用数量”的条件，或把整块总数当成剩余待填数。条件满足也不能据此随意选色，仍须与候选一致。 | 由 `buildHybridPaintPlan` 规划少数格先单点、多数格后块填充，再交给固定 `runStep`。已填少数格保留，块填充仅消费未填格。入口同 [区域身份契约](kstage-editor-workflow.md#region-identity-contract)。 | 库存变化与计划一致、最终棋盘经过完整计划模拟。**线上**：2748 用 **27 格单点 + 17 次块填充**完成 796 格；不能将这个数量套到所有图片。 |
| EX03 / 颜色识别与对比 | 截图 RGB 认错色；棕色被认成酒红；显示序号与颜色 ID 混淆 | asset 2569 的简单截图 RGB 比对只匹配 932/939 格，另 7 枚受珠粒阴影影响。页面第几行和材质规范 ID 也是不同概念。 | 操作身份用源 palette、规范 ID、DOM 中的 `data-color-id` / `data-prefill-cid` 及选中色块原色；截图用于视觉检查。使用 [executor](../scripts/kstage_executor.mjs) 的身份与库存校验；只有需要 Unity 导出时才额外运行 [validate_color_ids.py](../scripts/validate_color_ids.py)。 | **线上**：当前操作按规范 ID 与库存通过；**能力边界**：线上通用逐格 ID 回读尚未沉淀，当前报告 `pixel_comparison: not_run`，不能把视觉检查写成逐格自动比对通过。历史证据 H1。 |
| EX04 / 写入与保存 | 接口返回成功、剩余为 0，页面却没变；“内部保存了” | helper 算出或返回了新状态，但没有把状态应用到当前编辑器、也没有在目标浏览器保存。历史 commit 调用曾出现此情况。 | 使用 [固定浏览器入口](kstage-editor-workflow.md#normal-invocation) 实际填入当前页面，再执行 [固定收尾](kstage-editor-workflow.md#fixed-finish-sequence)。`prepare` 只读取源和块；本地 JSON、HTTP 成功都不能替代网页操作。 | 看见当前页面完整结果、库存核对通过、收到 `已保存浏览器进度。`。**线上**：2748 已保存；历史反例 H1。此验收不等于刷新恢复测试。 |
| EX05 / 保存位置 | 换到另一个浏览器或 KStage 页面点恢复没效果 | 使用了不同浏览器/配置、来源或素材身份的草稿。已检查的 V2 实现使用浏览器 IndexedDB；内部浏览器、用户 Chrome 和本地测试站点不会自动共享草稿。 | 先确认用户实际使用的现有 Chrome 标签页及同一素材身份，从读取到保存保持同一上下文；依 [One tab, one accepted run](kstage-editor-workflow.md#one-tab-one-accepted-run) 操作。当前方案不提供跨浏览器草稿同步。 | **线上保存 + 用户历史确认**：在用户实际 KStage 环境可恢复的结果曾获用户确认；2748 最近一轮只验证同页保存。不要据此宣称任意浏览器之间可以恢复。实现核查 H2。 |
| EX06 / 未完成进度恢复 | 显示“已恢复”但珠粒丢失，初始图变成原图 | asset 3874 的未提交单格存在前端临时填充映射中，保存/恢复链没有完整同步、重建它；不能与 EX05 的存储位置问题混为一谈。 | 正常交付采用现行 [固定收尾](kstage-editor-workflow.md#fixed-finish-sequence)，先完成提交再保存。未完成草稿完整恢复需要编辑器同步并重建预填充状态；历史本地补丁实现了这部分，**不是现行通用线上能力**。不得假定线上有“载入预填充方案”入口。 | **本地补丁已验证**：651 格保存/刷新/恢复，884 个坐标回读一致；其部署到线上未确认。已丢失且草稿从未保存的珠粒不能靠“恢复”凭空找回。证据 H2、H3。 |
| EX07 / 浏览器上下文 | 页面不见了、重复打开同图；`E_DUPLICATE_TAB`、`E_EDIT_LOCK` | 历史有页面丢失反馈和重复标签页操作。页面消失的具体成因未完全证实；不能一概归为令牌失效。新建同图也不能重建原会话，并可能形成编辑冲突。 | 通过 CUA 发现并复用用户现有页，定位相同 URL/素材后保留句柄；成功时由 executor 调用 `markDeliverable()`。遇到访问或占用问题先核对现有上下文，不靠再开副本恢复。入口：[单页工作流](kstage-editor-workflow.md#one-tab-one-accepted-run)。 | **线上**：2748 全程使用同一现有 Chrome 页至保存；**回归**：重复页、部分填充、编辑锁会在写入前拒绝。这些证据不证明历史页面消失的根因。 |
| EX08 / 本地产物生成 | 每张图临时写 Python、手工维护四份 JSON；`E_RUN_FILES`、`E_INPUT_CHANGED` | 分类、生成、验收未统一入口，AI 每张图重复实现胶水代码，容易产生多份不一致产物。 | 使用 [design-spec.md](design-spec.md) 的 `run_level.py` 流程，仅手写 `design_spec.json`、`visual_review.json`；其他产物和调用代码由脚本生成。通用 helper 的修改放到维护阶段，经测试后用于新运行。用户要求的额外复盘日志放在运行目录之外。 | **线上 + 回归**：2748 固定流程使用两个设计输入；`check` 核验产物和输入哈希。额外文件与手改生成物的拒绝行为见 [pipeline tests](../tests/pipeline_test.py)。 |
| EX09 / 获取操作块 | `HTTP 400`、`operation_invalid`、`operation.occurredAt 不能为空` | 仅在错误正文明确指出 `occurredAt` 缺失时匹配；历史 Python、JavaScript 请求封装都漏了编辑器本身会加的 UTC 时间。 | 使用修正后的 [fetch_kstage_source.py](../scripts/fetch_kstage_source.py) 与 [kstage_prefill_helpers.mjs](../scripts/kstage_prefill_helpers.mjs)，由通用封装添加时间；正常读取入口为 `run_level.py prepare`。其他 400 先看正文，不套此修复。 | **线上 + 回归**：同一链接 bootstrap、prefill/start 均返回 200，并取得 19 块；[fetch tests](../tests/fetch_test.py) 检查时间、请求 ID、版本和源状态。证据 H4。 |
| EX10 / 故障记录 | 只有 traceback / HTTP 状态，没有响应正文、失败阶段 | 原 `prepare` 等两次请求成功才写产物，HTTPError 未转成诊断报告，失败后无法判断服务端拒绝原因。 | `prepare_report.json` 自动记录每次请求的阶段、时间、耗时、HTTP 状态和去敏错误正文，失败也落盘；浏览器的 `editor_execution_report.json` 保留已确认动作和 `current_action`。直接读现有日志再判断，不为得到报错而重放写入。 | **回归**：实际 400 文本、非 JSON、网络失败、凭证去敏、尚无产物时的日志均覆盖；**线上**：prepare 成功日志与完整执行日志已生成。线上故障记录的每个分支并未逐一触发。 |
| EX11 / CUA 会话 | `dogSession is not defined`，上一轮初始化成功、下一轮读不到变量 | 执行会话变量声明在 `try` / 函数作用域中，没有成为跨工具调用可用的顶层绑定。 | 用 [run_level.py](../scripts/run_level.py) 的 `browser-code --browser-action setup` 生成固定代码，原样在 CUA 顶层执行一次；以后使用生成的 `advance`。会话由 `kstageRuntime.runStep` 管理，助手不再包装临时 session 或日志函数。操作细节见 [Normal invocation](kstage-editor-workflow.md#normal-invocation)。 | **线上 + 回归**：真实工具连续调用固定入口完成 63 个动作并保存；临时调用作用域丢弃后的状态保持也有回归。证据 H5、H6。 |
| EX12 / CUA 模块状态 | 每轮重新 `import` 后又初始化；紧接着 `E_EXISTING_EXECUTION` | 曾假设 CUA 与普通 Node 的 ESM 缓存一致。实际连续 import 没有保留 runner 的会话；本地测试未暴露环境差异。 | 复用 setup 生成的**顶层 `kstageRuntime` 模块绑定**及 `kstageOptions`；后续只调用它的 `runStep`，不要逐次 import。入口与 EX11 相同，修复范围是已观察的 CUA 行为，不泛化为所有 JS 环境。 | **线上**：保留模块绑定后的跨工具连续调用成功；此前仅依赖重复 import 的零写入失败记录仍保留。证据 H6。 |
| EX13 / 重新初始化 | `E_EXISTING_EXECUTION`、`E_TERMINAL`；看到库存为 0 就重新 start | 丢失句柄后重新 `startExecution`，已有执行记录触发拒绝。库存总量不足以证明会话可重建或推断每格位置。 | 未失败且顶层绑定仍在时，用 `browser-code` 生成的 `status` / `advance` 继续原会话。会话已失败或工具已重置时保留报告，按 [终止处理](kstage-editor-workflow.md#terminal-errors) 结束该次执行；维护后的新运行仍须通过实际空棋盘和身份检查，不能复制已开始的运行目录来绕过保护。 | **已观察拒绝 + 回归**：重复初始化确实被挡住；失败后不重复写入、并发初始化只运行一次有测试。**没有自动恢复部分棋盘的已验证方案**。 |
| EX14 / 完成与保存 | 点击“完成填充”就结束；最后一格后确认框阻塞后续读取；导出窗口未取消 | “完成填充”只同步/退出预填充，不等同完整收尾；最后一次写入可触发原生确认框，先读 DOM 可能被对话框阻塞。 | 交给 executor 的 `complete` / `finish`，采用 [唯一收尾顺序](kstage-editor-workflow.md#fixed-finish-sequence)。代码先处理原生确认，再取消导出；最终视觉检查后保存。无需由 AI 临时猜按钮顺序。 | **线上 + 回归**：2748 实际完成确认、取消导出、保存确认；重复调用 saved 状态不再触发浏览器动作有回归。完成按钮的无弹窗备用路径仅有实现，不声称已在当次线上触发。 |
| EX15 / 最终预览 | 截图裁掉右边/底部；`fullPage` 仍不全；`emitImage only accepts data or file URLs`；缩放快捷键没效果 | 图片在内部滚动区域，整页截图也受容器裁切；当前图片 src 不能直接交给 emitImage；本次尝试的快捷缩放未生效。不是已经发现棋盘配色错误。 | [executor `preview`](../scripts/kstage_executor.mjs) 按“打散后预览”图像的实际矩形检查可见范围，有限次向需要的方向滚动后再截图。预览无法完整容纳时返回 `E_CANVAS`，不能把裁切图当完整验收。此流程属于最后预览比较阶段，不在保存后追加检查。 | **手动线上验证 + 自动化回归**：2748 向右、向下滚动后看全并保存；自动滚动在保存后封装，**尚未再次线上整图验证**。不要再重复失败的 fullPage / src / 快捷缩放尝试。证据 H6。 |
| EX16 / 验收结论 | “测试全过”但真实操作仍失败；把局部修复称完整可用 | 离线数据、mock UI、普通 Node、CUA、线上页面与本地补丁覆盖的行为不同。occurredAt 和 import 缓存两次问题都落在测试边界外。 | 用 [test_skill.py](../scripts/test_skill.py) 证明回归范围，用真实 `prepare_report.json`、执行报告和实际保存确认证明线上步骤；分别记录仍未执行的恢复/逐格比对/新版本验证。每次新条目也采用本表的分层标记。 | 当前基线：38 项回归通过；2748 固定入口已实际保存；自动预览改进只完成回归，恢复测试未执行。证据 H6。不能把这些范围合并成“所有功能线上通过”。 |
| EX17 / 维护环境 | `ModuleNotFoundError: No module named 'yaml'` | 调用 skill-creator 的 `quick_validate.py`，系统和捆绑 Python 均缺 PyYAML；这是维护校验器依赖问题，不是 KStage 素材或配色故障。 | 为维护校验使用独立虚拟环境，安装 PyYAML 后用该环境 Python 运行 `quick_validate.py`；保持项目依赖不受影响。之前的 `/tmp` 环境只是一轮测试产物，后续先检查是否仍存在，不能硬编码假定可用。 | **本机命令已验证**：隔离环境运行返回 `Skill is valid!`。这是格式校验，不代替 runtime 回归或线上测试。证据 H4。 |

## 已沉淀的入口

| 要做的事 | 维护位置 / 正常入口 |
|---|---|
| 读取源、分析、生成、审查、校验 | [run_level.py](../scripts/run_level.py)；参数与输入见 [design-spec.md](design-spec.md) |
| 生成固定 CUA 调用代码 | `run_level.py browser-code` 的 `setup / advance / status / finish`；完整参数见 [Normal invocation](kstage-editor-workflow.md#normal-invocation) |
| 分区校验、计划模拟、选块身份验证 | [kstage_prefill_helpers.mjs](../scripts/kstage_prefill_helpers.mjs)，由正常入口调用 |
| 会话、逐步操作日志、预览、完成与保存 | [kstage_executor.mjs](../scripts/kstage_executor.mjs)，通过生成的固定代码调用 |
| 维护后的回归与范围证书 | [test_skill.py](../scripts/test_skill.py)；Node 不在 PATH 时传 `--node` 的真实可执行路径 |

## 历史证据

以下是当前工作机的归档位置，用于审计，不是执行依赖。迁移 Skill 后即使这些文件不在，表中匹配条件、脚本链接和验证范围仍可直接使用。不要将带 open_token/contextToken 的完整链接或请求体复制进本库。

- H1：[asset 2569 实测与接口/颜色识别问题](/Users/admin/yt_kiwifun/LD/pixel/skill-test-results/asset-2569/test-findings.md)。
- H2：[asset 3874 未完成进度恢复失败与存储核查](/Users/admin/yt_kiwifun/LD/pixel/skill-test-results/asset-3874/restore-test.md)。
- H3：[本地进度修复补丁及其部署边界](/Users/admin/yt_kiwifun/LD/pixel/kstage-progress-fix/README.md)。这是历史补丁文档，文中旧 helper 名称不作为当前入口；以本库及现行脚本为准。
- H4：[HTTP 400 修复、日志与环境问题](/Users/admin/yt_kiwifun/LD/pixel/operation-logs/asset-2748-rerun/repair-review.md)。
- H5：[会话变量丢失、重复初始化的未完成记录](/Users/admin/yt_kiwifun/LD/pixel/operation-logs/asset-2748-rerun/full-test-review.md)。
- H6：[固定入口实际保存与预览改进的验证边界](/Users/admin/yt_kiwifun/LD/pixel/operation-logs/asset-2748-rerun/fixed-flow-acceptance.md)，[逐项操作日志](/Users/admin/yt_kiwifun/LD/pixel/operation-logs/asset-2748-rerun/operations.jsonl)。

## 如何补充案例

新增或更新一行时保留：案例编号、可搜索现象、匹配条件、确认的原因、当前有效入口、验收信号、实际验证范围及证据。先搜已有案例，同一原因优先更新原行；失效方案标明被哪个方案替代。未解决的案例可以记录为“待定位/待验证”，不能把建议动作写成已成功方案。

操作步骤在工作流中维护，代码在 scripts 中维护；本库负责将错误定位到它们，不复制整套程序或另建一份配色规则。任何新增脚本或改动仍走现行维护验证流程。
