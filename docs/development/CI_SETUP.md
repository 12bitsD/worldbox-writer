# CI/CD 配置说明 (CI Setup Guide)

**文档状态**：Active (v0.6.0+)
**最后更新**：2026-04-17

## 1. GitHub Actions 权限配置

在推送 CI workflow 文件之前，需要先在仓库设置中开启 Workflow 写权限：

1. 进入仓库 `Settings → Actions → General`
2. 在 **Workflow permissions** 区域，选择 **Read and write permissions**
3. 点击 **Save**

## 2. CI 架构概览

当前 CI 采用并行 Job 架构，每次 push / PR 到 `main` 分支时自动触发三个独立的 Job：

```
┌─────────┐   ┌─────────────┐   ┌──────────┐
│  lint   │   │  typecheck  │   │   test   │
│ (black  │   │   (mypy)    │   │ (pytest  │
│  isort) │   │             │   │  L1 only)│
└─────────┘   └─────────────┘   └──────────┘
                                      │
                              ┌───────┴────────┐
                              │  model-eval    │
                              │ (手动触发,     │
                              │  Sprint 9+)    │
                              └────────────────┘
```

## 3. CI Workflow 文件

Workflow 文件位于 `.github/workflows/ci.yml`，包含以下 Job：

| Job | 触发条件 | 检查内容 | 运行时间 |
|---|---|---|---|
| `lint` | 每次 push / PR | `black --check` + `isort --check-only` | ~30s |
| `typecheck` | 每次 push / PR | `mypy src/` | ~60s |
| `test` | 每次 push / PR | `pytest -m "not integration"` + 覆盖率报告 | ~30s |
| `model-eval` | 手动 `workflow_dispatch` | 多模型评估基准（Sprint 9+ 实现） | ~10min |

### 3.1 关于集成测试

L2 集成测试（标记为 `@pytest.mark.integration`）**不在常规 CI 中运行**，需要开发者在本地手动执行：

```bash
# 运行集成测试（需要 LLM API 密钥）
pytest -m integration -v
```

原因：
- 需要真实的 LLM API 密钥（MIMO / OpenAI / Ollama）
- 运行时间较长（每个 Agent 测试 30-120 秒）
- LLM 输出的非确定性可能导致 CI 不稳定

### 3.2 关于模型评估

`model-eval` Job 通过 `workflow_dispatch` 手动触发，避免每次 PR 都消耗 API 额度。在 GitHub Actions 页面点击 "Run workflow" 并选择 `run_model_eval: true` 即可触发。

需要在仓库 `Settings → Secrets and variables → Actions` 中配置 `LLM_API_KEY` Secret。

## 4. 本地开发环境快速启动

```bash
# 克隆仓库
git clone https://github.com/12bitsD/worldbox-writer.git
cd worldbox-writer

# 安装项目依赖（包含开发工具）
pip install -e ".[dev]"

# 复制环境变量模板并配置 LLM 密钥
cp .env.example .env
# 编辑 .env，填入你的 LLM API 密钥

# 运行代码格式化
black .
isort .

# 运行 L1 纯逻辑测试（不需要 API 密钥）
pytest -m "not integration" -v --cov=worldbox_writer --cov-report=term-missing

# 运行 L2 集成测试（需要 API 密钥）
pytest -m integration -v

# 运行全部测试
pytest -v
```

## 5. Secrets 配置

| Secret 名称 | 用途 | 配置位置 |
|---|---|---|
| `LLM_API_KEY` | 模型评估基准测试的 LLM API 密钥 | GitHub → Settings → Secrets → Actions |
