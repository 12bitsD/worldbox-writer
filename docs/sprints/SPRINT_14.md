# Sprint 14 Plan：GM 结算与 Scene Script 提交

**文档状态**：Completed
**版本目标**：Sprint 14 / GM Settlement
**Sprint 周期**：2 周
**定位**：Product Planning v2 的第五个实现 Sprint
**作者**：Codex
**最后更新**：2026-04-21

---

## 1. Sprint 14 要解决什么问题

Sprint 13 已经能对每个 `ActionIntent` 产出 `IntentCritique`，并阻止被拒绝的意图进入候选事件。

但主链仍然把合法意图直接拼接成 legacy candidate event。这样还缺少“唯一客观事实源”：Narrator、记忆、导出和后续 Inspector 都无法稳定指向一个场景级结算结果。

Sprint 14 的目标是在 Critic 之后加入 GM 结算层，把合法意图收束成唯一 `SceneScript`，再继续复用现有 `GateKeeper -> NodeDetector -> Narrator` 保护链路。

---

## 2. Sprint Goal

**让 `GMAgent` 将 Critic 通过的 Actor Intent 结算成唯一 `SceneScript`，并让主链以 SceneScript 作为候选事件事实源。**

Sprint 14 结束时，项目具备：

- `GMAgent` 模块
- branch-aware `SceneScript` settlement
- accepted / rejected intent ids 写入 `SceneScript`
- `scene_script` runtime metadata 与 node metadata
- diagnostics 复用已持久化的 `SceneScript`
- branch-aware commit 回归测试

---

## 3. 方案骨架

### 3.1 承诺交付

1. GM settlement adapter
2. Graph 接线：Actor Intent -> Critic -> GM -> candidate event
3. `StoryNode` metadata 中持久化 `SceneScript`
4. compatibility snapshot 优先复用已结算 `SceneScript`
5. GM 与 graph commit 回归测试

### 3.2 非目标

- 不让 Narrator 直接消费 `SceneScript` 结构化 beats
- 不改写 export bundle 的正文来源
- 不引入复杂多 Actor 冲突博弈
- 不替换 `GateKeeper` 后置节点级校验

---

## 4. 方案收敛记录

### Round 1：直接让 `NodeDetector` 生成 `SceneScript`

问题：

- `NodeDetector` 的职责是提交节点和检测干预，不应该负责多意图结算
- SceneScript 会缺少清晰的 accepted / rejected intent lineage

结论：否决。

### Round 2：新增 `GMAgent`，保留 legacy 提交链

采用方案：

- `GMAgent.settle_scene()` 只消费 `ActionIntent` 与 `IntentCritique`
- 明确 accepted / rejected intent ids，并用 accepted intents 生成 beats
- 主链 candidate event 来自 `SceneScript.summary`
- `NodeDetector` 把 `SceneScript` 写入节点 metadata 和 world metadata
- diagnostics 兼容层优先复用 runtime / committed `SceneScript`

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| S14-01 | `GMAgent` settlement 模块 | P0 | Done |
| S14-02 | SceneScript runtime metadata | P0 | Done |
| S14-03 | StoryNode / SceneScript commit adapter | P0 | Done |
| S14-04 | diagnostics snapshot 复用持久化 SceneScript | P0 | Done |
| S14-05 | GM 与 graph commit 回归测试 | P0 | Done |

---

## 6. 成功标准

- isolated actor runtime 开启时，Critic 之后会产出 `SceneScript`
- candidate event 来自 `SceneScript.summary`
- `SceneScript.accepted_intent_ids` 不包含被 Critic 拒绝的 intent
- `StoryNode.metadata["scene_script"]` 可追踪本轮客观事实源
- diagnostics API 能展示已持久化的 `SceneScript`
- `make lint`、`make test` 通过，类型边界通过 `make typecheck`

---

## 7. 为什么这个范围满足设计预期

Sprint 14 完成了双循环逻辑层的关键闭环：角色不再直接把意图拼接进故事，而是先经过 Critic 审查，再由 GM 结算成唯一客观场景脚本。

这一步完成后：

- Sprint 15 可以围绕 `SceneScript` 做更稳定的认知记忆写回
- Sprint 16 可以展示 Actor Intent -> Critic -> GM 的完整 Inspector 链路
- Sprint 17 可以让 Narrator 正式消费 `SceneScript`，把逻辑层和文笔层拆开
