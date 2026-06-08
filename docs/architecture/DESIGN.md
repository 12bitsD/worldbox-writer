# WorldBox Writer 架构

> 一份关于"这是什么、它怎么工作、如何扩展"的导览。
> 读者：第一次接触本项目代码的工程师。

## 一句话总结

这是一个**事件推演引擎**。它把"我要写一篇 100 章的网文"这个任务，从"让 LLM 直接写"重构成"先把故事以结构化的事件 DAG 推演完，再用 LLM 把事件渲染成散文"。

为什么要这样？因为长篇生成的核心难题不是"句子写不写得漂亮"，而是"100 章之后角色还记不记得自己姓什么"——即**逻辑一致性**。先固化结构、再渲染文字，是用工程化手段解决这个问题的核心选择。

---

## 顶层结构

整个系统是一根**有向无环图**的推演循环，每轮（一个 tick）跑一次：

```
用户前提 (一句话)
    │
    ▼
[Director 初始化世界]──────[WorldBuilder 补全细节]
    │
    ▼  (tick 循环开始)
[Director 规划本幕：ScenePlan]
    │
    ▼
[Actor 决策：ActionIntent × N 个角色]  ←── 每个角色一个独立 LLM 调用
    │
    ▼
[Critic 审查：accept/reject 每个 intent]
    │
    ▼
[GM 结算：accepted intents → SceneScript]  ←── 唯一事实源
    │
    ▼
[GateKeeper 硬约束校验]  ←── HARD 违反 → 阻断推演
    │
    ▼
[NodeDetector 固化节点 + 判断是否需要用户干预]
    │
    ├── 需要干预 → 暂停 → 等用户指令
    │
    ▼
[Narrator 渲染：SceneScript → 800-2000 字小说正文]
    │
    ▼
[继续下一 tick | 结束]
```

每一步产出的都是**结构化数据**（JSON），不是自然语言。最后一步才把结构化数据扩写成散文。

---

## 三个角色组

按职责，系统可以分成三个组。**它们不是分层调用——是同一根循环上的不同步骤**。

### 故事编排组：决定"接下来发生什么"

| 组件 | 职责 | 关键产出 |
|---|---|---|
| **Director** | 接收前提，初始化世界；每轮规划 ScenePlan（objective / 重点角色 / 压力值） | `ScenePlan` |
| **WorldBuilder** | 扩写世界规则、势力、地理、力量体系 | `WorldState.factions/locations/world_rules` |
| **NodeDetector** | 决定是否需要用户干预（关键分歧点） | `InterventionSignal` |

### 角色扮演组：决定"角色做什么"

| 组件 | 职责 | 关键产出 |
|---|---|---|
| **Actor** × N | 每个 spotlight 角色独立 LLM 调用，**只看自己的私有记忆 + 公开场景**，不看其他角色意图 | `ActionIntent` |

> 这是整套架构的核心反直觉点：**角色在决策时互相不知道对方在想什么**。这种"信息物理隔离"是避免 LLM 串戏、幻觉的关键。每个角色单独起一个 LLM 实例，各自有独立的 prompt context。

### 校验结算组：决定"哪些能写进故事"

| 组件 | 职责 | 关键产出 |
|---|---|---|
| **Critic** | 廉价 LLM 策略审查：判断每个 intent 是否符合世界观 | `IntentCritique` (accepted/rejected) |
| **GateKeeper** | 硬约束检查：用户约束、HARD violation 直接阻断 | `ConstraintViolation` |
| **GM** | 结算所有 accepted intent 为本轮的**唯一事实源** | `SceneScript` |
| **Narrator** | 把 SceneScript + 三层记忆渲染成自然语言正文 | `rendered_text` |

> GM 是"事实守门员"：在 Critic 通过之后，GM 决定哪些 intent 真正进入 SceneScript，哪些合并、哪些降级。SceneScript 一旦产出就是权威——Narrator 不能改写事实。

---

## 一次 Tick 的完整数据流

把上面那张图展开成数据流：

```
输入: WorldState (上一 tick 的世界状态)
        │
        ▼
   ┌─── Director.plan_scene() ───┐
   │   输入: 前提 + 上一节点 + 当前世界
   │   输出: ScenePlan {
   │     objective, spotlight_character_ids,
   │     narrative_pressure: "calm" | "balanced" | "intense",
   │     ...
   │   }
   └────────────────────────────┘
        │
        ▼
   ┌─── Actor (并发 fan-out) ─────┐
   │   每个 spotlight 角色:
   │     - 拿自己的 prompt (性格卡 + 私有记忆 + 公开场景)
   │     - 调一次 LLM
   │     - 输出 ActionIntent {
   │         actor_id, action_type, summary,
   │         target_ids, confidence, ...
   │       }
   └────────────────────────────┘
        │
        ▼
   ┌─── Critic.review_batch() ───┐
   │   对每个 intent 调一次 LLM (廉价)
   │   输出: IntentCritique {
   │     accepted, reason_code, severity,
   │     revision_hint
   │   }
   │   拒绝的 intent 不进 SceneScript
   └────────────────────────────┘
        │
        ▼
   ┌─── GM.settle_scene() ────────┐
   │   聚合所有 accepted intents
   │   输出: SceneScript {
   │     scene_id, title, summary,
   │     public_facts, beats[],
   │     participating_character_ids,
   │     rejected_intent_ids,  ← prompt guard 防止被写入正文
   │   }
   │   ★ 这是本 tick 的唯一事实源
   └────────────────────────────┘
        │
        ▼
   ┌─── GateKeeper.validate() ────┐
   │   比对 SceneScript.beats 与 WorldState.constraints
   │   任何 HARD violation → 阻断整个 tick
   │   SOFT violation → 警告但放行
   └────────────────────────────┘
        │
        ▼
   ┌─── NodeDetector ─────────────┐
   │   检查 scene_script 是否包含 "分歧点" (关键决策 / 状态转折)
   │   输出: InterventionSignal { should_intervene, urgency }
   │   触发用户介入: needs_intervention = True
   └────────────────────────────┘
        │
        ▼
   ┌─── Narrator.render() ────────┐
   │   输入: SceneScript + 角色记忆 + 风格指令
   │   输出: 800-2000 字中文小说正文 (prose)
   │   严格遵守: 不改写 facts, 不写 rejected_intent_ids 对应内容
   └────────────────────────────┘
        │
        ▼
   StoryNode {
     id, title, tick, branch_id,
     rendered_text,     ← 用户看到的
     scene_script,      ← 持久化 (事实源)
     rejected_intents,  ← 防止漂移
   }
```

### 关键的"防漂移"约束

- **拒绝的 intent 不会被遗忘**：`rejected_intent_ids` 字段被持久化、传给 Narrator、写到 prompt guard 里。
- **事实与文笔分离**：Narrator 不能改写 SceneScript；它只能扩写。
- **每个 tick 独立**：重放或跳过 tick 不应改变 WorldState。

---

## 三个认知记忆层

解决长篇"遗忘"问题。每个角色都有三层记忆：

| 层 | 范围 | 写入方式 | 召回方式 |
|---|---|---|---|
| **工作记忆** (Character.memory) | 最近 20 条事件 | 推演中同步追加 | 直接进 prompt |
| **情景记忆** (MemoryEntry) | 全部历史事件 | tick 提交时按重要性持久化 | 向量检索 (ChromaDB) |
| **反思记忆** | 跨多条事件的总结 | 后台异步聚合（"经历三次被骗 → 生性多疑"） | 写到 Character.metadata.reflection_notes |

向量检索默认使用 ChromaDB，可在 `MEMORY_VECTOR_BACKEND=auto` 下自动 fallback 到 SQLite BM25。

---

## 持久化模型

### 三个 SQLite 表

| 表 | 存什么 | 为什么这样存 |
|---|---|---|
| `sessions` | 完整 WorldState JSON + 渲染节点 + telemetry | WorldState 是 Pydantic model，dump 出来就行 |
| `memory_entries` | 每个角色的情景/反思记忆条目 | 按 sim_id + character_id + tick 索引 |
| `branch_seed_snapshots` | (sim_id, node_id, branch_id) → WorldState 快照 | 关键：用于分支 fork，**不重放历史** |

### 分支恢复为什么用 snapshot 而不是 history replay？

因为 LLM 推演是**非确定性的**——同样的 prompt 调 LLM 两次会得到不同输出。如果从历史 replay，会得到不同的故事线。

所以 fork 时直接从**该节点的 WorldState 快照**开始，把"那一刻的世界"完整恢复，后面的推演以新分支的身份继续。

---

## LangGraph Wiring

`engine/graph.py` 把上面的循环编译成 LangGraph StateGraph。State 形状：

```python
class SimulationState(TypedDict):
    world: WorldState              # 核心状态
    memory: MemoryManager          # 三层记忆
    scene_plan: Optional[ScenePlan]
    action_intents: list[ActionIntent]
    intent_critiques: list[IntentCritique]
    scene_script: Optional[SceneScript]
    candidate_event: str           # 旧路径占位（生产路径用 scene_script）
    validation_passed: bool
    needs_intervention: bool
    initialized: bool
    world_built: bool
    max_ticks: int
    error: str
    sim_id: str
    trace_id: str
    streaming_callbacks: Dict[str, Any]  # SSE callback 句柄
```

节点顺序：

```
director_node → scene_director_node → actor_node → gate_keeper_node
                                                            ↓
                                                    node_detector_node
                                                            ↓
                                            narrator_node (conditional)
                                                            ↓
                                            world_builder_node (conditional, 首次)
                                                            ↓
                                            back to scene_director_node
```

LangGraph 提供 `interrupt_before` 支持关键节点的用户干预（NodeDetector 触发时暂停推演，等用户输入）。

---

## LLM 接入

- **统一入口**：`chat_completion_with_profile(profile_id, messages)` 走 `agent_profiles.yaml` 中的 profile
- **三层路由**：`logic` / `creative` / `role` 三种 role 在不同 provider 之间路由
- **支持 provider**：MiMo (默认) / Kimi / OpenAI / Ollama (本地)
- **降级**：当某 provider 的 benchmark score 低于阈值时自动回退到全局默认

Prompt 模板放在 `src/worldbox_writer/prompts/*.yaml`，运行时通过 `PromptRegistry` 加载，支持 `PROMPT_TEMPLATE_DIR` 环境变量覆盖而不需要改代码。

---

## 双循环运行时（当前生产路径）

`engine.dual_loop_enabled` 是一个**功能开关**（`FEATURE_DUAL_LOOP_ENABLED`，默认 `True`）。开启时走"双循环"——即 Actor 输出 `ActionIntent` 后必须经 Critic + GM 才生成 `SceneScript`；关闭时回退到"单循环"——Actor 直接输出候选事件文本（用于紧急回滚，**生产中永远走双循环**）。

### 为什么叫"双循环"？

- **内循环**：每 tick 的 Actor → Critic → GM 回路
- **外循环**：Narrator 把 SceneScript 扩写成正文、用户在前端读到结果

两层循环嵌套，内层负责"事实"，外层负责"文笔"。

---

## API 层

`api/server.py` 是 FastAPI 入口。三个核心路由：

| 路由 | 用途 |
|---|---|
| `POST /api/simulate/start` | 新建推演 |
| `GET /api/simulate/{id}/stream` | **SSE** 实时事件流（每个 tick 的 telemetry、节点更新、渲染完成） |
| `GET /api/simulate/{id}/dual-loop/compare` | 双循环 vs 单循环对比报告（用于灰度决策） |
| `GET /api/simulate/{id}/inspector` | Prompt Inspector：展示每次 LLM 调用的完整 prompt 与召回的记忆 |

SSE 推送的事件类型：节点提交、telemetry、LLM 路由、渲染进度——前端不轮询，所有状态由服务端 push。

---

## 前端

React + TypeScript + Vite。核心交互：

- **创作工作台**：左窗格推演事件流（时间倒序），右窗格渲染正文
- **Inspector**：点击任何角色，查看它最近一次 LLM 调用的完整 prompt 模板 + 注入的私有记忆片段
- **Prompt 编辑器**：用户可在 `prompts/*.yaml` 直接修改模板，热加载生效（无需重启服务）

---

## 关键设计决策

| 决策 | 原因 |
|---|---|
| 推演和渲染分离 | Token 短 + 结构化 + 单独 prompt = 幻觉率指数级下降；事实一旦固化就锁死 |
| 角色信息物理隔离 | 每个 Actor 独立 LLM 实例 + 独立 prompt context，从架构层杜绝"偷看剧本" |
| GM 作为唯一事实源 | SceneScript 是契约，谁也不能改写它——Narrator 也不行 |
| 分支用 snapshot 而非 replay | LLM 非确定性，replay 会得到不同故事 |
| Prompt 外部化为 YAML | 让 prompt 作者不需要改 Python 代码；支持热加载与环境覆盖 |
| Narrator 接收 rejected_intent_ids | 防止"我说不让写但 LLM 写了"的漂移 |
| 拒绝的 intent 持久化 | 否则下一 tick 的 Critic 没法避免重复犯同样的错 |

---

## 如何扩展

| 你想加什么 | 该改哪里 |
|---|---|
| 新的 Agent（比如"音乐 Agent"在场景里放背景音乐） | `agents/` 加文件 + `engine/graph.py` 加节点 + `engine/services/` 加业务逻辑 + `prompts/` 加 yaml |
| 新的状态字段（比如"角色心情"） | `core/models.py` 加 Pydantic field + `engine/state.py` 改 TypedDict |
| 新的 LLM provider | `utils/llm.py` 加 transport + `agent_profiles.yaml` 加 profile |
| 新的 LLM 路由策略 | `utils/llm.py` 改 `_should_fallback` |
| 新的约束类型 | `core/models.py` 加 `ConstraintType` enum |
| 新的渲染风格 | `prompts/narrator_system.yaml` 加 `system_variants` 键 |
| 新的 SSE 事件类型 | `engine/services/telemetry_service.py` 加 emit + 前端 `types/index.ts` 加类型 |
| 新的分支恢复策略 | `engine/services/actor_turn_service.py`（已经有 `FEATURE_DUAL_LOOP_ENABLED` 开关模式可以参考） |

---

## 几个容易混淆的概念

| 概念 | 不是你想的那个 | 它是 |
|---|---|---|
| "tick" | 不是程序循环的 tick | 一个完整的"导演→演员→审→算→渲"周期 |
| "scene" | 不是 HTML 标签 | Director 规划的一"幕"，可能跨多个 tick |
| "branch" | 不是 Git branch | 用户在某个 StoryNode 上做的"分叉选择"，对应一个独立的推演支线 |
| "intent" | 不是命令行 | 角色的"想做什么"——动词级（拔剑/逃跑/对话） |
| "beat" | 不是音频 beat | SceneScript 的一个剧情点（一个动作 + 一个结果） |
| "fast-forward" | 不是跳过 | Narrator 跳过文学渲染，直接把 SceneScript 压缩为概要文字 |

---

## 进一步阅读

- [DEVELOPMENT.md](../development/DEVELOPMENT.md) — 环境、命令、CI、灰度与回滚、双循环 rollout 流程
- [QUALITY_SPEC.md](../product/QUALITY_SPEC.md) — 评测系统（12 维 prose + 12 维 story + 7 维 AI-issue）
- [PRODUCT_STRATEGY.md](../product/PRODUCT_STRATEGY.md) — 产品定位与演进路线
