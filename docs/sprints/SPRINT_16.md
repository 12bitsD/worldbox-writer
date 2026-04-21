# Sprint 16 Plan：Inspector 与 PromptOps

**文档状态**：Completed
**版本目标**：Sprint 16 / Prompt Inspector
**Sprint 周期**：2 周
**定位**：Product Planning v2 的第七个实现 Sprint
**作者**：Codex
**最后更新**：2026-04-22

---

## 1. Sprint 16 要解决什么问题

Sprint 15 已经让记忆召回具备 working / episodic / reflective 三层结构，但用户仍只能在 diagnostics 中看到聚合摘要。

高阶用户需要能定位某一轮角色 prompt、可见角色、召回记忆、Critic verdict 和 GM 结算结果，否则无法判断问题来自 prompt、记忆、审查还是结算。

Sprint 16 的目标是把这些链路暴露为 Inspector API 和前端面板，并把 Actor system prompt 外部化为可热加载模板。

---

## 2. Sprint Goal

**提供 Prompt Inspector v1，让用户能查看当前场景的 prompt trace、memory trace、Critic verdict 与 SceneScript lineage。**

Sprint 16 结束时，项目具备：

- `/api/simulate/{sim_id}/inspector`
- Creative Studio Prompt Inspector 面板
- Prompt registry / template file
- Actor system prompt 外部化
- Prompt hot reload contract v1
- API / frontend / registry 回归测试

---

## 3. 方案骨架

### 3.1 承诺交付

1. Inspector API
2. Inspector 前端面板
3. Prompt registry
4. Packaged Actor prompt template
5. Prompt registry hot reload 测试

### 3.2 非目标

- 不做全量 prompt 编辑器
- 不做权限/审计系统
- 不做历史所有节点的 Inspector 翻页
- 不替换现有 telemetry 面板

---

## 4. 方案收敛记录

### Round 1：把所有 Inspector 信息塞进 diagnostics

问题：

- diagnostics 已经承担 routing、memory、dual_loop 汇总，不适合继续膨胀
- PromptTrace 可能较大，需要独立 API 便于后续分页和权限控制

结论：否决。

### Round 2：新增 Inspector API，前端诊断页并列展示

采用方案：

- diagnostics 继续负责聚合状态
- inspector 返回当前 ScenePlan、SceneScript、ActionIntent、IntentCritique、PromptTrace
- Creative Studio 诊断页增加 Prompt Inspector 卡片
- Prompt registry 每次读取文件，天然支持本地 hot reload

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| S16-01 | Inspector API | P0 | Done |
| S16-02 | Creative Studio Prompt Inspector | P0 | Done |
| S16-03 | Prompt registry / packaged template | P0 | Done |
| S16-04 | Actor system prompt 外部化 | P0 | Done |
| S16-05 | API / frontend / registry tests | P0 | Done |

---

## 6. 成功标准

- Inspector API 返回 prompt traces、memory traces、Critic verdicts 和 SceneScript
- Creative Studio 能显示 prompt 数、intent 数、rejected 数与 memory layer counts
- Actor system prompt 可从 packaged template 加载
- `PROMPT_TEMPLATE_DIR` 覆盖目录修改后，下一次读取能看到新模板
- `make lint`、`make test` 通过，API/type contract 通过 `make typecheck`

---

## 7. 为什么这个范围满足设计预期

Sprint 16 先提供可读 Inspector，而不是直接做复杂 PromptOps 平台。这样可以在不增加编辑权限和模板发布流程复杂度的前提下，先让双循环链路可观察、可定位。

这一步完成后：

- Sprint 17 可以基于 Inspector 暴露的 SceneScript lineage 做渲染链路排错
- Sprint 18 可以把 Inspector 数据纳入 A/B compare report
- 后续 PromptOps 可以在 registry contract 上继续扩展版本、校验和发布流程
