# Sprint 0: 基础设施与架构设计

**时间**：2026-04-16
**目标**：完成项目的所有前期准备工作，搭建工程脚手架，定义核心数据结构，为 Sprint 1 的开发扫清障碍。

## 1. Sprint 目标 (Sprint Goal)
- 明确产品愿景与架构设计。
- 完成敏捷开发所需的文档体系（PRD、User Stories、开发规范）。
- 初始化 GitHub 仓库，搭建基本的 Python 开发环境与 CI 流水线。
- **产出物**：一个包含完整文档、空目录结构、基础配置文件（`pyproject.toml` 等）且能在 CI 中跑通一个空测试的 `main` 分支。

## 2. Sprint Backlog (任务列表)

| Task ID | 任务描述 | 状态 | 负责人 |
| :--- | :--- | :--- | :--- |
| **T0-01** | 初始化 GitHub 仓库 `worldbox-writer` | Done | Manus AI |
| **T0-02** | 撰写产品愿景与 README | Done | Manus AI |
| **T0-03** | 撰写核心架构设计文档 (`DESIGN.md`) | Done | Manus AI |
| **T0-04** | 撰写产品需求与用户故事 (`USER_STORIES.md`) | Done | Manus AI |
| **T0-05** | 撰写敏捷开发指南与规范 (`AGILE_GUIDE.md`) | Done | Manus AI |
| **T0-06** | 搭建 Python 工程脚手架 (Poetry/uv + pytest) | To Do | - |
| **T0-07** | 配置 GitHub Actions (Lint + Test) | To Do | - |

## 3. Sprint 0 完成定义 (Definition of Done for Sprint 0)
- 所有列出的文档（T0-01 至 T0-05）已合并入 `main` 分支。
- 任何人 `git clone` 仓库后，运行 `make test` 能够成功执行（即使只有 1 个占位测试）。
- 代码规范工具（black, isort, mypy）配置完毕。

## 4. Sprint 1 展望 (Look Ahead to Sprint 1)
Sprint 1 的核心目标将是：**打通核心推演引擎的骨架（Epic 01）**。
- 实现 Director Agent 的需求解析（US-01.01）。
- 定义 DAG 节点的数据结构。
- 实现一个最简单的 Actor Agent 提议生成流（US-01.02）。
