# WorldBox Writer 架构设计

**文档状态**：Active  
**最后更新**：2026-04-29

本文档描述 WorldBox Writer 的整体架构与技术选型。
双循环推演引擎的详细设计与第一性原理推导，见 [DUAL_LOOP_ENGINE_DESIGN.md](DUAL_LOOP_ENGINE_DESIGN.md)。

---

## 1. 核心理念

系统不是"文本生成器"，而是"事件推演引擎"。

所有故事发展先在底层以**有向无环图（DAG）**形式推演并固化，再交由 LLM 进行文学性渲染。

目的：解决长篇小说生成的**逻辑一致性**与**用户干预持久性**问题。

---

## 2. 三层架构

### 2.1 世界推演层

维护世界物理规律、历史背景与角色自主行动。

- **Director**：产出 `ScenePlan`，决定每一幕的 objective、spotlight cast、叙事压力
- **WorldBuilder**：扩写世界规则、势力、地理，维护全局知识库（Vector DB）
- **Actor × N**：每个角色是独立 Agent，基于私有记忆与 ScenePlan 产出 `ActionIntent`

### 2.2 边界与结算层

系统的"大脑"与"裁判"，处理人类干预、保证世界不崩坏。

- **Critic**：意图级 LLM 策略审查，产出 `IntentCritique`（accepted / rejected）
- **GateKeeper**：节点级硬约束校验，HARD 违反阻断推演
- **GM**：结算 accepted intent，产出唯一 `SceneScript` 作为事实源
- **NodeDetector**：识别关键分歧节点，触发用户干预

### 2.3 表现与渲染层

将结构化数据转化为可读内容。

- **Narrator**：消费 `SceneScript` 与三层记忆上下文，渲染小说正文（`NarratorInput v2`）
- **Dashboard API**：提供实时事件流（SSE）、关系图谱与全局状态快照

---

## 3. 核心数据流

```
Director.plan_scene()
      │  产出 ScenePlan
      ▼
Actor fan-out (spotlight)
      │  每个角色私有 prompt → ActionIntent
      ▼
Critic.review_intents()
      │  accepted / rejected verdict
      ▼
GM.settle()
      │  SceneScript (单一事实源)
      ▼
GateKeeper.validate() ──┐
      │                 │ HARD 违反
      ▼                 ▼
NodeDetector         revision_hint / 阻断
      │
      ▼
Narrator.render()  ← SceneScript + 三层记忆
      │
      ▼
StoryNode.rendered_text
```

1. **初始化**：Director 接收用户前提，生成初始世界（WorldBuilder 异步补全）
2. **推演循环**：Actor 提议 → Critic 审查 → GM 结算 → GateKeeper 校验 → 固化节点
3. **渲染**：Narrator 立即将 SceneScript 渲染为正文，或跳过进入下一轮（快进模式）
4. **干预**：NodeDetector 检测到关键分歧时暂停，向用户请求干预

---

## 4. 技术栈

### 4.1 后端

| 组件 | 选型 | 理由 |
| :--- | :--- | :--- |
| 语言 | Python 3.11+ | 类型系统与生态匹配 |
| Agent 框架 | **LangGraph** | 有状态图执行，原生支持循环、分支、`interrupt_before` |
| API 框架 | **FastAPI** | 异步非阻塞，天然支持 SSE |

相比之下，CrewAI 偏线性任务流，AutoGen 状态管理复杂度过高。

### 4.2 存储

| 用途 | 当前选型 | 备注 |
| :--- | :--- | :--- |
| 持久化 | SQLite | `sessions.state_json` + `memory_entries` + `branch_seed_snapshots` |
| 向量检索 | ChromaDB (default `auto`) | 可 fallback 到 SQLite BM25 |
| 分支快照 | `branch_seed_snapshots` | 按 `sim_id + node_id + branch_id` 存完整 WorldState |

分支恢复采用 **snapshot 直接恢复**，不采用"重放历史"，因为 LLM 推演非确定性。

### 4.3 LLM 接入

- **云端**：MIMO（默认）/ Kimi / OpenAI / Anthropic
- **本地**：Ollama + Llama 3 / Qwen 2
- 支持 `logic / creative / role` 三级路由覆盖

### 4.4 前端

- **框架**：React 18 + Vite + TypeScript
- **样式**：TailwindCSS
- **测试**：Vitest + Testing Library

---

## 5. 关键架构决策

### 5.1 逻辑先于渲染

- 逻辑层只生成精简 JSON（意图/事件），Token 短、幻觉率低
- 渲染层消费结构化事实源（`SceneScript`），不凭空发挥
- 拒绝的 intent 明确不能写入正文（prompt guard）

### 5.2 角色隔离推演

- 每个 spotlight Actor 独立组装 prompt
- 只能看到自己的属性、目标、记忆片段和公开场景信息
- 在物理层面杜绝"偷看剧本"

### 5.3 分支意识内建

- `StoryNode.branch_id` / `merged_from_ids` 从 Sprint 8 起贯穿架构
- `fork_at_node()` 从 `branch_seed_snapshots` 恢复，不重放历史

### 5.4 渐进式发布护栏

- 双循环链路由 `FEATURE_DUAL_LOOP_ENABLED` 控制，可一键回滚
- `/api/simulate/{id}/dual-loop/compare` 产出 readiness 报告与 rollback runbook
- 详见 [DUAL_LOOP_ROLLOUT.md](../development/DUAL_LOOP_ROLLOUT.md)

### 5.5 Prompt 外部化

- Actor / Narrator 等 prompt 模板放在 `src/worldbox_writer/prompts/`
- 通过 `prompting/registry.py` 加载，支持 `PROMPT_TEMPLATE_DIR` 覆盖
- Inspector API 不重新组装 prompt，只展示运行时已沉淀的 `PromptTrace`

---

## 6. 可观测性

- **Telemetry**：每次 LLM 调用记录 `trace_id` / `request_id` / `provider` / `model` / `duration_ms`
- **PromptTrace / MemoryRecallTrace**：Actor 的 prompt 与三层记忆召回记录
- **Inspector API**：`/api/simulate/{id}/inspector` 暴露 ScenePlan / SceneScript / ActionIntent / IntentCritique / PromptTrace

---

## 7. 相关文档

- [双循环推演引擎设计](DUAL_LOOP_ENGINE_DESIGN.md)
- [开发指南](../development/DEVELOPMENT.md)
- [双循环灰度 Runbook](../development/DUAL_LOOP_ROLLOUT.md)
- [运行手册](../development/RUNBOOK.md)
- [质量评估框架](../product/QUALITY_FRAMEWORK.md)
