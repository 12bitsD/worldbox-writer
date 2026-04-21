# Sprint 15 Plan：认知记忆流 v2

**文档状态**：Completed
**版本目标**：Sprint 15 / Cognitive Memory v2
**Sprint 周期**：2 周
**定位**：Product Planning v2 的第六个实现 Sprint
**作者**：Codex
**最后更新**：2026-04-22

---

## 1. Sprint 15 要解决什么问题

Sprint 14 已经让 `SceneScript` 成为逻辑事实源，但记忆层仍主要把提交后的 `StoryNode` 当作单一事件写入。

这会带来两个问题：

- Actor prompt 虽然已有 `MemoryRecallTrace`，但 working / episodic / reflective 三层来源还不够清楚。
- 角色的长期性格连续性缺少稳定反思写回，后续 Inspector 也无法解释“为什么这个角色变得更谨慎”。

Sprint 15 的目标是在不改 SQLite 表结构的前提下，复用 `entry_kind` 扩展反思记忆层。

---

## 2. Sprint Goal

**把 durable memory 升级为可解释的 working / episodic / reflective 三层认知记忆，并在 SceneScript 提交后写回角色反思层。**

Sprint 15 结束时，项目具备：

- `reflection` memory entry kind
- SceneScript -> reflective memory writeback
- Character `reflection_notes` 自动更新
- `MemoryRecallTrace.metadata.layer_counts`
- diagnostics 暴露 reflection entry 计数
- Actor prompt 继续保持角色私有认知边界

---

## 3. 方案骨架

### 3.1 承诺交付

1. 记忆层 reflection entry kind
2. SceneScript beat -> character reflection writeback
3. PromptTrace 三层召回诊断
4. diagnostics / frontend reflection counters
5. memory 与 graph 回归测试

### 3.2 非目标

- 不新增数据库迁移字段
- 不引入异步后台 summarizer worker
- 不做可编辑记忆面板
- 不改变默认归档摘要策略

---

## 4. 方案收敛记录

### Round 1：新增独立 reflection 表

问题：

- 当前 memory_entries 已经有 `entry_kind`、tags 和 branch 字段
- 新表会要求更多迁移、API 和恢复逻辑，超出 Sprint 15 P0

结论：否决。

### Round 2：复用 memory_entries，扩展 `entry_kind=reflection`

采用方案：

- `MemoryManager.record_reflection()` 写入 durable memory
- `MemoryManager.write_reflections_from_scene_script()` 从 accepted beats 生成角色反思
- 反思同时写入 `Character.metadata["reflection_notes"]`，供下一轮 Actor prompt 使用
- `build_prompt_trace()` 将 episodic 与 reflective 召回分开，并记录 layer counts
- diagnostics 和 Creative Studio 展示 reflection entry 计数

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| S15-01 | reflection memory entry kind | P0 | Done |
| S15-02 | SceneScript reflective writeback | P0 | Done |
| S15-03 | MemoryRecallTrace 三层诊断 | P0 | Done |
| S15-04 | diagnostics / frontend counters | P0 | Done |
| S15-05 | memory / graph regression tests | P0 | Done |

---

## 6. 成功标准

- SceneScript 提交后，含 actor beat 的角色会获得 reflective memory
- `MemoryManager.get_stats()` 暴露 `reflection_entries`
- Actor `PromptTrace.memory_trace` 能区分 episodic 与 reflective snippets
- `MemoryRecallTrace.metadata.layer_counts` 记录三层数量
- `make lint`、`make test` 通过，类型边界通过 `make typecheck`

---

## 7. 为什么这个范围满足设计预期

Sprint 15 没有把记忆系统做成完整认知平台，但它完成了双循环链路最关键的记忆闭环：客观事实先由 GM 结算为 SceneScript，再从 accepted beats 写回角色反思。

这一步完成后：

- Sprint 16 的 Inspector 可以展示“prompt 为什么召回这些 working / episodic / reflective 记忆”
- Sprint 17 的 Narrator 可以基于 SceneScript 渲染，同时保留角色反思连续性
- 后续长期推演可以逐步增强 reflection summarizer，而不需要重做底层 schema
