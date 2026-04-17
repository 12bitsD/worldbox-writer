# Sprint 6 Demo Script

本文档用于 Sprint 6 的评审演示与回归验收。

目标不是展示“模型写得多精彩”，而是验证 Sprint 6 的最小闭环是否真实成立：
- 关系数据能生成并展示。
- Telemetry 能实时产生并展示。
- 用户干预后系统能继续推进。
- 会话刷新或重新打开后，历史关系与日志仍可见。

---

## 1. 演示前准备

确保以下服务可正常启动：

```bash
# 后端
python -m uvicorn worldbox_writer.api.server:app --host 0.0.0.0 --port 8000

# 前端
cd frontend && pnpm dev
```

浏览器打开：

```text
http://localhost:5173
```

建议使用已配置好的 LLM 提供商，避免演示中断。

---

## 2. 推荐演示前提

为了更稳定触发关系变化和关键日志，优先使用以下前提之一：

1. `两个敌对门派的年轻继承人被迫联手，对抗正在逼近的灭国危机`
2. `末日地下城里，昔日的搭档在争夺最后的净水源时再次相遇`
3. `王朝边境的两名将领在内乱中短暂结盟，但彼此都怀有疑心`

这些前提更容易产生：
- 角色同场互动
- 合作 / 冲突关键词
- 可解释的关系更新

---

## 3. 演示步骤

### Step 1：启动新推演

操作：
- 输入推荐前提。
- 点击“开始推演”。

预期：
- 页面进入推演态。
- 中间故事流开始出现节点。
- 右栏可切换 `Graph` 和 `Telemetry`。

### Step 2：验证 Telemetry 实时产生

操作：
- 切换到 `Telemetry` 标签。

预期：
- 能看到至少以下几类事件中的若干项：
  - `world_initialized`
  - `world_enriched`
  - `proposal_generated`
  - `passed` 或 `rejected`
  - `node_committed`
  - `started`
  - `completed`
- 日志事件数量会随推演推进增加。

### Step 3：验证关系图谱生成

操作：
- 切换到 `Graph` 标签。

预期：
- 出现角色节点。
- 若事件中出现合作、和解、结盟、背叛、攻击等关系关键词，则出现关系边。
- 下方关系卡片能显示：
  - 角色对
  - `label`
  - `affinity`
  - `note`

### Step 4：验证关键节点干预

操作：
- 等待系统进入 `waiting`。
- 在干预面板中输入一条简单指令，例如：
  - `让两位主角暂时放下分歧，共同撤离`
  - `让其中一人产生动摇，但不要立刻决裂`

预期：
- 干预指令可以成功提交。
- Telemetry 中出现 `intervention_submitted`。
- 故事继续推进，并生成后续节点。

### Step 5：验证历史回放

操作：
- 刷新浏览器页面。

预期：
- 当前会话自动恢复。
- 故事节点仍在。
- `Graph` 和 `Telemetry` 中已有内容仍可查看。

### Step 6：验证最近会话入口

操作：
- 点击“重置”回到 Start 页面。
- 在“最近会话”中打开刚刚的 session。

预期：
- 能重新进入该会话。
- 历史故事流、关系图谱和 telemetry 都可查看。

---

## 4. 通过标准

本次演示只有同时满足以下条件，才算 Sprint 6 主链路可验收：

- Telemetry 至少出现 8 条关键事件。
- 至少出现一条结构化关系边，且 UI 可见。
- 干预提交后系统能继续推进。
- 页面刷新后当前会话可恢复。
- 从 Start 页面重新打开历史会话时，历史内容可回显。

---

## 5. 常见失败信号

若出现以下情况，应视为 Sprint 6 仍未闭环：

- 只有故事流，没有 Telemetry。
- Telemetry 有实时事件，但刷新后全部丢失。
- 图谱只有角色点，没有任何关系边，且多次运行都如此。
- 干预提交后没有后续事件。
- 刷新页面后回到空白 Start 页且无法恢复最近会话。

---

## 6. 回归建议

每次修改以下模块后，都建议至少回放一次本 Demo Script：
- `core/models.py`
- `engine/graph.py`
- `api/server.py`
- `storage/db.py`
- `frontend/src/hooks/useSimulation.ts`
- `frontend/src/components/RelationshipPanel.tsx`
- `frontend/src/components/TelemetryPanel.tsx`
