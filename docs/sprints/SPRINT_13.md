# Sprint 13 Plan：Critic 审查链路

**文档状态**：Completed
**版本目标**：Sprint 13 / Intent Critic
**Sprint 周期**：2 周
**定位**：Product Planning v2 的第四个实现 Sprint
**作者**：Codex
**最后更新**：2026-04-21

---

## 1. Sprint 13 要解决什么问题

Sprint 12 已经让 spotlight Actor 在隔离上下文中产出真实 `ActionIntent`。

但这些意图在进入 legacy candidate bridge 之前还没有逐条审查。只依赖后置 `GateKeeper` 会把多个角色意图先合成一个事件，再做整体约束校验，无法明确回答“是哪一个角色意图越界、为什么被挡下、是否泄漏了不可见信息”。

Sprint 13 的目标是在结算前加入 Critic 审查层，让每个 `ActionIntent` 都有可诊断的 verdict。

---

## 2. Sprint Goal

**在 isolated actor runtime 和 legacy candidate bridge 之间插入 `CriticAgent`，只允许通过审查的 Actor Intent 进入候选事件合成。**

Sprint 13 结束时，项目具备：

- `IntentCritique` 契约
- `CriticAgent` intent-level policy guard
- 拒绝原因 taxonomy
- Critic telemetry 与 diagnostics payload
- SceneScript accepted / rejected intent 映射
- 前端诊断面板展示 Critic 通过 / 拒绝概览

---

## 3. 方案骨架

### 3.1 承诺交付

1. Intent validation contract
2. `CriticAgent` 模块
3. Graph 接线：Actor Intent -> Critic -> legacy bridge
4. Critic verdict metadata / diagnostics / frontend 类型
5. L1 + L2 回归测试

### 3.2 非目标

- 不引入 `GMAgent`
- 不把 `SceneScript` 接管事实提交
- 不重写 `NodeDetector` 的提交模型
- 不改变 `GateKeeper` 的节点级后置校验职责
- 不做 Prompt Inspector 产品化

---

## 4. 方案收敛记录

### Round 1：直接让 GateKeeper 审查合成后的候选事件

问题：

- 多个 Actor Intent 已经被合并，无法定位具体违规来源
- 难以记录每个角色的 accepted / rejected 状态
- 对“角色知道了不该知道的信息”缺少逐意图证据

结论：否决。

### Round 2：新增 Critic intent-level verdict，继续保留 legacy bridge

采用方案：

- `CriticAgent` 对每个 `ActionIntent` 输出 `IntentCritique`
- policy guard 先做确定性检查：世界规则、可见角色边界、角色状态、低置信度与元叙事泄漏
- 只把 accepted intents 交给 `synthesize_candidate_event_from_intents`
- `GateKeeper` 继续作为 candidate event 的后置节点级保护
- verdict 写入 world metadata、node metadata、diagnostics API 和前端诊断摘要

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| S13-01 | `IntentCritique` 契约 | P0 | Done |
| S13-02 | `CriticAgent` policy guard | P0 | Done |
| S13-03 | Actor runtime -> Critic -> bridge 接线 | P0 | Done |
| S13-04 | Critic telemetry / diagnostics / frontend 类型 | P0 | Done |
| S13-05 | Regression coverage | P0 | Done |

---

## 6. 成功标准

- 每个 isolated actor `ActionIntent` 都会产生一个 `IntentCritique`
- 被 Critic 拒绝的 intent 不会进入 legacy candidate event
- 世界规则、不可见角色引用和不一致角色状态有明确 `reason_code`
- diagnostics API 暴露 `intent_critiques`
- 前端诊断面板展示 Critic accepted / rejected 概览
- `SceneScript` compatibility snapshot 能保留 accepted / rejected intent ids
- Sprint 收尾阶段通过 `make lint`、`make test`，并对类型边界执行 `make typecheck`

---

## 7. 为什么这个范围满足设计预期

Sprint 13 不解决最终场景结算，但它把“是否允许进入结算”的责任从旧式候选事件整体校验前移到了单个 Actor Intent。

这一步完成后：

- Sprint 14 可以只消费 Critic 通过的合法意图，并把它们交给 GM 结算为唯一 `SceneScript`
- Sprint 16 的 Inspector 可以展示每个角色意图、prompt trace 与 Critic verdict 的完整链路
- legacy `GateKeeper -> NodeDetector -> Narrator` 仍然保留，降低双循环迁移风险
