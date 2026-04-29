# 敏捷开发指南

本文档聚焦本项目的**测试分层策略**、**Sprint 规则**、**完成定义**。
环境 / 命令 / CI 门禁 / 分支提交规范 详见 [DEVELOPMENT.md](./DEVELOPMENT.md)。

---

## 1. Sprint 规则

- **周期**：2 周 / Sprint
- **规划层级**：`Product Vision → Release Goals → Epics → User Stories → Sprint`
  - 每个 Sprint 目标必须从 Release Goal 和 Epic 自然推导，不做功能堆砌
- **估算**：斐波那契（1/2/3/5/8/13/21）。超过 13 点必须拆分
- **每日异步站会**：昨日完成 / 今日计划 / 阻塞

---

## 2. 测试分层策略

多 Agent 系统输出非确定性，必须分层测试。

| 层级 | 名称 | LLM 调用 | 运行时机 | 测试重点 |
|----|----|--------|------|------|
| **L1** | 单元测试 | 无 | 每次 CI | 数据模型、状态机、DAG 依赖、API 路由、DB CRUD |
| **L2** | 集成测试 | 真实调用 | 本地 / 定期 | Agent 输出格式、端到端推演、关系推理 |
| **L3** | 模型评估 | 真实调用 | 手动触发 | 多模型输出质量对比、降级阈值 |

### L1 单元测试
- 纯逻辑，毫秒级运行；CI 中自动执行
- 无特殊标记（默认运行）

### L2 集成测试
- 标记：`@pytest.mark.integration`
- 验证**结构和关键字段**，不验证具体文本
- 本地执行 `make integration`；不进常规 CI（避免 API 额度消耗 + 非确定性）
- 建议用小模型（MIMO / gpt-4o-mini / 本地 Ollama）降本

### L3 模型评估
- 标记：`@pytest.mark.model_eval`
- 通过 `workflow_dispatch` 手动触发
- 输出质量分数报告；低于阈值自动降级告警

### 覆盖率要求

| 层级 | 目标 | 说明 |
|----|----|----|
| L1 | > 80% | 核心模型 / 工具 > 90%；LLM 调用路径不计入 |
| L2 | 场景覆盖 | 每个 Agent 至少 1 个端到端场景 |
| L3 | 质量分 | 低于阈值自动降级告警 |

---

## 3. 完成定义 (DoD)

User Story 或 Task 必须同时满足：

1. 代码已推送到 feature 分支
2. L1 测试已编写并通过
3. 若涉及 Agent 行为变更，L2 集成测试已本地验证通过
4. PR 至少一名核心维护者 Approve
5. CI 默认门禁全绿
6. 文档同步更新：新增 API → Swagger；核心架构 / Agent 变更 → 设计文档；对应 Sprint 文档 + 根 README
7. 可在本地按 Acceptance Criteria 演示

---

## 相关文档

- [DEVELOPMENT.md](./DEVELOPMENT.md) — 环境、命令、CI 门禁、分支提交规范
- [RUNBOOK.md](./RUNBOOK.md) — 常见故障排查
- [RELEASE_PROCESS.md](./RELEASE_PROCESS.md) — 发布流程
