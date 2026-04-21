# Sprint 12 Plan：隔离 Actor 运行时 v1

**文档状态**：Completed
**版本目标**：Sprint 12 / Isolated Actor Runtime
**Sprint 周期**：2 周
**定位**：Product Planning v2 的第三个实现 Sprint
**作者**：Codex
**最后更新**：2026-04-21

---

## 1. Sprint 12 要解决什么问题

Sprint 10 冻结了双循环契约，Sprint 11 让 Director 能为每一幕生成 `ScenePlan`。

但主链里的 Actor 阶段仍然是一个共享上下文的候选事件生成器。这意味着角色仍然可能在同一个 prompt 中看到全局角色状态、其他角色记忆或过多剧本信息，无法满足双循环设计里“物理级上下文隔离”的核心要求。

Sprint 12 的目标是让主链第一次真正运行“按角色隔离”的 Actor 意图阶段，同时不提前引入 Critic / GM。

---

## 2. Sprint Goal

**让 spotlight cast 中的角色各自基于公开场景信息和私有记忆生成结构化 `ActionIntent`，再桥接回 legacy 候选事件链路。**

Sprint 12 结束时，项目具备：

- `ScenePlan.spotlight_character_ids` 驱动的 Actor fan-out / fan-in
- 每个 Actor 独立的 `PromptTrace` 与 `MemoryRecallTrace`
- 真实 `ActionIntent` 产出，不再只依赖 synthetic compatibility intent
- branch-aware runtime metadata
- legacy `gate_keeper -> node_detector -> narrator` 链路继续可用

---

## 3. 方案骨架

### 3.1 承诺交付

1. 隔离 Actor runtime v1
2. 私有 prompt / memory trace 组装
3. spotlight actor fan-out / fan-in 执行器
4. `ActionIntent` 到 legacy candidate event 的桥接
5. 信息泄漏与 graph routing 回归测试

### 3.2 非目标

- 不引入 `CriticAgent`
- 不引入 `GMAgent`
- 不把 `SceneScript` 接管事实提交
- 不重写 Narrator 输入
- 不做 Prompt Inspector UI 产品化
- 不改 memory layer schema

---

## 4. 方案收敛记录

### Round 1：直接引入 Critic / GM

问题：

- Actor intent 还没有真实进入主链，直接审查会缺少稳定输入
- `node_detector` 事实提交尚未适配 Scene Script
- 改动会跨过 Sprint 12 边界，放大回归风险

结论：否决。

### Round 2：先让 Actor intent 真实运行，再桥接 legacy 链路

采用方案：

- 使用现有 `ScenePlan` 选择 spotlight actor
- 为每个 Actor 组装只包含公开场景信息、可见角色、角色自身目标和私有记忆的 prompt
- 并发生成 `ActionIntent`
- 先把多个 intent 合成为一个 legacy candidate event，继续复用 GateKeeper / NodeDetector / Narrator
- 在 metadata 和 telemetry 中保留 runtime mode、branch id、prompt trace 和 intent trace

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| S12-01 | Isolated actor runtime v1 | P0 | Done |
| S12-02 | Private prompt / memory trace assembler | P0 | Done |
| S12-03 | Spotlight actor fan-out / fan-in | P0 | Done |
| S12-04 | Legacy candidate bridge | P0 | Done |
| S12-05 | Regression coverage | P0 | Done |

---

## 6. 成功标准

- feature flag 开启时，`actor_node` 使用 isolated actor runtime
- feature flag 关闭时，legacy shared prompt 仍可运行
- 非 spotlight 角色不会进入当前 Actor 的 visible character list
- 一个角色的 prompt 不包含其他角色的私有记忆
- `ActionIntent` metadata 中包含 runtime mode 与 branch id
- 节点提交时保留 action intent 和 prompt trace metadata
- `make lint`、`make test` 在 Sprint 12 收尾阶段通过

---

## 7. 为什么这个范围满足设计预期

Sprint 12 不解决最终对抗结算，但它完成了双循环路线中最关键的行为切换：Actor 不再从共享上下文里直接生成单个候选事件，而是开始以隔离角色身份生成结构化意图。

这一步完成后：

- Sprint 13 可以围绕真实 `ActionIntent` 引入 Critic 审查
- Sprint 14 可以把通过审查的多个 intent 交给 GM 结算为 `SceneScript`
- Sprint 16 的 Inspector 可以复用当前积累的 `PromptTrace` 与 `MemoryRecallTrace`
