# WorldBox Writer — Architecture Reference

> 真相源是 `src/`。本文档是**代码地图**，不是设计宣言。
> 每个声明都给出 `file:line` 锚点。如发现本文与代码不一致，**代码为准**。

## 目录

1. [一句话总结](#1-一句话总结)
2. [顶层 tick 循环](#2-顶层-tick-循环)
3. [8 个 Agent](#3-8-个-agent)
4. [14 个 Engine Service](#4-14-个-engine-service)
5. [LangGraph Wiring](#5-langgraph-wiring)
6. [Pydantic 契约](#6-pydantic-契约)
7. [4 个 SQLite 表](#7-4-个-sqlite-表)
8. [21 个 API 端点](#8-21-个-api-端点)
9. [10 个前端组件](#9-10-个前端组件)
10. [LLM 接入与 Prompt Registry](#10-llm-接入与-prompt-registry)
11. [角色记忆与状态](#11-角色记忆与状态)
12. [双循环运行时](#12-双循环运行时)
13. [Gotchas 与 Invariants](#13-gotchas-与-invariants)
14. [扩展地图](#14-扩展地图)
15. [术语表 + 进一步阅读](#15-术语表--进一步阅读)

---

## 1. 一句话总结

这是一个**结构化推演 + 渲染管线**：每轮（一个 tick）让 LLM 产出结构化 JSON 事件，再让另一个 LLM 把结构化事件扩写成中文网文。结构化层负责"事实"（角色做了什么、结果是什么），渲染层负责"文笔"。所有跨 tick 的事实固化在 `WorldState` + `StoryNode` 里，渲染层只能读取、不能改写。

---

## 2. 顶层 tick 循环

每轮（一个 tick）跑一次完整循环。所有调用都是结构化数据，最后一步才渲染散文。

```
Director.plan_scene()                              [agents/director.py:97]
    │ 产出 ScenePlan
    ▼
Actor 并发 fan-out (每个 spotlight 角色一次 LLM)  [engine/services/isolated_actor_service.py]
    │ 产出 ActionIntent × N
    ▼
Critic.review_intent()                            [agents/critic.py:64]
    │ 产出 IntentCritique (accepted/rejected)
    ▼
GM.settle_scene()                                  [agents/gm.py:77]
    │ 产出 SceneScript (本 tick 唯一事实源)
    ▼
GateKeeper.validate()                              [agents/gate_keeper.py:78]
    │ HARD 违反 → 阻断整个 tick
    ▼
NodeDetector.evaluate()                            [agents/node_detector.py:108]
    │ 产出 InterventionSignal (should_intervene)
    ├── 触发用户介入 → 暂停
    ▼
SceneNode 固化 + Narrator 渲染                    [engine/services/narration_service.py]
    │ 产出 800-1500 字中文网文（`prompts/narrator_system.yaml:11`）
    ▼
下一 tick 或结束
```

每一步都产出**结构化 Pydantic 对象**（不是裸 dict）。最后一步才把 SceneScript 扩写为散文。

---

## 3. 8 个 Agent

| 文件 | 类 | 关键方法 → 返回 | 角色 |
|---|---|---|---|
| `agents/director.py:61` | `DirectorAgent` | `plan_scene() → ScenePlan` | 故事编排（每 tick 规划本幕）|
| `agents/world_builder.py:30,43` | `WorldBuilderAgent` | `expand_world() → WorldState` | 世界观扩写（首次时异步补全）|
| `agents/actor.py:49` | `ActorAgent` | `propose_action() → ActionProposal` | **legacy 路径**，生产用 `isolated_actor_service` |
| `agents/critic.py:46` | `CriticAgent` | `review_intent() → IntentCritique` | intent 策略审查 |
| `agents/gate_keeper.py:65` | `GateKeeperAgent` | `validate() → ValidationResult` | HARD/SOFT 约束校验 |
| `agents/gm.py:74` | `GMAgent` | `settle_scene() → SceneScript` | accepted intents → SceneScript 结算 |
| `agents/node_detector.py:91` | `NodeDetector` | `evaluate() → InterventionSignal` | 决定是否需要用户介入 |
| ~~`agents/narrator.py`~~ | — | (Sprint 26 已删) | narration 移到 `engine/services/narration_service.py` |

> **重要区分**：生产路径**不直接调用 `ActorAgent.propose_action()`**。Actor 类的该方法返回 `ActionProposal`（legacy 单事件流），**生产用的 `ActionIntent` 是 `isolated_actor_service.run_isolated_actor_runtime()` 产出的**（`isolated_actor_service.py:116`）。详见 §13 gotcha #1。

---

## 4. 14 个 Engine Service

`engine/services/` 下 14 个模块，把业务实现从 agent 类里抽出来。

| 服务 | 职责 | 主入口 |
|---|---|---|
| `actor_event_service.py` | legacy actor prompt 装配 | `build_actor_event_payload()` |
| `actor_prompt_context_service.py` | 构造 actor 的 prompt | `build_actor_prompt()` |
| `actor_runtime_service.py` | actor runtime metadata 持久化到 `world.metadata` | `record_actor_runtime()` |
| **`actor_turn_service.py`** | 调度 `runtime_actor_turn`（生产）vs `legacy_actor_turn` | `dispatch_actor_turn()` |
| `boundary_revision_service.py` | 修订被拒绝的 candidate event | `revise_rejected_event()` |
| `boundary_validation_service.py` | HARD/SOFT 约束检查 | `validate_against_boundaries()` |
| **`isolated_actor_service.py`** | **生产路径**：per-character 独立 LLM 调用 + 产出 `ActionIntent` | `run_isolated_actor_runtime()` |
| `narration_service.py` | SceneScript → 中文散文（替代已删的 `narrator.py`） | `render_scene_prose()` |
| `node_commit_service.py` | 提交 StoryNode | `commit_node()` |
| `node_lifecycle_service.py` | 节点生命周期（commit + 介入检测）| `run_node_lifecycle()` |
| `relationship_service.py` | 角色关系更新 | `update_relationships()` |
| `simulation_runner_service.py` | 顶层 runner | `run_simulation()` |
| `telemetry_service.py` | 发出 SSE telemetry 事件 | `emit_telemetry()` |
| `world_setup_service.py` | 世界初始化、场景规划、world builder | `setup_world()` |

**两个粗体是生产路径的关键服务**：`actor_turn_service` 决定走哪条路，`isolated_actor_service` 实际调 LLM。

---

## 5. LangGraph Wiring

`engine/graph.py:395-405` 编译了 7 个节点的 StateGraph（`build_simulation_graph()`）。**Critic 和 GM 不是独立 graph 节点**——它们作为 factory 注入到 `actor_node` 里。

```
director_node          (首次: 解析前提, 初始化世界)
  → scene_director_node (每 tick: 规划本幕)
  → actor_node          (内部: →isolated_actor →critic →gm → action_intents + scene_script)
  → gate_keeper_node    (约束校验)
  → node_detector_node  (固化节点, 判断介入)
  → narrator_node       (渲染正文, 条件)
  → world_builder_node  (首次条件)
  → scene_director_node (循环)
```

**关键修正**（澄清常见误解）：
- `actor_node` 内部**调 4 次 LLM**（per-character isolated + critic + gm）
- 完整 graph 只有 **7 个节点**，不是 9 个
- `critic_factory=CriticAgent` 和 `gm_factory=GMAgent` 在 `graph.py:221-222` 注入到 `actor_node`

```python
# engine/state.py:20 - SimulationState
class SimulationState(TypedDict):
    world: WorldState                  # 核心状态
    memory: MemoryManager              # 三层记忆
    scene_plan: Optional[ScenePlan]
    action_intents: list[ActionIntent]
    intent_critiques: list[IntentCritique]
    prompt_traces: list[PromptTrace]   # 每次 LLM 调用记录一条（debug 用）
    scene_script: NotRequired[Optional[SceneScript]]
    candidate_event: str               # 旧路径占位（生产不用）
    validation_passed: bool
    needs_intervention: bool
    initialized: bool
    world_built: bool
    max_ticks: int
    error: str
    sim_id: str
    trace_id: str
    streaming_callbacks: Dict[str, Any]
```

---

## 6. Pydantic 契约

`core/dual_loop.py` 定义了 dual-loop 的数据契约。

### `ScenePlan` (`core/dual_loop.py:114`) — Director 产出
```python
scene_id, branch_id, tick, title, objective, conflict_type, suspense_hook,
setting, public_summary, spotlight_character_ids, narrative_pressure,
constraints, source_node_id
# Default: narrative_pressure="balanced", conflict_type="external"
```

### `SceneScript` (`core/dual_loop.py:133`) — GM 产出（事实源）
```python
script_id, scene_id, branch_id="main", tick=0, title, summary,
public_facts, participating_character_ids,
accepted_intent_ids,              # accepted by Critic → goes into beats
rejected_intent_ids,              # excluded from beats
beats,                            # List[SceneBeat]
source_node_id, metadata
# accepted_intent_ids + rejected_intent_ids 一起：保证 beat 仅来自 accepted intents
```

### `ActionIntent` (`core/dual_loop.py:52`) — Actor 产出
```python
intent_id, scene_id, actor_id, actor_name, action_type, summary,
rationale, target_ids, confidence (0-1), prompt_trace_id
# Default: action_type="action", confidence=0.5
# ⚠ action_type 是 str，不是 enum。prompt 文档建议 "dialogue|action|decision|reaction" 但代码不强制
```

### `IntentCritique` (`core/dual_loop.py:68`) — Critic 产出
```python
critique_id, scene_id, intent_id, actor_id, actor_name,
accepted (bool), reason_code, severity, reason, revision_hint
# Default: accepted=True, reason_code="accepted", severity="info"
```

### `SceneBeat` (`core/dual_loop.py:101`)
```python
beat_id, actor_id, actor_name, summary, outcome,
visibility ("public"|"private"|"secret"), source_intent_id
```

### `NarratorInput` (`core/dual_loop.py:151`) — 传给 Narrator
```python
contract_version: str = "narrator-input-v2"   # ⚠ 默认值里还带 "v2" 后缀
source: str = "story_node"                   # "scene_script"（生产）| "story_node"（fallback）
scene_id, script_id, title, summary, public_facts, beats,
participating_character_ids, rejected_intent_ids, memory_context,
character_summaries, location_context, metadata
# 字段默认值 `contract_version="narrator-input-v2"` 是历史命名残留，不要改
```

### `InterventionSignal` (`agents/node_detector.py:31`)
```python
should_intervene: bool
urgency: str  # "low" | "medium" | "high" | "critical"（不强制）
reason, context, suggested_options
```

### `PromptTrace` (`core/dual_loop.py:36`)
```python
trace_id, agent, scene_id, character_id, system_prompt, user_prompt,
assembled_prompt, narrative_pressure, visible_character_ids,
memory_trace, metadata
```

---

## 7. 4 个 SQLite 表

`storage/db.py:42-96` 定义了 4 个表。

| 表 | 主键 | 存什么 | 用途 |
|---|---|---|---|
| `worlds` | `world_id` | `WorldState` Pydantic dump 到 `state_json` | WorldState 的 canonical 持久化 |
| `sessions` | `sim_id` | session 状态、nodes_json、telemetry_events、metadata | session-level 状态 |
| `memory_entries` | `entry_id` | per-character episodic memory + 可选 vector embedding | 角色记忆向量检索 |
| `branch_seed_snapshots` | `(sim_id, node_id, branch_id)` | fork 时点的 `WorldState` 快照 | **分支 fork**（用 snapshot 不 replay） |

**`seed_kind` 列**（`storage/db.py:72`）默认值 `'world_state_v1'` 是历史命名残留，写但从不读。详见 §13 gotcha #6。

---

## 8. 21 个 API 端点

`api/routes/{simulations,branches,workspace}.py` 共定义 21 个端点，**其中 20 个是业务端点**（`/health` 也算在表内）。

### 仿真核心 (`api/routes/simulations.py`)
| 方法 | 路径 | 行 | 用途 |
|---|---|---|---|
| GET | `/api/health` | 42 | 健康检查 + LLM 配置信息 |
| POST | `/api/simulate/start` | 50 | 启动新推演 |
| GET | `/api/simulate/{id}` | 54 | 拉取当前推演状态 |
| GET | `/api/simulate/{id}/diagnostics` | 58 | 内存/路由/成本摘要 |
| GET | `/api/simulate/{id}/inspector` | 146 | Prompt Inspector：完整 prompt + 召回记忆 |
| GET | `/api/simulate/{id}/dual-loop/compare` | 191 | 双循环 vs 单循环对比报告 |
| POST | `/api/simulate/{id}/intervene` | 215 | 提交用户干预指令 |
| GET | `/api/simulate/{id}/export` | 221 | 导出 bundle（TXT/MD/HTML/DOCX/PDF） |
| GET | `/api/simulate/{id}/export/file` | 225 | 下载导出文件 |
| GET | `/api/simulate/{id}/stream` | 247 | **SSE 实时事件流** |
| GET | `/api/sessions` | 291 | 列出最近会话 |

### 分支 (`api/routes/branches.py`)
| 方法 | 路径 | 行 | 用途 |
|---|---|---|---|
| POST | `/api/simulate/{id}/branch` | 20 | 从历史节点 fork |
| POST | `/api/simulate/{id}/branch/switch` | 26 | 切换活跃分支 |
| GET | `/api/simulate/{id}/branch/compare` | 30 | 主线/支线对比 |
| POST | `/api/simulate/{id}/branch/pacing` | 34 | 设置分支节奏档位 |

### 工作区编辑 (`api/routes/workspace.py`)
| 方法 | 路径 | 行 | 用途 |
|---|---|---|---|
| PATCH | `/api/simulate/{id}/characters/{char_id}` | 21 | 编辑角色属性（waiting 状态） |
| PATCH | `/api/simulate/{id}/relationships` | 27 | 建立/修改角色关系 |
| PATCH | `/api/simulate/{id}/world` | 31 | 编辑世界设定 |
| POST | `/api/simulate/{id}/constraints` | 35 | 添加约束 |
| PUT | `/api/simulate/{id}/wiki` | 39 | 保存 Wiki 设定 |
| PATCH | `/api/simulate/{id}/nodes/{node_id}/rendered-text` | 43 | 保存富文本正文 |

**SSE 事件类型**（从 `engine/services/telemetry_service.py`）：节点提交、telemetry、LLM 路由、渲染进度。前端不轮询，全由服务端 push。

---

## 9. 10 个前端组件

`frontend/src/components/` 下 10 个 React 组件（不含 `*.test.tsx`）。

| 文件 | 组件 | 渲染什么 |
|---|---|---|
| `StartPanel.tsx` | `StartPanel` | 启动新推演的表单 |
| `StoryFeed.tsx` | `StoryFeed` | tick 事件流（时间倒序） |
| `BranchPanel.tsx` | `BranchPanel` | 分支树 + 切换 UI |
| `ExportPanel.tsx` | `ExportPanel` | 导出/下载控制 |
| `RelationshipPanel.tsx` | `RelationshipPanel` | 角色关系图谱 |
| `InterventionPanel.tsx` | `InterventionPanel` | 导演指令 modal |
| `WorldPanel.tsx` | `WorldPanel` | 世界状态查看 |
| `EditPanel.tsx` | `EditPanel` | 编辑角色/世界/关系 |
| `RichTextEditor.tsx` | `RichTextEditor` | 富文本正文编辑器 |
| `Header.tsx` | `Header` | 应用 chrome（顶部导航） |

---

## 10. LLM 接入与 Prompt Registry

### 统一入口
- **`chat_completion_with_profile(profile_id, messages)`** — `utils/llm.py`
- 通过 `agent_profiles.yaml` 中的 profile 路由
- 不再存在公共 `chat_completion(...)`（Sprint 26 已私有化为 `_execute_chat_completion`）

### 三层路由
- `logic` / `creative` / `role` — 决定 provider 优先级
- `agent_profiles.yaml` 定义每个 profile_id 的 temperature / max_tokens / top_p

### 支持的 provider
- **MiMo** (默认) / Kimi / OpenAI / Ollama (本地)
- benchmark score < 阈值时自动回退到全局默认（`utils/llm.py:_should_fallback`）

### Prompt 模板
- **`src/worldbox_writer/prompts/`** — 外部化 prompt（**markdown + YAML frontmatter**）
  - 按 role 分组到子目录：`actor/` / `critic/` / `director/` / `evals/` / `engine/` / `gate_keeper/` / `memory/` / `narrator/` / `node_detector/` / `world_builder/`
  - 顶层 `catalog.json` 是 agent → prompt 的唯一映射表（启动时校验）
  - `_schema.md` 描述 markdown 文件结构（frontmatter schema + variant 机制）
  - `_` 前缀的文件/目录被加载器忽略（用于本地笔记、设计文档）
- **`prompting/registry.py`** — `PromptCatalog` 类负责 glob 扫描、按 id 索引、mtime 缓存、热重载
- **`PROMPT_TEMPLATE_DIR`** 环境变量仍可指定 override 目录（用于本地试调，不进 git）
- **运行时热加载**（按 mtime 缓存）— **仅适用于 prompt md / yaml**。agent_profiles.yaml 不热加载（见 gotcha #13）

### 加一个新 prompt（4 步，**不改 Python 代码**）
1. 在 `prompts/<role>/` 下创建 `<prompt_id>.md`，含 frontmatter（`id` / `version` / `role` / `changelog`）和 body
2. （可选）把 id 加到 `catalog.json` 的对应 role 的 `prompts` 列表里
3. agent 代码调 `load_prompt_template("<prompt_id>")` 或 `load_prompt_template("<prompt_id>", variant="<name>")`
4. 下次 LLM 调用时生效（mtime 缓存触发 reload）

### Profile 列表（`src/worldbox_writer/config/agent_profiles.yaml`）
Sprint 26 后剩 22 个 profile，按 role 分组：
- **director** (3): `director_init` / `director_intervention` / `director_title`
- **actor** (3): `actor_event`（legacy）/ `actor_intent`（dual-loop）/ `model_eval_logic_structured_action`
- **critic / gate_keeper** (3): `critic_review` / `gate_keeper_validate` / `boundary_reviser`
- **narrator** (3): `narrator_render` / `model_eval_creative_scene` / `model_eval_creative_dialogue`
- **node_detector** (1): `node_detector`
- **world_builder** (3): `world_builder_expand` / `world_builder_location` / `model_eval_creative_worldbuild`
- **memory** (4): `memory_consistency` / `memory_character_arc` / `memory_summarize` / `model_eval_logic_memory_summary`
- **judge** (2): `judge_committee` / `judge_multi_chapter`

---

## 11. 角色记忆与状态

### 角色属性 (`core/models.py:90` `Character`)
```python
id, name, description, personality, goals, status,
relationships: Dict[str, Relationship],
memory: List[str],                   # ⚠ 工作记忆：上限 20，append-only
metadata: Dict[str, Any]             # ⚠ 反思记忆存在这里
```

### `WorldState` (`core/models.py:315`)
```python
world_id, title, premise,
world_rules, factions, locations,    # WorldBuilder 扩写
characters: Dict[str, Character],
nodes: Dict[str, StoryNode],
current_node_id,
branches: Dict[str, Dict],            # 分支元数据
active_branch_id: str = "main",
constraints: List[Constraint],
pending_intervention, intervention_context,
tick, is_complete, metadata
```

### 实际持久化（**纠正"三个认知记忆层"的过度包装**）

| 层 | 实际存储 | 性质 |
|---|---|---|
| 工作记忆 | `Character.memory: List[str]` | Python list，append-only，**上限 20 条** |
| 情景记忆 | `memory_entries` 表（`storage/db.py:81`）+ 可选 vector embedding | 真正可向量检索 |
| 反思记忆 | `Character.metadata["reflection_notes"]: List[str]`（`memory/memory_manager.py:629`） | **就是个 metadata list，不是独立 tier** |

> **不是"后台异步聚合系统"**，是手工调 `MemoryManager.assess_consistency()` / `get_character_arc()` 触发的同步操作，输出写到 `reflection_notes` metadata 字段。

### 向量检索后端
- 默认 `chroma`，`MEMORY_VECTOR_BACKEND=auto` 时 fallback 到 SQLite BM25
- 配置：(`MEMORY_VECTOR_BACKEND`, `MEMORY_VECTOR_PATH`, `MEMORY_VECTOR_COLLECTION`)

---

## 12. 双循环运行时

**生产路径**（`FEATURE_DUAL_LOOP_ENABLED=True`，默认）：

```
actor_turn_service.run_actor_turn(world, memory, scene_plan=...)
  → if dual_loop_enabled_func() and scene_plan:
      → runtime_actor_turn(...)
        → isolated_actor_service.run_isolated_actor_runtime()  [PER-CHARACTER LLM]
        → critic.review_batch(world, scene_plan, action_intents)    [1× LLM]
        → gm.settle_scene(world, scene_plan, accepted_intents)      [1× LLM]
        → actor_runtime_service.persist_actor_runtime_metadata()    [写入 world.metadata]
      → return ActorTurnResult(...)
```

**为什么叫"双循环"**：
- **内循环**（logic loop）：每个 tick 的 Actor → Critic → GM 回路
- **外循环**（prose loop）：Narrator 把 SceneScript 扩写成正文

**Legacy 单循环路径**（`legacy_actor_turn`，`FEATURE_DUAL_LOOP_ENABLED=False`）：保留作为**紧急回滚**用。生产永远走双循环。

**内/外循环的命名是比喻**，代码上没有"内循环节点 / 外循环节点"这样的 LangGraph 划分——它们都是 `actor_node` 内部的子调用。

---

## 13. Gotchas 与 Invariants

**修改代码前必读**。每条都是"踩过的坑"或"易误解的地方"。

1. **`ActorAgent.propose_action()` 返回 `ActionProposal`，不是 `ActionIntent`**（`agents/actor.py:62`）。生产用的 `ActionIntent` 是 `isolated_actor_service.run_isolated_actor_runtime()` 产出的（`isolated_actor_service.py:116`），它在内部对每个 spotlight 角色调 `invoke_isolated_actor_intent`（line 188）拼出 `ActionIntent`。别混淆。
2. **Critic 和 GM 不是 LangGraph 节点**，是 factory 注入到 `actor_node` 的 callable（`graph.py:221-222`）。改 Critic/GM 行为时改 agent 类，**不要**在 `graph.py` 加节点。
3. **`ActionIntent.action_type` 是 `str = "action"`**（`core/dual_loop.py:59`），**不是 enum**。prompt 文档建议 `"dialogue|action|decision|reaction"`，但代码不强制。加新 value 不需要改 schema。
4. **`NarratorInput.contract_version` 默认值是 `"narrator-input-v2"`**（`core/dual_loop.py:154`），是历史命名残留。**改这个值会破坏 Inspector 输出的兼容**。
5. **node.metadata 里存的是 `narrator_input`**（不是 `narrator_input_v2`，Sprint 26 已重命名）。`api/core/serialization.py:61` 读这个 key。
6. **`WorldState` 是真正的"事实源"**（不是 `SceneScript`）。`SceneScript` 是 per-tick 的"本幕事实"，但 `WorldState.nodes` 持久化全部 tick。GM 不是唯一事实源，**只是 per-tick 唯一结算者**。
7. **`storage/db.py` 的 `seed_kind` 列**（schema 第 72 行）写但从不读——历史残留，**不要**依赖它做版本判断。
8. **branch fork 用 snapshot 不 replay**（`storage/db.py:323, 296-317`），因为 LLM 推演非确定性。replay 会得到不同故事线。
9. **"信息物理隔离"是比喻**。每个 Actor 用独立的 LLM 调用 + 独立的 prompt context，**但**同进程、同 `WorldState`、同 `MemoryManager`。找 process/sandbox 找不到。
10. **`NodeDetector` 触发介入**靠的是 LLM 调用（`node_detector` profile）+ 关键词扫描（**15 中文 + 18 英文 = 33 个**高风险关键词，定义在 `agents/node_detector.py:45-82` 的 `_HIGH_STAKES_KEYWORDS_ZH` / `_HIGH_STAKES_KEYWORDS_EN`）+ 每 5 tick 周期性检查，**不是**"scene_script 包含分歧点"。
11. **`Critic` 不一定用"廉价" LLM**——它走和 Actor 一样的 `chat_completion_with_profile`。"廉价"是 profile 路由选择（temperature 0.0, 廉价 prompt），不是不同引擎。
12. **dual-loop 路径是唯一生产路径**。`legacy_actor_turn` 仅作紧急回滚。`engine/dual_loop.py` 里的 `build_compatibility_intent` / `_derive_intent_summary` 等是 Sprint 26 stub（raise `NotImplementedError`），**别**在新代码里调用。
13. **改 profile_id 要重启服务**：`src/worldbox_writer/config/agent_profiles.yaml` 在启动时加载（`config/settings.py` 的 `PROFILES_FILE` 常量），热加载仅适用于 `prompts/` 下的 markdown / yaml。改了 profile 后下次启动生效。
14. **Graph state 是 TypedDict，不是 Pydantic**（`engine/state.py:20`）。新字段加在 `SimulationState` 里时，**所有** `_actor_node` / `scene_director_node` 等函数返回的 dict 都要对应更新。

---

## 14. 扩展地图

| 你想加什么 | 该改哪里 |
|---|---|
| 新的 Agent | 1) `src/worldbox_writer/agents/` 加新文件（参考 `actor.py:49` 类骨架）<br>2) `src/worldbox_writer/engine/graph.py:399-405` `add_node` 注册<br>3) `src/worldbox_writer/engine/services/` 加对应业务逻辑<br>4) `src/worldbox_writer/prompts/` 加 yaml<br>5) `src/worldbox_writer/config/agent_profiles.yaml` 加 profile_id |
| 新的 State 字段 | `engine/state.py:20` `SimulationState` 加字段，**所有** graph node 函数的返回 dict 都要更新 |
| 新的 LLM provider | `utils/llm.py` 加 `_build_client` 分支 + `_chat_completion_<provider>` 传输 |
| 新的 LLM 路由策略 | `utils/llm.py` 改 `_should_fallback` |
| 新的约束类型 | `core/models.py:42` `ConstraintType` enum |
| 新的渲染风格 | `prompts/narrator_system.yaml` 加 `system_variants` 键 |
| 新的 SSE 事件类型 | `engine/services/telemetry_service.py` 加 emit + `frontend/src/types/index.ts` 加类型 |
| 新的 SQLite 表 | `storage/db.py:42-96` 加 `CREATE TABLE`，记得加迁移逻辑（无 auto-migration framework）|

---

## 15. 术语表 + 进一步阅读

### 容易混淆的概念

| 概念 | 不是你想的那个 | 它是 |
|---|---|---|
| `tick` | 不是 CPU tick | 一个完整的 Director→Actor→Critic→GM→GateKeeper→Narrator 周期 |
| `scene` | 不是 HTML 标签 | Director 规划的一"幕"（可能跨多个 tick）|
| `branch` | 不是 Git branch | 用户在某个 StoryNode 上做的分叉选择 |
| `intent` | 不是命令行 | 角色的"想做什么"——动词级（对话/动作/决策/反应）|
| `beat` | 不是音频 beat | SceneScript 的一个剧情点（动作 + 结果）|
| `fast-forward` | 不是跳过 | Narrator 跳过文学渲染直接输出 SceneScript 概要 |

### 不在本文档范围
- 没有"100 章网文"等市场定位（见 `PRODUCT_STRATEGY.md`）
- 没有评测维度（见 `QUALITY_SPEC.md`）
- 没有开发/部署命令（见 `DEVELOPMENT.md`）
- 没有 Sprint 计划/历史（见 `docs/sprints/`）
- 本文档只描述"代码是什么"，不描述"代码应为什么"

### 进一步阅读

- [DEVELOPMENT.md](../development/DEVELOPMENT.md) — 环境、命令、CI、灰度与回滚、双循环 rollout 流程
- [QUALITY_SPEC.md](../product/QUALITY_SPEC.md) — 评测系统（12 维 prose + 12 维 story + 7 维 AI-issue）
- [PRODUCT_STRATEGY.md](../product/PRODUCT_STRATEGY.md) — 产品定位与演进路线
- `src/worldbox_writer/config/_schema.md` — env vars 和 agent profile_ids 完整清单
