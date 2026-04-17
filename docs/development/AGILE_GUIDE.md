# 敏捷开发指南与工程规范 (Agile Development Guide)

**文档状态**：Active (v0.6.0+)
**作者**：Manus AI
**最后更新**：2026-04-17

本文档规定了 WorldBox Writer 项目的开发流程、代码规范与质量标准。所有贡献者必须严格遵守。

## 1. 敏捷开发流程 (Agile Workflow)

本项目采用标准的 Scrum 框架进行迭代开发。

### 1.1 迭代周期 (Sprint Cycle)
- **时长**：每个 Sprint 周期为 2 周（14 天）。
- **Sprint 计划会**：Sprint 第一天举行。从 Product Backlog 中挑选高优先级 Story 移入 Sprint Backlog，并拆解为具体 Task（估算以小时计）。
- **每日站会 (Daily Standup)**：每天异步同步进度（昨日完成、今日计划、阻塞问题）。
- **Sprint 评审会与回顾会**：Sprint 最后一天举行。演示可工作的软件增量（Increment），回顾流程中可改进的点。

### 1.2 产品规划层级 (Planning Hierarchy)

产品规划遵循自顶向下的递进结构：

```
Product Vision (产品愿景)
  └── Release Goals (阶段大目标)
        └── Epics (史诗故事)
              └── User Stories (用户故事)
                    └── Sprint Planning (冲刺排期)
```

每个 Sprint 的目标必须从 Release Goal 和 Epic 中自然推导而出，而非功能的随意堆砌。

### 1.3 故事点估算 (Story Point Estimation)
- 采用斐波那契数列（1, 2, 3, 5, 8, 13, 21）。
- 估算不仅考虑代码工作量，还必须包含测试、文档更新和 Prompt 调优的复杂度。
- 超过 13 点的 Story 必须被拆分。

## 2. 测试策略 (Testing Strategy)

由于多 Agent 系统的输出具有非确定性，分层测试是保障系统稳定性的核心手段。

### 2.1 测试分层

本项目采用三层测试策略：

| 层级 | 名称 | LLM 调用 | 运行时机 | 测试重点 |
|---|---|---|---|---|
| **L1** | 纯逻辑测试 (Unit Tests) | 无 | 每次 CI | 数据模型验证、状态机流转、DAG 节点依赖校验、API 端点路由、数据库 CRUD |
| **L2** | 集成测试 (Integration Tests) | 真实调用 | 本地手动 / 定期调度 | Agent 输出格式合规性、端到端推演流程、关系推理正确性 |
| **L3** | 模型评估基准 (Model Eval) | 真实调用 | 手动触发 (Sprint 9+) | 多模型输出质量对比、成本效益分析、降级阈值验证 |

### 2.2 L1 纯逻辑测试

- **不涉及任何 LLM 调用**，测试纯代码逻辑。
- 测试重点：输入数据的解析、Pydantic 模型验证、状态机的流转逻辑、DAG 节点的依赖校验、Gate Keeper 的规则拦截、API 端点的请求/响应格式、SQLite 持久化的 CRUD 操作。
- 要求：毫秒级运行，在 CI 中自动执行。
- 标记：无特殊标记（默认运行）。

### 2.3 L2 集成测试

- **使用真实的 LLM API 调用**，验证 Agent 在真实模型输出下的行为。
- 测试重点：Agent 是否能根据给定的上下文输出符合预期格式（如 JSON）的行动提议；端到端推演流程是否能正常完成；关系推理和约束校验是否正确。
- 要求：使用断言验证输出的**结构和关键字段**，而非验证具体文本内容（因为 LLM 输出不确定）。
- 标记：`@pytest.mark.integration`。
- 运行方式：本地手动执行 `pytest -m integration`，不在常规 CI 中运行（避免消耗 API 额度）。
- 建议使用较小、较快的模型（如 MIMO、GPT-4o-mini 或本地 Ollama）以降低成本。

### 2.4 L3 模型评估基准 (Sprint 9+)

- 针对多模型路由场景，创建一套固定的"金标准"场景。
- 对每个模型组合运行并评估输出质量（结构合规性、逻辑一致性、字段完整性）。
- 在 CI 中通过 `workflow_dispatch` 手动触发，输出质量分数报告。
- 标记：`@pytest.mark.model_eval`。

### 2.5 覆盖率要求

| 层级 | 覆盖率目标 | 说明 |
|---|---|---|
| L1 纯逻辑测试 | > 80% | 核心模型和工具函数力争 > 90%；Agent 的 LLM 调用路径不计入 |
| L2 集成测试 | 不设硬性指标 | 以场景覆盖为主，确保每个 Agent 至少有 1 个端到端场景 |
| L3 模型评估 | 不设硬性指标 | 以质量分数为主，低于阈值自动降级告警 |

## 3. 分支策略 (Branching Strategy)

本项目采用简化的 GitHub Flow。

### 3.1 分支命名规范
- 主分支：`main`（永远保持可部署状态）。
- 功能分支：`feature/US-{ID}-short-desc`（例如：`feature/US-01.01-init-director`）。
- 修复分支：`bugfix/ISSUE-{ID}-short-desc`。
- 实验分支：`spike/short-desc`（用于技术验证，不合并入主分支）。

### 3.2 提交规范 (Commit Convention)
必须遵循 Conventional Commits 规范：
- `feat:` 新功能
- `fix:` 修复 Bug
- `test:` 添加或修改测试
- `docs:` 文档更新
- `refactor:` 重构代码（不改变行为）
- `chore:` 构建过程或辅助工具的变动

示例：`feat(director): US-01.01 add prompt parsing for world initialization`

## 4. 完成定义 (DoD - Definition of Done)

一个 User Story 或 Task 只有满足以下所有条件，才能被标记为"完成"（Done）：

1. **代码已提交**：所有代码已推送到对应的 feature 分支。
2. **测试达标**：
   - 对应的 L1 纯逻辑测试已编写并全部通过。
   - 如涉及 Agent 行为变更，对应的 L2 集成测试已编写并在本地验证通过。
3. **代码审查通过**：提交 Pull Request (PR)，并至少获得一名核心维护者的 Approve。
4. **CI 流水线通过**：GitHub Actions 中的 Lint、Type Check、L1 Tests 全部呈绿色。
5. **文档已更新**：
   - 如果新增了 API，Swagger/OpenAPI 文档已更新。
   - 如果修改了核心架构或 Agent 行为，对应的设计文档已同步更新。
   - README 与相关 Sprint 文档已同步更新。
6. **可演示 (Demonstrable)**：在本地或 Staging 环境中，能够按照 Acceptance Criteria 演示该功能。

## 5. 持续集成与部署 (CI/CD)

### 5.1 CI 触发条件与检查项

| 触发条件 | Job | 检查内容 |
|---|---|---|
| 每次 push / PR 到 `main` | `lint` | `black` 格式化检查 + `isort` 导入排序检查 |
| 每次 push / PR 到 `main` | `typecheck` | `mypy` 静态类型检查 |
| 每次 push / PR 到 `main` | `test` | L1 纯逻辑测试（`pytest -m "not integration"`） |
| 手动触发 (`workflow_dispatch`) | `model-eval` | L3 多模型评估基准（Sprint 9+ 实现） |

### 5.2 集成测试的 CI 策略

L2 集成测试（`@pytest.mark.integration`）**不在常规 CI 中运行**，原因如下：
- 需要真实的 LLM API 密钥和额度。
- 运行时间较长（每个 Agent 测试需 30-120 秒）。
- LLM 输出的非确定性可能导致 CI 不稳定。

开发者应在本地提交 PR 前手动运行集成测试确认通过。

### 5.3 CD 部署

合并入 `main` 分支后，自动构建 Docker 镜像并部署到测试环境（待配置）。
