# Contributing Guide

**文档状态**：Active (v0.6.0+)  
**最后更新**：2026-04-18

本文档说明如何向 WorldBox Writer 提交代码、文档和测试变更。

## 1. 开发前准备

首次进入仓库后，建议先执行：

```bash
make setup
cp .env.example .env
```

日常开发最常用的命令：

```bash
make lint
make test
make typecheck
make integration
```

更多背景请参考：

- [README](README.md)
- [开发指南](docs/development/DEVELOPMENT.md)
- [敏捷开发指南](docs/development/AGILE_GUIDE.md)

## 2. 分支与提交规范

分支命名：

- `feature/US-{ID}-short-desc`
- `bugfix/ISSUE-{ID}-short-desc`
- `spike/short-desc`

提交信息遵循 Conventional Commits：

- `feat:`
- `fix:`
- `docs:`
- `test:`
- `refactor:`
- `chore:`

示例：

```text
feat(api): add waiting-state world edit endpoint
```

## 3. 提交 PR 前最低要求

所有 PR 至少需要满足：

1. `make lint` 通过
2. `make test` 通过
3. 如改动涉及类型边界、接口结构或 TypedDict/Pydantic 模型，执行 `make typecheck`
4. 如改动涉及 Agent 行为、Prompt 或真实模型交互，执行 `make integration`
5. 同步更新相关文档

说明：

- `make typecheck` 当前不是默认 CI 阻塞项，因为仓库仍有历史类型债务
- 但**新增改动不应引入新的 mypy 错误**

类型债务现状见：

- [TYPECHECK_BASELINE.md](docs/development/TYPECHECK_BASELINE.md)

## 4. 文档更新要求

以下变更必须同步更新文档：

- API 路径、请求/响应结构变化
- 核心模型字段变化
- Agent 职责或行为边界变化
- 本地开发方式、测试方式、CI 方式变化
- 版本发布策略变化

常见目标文档：

- [README](README.md)
- [开发指南](docs/development/DEVELOPMENT.md)
- [发布流程](docs/development/RELEASE_PROCESS.md)
- [运行手册](docs/development/RUNBOOK.md)

## 5. 代码评审约定

- PR 应聚焦单一目的，避免将功能、重构、格式化混在一起
- 涉及 `frontend/`、`api/`、`agents/` 或 CI 改动时，请确保相关 owner 参与审查
- 重要行为变更应在 PR 描述中明确写出验证方法和风险点

模块 owner 见：

- [.github/CODEOWNERS](.github/CODEOWNERS)

## 6. 不要这样做

- 不要提交真实 API Key、Token、Cookie 或生产配置
- 不要在无说明的情况下修改大面积格式化结果
- 不要绕过 `Makefile` 和 `scripts/ci/*` 另写一套 CI 命令
- 不要把不稳定的真实 LLM 测试直接塞进默认 PR 门禁

## 7. 安全问题

如果你发现的是安全漏洞，而不是普通 bug，请不要直接公开提 Issue。

请先阅读：

- [SECURITY.md](SECURITY.md)
