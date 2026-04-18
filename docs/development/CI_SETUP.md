# CI/CD 配置说明 (CI Setup Guide)

**文档状态**：Active (v0.6.0+)
**最后更新**：2026-04-18

## 1. GitHub Actions 权限配置

在推送 CI workflow 文件之前，需要先在仓库设置中开启 Workflow 写权限：

1. 进入仓库 `Settings → Actions → General`
2. 在 **Workflow permissions** 区域，选择 **Read and write permissions**
3. 点击 **Save**

## 2. CI 架构概览

当前 CI 采用并行 Job 架构，每次 push / PR 到 `main` 分支时自动触发两个独立的常规门禁 Job：

```
┌────────────────────┐   ┌─────────────────────┐
│  backend-quality   │   │  frontend-quality   │
│ black/isort + L1   │   │ eslint + vitest +   │
│ pytest + coverage  │   │ production build    │
└────────────────────┘   └─────────────────────┘
             │
     ┌───────┴────────┐
     │   model-eval   │
     │ (手动触发,     │
     │  Sprint 9+)    │
     └────────────────┘
```

## 3. CI Workflow 文件

Workflow 文件位于 `.github/workflows/ci.yml`，包含以下 Job：

| Job | 触发条件 | 检查内容 | 运行时间 |
|---|---|---|---|
| `backend-quality` | 每次 push / PR | `black --check` + `isort --check-only` + `pytest -m "not integration"` + coverage/junit | ~1-2min |
| `frontend-quality` | 每次 push / PR | `eslint` + `vitest` + `pnpm build` | ~1min |
| `model-eval` | 手动 `workflow_dispatch` | 多模型评估基准（Sprint 9+ 实现） | ~10min |

这些 workflow 不直接把命令写死在 YAML 中，而是调用仓库内统一脚本：

- `scripts/ci/backend-quality.sh`
- `scripts/ci/frontend-quality.sh`
- `scripts/ci/model-eval.sh`

这样本地开发、GitHub Actions 和后续任意 CI 平台都复用同一套命令入口。

### 3.1 关于类型检查

当前仓库仍有一批历史 `mypy` 错误，因此 `typecheck` 暂未纳入默认 PR 阻塞门禁，但命令入口已经保留：

```bash
make typecheck
```

待类型债务清理完成后，可以将其恢复为常规 CI Job。

### 3.2 关于集成测试

L2 集成测试（标记为 `@pytest.mark.integration`）**不在常规 CI 中运行**，需要开发者在本地手动执行：

```bash
# 运行集成测试（需要 LLM API 密钥）
make integration
```

原因：
- 需要真实的 LLM API 密钥（MIMO / OpenAI / Ollama）
- 运行时间较长（每个 Agent 测试 30-120 秒）
- LLM 输出的非确定性可能导致 CI 不稳定

### 3.3 关于模型评估

`model-eval` Job 通过 `workflow_dispatch` 手动触发，避免每次 PR 都消耗 API 额度。在 GitHub Actions 页面点击 "Run workflow" 并选择 provider 即可触发。

需要在仓库 `Settings → Secrets and variables → Actions` 中配置：

- Secret: `LLM_API_KEY`
- 可选 Secret: `LLM_BASE_URL`
- 可选 Variable: `LLM_MODEL`

## 4. 本地开发环境快速启动

```bash
# 克隆仓库
git clone https://github.com/12bitsD/worldbox-writer.git
cd worldbox-writer

# 一键安装项目依赖（后端 + 前端）
make setup

# 复制环境变量模板并配置 LLM 密钥
cp .env.example .env
# 编辑 .env，填入你的 LLM API 密钥

# 运行常规质量检查
make lint
make test

# 可选：运行类型检查（当前不阻塞 CI）
make typecheck

# 运行 L2 集成测试（需要 API 密钥）
make integration
```

## 5. Secrets 配置

| Secret 名称 | 用途 | 配置位置 |
|---|---|---|
| `LLM_API_KEY` | 模型评估基准测试的 LLM API 密钥 | GitHub → Settings → Secrets → Actions |
| `LLM_BASE_URL` | 兼容 OpenAI / MIMO / Ollama 的自定义网关地址 | GitHub → Settings → Secrets → Actions |

## 6. CI/CD 设计原则

当前流程遵循一套平台无关的工程标准：

- 常规 PR 门禁只跑快速、可重复、无外部依赖的检查
- 真实 LLM 调用不进入默认 CI，避免成本和不稳定性扩散
- 所有 CI 命令必须先在仓库脚本中落地，再由平台调用
- 前后端分开门禁，减少单点失败导致的排障成本

## 7. 推荐仓库设置

为了让文档、代码审查和 CI 真正形成闭环，建议在 GitHub 仓库侧至少开启：

- Branch protection：保护 `main`
- Required status checks：
  - `backend-quality`
  - `frontend-quality`
- Require pull request reviews before merging
- Require review from Code Owners

相关配套文档：

- [贡献指南](../../CONTRIBUTING.md)
- [代码归属](../../.github/CODEOWNERS)
- [发布流程](RELEASE_PROCESS.md)

## 8. 发布自动化

仓库已新增：

- `.github/workflows/release.yml`

默认行为：

- push 形如 `v*` 的 tag 时自动创建 GitHub Release
- 也支持 `workflow_dispatch` 手动输入 tag 创建 Release

该 workflow 使用 GitHub 自动生成 release notes，适合作为当前阶段的最小发布自动化。
