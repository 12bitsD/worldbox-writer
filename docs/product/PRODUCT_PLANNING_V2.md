# WorldBox Writer：Product Planning v2（双循环推演引擎）

**文档状态**：Proposed  
**适用范围**：Sprint 10+ / Dual-Loop Track  
**最后更新**：2026-04-21

本文档用于把 [双循环推演引擎设计方案](../architecture/DUAL_LOOP_ENGINE_DESIGN.md) 转换成可执行的 Agile 产品规划。它不改写 Sprint 0-9 的既有交付，而是定义下一阶段的增量路线：在保持现有系统可运行、可回滚的前提下，把当前单链路推演升级为真正的“双循环 + 白盒调优”架构。

---

## 1. 为什么需要 v2

Sprint 0-9 已经证明了这条产品线具备真实价值：

- 已有结构化推演、Narrator 渲染、SSE 实时事件流、Telemetry、branching、durable memory、Creative Studio。
- 当前系统已经不再是“一次性吐长文”的纯文本工具，而是一个可观察、可干预、可分支的故事引擎。

但从 [DUAL_LOOP_ENGINE_DESIGN.md](../architecture/DUAL_LOOP_ENGINE_DESIGN.md) 的要求看，当前代码还停留在“**共享上下文下生成单个候选事件**”的阶段，没有进入“**按角色隔离并发 -> 对抗结算 -> 生成客观 Scene Script -> 再做文笔渲染**”的阶段。

所以 v2 的目标不是再补一个局部功能，而是完成一次**架构层级的升级**：

1. 让逻辑推演真正脱离长文本渲染，降低幻觉和串戏。
2. 让 Director 从“初始化器”升级为“场控器”，显式管理聚光灯与叙事压力。
3. 让调优入口从 Telemetry 升级为 Prompt/Memory 可透视的 Inspector。

---

## 2. 设计文档的逻辑链路

双循环方案的完整链路，不是“多加几个 Agent”这么简单，而是一条严格的因果链：

1. **用户前提 -> 世界初始化**  
   Director 解析 premise，生成世界骨架、角色、约束和开场局面。
2. **世界状态 -> Scene Plan**  
   Director 不直接写正文，而是决定下一幕的场景目标、参与角色、场景公开信息和叙事压力。
3. **Scene Plan + 记忆 -> 私有 Actor Context**  
   系统为每个被点亮的角色组装独立 Prompt，只注入该角色可见的信息、私有记忆和反思结果。
4. **并发 Actor -> 结构化 Intent**  
   每个 Actor 只返回 JSON 意图，而不是直接写小说。
5. **Intent -> Critic 审查**  
   Critic 负责检查世界规则、角色认知边界、物理/魔法法则、约束违规。
6. **通过的 Intent -> GM 结算**  
   GM 对多个合法意图做冲突结算，得到唯一的客观 Scene Script。
7. **Scene Script -> 状态提交**  
   Scene Script 被固化到 WorldState / Memory / Telemetry，成为后续推演的逻辑真相源。
8. **Scene Script -> Narrator 渲染**  
   Narrator 只做文笔工作，把结构化场景渲染成章节正文。
9. **Prompt/Memory/Pressure/裁决过程 -> Inspector**  
   用户可以查看每个角色看到的上下文、召回了哪些记忆、承受了什么压力、为什么某个意图被拒绝。

这条链路对应三类核心期望：

- **一致性**：靠“结构化逻辑 + 信息隔离 + 对抗结算”避免串戏和逻辑崩坏。
- **张力**：靠“Director 的叙事压力 + 聚光灯场控”避免沙盒流水账。
- **可调优性**：靠“SSE + Prompt/Memory Inspector”把系统从黑盒变白盒。

---

## 3. 对当前代码和项目的判断

### 3.1 已有基础，不是从零开始

当前仓库已经具备 v2 的关键地基：

- `src/worldbox_writer/engine/graph.py` 已经把“结构化节点提交”和“Narrator 渲染”分开，具备双循环雏形。
- `src/worldbox_writer/api/server.py` 与前端已具备 SSE、Telemetry、诊断面板、branch-aware 会话恢复能力。
- `src/worldbox_writer/memory/memory_manager.py` 已具备 durable memory、归档摘要、branch-aware 检索能力。
- `src/worldbox_writer/agents/actor.py`、`director.py`、`gate_keeper.py`、`narrator.py` 已经拆分成独立 agent 模块，适合增量演进。

结论：**可以演进，不应推倒重写。**

### 3.2 核心缺口

| 区域 | 当前状态 | v2 要求 | 改动判断 |
| :--- | :--- | :--- | :--- |
| `engine/graph.py` | 当前是 `director -> actor -> gate_keeper -> node_detector -> narrator` 的单候选事件链 | 需要改成 `scene_plan -> isolated actors -> critic -> gm -> scene_commit -> narrator` | **高风险核心改造**，必须走 feature flag |
| `agents/director.py` | 只负责初始化世界和处理 intervention | 需要持续输出 Scene Plan、spotlight cast、narrative pressure | **高改动**，职责会升级 |
| `agents/actor.py` | 有单角色 `propose_action()`，但主图没有真正使用；当前主路径仍是共享上下文生成候选事件 | 需要成为主执行链路，并严格做私有上下文隔离 | **高改动**，但已有可复用雏形 |
| `agents/gate_keeper.py` | 校验的是最终候选事件 | v2 需要先审查 Actor Intent，再交给 GM 结算 | **中高改动**，建议保留为 policy guard，并新增 Critic |
| `agents/node_detector.py` | 负责固化 StoryNode + 干预检测 | v2 中“固化”前会先出现 Scene Script | **中高改动**，需要适配 scene commit |
| `agents/narrator.py` | 直接渲染单节点事件 | 需要消费 Scene Script，而不是直接消费“候选事件文本” | **中改动** |
| `memory/memory_manager.py` | 已有短期 + durable + 摘要归档 | 还缺 public/private/reflective 三层检索与写回 | **高改动** |
| `core/models.py` | 只有 `StoryNode` / `WorldState` / `TelemetryEvent` 等基础模型 | 需要新增 `ScenePlan`、`ActionIntent`、`SceneScript`、`PromptTrace`、`MemoryRecallTrace` 等契约 | **高风险核心模型改造** |
| `storage/db.py` | 关注 session / branch snapshot / memory entries | 需要决定 scene-level persistence、trace retention、Inspector 数据策略 | **中高改动** |
| `api/server.py` + `frontend/src/types` | 有 telemetry/diagnostics，但没有 Prompt Inspector | 需要新增 inspector API、scene telemetry v2、前端 inspector 面板 | **中高改动** |
| 前端面板 | 已有 Story/Telemetry/Branch/Creative Studio | 需要新增 Agent Inspector、Scene Script 可视化、Prompt hot reload UI | **中改动** |

### 3.3 关键判断

1. **现有系统已经有“逻辑先于正文”的方向，但还没有“角色隔离推演”的真闭环。**
2. **v2 的爆炸半径最大的位置是 `core/models.py` 和 `engine/graph.py`，不能直接一次性替换。**
3. **`WorldBuilder` 不应被删除，而应重新定位为异步/按需的世界细化器，不再卡死逻辑主链。**
4. **Prompt Inspector 必须建立在 trace contract 先稳定的前提上，不能先做 UI 再补数据。**
5. **branching、Creative Studio、导出链路都已经存在，因此 v2 必须从第一天就是 branch-aware，而不是后补兼容。**

---

## 4. v2 规划原则

v2 的排期必须服从以下原则：

1. **不做 Big Bang Rewrite**  
   新双循环链路必须挂在 feature flag 下，与现有引擎并行存在一段时间。
2. **每个 Sprint 只解决 1 个用户能力 + 1 个工程使能项**  
   保证 Sprint Goal 单一、可演示、可关闭。
3. **先冻结契约，再扩行为，再做可视化**  
   先有 schema / state / trace contract，再做 Inspector 和高级 UI。
4. **优先复用现有资产**  
   现有 Telemetry、SSE、branch seed snapshot、durable memory、Creative Studio 都要复用。
5. **先让逻辑真相源成立，再讨论文笔升级**  
   没有 Scene Script，就不要提前重写 Narrator。
6. **所有新增能力默认 branch-aware**  
   否则会破坏 Sprint 8 之后已经建立的控制能力。

---

## 5. 产品规划层级

### 5.1 Product Vision

**让 WorldBox Writer 从“可观察的故事推演器”升级为“可解释、可调优、低幻觉的长篇网文生产引擎”。**

### 5.2 Release Goals

| Release Goal | 目标 | 对应 Sprint |
| :--- | :--- | :--- |
| **RG-05：双循环基础冻结** | 冻结核心契约，安全引入双循环试验链路 | Sprint 10-11 |
| **RG-06：隔离推演与对抗结算** | 让 Scene Plan、Isolated Actor、Critic、GM 成为新的逻辑主链 | Sprint 12-15 |
| **RG-07：白盒调优与稳定上线** | 提供 Inspector、场景级渲染适配与灰度发布护栏 | Sprint 16-18 |

### 5.3 Epics

| Epic ID | 名称 | 描述 |
| :--- | :--- | :--- |
| **E07** | 双循环核心契约 (Dual-Loop Contracts) | 冻结 Scene Plan / Action Intent / Scene Script / Trace 契约 |
| **E08** | 聚光灯导演 (Spotlight Director) | 让 Director 输出场景计划与叙事压力 |
| **E09** | 隔离 Actor 运行时 (Isolated Actor Runtime) | 让角色在私有上下文中并发地产生 JSON 意图 |
| **E10** | Critic / GM 对抗结算 | 审查 Actor 意图并生成唯一客观场景剧本 |
| **E11** | 认知记忆流 v2 (Cognitive Memory Stream) | 建立工作/情景/反思三层记忆与可追踪召回 |
| **E12** | Inspector 与 PromptOps | 提供 Prompt / Memory / Pressure / Verdict 的白盒调试入口 |
| **E13** | 场景级渲染闭环 | 让 Narrator 消费 Scene Script 并保持导出/创作链兼容 |
| **E14** | 迁移与发布护栏 | 用对比、评估、回滚策略让 v2 安全落地 |

---

## 6. Sprint Roadmap

说明：

- Sprint 周期默认继续遵循 [AGILE_GUIDE.md](../development/AGILE_GUIDE.md) 的 2 周节奏。
- 每个 Sprint 只承诺 1 个用户故事 + 1 个工程使能项。
- Story Points 只用于相对估算；若任一故事超过 13 点，必须继续拆分。

### Sprint 10：冻结双循环契约

**Sprint Goal**：定义清楚“下一代逻辑真相源是什么”，但不在本 Sprint 做行为替换。

| 类型 | ID | 条目 | 优先级 | 估算 |
| :--- | :--- | :--- | :--- | :--- |
| User Story | **US-07.01** | 作为系统架构师，我希望系统先拥有稳定的 `ScenePlan / ActionIntent / SceneScript / PromptTrace` 契约，以便后续实现不会在 state 和 API 上反复返工 | P0 | 8 |
| Enabler | **S10-EN-01** | 双循环 feature flag + compatibility adapter v1 | P0 | 5 |

**标准产物**

- 后端 Pydantic 契约
- 前端 TypeScript 契约
- Scene telemetry v2 字段草案
- 兼容层 ADR / 迁移说明
- L1 模型测试 + API 契约测试

### Sprint 11：Director 升级为场控器

**Sprint Goal**：让 Director 能决定“下一幕该看谁、发生在哪、要施加什么叙事压力”。

| 类型 | ID | 条目 | 优先级 | 估算 |
| :--- | :--- | :--- | :--- | :--- |
| User Story | **US-08.01** | 作为创世神，我希望 Director 能为每一幕生成 scene objective、spotlight cast 和 narrative pressure，以便故事不会失焦或流水账 | P0 | 8 |
| Enabler | **S11-EN-01** | Scene Plan 持久化与 graph state 接线 | P0 | 5 |

**标准产物**

- `DirectorAgent` 输出 schema
- Scene Plan -> graph state 映射
- narrative pressure telemetry
- Director 集成测试
- Architecture doc 增量更新

### Sprint 12：隔离 Actor 运行时 v1

**Sprint Goal**：让主链第一次真正运行“按角色隔离”的逻辑推演。

| 类型 | ID | 条目 | 优先级 | 估算 |
| :--- | :--- | :--- | :--- | :--- |
| User Story | **US-09.01** | 作为角色 Agent，我希望只看到我应当知道的公开信息、私有记忆和自身目标，以便不再偷看全局剧本 | P0 | 13 |
| Enabler | **S12-EN-01** | spotlight actor fan-out / fan-in 并发执行器 | P0 | 8 |

**标准产物**

- public/private context assembler
- actor invocation runtime
- 每个 Actor 的意图 telemetry
- “信息泄漏”回归测试
- branch-aware actor intent trace

### Sprint 13：Critic 审查链路

**Sprint Goal**：在进入结算前，先让系统能审查每个 Actor Intent 是否越界或离谱。

| 类型 | ID | 条目 | 优先级 | 估算 |
| :--- | :--- | :--- | :--- | :--- |
| User Story | **US-10.01** | 作为世界规则守卫，我希望系统先审查每个 Actor Intent，再决定哪些意图可以进入场景结算，以便不把违规动作混进事实层 | P0 | 8 |
| Enabler | **S13-EN-01** | GateKeeper -> Critic / Policy Guard 职责拆分 | P0 | 5 |

**标准产物**

- `CriticAgent` 模块
- Intent validation contract
- 拒绝原因 taxonomy
- Critic telemetry / diagnostics
- L1 + L2 审查链路测试

### Sprint 14：GM 结算与 Scene Script 提交

**Sprint Goal**：把“多个合法意图”收束为“一个唯一的客观场景剧本”。

| 类型 | ID | 条目 | 优先级 | 估算 |
| :--- | :--- | :--- | :--- | :--- |
| User Story | **US-10.02** | 作为创世神，我希望系统把多个合法角色意图结算成唯一的 Scene Script，以便后续渲染和记忆都基于同一份客观事实 | P0 | 13 |
| Enabler | **S14-EN-01** | scene commit adapter，接管 `node_detector` 之前的事实提交流程 | P0 | 8 |

**标准产物**

- `GMAgent` 模块
- Scene Script persistence 策略
- `StoryNode` / `SceneScript` 适配层
- branch-aware commit 测试
- compare/export 兼容性测试

### Sprint 15：认知记忆流 v2

**Sprint Goal**：把 durable memory 升级成“可解释的三层认知记忆”。

| 类型 | ID | 条目 | 优先级 | 估算 |
| :--- | :--- | :--- | :--- | :--- |
| User Story | **US-11.01** | 作为角色 Agent，我希望系统能区分工作记忆、情景记忆和反思记忆，以便长期推演时仍保持认知边界和性格连续性 | P0 | 13 |
| Enabler | **S15-EN-01** | reflective summary / trait writeback pipeline | P0 | 8 |

**标准产物**

- memory layer schema
- recall trace / retrieval diagnostics
- reflective writeback 任务
- consistency regression harness
- `make typecheck` 与 memory 集成测试

### Sprint 16：Inspector 与 PromptOps

**Sprint Goal**：把“为什么系统这样写”从 Telemetry 提升到可点击、可追踪、可定位的问题面板。

| 类型 | ID | 条目 | 优先级 | 估算 |
| :--- | :--- | :--- | :--- | :--- |
| User Story | **US-12.01** | 作为高阶用户，我希望能查看某个角色本轮的 prompt、召回记忆、叙事压力和裁决结果，以便精准调优系统 | P0 | 8 |
| Enabler | **S16-EN-01** | Prompt 模板外部化 + hot reload contract v1 | P0 | 8 |

**标准产物**

- Inspector API
- Inspector 前端面板
- Prompt registry / 模板文件
- Prompt trace retention 策略
- 前端交互测试 + API 回归测试

### Sprint 17：场景级渲染闭环

**Sprint Goal**：让 Narrator 正式消费 Scene Script，而不是继续依赖旧的“单节点事件文本”。

| 类型 | ID | 条目 | 优先级 | 估算 |
| :--- | :--- | :--- | :--- | :--- |
| User Story | **US-13.01** | 作为叙述者，我希望 Narrator 基于 Scene Script 渲染章节正文，以便文笔层不再污染逻辑层 | P0 | 8 |
| Enabler | **S17-EN-01** | Creative Studio / export / story feed 兼容适配 | P0 | 5 |

**标准产物**

- narrator input v2 contract
- scene-to-chapter render adapter
- export bundle 兼容性更新
- 前端 story feed 适配
- rendering regression tests

### Sprint 18：灰度上线与对比评估

**Sprint Goal**：证明双循环链路不仅“能跑”，而且“可以安全替换默认主链”。

| 类型 | ID | 条目 | 优先级 | 估算 |
| :--- | :--- | :--- | :--- | :--- |
| User Story | **US-14.01** | 作为系统管理员，我希望能在旧引擎和双循环引擎之间做可观测的 A/B 对比和手动回退，以便安全发布 | P0 | 8 |
| Enabler | **S18-EN-01** | perf / integration / model-eval / rollback runbook 组合护栏 | P0 | 8 |

**标准产物**

- compare report API / CLI
- feature flag rollout plan
- 评估脚本与门禁策略
- rollback runbook
- 发布文档更新

---

## 7. Sprint 之间的依赖关系

这条路线必须按顺序推进，不能跳步：

1. **Sprint 10** 不完成，后面所有 Agent/UI 都没有稳定契约。
2. **Sprint 11** 不完成，Actor 无法收到统一的 Scene Plan。
3. **Sprint 12** 不完成，Critic/GM 只能审查旧式共享候选事件，没有意义。
4. **Sprint 13-14** 不完成，Narrator 仍然没有可靠的 Scene Script 真相源。
5. **Sprint 15** 不完成，Inspector 只能展示 Prompt，不能解释“为什么召回这些记忆”。
6. **Sprint 16-17** 不完成，v2 虽然能跑逻辑，但没有作者可用的调优与渲染闭环。
7. **Sprint 18** 不完成，v2 只能算实验链路，不能算正式产品能力。

---

## 8. 每个 Sprint 的 DoD（标准完成定义）

每个 Sprint 的承诺项只有同时满足以下条件，才算 Done：

1. 对应的 Pydantic / TypeScript 契约已冻结并提交。
2. `make lint`、`make test` 默认通过。
3. 若涉及模型字段、API payload 或 `frontend/src/types`，执行 `make typecheck`。
4. 若涉及 Agent 行为、Prompt、真实模型交互，执行 `make integration`。
5. Telemetry / diagnostics / branch-aware 行为至少有一条自动化回归测试。
6. 相关文档同步更新：
   - 架构文档
   - 产品规划 / 用户故事
   - runbook / release 文档（如影响上线）
7. 本地可以演示完整主链，而不是只有底层代码存在。

---

## 9. 明确不纳入 v2 首期承诺范围的事项

为了保持 Sprint 干净，以下事项不作为当前路线的默认承诺范围：

- 立刻拆分独立 AI 微服务
- 自动分支合并（Reconvergence）
- 全量 Prompt 可视化编辑器平台化
- 全量多 Actor 协商博弈系统
- 全量运行时 schema 产品化平台

这些方向都可能有价值，但都不应该先于“先把双循环逻辑真相源跑稳”。

---

## 10. 最终结论

双循环设计对当前项目不是“小修小补”，而是一次**从单候选事件链升级到场景级逻辑引擎**的中长期演进。

从当前代码基线看，最佳策略不是重写，而是：

1. 先冻结契约。
2. 再替换逻辑主链。
3. 再补 Inspector 和场景级渲染。
4. 最后做灰度上线与默认切换。

这也是本 Product Planning v2 的核心立场：**用 9 个干净 Sprint，把一篇设计文章，落成一条真正可交付、可回滚、可演示的产品路线。**
