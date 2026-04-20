# Sprint 11 Plan：Director 升级为 Scene Planner

**文档状态**：Completed  
**版本目标**：Sprint 11 / Spotlight Director  
**Sprint 周期**：2 周  
**定位**：Product Planning v2 的第二个实现 Sprint  
**作者**：Codex  
**最后更新**：2026-04-21

---

## 1. Sprint 11 要解决什么问题

Sprint 10 已经把 `ScenePlan / ActionIntent / SceneScript / PromptTrace` 契约冻结下来，但当前默认主图里，Director 仍然只负责第一次世界初始化。

这会带来 3 个直接问题：

- 后续每一幕没有显式的 scene objective，Actor 只能在全局上下文里“凭感觉往前写”。
- 当前链路缺少 spotlight cast，故事容易平均用力，导致叙事失焦。
- Sprint 10 冻结下来的 `ScenePlan` 还没有进入真实 graph state，compatibility contract 仍然只是旁路快照。

所以 Sprint 11 的目标不是提前做掉 Critic / GM，而是先让 Director 成为每一幕的场控器。

---

## 2. Sprint Goal

**让 Director 在每一幕产出稳定的 `ScenePlan`，并把它接入 graph state、world metadata 与 legacy actor prompt。**

Sprint 11 结束时，项目应该具备：

- `DirectorAgent.plan_scene()` 能输出可复用的 `ScenePlan`
- LangGraph state 内存在稳定的 `scene_plan`
- `world.metadata["current_scene_plan"]` 成为 scene-level truth source
- legacy `actor_node` 已开始消费 Director 的场景目标、聚光灯和叙事压力
- telemetry 能看到 `scene_planned` 阶段

---

## 3. 方案骨架

### 3.1 承诺交付

1. `DirectorAgent` 的 scene planning 能力
2. `scene_director_node` 与 `scene_plan` graph state 接线
3. `world.metadata["current_scene_plan"]` 持久化写回
4. legacy actor prompt 接入 Scene Plan 上下文
5. Director scene planning 单元测试与 graph routing 回归测试

### 3.2 非目标

- 不在本 Sprint 做 isolated actor fan-out / fan-in
- 不引入 `CriticAgent` 或 `GMAgent`
- 不替换 `node_detector -> narrator` 的既有提交与渲染模式
- 不做 Prompt Inspector UI 产品化
- 不在本 Sprint 改 memory layer schema

---

## 4. 方案收敛记录

### Round 1：直接把主图切成 isolated actors

初版思路是把主图直接改成 `scene_plan -> actors -> critic -> gm -> narrator`。

问题：

- 超出 Sprint 11 的边界，直接侵入 Sprint 12-14
- `ScenePlan` 还没有在真实 graph state 中站稳，后续问题难以定位
- 当前测试覆盖只够保护小步迁移，不够保护一次性大替换

结论：否决。

### Round 2：Director 成为 Scene Planner，legacy actor 先消费场控结果

第二版思路是：

- 给 `DirectorAgent` 增加 `plan_scene()`，输出 Director-owned `ScenePlan`
- 在 LangGraph 中插入 `scene_director_node`
- 每轮都把 `scene_plan` 写入 graph state 和 `world.metadata`
- 先让 legacy `actor_node` 消费 `ScenePlan`，但保持单候选事件主链不变

对照双循环设计文档后的判断：

- 满足“Director 从初始化器升级为场控器”的核心预期
- 满足“先冻结契约，再扩行为”的规划原则
- 给 Sprint 12 的 isolated actor runtime 提供稳定导演输入，而不提前膨胀改造面

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 说明 |
| :--- | :--- | :--- | :--- |
| S11-01 | Director scene planner v1 | P0 | 输出 objective / spotlight / pressure |
| S11-02 | Graph state wiring | P0 | 新增 `scene_plan` 与 `scene_director_node` |
| S11-03 | Scene Plan persistence | P0 | 写回 `world.metadata["current_scene_plan"]` |
| S11-04 | Legacy actor consumption | P0 | 让 `actor_node` 消费 Scene Plan |
| S11-05 | Regression coverage | P0 | Director / routing / adapter / graph 测试 |

---

## 6. 成功标准

- 每轮推演都能得到一个可验证的 `ScenePlan`
- `scene_director_node` 成为真实主图的一部分，而不是 diagnostics 旁路逻辑
- `world.metadata["current_scene_plan"]` 可被 compatibility adapter 直接复用
- `actor_node` 的 prompt 中含有 scene objective、spotlight 角色和 narrative pressure
- `make lint`、`make typecheck`、`make test` 在 Sprint 11 收尾阶段通过

---

## 7. 为什么这个范围满足设计预期

Sprint 11 的价值不在于“功能看起来更多”，而在于让 Director 第一次真正参与每一幕的运行时决策。

只要这一步做对了：

- Sprint 12 可以在不重新定义导演输入的前提下切入 isolated actors
- Sprint 13 可以围绕同一份 `ScenePlan` 审查 Intent 是否越界
- Sprint 14 可以把 Director 的场控目标与 GM 的事实结算对齐起来

这意味着从 Sprint 11 开始，双循环不再只是契约和 diagnostics，而是开始进入真实主链。
