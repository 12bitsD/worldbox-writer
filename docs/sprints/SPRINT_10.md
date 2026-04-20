# Sprint 10 Plan：双循环契约冻结与兼容适配

**文档状态**：Completed  
**版本目标**：Sprint 10 / Dual-Loop Foundation  
**Sprint 周期**：2 周  
**定位**：Product Planning v2 的第一个实现 Sprint  
**作者**：Codex  
**最后更新**：2026-04-21

---

## 1. Sprint 10 要解决什么问题

双循环设计已经明确了长期正确方向，但当前代码基线还没有稳定的 Scene 级契约。

现在如果直接重写 `engine/graph.py`，会立刻遇到 4 个问题：

- 没有冻结好的 `ScenePlan / ActionIntent / SceneScript / PromptTrace` 数据边界。
- 没有 feature flag，无法安全并行保留旧链路。
- 没有兼容层，前端和 diagnostics 看不到新契约的真实落点。
- 没有最小可验证产物，后续 Sprint 11-14 很容易边做边改 schema。

所以 Sprint 10 的目标不是“提前做掉双循环主链”，而是先把后面所有 Sprint 依赖的基础冻结下来。

---

## 2. Sprint Goal

**冻结双循环契约，并在不替换默认运行时的前提下，把它以 compatibility adapter 的方式接入现有系统。**

Sprint 10 结束时，项目应该具备：

- 稳定的后端 Pydantic 契约
- 对应的前端 TypeScript 契约
- 独立的 dual-loop feature flag
- 基于现有 `WorldState` 的 compatibility snapshot
- 能在 diagnostics 中看到双循环契约当前长什么样

---

## 3. 方案骨架

### 3.1 承诺交付

1. `ScenePlan / ActionIntent / SceneScript / PromptTrace / MemoryRecallTrace` 契约冻结
2. `FEATURE_DUAL_LOOP_ENABLED` 开关接线
3. legacy -> dual-loop compatibility adapter v1
4. diagnostics 最小可见化
5. 单元测试 / API 测试 / 前端测试补齐

### 3.2 非目标

- 不在本 Sprint 替换 `run_simulation()` 的默认主链
- 不实现真实的 isolated actor fan-out
- 不实现 Critic / GM
- 不做 Prompt Inspector 产品化 UI
- 不改 Story Feed / Export 的主消费模型

---

## 4. 方案收敛记录

### Round 1：直接改主图

初版思路是把 `engine/graph.py` 直接切成 `scene_plan -> actors -> critic -> gm -> narrator`。

问题：

- 风险过高，跨越 Sprint 10 的边界
- 没有稳定契约时，`core/models`、API、前端类型会一起抖动
- 当前测试体系没有足够保护，回归成本过高

结论：否决。

### Round 2：先冻结契约 + 接 compatibility adapter

第二版思路是：

- 新建 dual-loop contract module
- 保持 legacy runtime 不变
- 用 adapter 从当前 `WorldState` 派生 Scene 级 snapshot
- 通过 feature flag 和 diagnostics 让这层能力可见、可测试、可逐步接线

回归到设计文档后的判断：

- 满足“先冻结契约，再扩行为”的规划原则
- 不违背“双循环推演引擎与一键成书架构方案”的最终方向
- 给 Sprint 11-14 留下清晰的数据真相源

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 说明 |
| :--- | :--- | :--- | :--- |
| S10-01 | Dual-loop contracts v1 | P0 | 冻结 Scene / Intent / Trace 契约 |
| S10-02 | Feature flag wiring | P0 | 独立接入 `FEATURE_DUAL_LOOP_ENABLED` |
| S10-03 | Compatibility adapter v1 | P0 | 从 legacy world 派生 dual-loop snapshot |
| S10-04 | Diagnostics exposure | P0 | 在 API 和前端 diagnostics 暴露最小可见信息 |
| S10-05 | Regression coverage | P0 | 核心模型、adapter、API、前端测试 |

---

## 6. 成功标准

- `FEATURE_DUAL_LOOP_ENABLED` 可独立开关，不影响现有主链运行
- diagnostics 中能看到 contract version、adapter mode、scene plan、scene script
- 前端 diagnostics 至少展示 dual-loop 已启用、契约版本、适配模式
- 所有新增契约都有自动化测试
- `make lint`、`make test` 在 Sprint 10 收尾阶段通过

---

## 7. 为什么这个范围满足设计预期

Sprint 10 不解决“真正的双循环推演”，但它解决了一个更前置的问题：

**后面的双循环推演到底围绕什么契约演进。**

只要 Sprint 10 做对了：

- Sprint 11 可以直接让 Director 输出 `ScenePlan`
- Sprint 12 可以直接让 Actor 消费 `PromptTrace`
- Sprint 13-14 可以直接围绕 `ActionIntent / SceneScript` 接 Critic 和 GM
- Sprint 16 的 Inspector 也有稳定 trace 数据模型可用

这就是 Sprint 10 的价值：它不是结果层的大功能，而是整个 v2 主线的第一块地基。
