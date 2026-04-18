# Sprint 8 开发任务拆解

**文档状态**：Draft for Execution  
**适用 Sprint**：Sprint 8 (v0.7.x)  
**最后更新**：2026-04-18

本文档用于把 Sprint 8 已确认的方向继续下钻到开发任务层，供 Sprint Planning、任务分派、PR 拆分和验收使用。

Sprint 8 的关键判断只有一个：当前仓库虽然已经预留了 `branch_id`、`merged_from_ids`、`branches` 和 `active_branch_id`，但并没有真正的 branch engine，也没有“历史节点可恢复状态”。所以 Sprint 8 不能把“分支 UI”“节奏控制”“上线护栏”并列推进，而必须先补齐能从历史节点安全续跑的 branch substrate。

---

## 1. Sprint 8 承诺范围

### P0 用户故事

- `US-06.01` 时间线回溯与分叉
- `US-06.02` 多分支查看、切换与基础对比

### P0 工程使能项

- `S8-EN-01` Branch Seed Snapshot v1
- `S8-EN-02` Branch-aware API & Persistence Contract
- `S8-EN-03` Branch Trace & Telemetry Extension
- `S8-EN-04` Feature Flag & Rollback Runbook

### P1 伸缩项

- `US-06.03` 叙事节奏控制器
- `S8-EN-05` 时间线性能护栏

---

## 2. 推荐开发顺序

建议按以下顺序推进，避免前后返工：

1. `S8-EN-01`
2. `S8-EN-02`
3. `US-06.01`
4. `S8-EN-03`
5. `US-06.02`
6. `S8-EN-04`
7. `US-06.03`
8. `S8-EN-05`

原因：

- 先解决“历史节点如何恢复”的问题，再谈“从哪里分叉”和“前端怎么切换”。
- 先冻结分支 API 与持久化契约，再做 Timeline UI，避免前端建立在虚构接口上。
- 节奏控制和性能优化属于后置增强，不应阻塞首个 branching loop 收口。

---

## 3. 需求拆解

## 3.1 S8-EN-01 Branch Seed Snapshot v1

**目标**

- 为每个可分叉历史节点提供可恢复的 fork seed，让分支创建不是“复制节点数组”，而是“从当时世界状态继续推演”。

**期望收口**

- 至少一种可持久化、可回放、可验证的 fork seed 方案被冻结并文档化。
- 从历史节点创建分支时，系统能恢复该节点对应的 branch seed。
- 实现优先选择简单可靠，而不是过早追求最优存储压缩。

**开发任务**

| Task ID | 开发任务 | Owner | 依赖 | 产物 |
| :--- | :--- | :--- | :--- | :--- |
| S8-EN-01-T1 | 盘点当前会话、节点和世界状态持久化路径，确认哪些数据可作为 fork seed 来源 | 服务端架构团队 | 无 | 持久化盘点结论 |
| S8-EN-01-T2 | 定义 fork seed v1 契约：推荐采用完整 `WorldState` snapshot 或其他明确可恢复表示，并明确 key、生命周期和清理策略 | 服务端架构团队 | T1 | schema 草案 |
| S8-EN-01-T3 | 扩展 SQLite 持久化层，保存 `sim_id + node_id + branch_id` 维度的 fork seed | 服务端架构团队 | T2 | 存储实现 |
| S8-EN-01-T4 | 为历史恢复补读取逻辑，确保从指定节点恢复出可续跑的世界状态 | 服务端架构团队 | T3 | 恢复逻辑 |
| S8-EN-01-T5 | 为老会话定义兼容策略：未命中 fork seed 时给出明确不可分叉提示，而不是静默失败 | 服务端架构团队 | T4 | 兼容处理 |
| S8-EN-01-T6 | 增加后端测试，覆盖 fork seed 保存、读取、老数据兼容和错误提示 | 服务端架构团队 | T3, T4, T5 | pytest |
| S8-EN-01-T7 | 更新架构文档，写明为什么 v1 不采用“重放整条 LLM 历史再分叉” | 服务端架构团队 | T6 | 文档更新 |

**验收检查**

- 任意一个已持久化分支点都能加载出 fork seed。
- 未命中 fork seed 的历史节点有显式错误语义，不会产生半残分支。
- 测试中能证明 fork seed 恢复结果独立于原分支后续节点变化。

---

## 3.2 S8-EN-02 Branch-aware API & Persistence Contract

**目标**

- 建立分支能力所需的后端 API、前端类型和持久化契约，让“创建分支 / 读取分支 / 切换分支 / 比较分支”有同一套真相源。

**期望收口**

- API 契约冻结并前后端同步。
- `WorldState.branches`、`active_branch_id` 和节点 `branch_id` 的语义被统一消费。
- 不引入第二套前端本地 branch state 真相源。

**开发任务**

| Task ID | 开发任务 | Owner | 依赖 | 产物 |
| :--- | :--- | :--- | :--- | :--- |
| S8-EN-02-T1 | 设计 Sprint 8 必要接口：`POST /branch`、`POST /branch/switch`、`GET /simulate/{id}?branch=...`、`GET /branch/compare` | 服务端架构团队 + 前端团队 | S8-EN-01 | API 草案 |
| S8-EN-02-T2 | 冻结 branch metadata 字段，如 `label`、`forked_from_node`、`source_branch_id`、`created_at_tick`、`status` | 服务端架构团队 | T1 | metadata schema |
| S8-EN-02-T3 | 落地服务端路由、序列化和存储 round-trip，确保会话恢复时保留 active branch 语义 | 服务端架构团队 | T2 | API 实现 |
| S8-EN-02-T4 | 更新前端类型、fixtures 和状态合并逻辑，消费 branch-aware 载荷 | 前端团队 | T3 | TS 类型与 state 合并 |
| S8-EN-02-T5 | 为分支相关 API 增加契约测试，覆盖创建、切换、按分支读取和基础对比摘要 | 服务端架构团队 + 前端团队 | T3, T4 | API/fixture 测试 |
| S8-EN-02-T6 | 更新 README、USER_STORIES 和 Sprint 文档中的分支字段说明 | 前端团队 + 服务端架构团队 | T5 | 文档更新 |

**验收检查**

- 创建分支、切换分支、按分支读取三条路径使用同一套 branch metadata。
- 前端切换分支时不需要额外猜测或二次推断 branch 结构。
- 新增契约字段进入 fixtures 和测试，不再只是隐式约定。

---

## 3.3 US-06.01 时间线回溯与分叉

**目标**

- 让用户真正从一个历史节点启动新的世界线，而不是在主线末尾追加一条“假支线”。

**期望收口**

- 用户可以在一个历史节点触发分支创建。
- 新分支会注册到 `WorldState.branches`，并拥有独立的后续节点链。
- 分支继续推演不会修改原分支已有节点或 active branch 指向错误。

**开发任务**

| Task ID | 开发任务 | Owner | 依赖 | 产物 |
| :--- | :--- | :--- | :--- | :--- |
| US-06.01-T1 | 定义分支创建语义：是否立即切换为活跃分支、默认命名、父子关系、源节点约束 | AI 系统团队 + 产品 | S8-EN-02 | 行为规范 |
| US-06.01-T2 | 在引擎层实现 `fork_at_node()` 或等价能力，基于 fork seed 创建新 branch world | AI 系统团队 | S8-EN-01, S8-EN-02 | 引擎实现 |
| US-06.01-T3 | 保证分支续跑时只向新 branch 追加节点，并正确写入 `branch_id` | AI 系统团队 | T2 | 节点写入逻辑 |
| US-06.01-T4 | 增加从分叉点继续推演的后端测试，覆盖“主线不被污染”和“支线可独立推进” | AI 系统团队 | T2, T3 | pytest |
| US-06.01-T5 | 补用户错误处理：源节点不可分叉、分支名冲突、旧会话不支持分叉等场景 | 服务端架构团队 | T2 | 错误语义与 API 返回 |
| US-06.01-T6 | 更新架构说明与 API 文档，明确分叉 v1 行为边界 | AI 系统团队 + 服务端架构团队 | T4, T5 | 文档更新 |

**验收检查**

- 同一历史节点至少可创建 2 条不同分支。
- 支线新增节点只写入该支线的 `branch_id`。
- 主线和支线切回后，已有节点链不发生串写或覆盖。

---

## 3.4 S8-EN-03 Branch Trace & Telemetry Extension

**目标**

- 在 Sprint 7 已完成的调用链与 Telemetry 基础上，把“这是哪条世界线上的哪次分叉”也纳入可追踪范围。

**期望收口**

- 关键分支链路至少能追到 `branch_id`、`forked_from_node_id`、`source_branch_id`。
- 创建分支、切换分支和支线续跑都有可读 Telemetry。
- 前端不需要读取 raw payload 才知道当前事件属于哪条 branch。

**开发任务**

| Task ID | 开发任务 | Owner | 依赖 | 产物 |
| :--- | :--- | :--- | :--- | :--- |
| S8-EN-03-T1 | 设计分支追踪字段，补充到 Telemetry / Trace schema | 服务端架构团队 | S8-EN-02 | 字段草案 |
| S8-EN-03-T2 | 在分支创建、切换、续跑路径中发射 Telemetry 事件 | 服务端架构团队 | T1, US-06.01 | 后端实现 |
| S8-EN-03-T3 | 更新前端 Telemetry 类型和展示，补 branch context 徽标或字段 | 前端团队 | T2 | 前端展示 |
| S8-EN-03-T4 | 补 API/SSE/恢复一致性测试，确认 branch trace 不在恢复时丢字段 | 服务端架构团队 + 前端团队 | T2, T3 | 契约测试 |
| S8-EN-03-T5 | 更新 Telemetry schema 文档 | 服务端架构团队 | T4 | 文档更新 |

**验收检查**

- 至少一条分支创建到续跑的链路能在 Telemetry 中完整阅读。
- 同一事件在 DB、REST、SSE 和前端 state 中的 branch context 一致。

---

## 3.5 US-06.02 多分支查看、切换与基础对比

**目标**

- 让用户在 UI 中真正管理多条世界线，而不是只能创建分支却无法有效阅读和比较。

**期望收口**

- 用户可查看 branch 列表并切换 active branch。
- 用户至少能看见每条 branch 的来源节点、节点数量、最新 tick 和最后节点摘要。
- 刷新页面、重开历史会话后，active branch 和 branch 列表仍一致。

**开发任务**

| Task ID | 开发任务 | Owner | 依赖 | 产物 |
| :--- | :--- | :--- | :--- | :--- |
| US-06.02-T1 | 设计分支面板交互：branch list、active 状态、fork source、基础 compare 区域 | 前端团队 + 产品 | S8-EN-02 | 交互草图 |
| US-06.02-T2 | 在前端状态层增加 active branch 派生选择器，保证 StoryFeed / WorldPanel / Telemetry 按当前 branch 渲染 | 前端团队 | T1 | 状态逻辑 |
| US-06.02-T3 | 开发多分支面板和基础 compare UI，默认折叠非活跃支线详情 | 前端团队 | T2 | 组件实现 |
| US-06.02-T4 | 增加刷新恢复、历史打开和 branch 切换的前端测试 | 前端团队 | T2, T3 | Vitest |
| US-06.02-T5 | 必要时补服务端 compare summary 载荷，避免前端自己扫描全量节点做重计算 | 服务端架构团队 | T1 | compare API/summary |
| US-06.02-T6 | 调整空状态和错误提示，覆盖“只有主线”“旧会话不可分叉”“分支已归档” | 前端团队 | T3 | UX 打磨 |

**验收检查**

- 切换 branch 后，StoryFeed、世界信息和 Telemetry 都只展示对应 branch 数据。
- 比较信息不依赖用户肉眼翻完整节点流。
- 页面刷新或重开最近会话后，active branch 语义不丢失。

---

## 3.6 S8-EN-04 Feature Flag & Rollback Runbook

**目标**

- 让首个 branching release 能被显式开关和快速止损，而不是默认全量暴露。

**期望收口**

- 分支能力可以通过 feature flag 开启或关闭。
- 关闭后系统回退到单主线安全行为，旧主链路不受影响。
- 运行手册明确写出发现问题后的关闭、验证和恢复步骤。

**开发任务**

| Task ID | 开发任务 | Owner | 依赖 | 产物 |
| :--- | :--- | :--- | :--- | :--- |
| S8-EN-04-T1 | 选择当前仓库可承载的 feature flag 方案（环境变量或服务端配置） | 服务端架构团队 | 无 | 方案结论 |
| S8-EN-04-T2 | 为分支 API 和前端入口加开关保护 | 服务端架构团队 + 前端团队 | T1, S8-EN-02 | 代码开关 |
| S8-EN-04-T3 | 补关闭场景测试，确保禁用时系统仍按单主线工作 | 服务端架构团队 + 前端团队 | T2 | 测试 |
| S8-EN-04-T4 | 编写 Runbook：如何开启、如何关闭、如何验证关闭后系统恢复正常 | 服务端架构团队 | T3 | Runbook 文档 |

**验收检查**

- 开关关闭时，分支创建入口和 API 都不可用且错误可解释。
- 关闭分支功能后，单主线主路径仍可运行。

---

## 3.7 US-06.03 叙事节奏控制器

**目标**

- 给用户第一层“偏导演”的控制权，但不把 Sprint 8 主线拖进复杂策略系统。

**期望收口**

- 仅提供有限档位的节奏模式，不开放无约束自由文本参数。
- 节奏上下文能跟随 branch 持久化。
- Telemetry 中可看见节奏上下文被读取或应用。

**开发任务**

| Task ID | 开发任务 | Owner | 依赖 | 产物 |
| :--- | :--- | :--- | :--- | :--- |
| US-06.03-T1 | 设计最小节奏模型，如 `calm` / `balanced` / `intense` | AI 系统团队 + 产品 | US-06.01 | 档位定义 |
| US-06.03-T2 | 在 branch metadata 或 session context 中持久化 pacing 选择 | 服务端架构团队 | T1, S8-EN-02 | 持久化字段 |
| US-06.03-T3 | 在 GateKeeper 或节点筛选逻辑中读取 pacing 上下文并产生可观测影响 | AI 系统团队 | T2, S8-EN-03 | 后端实现 |
| US-06.03-T4 | 在前端补节奏切换入口和反馈说明 | 前端团队 | T2 | UI |
| US-06.03-T5 | 增加测试，覆盖档位保存和至少一种行为差异 | AI 系统团队 + 前端团队 | T3, T4 | 测试 |

**验收检查**

- 用户设置的节奏档位会随 branch 一起恢复。
- 至少一条 Telemetry 能看见 pacing 被读取。

---

## 3.8 S8-EN-05 时间线性能护栏

**目标**

- 在不预设沉重前端框架的前提下，保证多分支时间线不会把当前 UI 直接拖垮。

**期望收口**

- 先有性能基线，再决定是否引入懒加载或虚拟化。
- 非活跃分支默认折叠。
- 只有在性能证明必要时，才引入额外依赖。

**开发任务**

| Task ID | 开发任务 | Owner | 依赖 | 产物 |
| :--- | :--- | :--- | :--- | :--- |
| S8-EN-05-T1 | 构造多分支 fixture，覆盖 3-5 条支线、100+ 节点场景 | 前端团队 | US-06.02 | fixture |
| S8-EN-05-T2 | 记录当前分支面板和 StoryFeed 的渲染性能基线 | 前端团队 | T1 | 基线数据 |
| S8-EN-05-T3 | 若性能不足，再选择最小化方案：懒加载、摘要列表或虚拟滚动 | 前端团队 | T2 | 优化实现 |
| S8-EN-05-T4 | 对比优化前后收益，沉淀到 Sprint 复盘 | 前端团队 | T3 | 对比记录 |

**验收检查**

- 没有基线数据前，不引入新依赖。
- 非活跃分支默认不展开全量节点细节。

---

## 4. 周节奏建议

### Week 1

- 完成 `S8-EN-01`
- 完成 `S8-EN-02`
- 启动 `US-06.01`

**周中收口**

- fork seed 方案冻结
- branch API 和 metadata 契约冻结
- 后端能从一个历史节点创建 branch world

### Week 2

- 完成 `US-06.01`
- 完成 `S8-EN-03`
- 完成 `US-06.02`
- 完成 `S8-EN-04`

**周末收口**

- 用户可在真实界面分叉、切换并做基础对比
- 分支能力具备可关闭的发布护栏

### Stretch

- `US-06.03`
- `S8-EN-05`

---

## 5. PR 拆分建议

- PR1: `S8-EN-01` fork seed schema + 存储 + 测试
- PR2: `S8-EN-02` branch API / 序列化 / 前端类型
- PR3: `US-06.01` 分叉引擎与支线续跑
- PR4: `S8-EN-03` branch telemetry / trace
- PR5: `US-06.02` 多分支 UI 与基础 compare
- PR6: `S8-EN-04` feature flag / runbook
- PR7: `US-06.03` 或 `S8-EN-05` 伸缩项

原则：

- 先合并 fork seed 与契约，再合并 UI。
- 先让单分叉链路跑通，再补 compare 和 telemetry 可读性。
- 发布护栏必须在对外默认开启前合并。

---

## 6. 总收口标准

Sprint 8 是否真正收口，不看“分支相关任务都动过”，而看下面 6 条是否同时成立：

1. 用户能从历史节点创建新分支，并在支线继续推演。
2. 分支切换后，节点、世界状态和 Telemetry 不发生跨分支串写。
3. 历史恢复和页面刷新后，active branch 语义仍然一致。
4. 用户至少能比较每条 branch 的来源节点、节点数、最新 tick 和最后节点摘要。
5. 分支链路在 API、持久化和 Telemetry 上有同一套 branch context。
6. 分支功能可以通过 feature flag 显式关闭，关闭后系统退回单主线安全行为。
