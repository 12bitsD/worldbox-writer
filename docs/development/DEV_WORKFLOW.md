# 开发流程说明

**文档状态**：Active (v0.6.0+)  
**最后更新**：2026-04-18

本文档说明 WorldBox Writer 的本地开发环境、日常工作流，以及与 GitHub Actions 对齐的质量门禁。

## 1. 目标

项目当前采用一套平台无关的工程流程：

- 本地开发和 CI 复用同一套命令入口
- PR 门禁只运行快速、稳定、可重复的检查
- 真实 LLM 调用保留为手动流程

这套设计可以兼容 GitHub Actions，也便于后续迁移到其他 CI/CD 平台，而不需要改业务仓库结构。

## 2. 命令入口

根目录统一通过 `Makefile` 触发：

```bash
make setup
make lint
make typecheck
make test
make check
make integration
make model-eval
make perf
make dev-api
make dev-web
```

对应脚本：

- `scripts/dev/bootstrap-backend.sh`
- `scripts/dev/bootstrap-frontend.sh`
- `scripts/ci/backend-quality.sh`
- `scripts/ci/frontend-quality.sh`
- `scripts/ci/model-eval.sh`
- `scripts/ci/perf-gate.sh`

## 3. 日常开发流程

推荐顺序：

1. `make setup`
2. 开发功能
3. `make lint`
4. `make test`
5. 如修改了类型边界或接口，再执行 `make typecheck`
6. 如涉及 Agent 行为、Prompt、真实模型依赖，再执行 `make integration`

其中：

- `make lint` 会执行后端 `black/isort` 和前端 `eslint`
- `make test` 会执行后端 L1 pytest、前端 vitest 和前端生产构建
- `make typecheck` 当前为非阻塞检查，主要因为仓库还有历史类型债务

## 4. 环境准备

### 4.1 后端

- Python 3.11+
- 默认使用仓库内 `.venv`
- `make setup` 会自动创建虚拟环境并安装 `.[dev]`，其中已包含 `chromadb`、`python-docx`、`reportlab`

### 4.2 前端

- Node.js 18+
- 推荐 Node.js 20
- `make setup` 会通过 `corepack` 准备 `pnpm`

### 4.3 环境变量

复制 `.env.example` 为 `.env`，并按实际模型提供商填写：

```bash
cp .env.example .env
```

需要真实模型时，至少配置：

- `LLM_PROVIDER`
- `LLM_API_KEY`
- 可选 `LLM_BASE_URL`
- 可选 `LLM_MODEL`
- 可选 `MEMORY_VECTOR_BACKEND`（默认 `auto`，优先使用 ChromaDB）
- 可选 `MEMORY_VECTOR_PATH`（用于持久化 ChromaDB 索引）

## 5. CI/CD 约定

默认 GitHub Actions 常规门禁包括：

- 后端：`black --check`、`isort --check-only`、`pytest -m "not integration"`
- 前端：`eslint`、`vitest`、`pnpm build`

不进入默认 PR 门禁的内容：

- `mypy`
- `pytest -m integration`
- 多模型 `model-eval`

原因：

- `mypy` 当前有历史类型债务，直接阻塞 PR 会降低迭代效率
- 集成测试和模型评估依赖真实 LLM，成本更高且更不稳定

## 6. 常见场景

### 6.1 新功能开发

```bash
make setup
make lint
make test
```

### 6.2 修改类型定义、接口结构

```bash
make typecheck
```

### 6.3 修改 Agent 行为或 Prompt

```bash
make integration
```

### 6.4 验证本地服务

```bash
make dev-api
make dev-web
```

## 7. 当前限制

- `make typecheck` 目前不会全绿，这是已知历史问题，不是新流程引入的问题
- `model-eval` 现为手动评估流程，需要真实可达的 LLM Provider 才能输出有效报告
- `perf` 使用合成推演基线做容量门禁，不替代真实线上压测
- 默认 CI 仍以“快速反馈”优先，不承担长耗时 LLM 回归
