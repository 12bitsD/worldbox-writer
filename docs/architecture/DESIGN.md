# WorldBox Writer 架构设计

**文档状态**：Active
**最后更新**：2026-05-11

本文档是 WorldBox Writer 的整体架构单一真相源，合并了原 `DUAL_LOOP_ENGINE_DESIGN.md` 的第一性原理推导。
灰度与回滚流程已并入 [开发指南 §10 双循环灰度与运行手册](../development/DEVELOPMENT.md#10-双循环灰度与运行手册)。

---

## 1. 核心理念

系统不是"文本生成器"，而是"事件推演引擎"。

所有故事发展先在底层以**有向无环图（DAG）**形式推演并固化，再交由 LLM 进行文学性渲染。
目的：解决长篇小说生成的**逻辑一致性**与**用户干预持久性**问题。

---

## 2. 终极目标与第一性原理

在设计任何模块前，先明确系统要解决的三个痛点——每一项架构决策都围绕它们展开。

### 2.1 彻底消灭"串戏"与"逻辑崩坏"

- **目标**：角色决策时不得知道只有读者或其他角色才知道的秘密；长篇推演 100 章后逻辑仍严密。
- **手段**：
  - **推演与渲染解耦**：逻辑层只产出精简 JSON 意图（如"拔剑"/"逃跑"），Token 短、结构化，幻觉率指数级下降；渲染层只把 JSON 扩写为小说，不凭空发挥。
  - **物理级上下文隔离**：每个核心角色独立起 Agent 实例。Prompt 中只注入该角色自己的属性卡、私有记忆片段、公开场景信息——在物理层面杜绝"偷看剧本"。

### 2.2 拒绝"流水账"，确保"网文张力"

- **目标**：多 Agent 沙盒常陷入无聊寒暄；我们要的是跌宕起伏的网文，不是模拟人生。
- **手段**：
  - **叙事压力（Narrative Pressure）+ 导演强干预**：Director 不只是环境描述者，而是宏观情节控制器。它维护情节曲线（平缓 → 危机 → 高潮），当沙盒陷入平淡时，在 Actor 的私有 Context 里隐蔽注入心理暗示（如"你突然感到莫名烦躁，急需发泄口"），以符合人设的方式强行打破僵局。

### 2.3 所见即所得的调优与交互体验

- **目标**：告别黑盒等待；用户必须能实时看到推演过程，并能透视任一角色的底层设定。
- **手段**：
  - **SSE 并发流式推送**：任一 Actor 思考完毕即推送到前端，用户无需等整轮结束。
  - **Agent Inspector 透视调试**：点击任何角色可查看当前 LLM 调用的完整 Prompt、召回了哪些历史记忆——白盒化定位"是记忆没召回，还是人设被污染"。

---

## 3. 三层架构

### 3.1 世界推演层（内循环：逻辑）

快速生成逻辑严密、充满冲突的结构化"场景剧本（Scene Script）"。

- **Director**（`agents/director.py`）：产出 `ScenePlan`，决定每一幕的 objective、spotlight cast、叙事压力；在合适时机向 Actor 注入 Narrative Pressure。
- **WorldBuilder**（`agents/world_builder.py`）：扩写世界规则、势力、地理，维护全局知识库（Vector DB）。
- **Actor × N**（`agents/actor.py`）：按需唤醒，每个角色独立 Agent。只能读取自己的私有记忆库和公开环境简报，通过 Map-Reduce 并发调用独立产出 `ActionIntent`。

### 3.2 边界与结算层

系统的"大脑"与"裁判"，处理人类干预，保证世界不崩坏。

- **Critic**（`agents/critic.py`）：意图级 LLM 策略审查，产出 `IntentCritique`（accepted / rejected）；放弃复杂硬编码规则，以廉价 LLM 判断世界观兼容性。
- **GateKeeper**（`agents/gate_keeper.py`）：节点级硬约束校验，HARD 违反阻断推演。
- **GM**（`agents/gm.py`）：结算 accepted intent，产出本轮唯一 `SceneScript` 作为事实源。
- **NodeDetector**（`agents/node_detector.py`）：识别关键分歧节点，触发用户干预。

### 3.3 表现与渲染层（外循环：文笔）

将干瘪的结构化剧本转化为大师级文笔的长篇网文。

- **Narrator**（`agents/narrator*.py`）：后台监听器。内循环积累够一个完整的情节片段（Scene）后，触发高文笔模型（如 Claude 3.5），结合指定主角视角和文风，将 SceneScript + 三层记忆流式渲染为 800-2000 字的小说正文（`NarratorInput v2`）。
- **Dashboard API**（`api/`）：提供实时事件流（SSE）、关系图谱与全局状态快照。

### 3.4 多层认知记忆管线（Cognitive Memory Stream）

解决长篇连载的"遗忘"和"记错设定"问题，同时降低每次调用的上下文长度。角色记忆分为三层：

- **工作记忆**：最近发生的事，直接入 Prompt。
- **情景记忆**：历史日志，按"重要性 + 近期性 + 相关性"召回。
- **反思记忆**：后台异步触发，将多次经历总结为一条高级性格设定（如"经历三次被骗 → 生性多疑"）。

---

## 4. 核心数据流

```
Director.plan_scene()
      │  产出 ScenePlan（含叙事压力）
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

1. **初始化**：Director 接收用户前提，生成初始世界（WorldBuilder 异步补全）。
2. **内循环推演**：Actor 提议 → Critic 审查 → GM 结算 → GateKeeper 校验 → 固化节点。
3. **外循环渲染**：Narrator 将 SceneScript 渲染为正文，或跳过进入下一轮（快进模式）。
4. **干预**：NodeDetector 检测到关键分歧时暂停，向用户请求干预。

---

## 5. 技术栈

### 5.1 后端

| 组件 | 选型 | 理由 |
| :--- | :--- | :--- |
| 语言 | Python 3.11+ | 类型系统与生态匹配 |
| Agent 框架 | **LangGraph** | 有状态图执行，原生支持循环、分支、`interrupt_before` |
| API 框架 | **FastAPI** | 异步非阻塞，天然支持 SSE |

相比之下，CrewAI 偏线性任务流，AutoGen 状态管理复杂度过高。

### 5.2 存储

| 用途 | 当前选型 | 备注 |
| :--- | :--- | :--- |
| 持久化 | SQLite | `sessions.state_json` + `memory_entries` + `branch_seed_snapshots` |
| 向量检索 | ChromaDB（default `auto`） | 可 fallback 到 SQLite BM25 |
| 分支快照 | `branch_seed_snapshots` | 按 `sim_id + node_id + branch_id` 存完整 WorldState |

分支恢复采用 **snapshot 直接恢复**，不采用"重放历史"——LLM 推演非确定性。

### 5.3 LLM 接入

- **云端**：MIMO（默认）/ Kimi / OpenAI / Anthropic
- **本地**：Ollama + Llama 3 / Qwen 2
- 支持 `logic / creative / role` 三级路由覆盖

### 5.4 前端

- **框架**：React 18 + Vite + TypeScript
- **样式**：TailwindCSS
- **测试**：Vitest + Testing Library

---

## 6. 关键架构决策

### 6.1 逻辑先于渲染

- 逻辑层只生成精简 JSON（意图/事件），Token 短、幻觉率低
- 渲染层消费结构化事实源（`SceneScript`），不凭空发挥
- 拒绝的 intent 明确不能写入正文（prompt guard）

### 6.2 角色隔离推演

- 每个 spotlight Actor 独立组装 prompt
- 只能看到自己的属性、目标、记忆片段和公开场景信息
- 在物理层面杜绝"偷看剧本"

### 6.3 分支意识内建

- `StoryNode.branch_id` / `merged_from_ids` 从 Sprint 8 起贯穿架构
- `fork_at_node()` 从 `branch_seed_snapshots` 恢复，不重放历史

### 6.4 渐进式发布护栏

- 双循环链路由 `FEATURE_DUAL_LOOP_ENABLED` 控制，可一键回滚
- `/api/simulate/{id}/dual-loop/compare` 产出 readiness 报告与 rollback 依据
- 灰度与恢复详见 [开发指南 §10](../development/DEVELOPMENT.md#10-双循环灰度与运行手册)

### 6.5 Prompt 外部化

- Actor / Narrator 等 prompt 模板放在 `src/worldbox_writer/prompts/`
- 通过 `prompting/registry.py` 加载，支持 `PROMPT_TEMPLATE_DIR` 覆盖
- Inspector API 不重新组装 prompt，只展示运行时已沉淀的 `PromptTrace`

---

## 7. 可观测性

- **Telemetry**：每次 LLM 调用记录 `trace_id` / `request_id` / `provider` / `model` / `duration_ms`
- **PromptTrace / MemoryRecallTrace**：Actor 的 prompt 与三层记忆召回记录
- **Inspector API**：`/api/simulate/{id}/inspector` 暴露 ScenePlan / SceneScript / ActionIntent / IntentCritique / PromptTrace

---

## 8. 架构价值收敛

- **双循环** 保证了逻辑的严丝合缝与最终文笔的华丽
- **带压力的 Director** 保证了网文的爽感和节奏
- **隔离并发的 Actor** 贡献了意想不到的群像涌现
- **Critic 对抗结算** 守住了不崩坏的底线

这套基于第一性原理推演出的架构，是面向"长篇网文生产力"的目标解法。

---

## 9. 相关文档

- [开发指南](../development/DEVELOPMENT.md) — 环境、命令、CI、灰度、发布、类型基线
- [质量评测系统 SPEC](../product/QUALITY_SPEC.md) — 评测维度 + 中间节点评测
- [产品策略](../product/PRODUCT_STRATEGY.md)
