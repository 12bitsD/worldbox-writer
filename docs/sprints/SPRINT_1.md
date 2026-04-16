# Sprint 1 — 核心引擎

**Sprint 周期**：Sprint 1（2 周）
**目标**：实现系统核心骨架，包括数据模型、Director Agent、Gate Keeper 边界层、关键节点识别机制，以及完整的 TDD 测试套件。

---

## Sprint 目标（Sprint Goal）

> 用户能够输入一句话故事前提，系统能够初始化一个结构化的故事世界，并在推演过程中自动识别需要用户干预的关键节点，同时通过 Gate Keeper 确保所有推演结果不违反用户设定的边界。

---

## 完成的 User Stories

| Issue | User Story | 状态 | 测试数 |
| :--- | :--- | :--- | :--- |
| #4 | 作为创作者，我希望输入一句话前提，系统自动初始化故事世界 | ✅ Done | 22 |
| #5 | 作为创作者，我希望系统在关键节点暂停并询问我是否干预 | ✅ Done | 19 |
| #6 | 作为创作者，我希望设定的边界在整个推演过程中持续有效 | ✅ Done | 11 |

---

## 技术交付物

### 核心数据结构（`src/worldbox_writer/core/models.py`）

| 模型 | 职责 |
| :--- | :--- |
| `WorldState` | 故事世界的完整状态，所有 Agent 共享的单一数据源 |
| `StoryNode` | 故事因果链中的单个事件节点，构成叙事 DAG |
| `Character` | 具有记忆、目标和关系的角色实体 |
| `Constraint` | Gate Keeper 执行的边界规则，区分 HARD/SOFT 两种严重度 |

### Agent 实现

| Agent | 文件 | 核心职责 |
| :--- | :--- | :--- |
| `DirectorAgent` | `agents/director.py` | 解析用户意图，初始化世界，将意图持久化为 Constraint |
| `GateKeeperAgent` | `agents/gate_keeper.py` | 校验每个 StoryNode 是否违反活跃 Constraint，返回 ValidationResult |
| `NodeDetector` | `agents/node_detector.py` | 识别关键叙事时刻，生成 InterventionSignal |

### 技术选型结论（Spike #15）

经过调研，选择 **LangGraph** 作为 Agent 编排框架：

- **LangGraph** 提供有状态的图执行模型，天然支持循环、条件分支和人机交互暂停（`interrupt_before`），完全契合本项目的"推演-校验-干预"循环。
- CrewAI 适合线性任务流，不适合本项目的动态循环推演。
- AutoGen 更适合对话式多 Agent 协作，状态管理复杂度高。

---

## 测试报告

```
76 passed in 2.28s
Coverage: 99%

tests/test_agents/test_director.py      22 passed
tests/test_agents/test_gate_keeper.py   11 passed
tests/test_agents/test_node_detector.py 19 passed
tests/test_core/test_models.py          24 passed
```

所有测试均使用 MockLLM，无真实 API 调用，CI 可在无密钥环境下完整运行。

---

## Sprint 回顾

### 做得好的
- TDD 严格执行，所有功能先写测试再写实现
- MockLLM 策略使测试完全隔离，运行速度快（< 3s）
- 核心数据结构设计稳固，后续 Agent 扩展无需修改

### 需要改进的
- Gate Keeper 和 Director 的 LLM prompt 需要在真实场景中进一步调优
- 缺少集成测试（Agent 之间的协作流程）

---

## Sprint 2 预览

Sprint 2 目标：实现 Actor Agent（角色自主行动）和 LangGraph 编排图，完成第一个端到端可运行的故事推演 Demo。

关键 Issues：
- [ ] #7 Actor Agent 实现（角色记忆 + 自主决策）
- [ ] #8 LangGraph StateGraph 编排（Director → GateKeeper → NodeDetector → Narrator 流水线）
- [ ] #9 快速推演模式（Fast-Forward Mode）
