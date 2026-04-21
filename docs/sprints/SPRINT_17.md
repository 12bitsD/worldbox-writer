# Sprint 17 Plan：SceneScript 驱动 Narrator 渲染

**文档状态**：Completed
**版本目标**：Sprint 17 / Narrator Input v2
**Sprint 周期**：2 周
**定位**：Product Planning v2 的第八个实现 Sprint
**作者**：Codex
**最后更新**：2026-04-22

---

## 1. Sprint 17 要解决什么问题

Sprint 14 已经让 `SceneScript` 成为逻辑事实源，Sprint 15-16 又让它进入记忆写回和 Inspector。但渲染层仍主要消费 `StoryNode.description`，这会让“逻辑结算”和“文笔扩写”之间缺少明确合同。

Sprint 17 的目标是让 Narrator 正式消费 GM 结算后的 `SceneScript`，把已接受 beats 作为正文渲染依据，并显式阻止被 Critic 拒绝的 intent 进入小说正文。

---

## 2. Sprint Goal

**让 Narrator 基于 `SceneScript` 渲染章节正文，同时保持旧导出和旧节点 payload 兼容。**

Sprint 17 结束时，项目具备：

- `NarratorInput` v2 contract
- SceneScript -> narrator prompt adapter
- rejected intent 防写入提示
- StoryNode API 中的 scene script lineage 摘要
- StoryFeed 中的 SceneScript lineage 展示
- rendering / API / export / frontend 回归测试

---

## 3. 方案骨架

### 3.1 承诺交付

1. `NarratorInput` v2 契约
2. `narrator_node` 优先消费节点 metadata 中的 `SceneScript`
3. SceneScript summary / public facts / beats 进入 Narrator prompt
4. API 可选暴露 `scene_script_id`、`scene_script_summary`、`narrator_input_source`
5. StoryFeed 展示场景结算摘要
6. 导出继续基于 `rendered_text`，保持 bundle 格式兼容

### 3.2 非目标

- 不替换 `GateKeeper -> NodeDetector` 提交流程
- 不改变 `StoryNode.description` 语义
- 不把 rejected intent 的完整内容暴露给前端故事流
- 不新增导出文件格式

---

## 4. 方案收敛记录

### Round 1：直接把 SceneScript 展开写进 StoryNode.description

问题：

- 会污染 legacy 事件描述字段，后续难以区分逻辑摘要与渲染输入
- 导出、编辑器和历史节点恢复会误以为 description 就是唯一事实源

结论：否决。

### Round 2：新增 NarratorInput v2，作为渲染层输入合同

采用方案：

- `StoryNode.metadata["scene_script"]` 继续作为持久化事实源
- `NarratorInput` v2 只在 Narrator 渲染前组装，并写回 `metadata["narrator_input_v2"]`
- 当节点没有 SceneScript 时，自动回退到旧 `StoryNode.description` 路径
- API 只暴露轻量 lineage 字段，不暴露完整 prompt

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| S17-01 | `NarratorInput` v2 contract | P0 | Done |
| S17-02 | SceneScript narrator adapter | P0 | Done |
| S17-03 | rejected intent 防写入 prompt guard | P0 | Done |
| S17-04 | API / StoryFeed lineage 字段 | P1 | Done |
| S17-05 | rendering / export / frontend tests | P0 | Done |

---

## 6. 成功标准

- 含 `SceneScript` 的节点会让 Narrator prompt 使用 summary、public facts 和 beats
- prompt 明确禁止写入 `rejected_intent_ids`
- `StoryNode.metadata["narrator_input_v2"]` 能追踪本次渲染来源
- API 返回轻量 scene script lineage 字段，旧 payload 字段不移除
- 导出 bundle 继续使用 `rendered_text`，不依赖新字段
- `make lint`、`make test`、`make typecheck` 通过；因 Narrator prompt 改动需跑 `make integration`

---

## 7. 为什么这个范围满足设计预期

Sprint 17 没有重写整个章节生成器，而是把 Narrator 的输入从“单段事件文本”升级为可审计的 `NarratorInput`。这样逻辑层、记忆层、Inspector 和渲染层都能追溯到同一个 `SceneScript`，同时旧导出、旧节点恢复和旧节点描述仍然保持兼容。

这一步完成后，Sprint 18 可以围绕 dual-loop rollout 做 compare report、eval guardrails 和 rollback runbook。
