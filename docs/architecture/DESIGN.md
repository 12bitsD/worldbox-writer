# WorldBox Writer 架构设计与技术选型

**文档状态**：Active (Sprint 1 Updated)
**作者**：Manus AI

## 1. 系统核心理念 (Core Architecture Principles)

本系统不再是一个单纯的"文本生成器"，而是一个"事件推演引擎"。
所有的故事发展，首先在底层数据结构中以**有向无环图（DAG）**的形式推演并固化，然后才交由大语言模型（LLM）进行文学性渲染。

这种架构设计的目的是为了解决长篇小说生成中的**逻辑一致性**与**用户干预持久性**问题。

## 2. 核心模块与组件

系统分为三个主要层级：**世界推演层（World Simulation Layer）**、**边界与意图层（Constraint & Intent Layer）**、**表现与渲染层（Presentation Layer）**。

### 2.1 世界推演层 (World Simulation Layer)

负责维护世界的物理规律、历史背景以及角色的自主行动。

- **World Builder (世界构建师 Agent)**：
  - 维护全局知识库（Global Context）。
  - 当新区域被探索或新势力出现时，动态生成设定并存入向量数据库（Vector DB）。
- **Actor (角色扮演者 Agent 集群)**：
  - 每个核心角色是一个独立的 Agent 实例。
  - 维护个人的属性面板、好感度矩阵以及短期/长期记忆。
  - 基于当前世界状态和自身目标，向调度中心提交"行动意图"（Action Proposal）。

### 2.2 边界与意图层 (Constraint & Intent Layer)

这是系统的"大脑"和"裁判"，负责处理人类干预，并确保世界不会崩溃。

- **Gate Keeper (边界守卫 Agent)**：
  - 接收并解析用户的"神谕"（自然语言干预指令）。
  - 将用户意图转化为硬性约束（Hard Constraints）或软性倾向（Soft Preferences）。
  - 拦截所有违反世界规则或叙事红线的 Actor 行动意图。
- **Logic Manager (逻辑校验者 Agent)**：
  - 维护事件的有向无环图（Event DAG）。
  - 确保因果关系成立（例如：A 必须先获得钥匙，才能打开宝箱）。
  - 解决并发冲突（例如：两个 Actor 同时试图杀死同一个目标）。

### 2.3 表现与渲染层 (Presentation Layer)

负责将底层的结构化数据转化为人类可读的内容。

- **Narrator (叙述者 Agent)**：
  - 读取已确认的 Event DAG 节点序列。
  - 结合参与角色的性格和历史记忆，将结构化事件渲染为带有对话、心理活动和环境描写的文学正文。
- **Dashboard API (前端接口)**：
  - 提供实时更新的事件流（Event Stream）、人物关系图谱数据和全局状态快照。

## 3. 核心数据流转 (Data Flow)

1. **初始化**：Director Agent 接收用户的一句话需求，生成初始世界设定（存入 Vector DB）和初始矛盾（生成首个 DAG 节点）。
2. **提议阶段**：Actor Agents 观察当前 DAG 末端节点，结合自身记忆，各自生成下一步行动提议。
3. **校验阶段**：Gate Keeper 和 Logic Manager 对所有提议进行审查，剔除不合逻辑或违背用户意图的行动。
4. **决议阶段**：系统根据权重或随机概率，从合法提议中选出一个或多个，固化为新的 DAG 节点。
5. **渲染阶段**：
   - **精细模式**：Narrator Agent 立即将新节点渲染为小说正文。
   - **快进模式**：跳过 Narrator，直接进入下一轮提议，仅输出结构化摘要。
6. **干预中断**：当系统检测到即将生成的节点属于"关键分歧点"（如主角生死、重大结盟）时，暂停推演，向用户发起交互请求（Prompt for Intervention）。

## 4. 技术栈选型 (Tech Stack Selection)

### 4.1 后端与 Agent 编排 (Backend & Orchestration)
- **语言**：Python 3.11+
- **Agent 框架**：LangGraph（Sprint 1 Spike 选型确认）。
  - *理由*：LangGraph 提供有状态的图执行模型，天然支持循环、条件分支和人机交互暂停（`interrupt_before`），完全契合本项目的"推演-校验-干预"循环。相比之下，CrewAI 偏向线性任务流，AutoGen 状态管理复杂度过高。
- **API 框架**：FastAPI。
  - *理由*：支持异步非阻塞 I/O，适合处理长时间运行的 Agent 推演任务和 Server-Sent Events (SSE) 流式输出。

### 4.2 数据存储 (Data Storage)
- **图数据库 (Graph DB)**：Neo4j。
  - *用途*：存储事件的有向无环图（Event DAG）以及动态更新的人物关系网络（Social Graph）。
- **向量数据库 (Vector DB)**：Chroma 或 Milvus。
  - *用途*：存储世界观设定集（Wiki）、角色的长期记忆（Long-term Memory），支持语义检索（RAG）。
- **关系型数据库 (RDBMS)**：PostgreSQL 或 SQLite。
  - *用途*：存储用户账户、项目元数据、存档快照（Save States）。

#### Sprint 8 补充：Branch Seed Snapshot v1

为支撑时间线分叉，SQLite 在原有 `sessions.state_json` 之外，补充了按 `sim_id + node_id + branch_id` 建模的 `branch_seed_snapshots` 表。

- **seed 形态**：v1 直接保存完整 `WorldState` JSON snapshot，而不是 diff。
- **写入时机**：每次会话持久化时，如果当前世界存在 `current_node_id`，就为该历史节点 upsert 一份 snapshot。
- **恢复语义**：后续 `fork_at_node()` 必须从对应节点的 snapshot 恢复，而不是重放整条 LLM 历史。
- **兼容策略**：旧会话若不存在对应 snapshot，系统应显式返回“该节点暂不支持分叉”，而不是静默降级或伪造支线。

当前不采用“回放整条历史再从中途分叉”的原因很直接：LLM 推演并非严格确定性过程。即使提示词和历史节点文本相同，重放得到的中间世界状态、角色记忆和后续候选事件也可能发生漂移。对于 Sprint 8 的首个 branching release，优先级是**可恢复、可验证、可解释**，而不是最小存储占用。

#### Sprint 8.5 补充：先做 Progressive Feedback，再评估服务拆分

当前首屏等待问题并不主要来自“FastAPI 和 LLM 编排必须立即拆成两个服务”，而主要来自两件事：

- 首个可见反馈暴露得太晚
- `WorldBuilder` 位于第一幕正文之前的关键路径上

因此 Sprint 8.5 的架构决策是：

- **短期**：继续保持单体后端 + 线程池后台任务模型，先把初始化 Telemetry、SSE 首包和主区域进度反馈做顺。
- **短期**：把 `WorldBuilder` 延后到第一幕开始可见之后执行，让首个正文 token 更早出现。
- **中期**：若这一轮后仍证明体验不可接受，再演进到 `API / Session Service + Simulation Worker` 的双层组织形式。

这项决策的重点是先验证：在不新增队列、缓存和跨进程状态同步复杂度的前提下，仅靠关键路径裁剪和更早暴露进度，是否已经足够改善首次推演体验。

#### Sprint 9 补充：先冻结 Durable Memory / Routing Contract，再谈外部向量库

Sprint 9 的首要任务不是立刻接入新的向量数据库，而是先把 **记忆持久化契约** 和 **模型路由契约** 固化下来：

- **Durable Memory**：`memory_entries` 继续复用 SQLite，但升级为 branch-aware、可归档的持久化表；旧事件可被摘要压缩为 summary entry，而不是只停留在内存窗口里。
- **Routing Contract**：LLM 调用支持 `logic / creative / role` 三级覆盖，先解决“不同链路可配置、可诊断、可 fallback”的问题。
- **Eval / Perf Guard**：模型评估与容量门禁优先作为手动工作流落地，不直接塞入默认 PR gate。

这样做的原因是：如果 Durable Memory / Routing 的契约都还不稳定，那么无论接 ChromaDB、做更复杂的工作流编辑器还是上更重的 CI 评估矩阵，后续都会反复返工。

#### Sprint 11 补充：先让 Director 成为 Scene Planner，再做角色隔离运行时

在双循环路线里，最容易犯的错误是过早把主图直接切成“多 Actor 并发”，但 Director 还没有稳定地产出场景级真相源。

Sprint 11 的架构决策因此是：

- **先补 Scene Planner**：Director 不再只负责初始化世界，而是每一幕都要输出 `ScenePlan`，显式决定 scene objective、spotlight cast、public summary 与 narrative pressure。
- **先补 graph state contract**：`ScenePlan` 必须进入 LangGraph shared state，并写回 `world.metadata["current_scene_plan"]`，作为后续 compatibility snapshot、diagnostics 与下一轮 Actor runtime 的共同来源。
- **Actor 先消费，不先隔离**：本 Sprint 允许 legacy `actor_node` 读取 `ScenePlan` 来收敛目标和聚光灯，但不提前做 fan-out / fan-in，也不在本 Sprint 引入 Critic / GM。
- **世界细化仍保持异步补全定位**：`WorldBuilder` 继续作为首幕可见后的延迟步骤存在，不重新塞回逻辑主链前端。

这样切的原因很直接：

- 没有稳定 `ScenePlan`，Sprint 12 的 isolated actors 会缺少统一的导演输入。
- 没有 graph-state 持久化，Sprint 10 做出来的 dual-loop contract 只会停留在 compatibility 层，无法进入真实运行时。
- 先让 Actor 在单链路上消费 `ScenePlan`，可以在不放大爆炸半径的前提下验证“Director 场控”是否真的改善失焦和流水账问题。

#### Sprint 12 补充：先让隔离 Actor 意图真实进入主链，再引入 Critic / GM

Sprint 12 的架构决策是：

- **Actor fan-out/fan-in 先行**：`ScenePlan.spotlight_character_ids` 作为本轮 Actor 唤醒名单，每个角色独立组装 prompt 并产出 `ActionIntent`。
- **私有上下文边界先行**：Actor prompt 只包含公开场景信息、可见角色、自身目标、自身短期记忆和该角色相关的持久记忆片段，不再把所有角色状态打包进同一个共享 prompt。
- **legacy bridge 保守接入**：多个 `ActionIntent` 暂时合成为一个 legacy candidate event，继续复用 `GateKeeper -> NodeDetector -> Narrator`，不在本 Sprint 提前切换事实提交模型。
- **trace 先沉淀**：`PromptTrace`、`MemoryRecallTrace` 和 `ActionIntent` 被写入 runtime metadata / node metadata，为后续 Critic、GM 和 Inspector 提供可追踪输入。

这样切的原因同样直接：

- 没有真实 `ActionIntent`，Sprint 13 的 Critic 只能审查旧式共享候选事件，无法验证角色认知边界。
- 没有隔离 prompt trace，Sprint 16 的 Inspector 只能展示黑盒日志，不能定位“角色为什么知道了不该知道的信息”。
- 保留 legacy bridge 可以把最大风险控制在 Actor 阶段，让 GateKeeper、NodeDetector、Narrator 的既有回归继续发挥保护作用。

#### Sprint 13 补充：Critic 先审查单个 Intent，GateKeeper 继续守住节点边界

Sprint 13 的架构决策是：

- **Critic 前置到结算前**：`ActionIntent` 进入 legacy candidate bridge 前，必须先生成 `IntentCritique`，明确 accepted / rejected、原因码、严重级别和修正提示。
- **职责拆分而不是替换 GateKeeper**：`CriticAgent` 聚焦单个角色意图的世界规则、角色状态、认知边界与荒诞行为；`GateKeeper` 继续校验合成后的候选事件是否违反节点级约束。
- **只桥接合法意图**：被 Critic 拒绝的 intent 保留在 metadata / diagnostics 中，但不会进入当前 candidate event 合成。
- **兼容层继续沉淀 SceneScript 映射**：compatibility snapshot 使用 Critic verdict 生成 `accepted_intent_ids` 和 `rejected_intent_ids`，但暂不接管 `NodeDetector` 的事实提交。

这样切的原因很直接：

- 没有逐 intent verdict，Sprint 14 的 GM 无法知道哪些角色意图可以参与结算。
- 如果只审查合成后的候选事件，系统无法定位“是哪一个角色越界或偷看了不可见信息”。
- 保留 GateKeeper 后置保护可以继续兜住合成文本层面的约束问题，降低双循环迁移风险。

#### Sprint 14 补充：GM 结算成为 SceneScript 的主来源

Sprint 14 的架构决策是：

- **GM 接在 Critic 之后**：`GMAgent` 只消费 `ActionIntent` 与 `IntentCritique`，把通过审查的合法意图结算成唯一 `SceneScript`。
- **SceneScript 先成为事实源，不立刻替换所有下游**：主链 candidate event 来自 `SceneScript.summary`，但 `GateKeeper`、`NodeDetector` 和 `Narrator` 继续保留现有执行职责。
- **提交时保留 lineage**：`StoryNode.metadata["scene_script"]`、`accepted_intent_ids`、`rejected_intent_ids` 和 beats 一起持久化，后续 Inspector / export / rendering 都能追溯来源。
- **diagnostics 优先读运行时脚本**：compatibility snapshot 先复用 `world.metadata["last_scene_script"]` 或已提交节点 metadata，再回退到兼容层合成脚本。

这样切的原因是：

- Sprint 17 前，Narrator 仍可消费单段事件文本，但这段文本必须已经来自场景级逻辑结算。
- Sprint 15 的记忆写回需要稳定事实源，否则会把被拒绝的角色意图写入长期记忆。
- 保留 legacy 提交链可以让 SceneScript 先落地并被验证，再逐步替换渲染和导出层。

#### Sprint 15 补充：SceneScript 驱动三层认知记忆

Sprint 15 的架构决策是：

- **不新增独立记忆表**：继续复用 `memory_entries`，通过 `entry_kind=reflection` 和 tags 表达反思层，避免破坏 Sprint 9 的 durable memory contract。
- **SceneScript accepted beats 是反思写回来源**：只有 GM 结算后的 accepted beats 会写入角色反思，Critic 拒绝的 intent 不进入长期认知。
- **PromptTrace 暴露三层召回诊断**：`MemoryRecallTrace` 继续承载 working / episodic / reflective 三层内容，并在 metadata 中记录 layer counts 与 retrieval backend。
- **角色 metadata 保留轻量反思缓存**：`Character.metadata["reflection_notes"]` 作为下一轮 Actor prompt 的快速反思上下文，durable memory 作为持久来源。

这样切的原因是：

- 如果反思层直接从 raw intent 写回，会把被拒绝或荒诞的行动污染角色认知。
- 如果 Sprint 15 先做独立 memory schema，会放大存储迁移风险，并拖慢 Inspector / rendering 闭环。
- 三层 trace 先稳定下来，Sprint 16 才能把“为什么召回这些记忆”做成可解释面板。

#### Sprint 16 补充：Inspector 独立于 diagnostics，Prompt 模板文件化

Sprint 16 的架构决策是：

- **Inspector API 独立出来**：`/api/simulate/{sim_id}/inspector` 返回当前场景的 `ScenePlan`、`SceneScript`、`ActionIntent`、`IntentCritique` 和 `PromptTrace`，而 diagnostics 继续聚焦聚合计数。
- **前端先展示关键链路，不做编辑器**：Creative Studio 的 Prompt Inspector 只展示 prompt 数、intent 数、critic rejected 数和三层记忆计数，避免提前引入模板编辑权限。
- **Prompt registry 每次读文件**：Actor system prompt 从 packaged template 或 `PROMPT_TEMPLATE_DIR` 读取，默认不缓存，满足本地 hot reload contract v1。
- **PromptTrace 仍是事实来源**：Inspector 不重新组装 prompt，而是展示运行时已经沉淀的 trace，避免 UI 与后端 prompt 逻辑出现第二套真相源。

这样切的原因是：

- PromptOps 的第一步不是在线编辑，而是可定位和可复现。
- 独立 Inspector API 让后续分页、权限和历史节点查看有演进空间。
- 模板文件化后，后续可以逐步加版本管理，而不需要再改 Agent prompt 入口。

### 4.3 大语言模型接入 (LLM Integration)
- **云端 API**：OpenAI (GPT-4o), Anthropic (Claude 3.5 Sonnet)。
  - *用途*：用于复杂的逻辑推理、边界校验和高质量文本渲染。
- **本地部署**：Ollama + Llama 3 / Qwen 2。
  - *用途*：为关注隐私的用户提供纯本地运行方案，用于轻量级的 Actor 决策和意图提议。

### 4.4 前端 (Frontend - 规划中)
- **框架**：React 18+ (Vite)
- **状态管理**：Zustand
- **可视化库**：
  - React Flow：用于展示事件 DAG 和故事树。
  - ECharts / D3.js：用于渲染人物好感度矩阵和势力分布图。
