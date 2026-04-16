# 敏捷开发指南与工程规范 (Agile Development Guide)

**文档状态**：Draft (Sprint 0)
**作者**：Manus AI

本文档规定了 WorldBox Writer 项目的开发流程、代码规范与质量标准。所有贡献者必须严格遵守。

## 1. 敏捷开发流程 (Agile Workflow)

本项目采用标准的 Scrum 框架进行迭代开发。

### 1.1 迭代周期 (Sprint Cycle)
- **时长**：每个 Sprint 周期为 2 周（14 天）。
- **Sprint 计划会**：Sprint 第一天举行。从 Product Backlog 中挑选高优先级 Story 移入 Sprint Backlog，并拆解为具体 Task（估算以小时计）。
- **每日站会 (Daily Standup)**：每天异步同步进度（昨日完成、今日计划、阻塞问题）。
- **Sprint 评审会与回顾会**：Sprint 最后一天举行。演示可工作的软件增量（Increment），回顾流程中可改进的点。

### 1.2 故事点估算 (Story Point Estimation)
- 采用斐波那契数列（1, 2, 3, 5, 8, 13, 21）。
- 估算不仅考虑代码工作量，还必须包含测试（TDD）、文档更新和 Prompt 调优的复杂度。
- 超过 13 点的 Story 必须被拆分。

## 2. 测试驱动开发 (TDD - Test-Driven Development)

由于多 Agent 系统的输出具有非确定性，TDD 是保障系统稳定性的唯一手段。

### 2.1 TDD 核心原则
- **红-绿-重构 (Red-Green-Refactor)**：
  1. 先写一个会失败的测试用例（Red）。
  2. 编写最少量的代码让测试通过（Green）。
  3. 优化代码结构，确保测试依然通过（Refactor）。
- **不允许存在没有测试覆盖的业务逻辑**。

### 2.2 Agent 测试策略
由于 LLM 调用的成本和延迟，测试分为两层：
- **单元测试 (Unit Tests)**：
  - **必须 Mock 掉所有 LLM 调用**。
  - 测试重点在于：输入数据的解析、状态机的流转逻辑、DAG 节点的依赖校验、Gate Keeper 的规则拦截。
  - 要求：毫秒级运行，覆盖率 > 90%。
- **集成测试/行为测试 (Integration / Behavior Tests)**：
  - 允许真实的 LLM 调用（建议使用较小、较快的模型如 GPT-4o-mini 或本地 Ollama）。
  - 测试重点在于：Agent 是否能根据给定的上下文输出符合预期格式（如 JSON）的行动提议。
  - 要求：使用断言验证输出的结构和关键字段，而非验证具体文本内容。

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
2. **TDD 达标**：
   - 对应的单元测试已编写并全部通过。
   - 核心业务逻辑的测试覆盖率达到 90% 以上。
3. **代码审查通过**：提交 Pull Request (PR)，并至少获得一名核心维护者的 Approve。
4. **CI 流水线通过**：GitHub Actions 中的 Linting、Unit Tests 构建全部呈绿色。
5. **文档已更新**：
   - 如果新增了 API，Swagger/OpenAPI 文档已更新。
   - 如果修改了核心架构或 Agent 行为，对应的设计文档已同步更新。
6. **可演示 (Demonstrable)**：在本地或 Staging 环境中，能够按照 Acceptance Criteria 演示该功能。

## 5. 持续集成与部署 (CI/CD)

- **CI 触发条件**：每次向 `main` 分支提交 PR 时自动触发。
- **CI 检查项**：
  - 代码格式化检查（如 Python 的 `black` 和 `isort`）。
  - 静态类型检查（如 Python 的 `mypy`）。
  - 运行所有单元测试（Mock LLM）。
- **CD 部署**：(Sprint 1 之后配置) 合并入 `main` 分支后，自动构建 Docker 镜像并部署到测试环境。
