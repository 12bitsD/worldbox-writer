# Sprint 20 Plan：双视窗创作工作台与透明推演状态

**文档状态**：Completed
**版本目标**：Sprint 20 / Split-view authoring workspace
**Sprint 周期**：快速体验修复
**定位**：Sprint 19 之后的结构性前端体验升级
**作者**：Codex
**最后更新**：2026-04-22

---

## 1. Sprint 20 要解决什么问题

Sprint 19 解决了“关键节点大面板挡阅读”的问题，但 StoryFeed 仍把内循环逻辑和外循环小说正文放在同一个信息流里。结果是：想读小说的人会被逻辑事实打断，想调内循环的人会被正文淹没。

Sprint 20 的目标是把创作界面拆成双视窗：左侧是跑团控制台，右侧是纯小说阅读区，并把设定编辑和工程状态融入当前上下文。

---

## 2. Sprint Goal

**把内循环控制台、外循环阅读器、设定快改和实时工程状态拆清楚，但保持同一节点的双向锚点绑定。**

Sprint 20 结束时，项目具备：

- StoryFeed 双视窗工作台
- 左侧 Slack-style 跑团控制台
- 右侧白纸黑字小说阅读区
- 节点双向锚点高亮和跳转
- 角色名实体提及与 inline hover card
- hover card 内直接修改角色性格和目标
- 跑团控制台底部实时遥测状态胶囊
- 关系图谱拖拽建边/改边
- 关系更新 API 和测试

---

## 3. 方案骨架

### 3.1 承诺交付

1. `StoryFeed` 从单流卡片改为 split-view workspace
2. 内循环内容只进入左侧控制台
3. 小说正文只进入右侧阅读器
4. console / reader 节点点击互相滚动并高亮
5. reader 滚动时同步高亮左侧逻辑节点
6. 角色名自动转为 entity mention
7. 点击角色名弹出 Prompt 属性卡和记忆列表
8. 属性卡可直接保存角色性格和目标
9. telemetry 事件转为状态胶囊
10. 关系图谱支持拖拽节点建立/修改关系
11. 新增 `PATCH /api/simulate/{sim_id}/relationships`

### 3.2 非目标

- 不做完整 IDE 级多窗格布局持久化
- 不做全文 NLP 实体识别，仅先基于世界中的角色名匹配
- 不做单个 intent 的后续局部重跑，因为当前后端还没有 intent-level replay API
- 不允许运行中直接改世界状态，仍遵守等待态/完成态可改的工作区约束

---

## 4. 方案收敛记录

### Round 1：在原 StoryFeed 中继续折叠逻辑信息

问题：

- 折叠仍然把内循环和外循环塞在同一个阅读节奏里
- 用户无法同时对照“这一段正文来自哪个逻辑节点”

结论：否决。

### Round 2：新增独立调试页

问题：

- 调试页会把创作上下文切走，不能边看正文边看逻辑
- 关键节点干预时需要同时参考两侧信息

结论：否决。

### Round 3：同屏双视窗 + 锚点绑定

采用方案：

- 左侧用跑团控制台展示导演、内循环、SceneScript、用户干预
- 右侧只展示小说正文
- 两侧共享 `node.id` 锚点
- 实体提及和关系图谱直接连接设定编辑入口
- telemetry 以状态胶囊形式放在左侧底部，解释后台等待时间

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| S20-01 | StoryFeed split-view workspace | P0 | Done |
| S20-02 | console / reader 双向锚点绑定 | P0 | Done |
| S20-03 | Entity mention hover card | P0 | Done |
| S20-04 | hover card 角色属性快改 | P0 | Done |
| S20-05 | telemetry status chips | P0 | Done |
| S20-06 | relationship drag-to-edit UI | P1 | Done |
| S20-07 | relationship update API | P1 | Done |
| S20-08 | tests / docs / API docs | P0 | Done |

---

## 6. 成功标准

- 小说正文不再和逻辑摘要混排
- 内循环控制台可独立扫描 SceneScript / 逻辑摘要 / 用户干预
- 点击左侧逻辑节点能跳到右侧正文，点击右侧正文能定位左侧逻辑节点
- 小说中的角色名可打开设定卡
- 用户可在设定卡中修改性格和目标，并刷新世界状态
- 推演等待时可以看到最近 telemetry 状态胶囊
- 用户可在可编辑阶段通过关系图谱直接建立或修改关系
- `make lint`、`make test`、`make typecheck` 通过

---

## 7. 风险与后续

当前“局部重跑单个 intent 后续逻辑”还没有实现，因为后端缺少 intent-level replay 和 graph patch API。Sprint 20 先把界面和设定编辑入口铺好，下一步如果要做“拔刀改成下毒后只重跑后续逻辑”，需要新增可持久化的 intent 节点、依赖边和局部重放端点。
