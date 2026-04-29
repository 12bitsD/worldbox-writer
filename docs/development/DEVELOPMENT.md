# 开发指南 (Development Guide)

**文档状态**：Active  
**最后更新**：2026-04-29

本文档合并了原 `DEV_WORKFLOW.md`、`CI_SETUP.md` 与 `SECRETS_POLICY.md`，
是本项目本地开发、CI 门禁与 secret 管理的单一入口。

---

## 1. 环境准备

### 1.1 版本要求

- Python 3.11+
- Node.js 18+（推荐 20）
- pnpm（通过 `corepack` 准备）

### 1.2 一键安装

```bash
git clone https://github.com/12bitsD/worldbox-writer.git
cd worldbox-writer
make setup
```

`make setup` 会依次执行：

- `scripts/dev/bootstrap-backend.sh`：创建 `.venv` 并安装 `.[dev]`（含 `chromadb`、`python-docx`、`reportlab`）
- `scripts/dev/bootstrap-frontend.sh`：通过 `corepack` 准备 pnpm 并安装前端依赖

### 1.3 环境变量

复制 `.env.example` 为 `.env`，按实际 provider 填写：

```bash
cp .env.example .env
```

至少需要：

- `LLM_PROVIDER`
- `LLM_API_KEY`

可选：

- `LLM_BASE_URL`
- `LLM_MODEL`
- `MEMORY_VECTOR_BACKEND`（默认 `auto`，优先 ChromaDB）
- `MEMORY_VECTOR_PATH`（ChromaDB 索引路径）
- `FEATURE_DUAL_LOOP_ENABLED`（双循环开关，默认 1；详见 `DUAL_LOOP_ROLLOUT.md`）
- `FEATURE_BRANCHING_ENABLED`（分支能力开关，默认 1）

---

## 2. 命令入口

所有命令统一走根目录 `Makefile`：

| 命令 | 作用 |
| :--- | :--- |
| `make setup` | 安装后端 + 前端依赖 |
| `make lint` | `black --check` + `isort --check-only` + `eslint` |
| `make typecheck` | 运行 `mypy`（非阻塞，见 `TYPECHECK_BASELINE.md`） |
| `make test` | 后端 L1 pytest + 前端 vitest + 前端 build |
| `make check` | `lint` + `typecheck` + `test` 合集 |
| `make integration` | 依赖真实 LLM 的集成测试（`-m integration`） |
| `make model-eval` | 多模型评估 harness（手动触发） |
| `make perf` | 容量门禁合成推演（手动触发） |
| `make dev-api` | 启动 FastAPI 后端 |
| `make dev-web` | 启动 Vite 前端 dev server |

对应脚本：

- `scripts/ci/backend-quality.sh`
- `scripts/ci/frontend-quality.sh`
- `scripts/ci/model-eval.sh`
- `scripts/ci/perf-gate.sh`
- `scripts/e2e_judge.py`

本地开发、GitHub Actions 与后续任意 CI 平台都复用这套脚本，不允许把命令直接写死在 workflow YAML 里。

---

## 3. 日常开发流程

推荐顺序：

1. `make setup`（首次）
2. 开发功能
3. `make lint`
4. `make test`
5. 如修改类型边界或接口，执行 `make typecheck`
6. 如修改 Agent 行为、Prompt 或真实模型依赖，执行 `make integration`

---

## 4. CI 门禁

### 4.1 Workflow 概览

```
┌────────────────────┐   ┌─────────────────────┐
│  backend-quality   │   │  frontend-quality   │
│ black/isort + L1   │   │ eslint + vitest +   │
│ pytest + coverage  │   │ production build    │
└────────────────────┘   └─────────────────────┘
             │
     ┌───────┴────────┐     ┌───────────────┐
     │   model-eval   │     │  perf-gate    │
     │ (workflow_     │     │ (workflow_    │
     │  dispatch)     │     │  dispatch)    │
     └────────────────┘     └───────────────┘
```

| Job | 触发条件 | 检查内容 | 运行时间 |
| :--- | :--- | :--- | :--- |
| `backend-quality` | push / PR 到 `main` | `black --check` + `isort --check-only` + `pytest -m "not integration"` + coverage/junit | ~1-2 min |
| `frontend-quality` | push / PR 到 `main` | `eslint` + `vitest` + `pnpm build` | ~1 min |
| `model-eval` | 手动 `workflow_dispatch` | 多模型评估基准，产出 report artifact | ~10 min |
| `perf-gate` | 手动 `workflow_dispatch` | 合成推演容量门禁 | ~1 min |

Workflow 文件位于 `.github/workflows/`。

### 4.2 阻塞门禁之外的检查

以下检查**不在**默认 PR 阻塞门禁中：

- `make typecheck`：仓库存在历史 mypy 债务，详见 `TYPECHECK_BASELINE.md`
- `make integration`：需要真实 LLM API 密钥、耗时长、输出非确定
- `make model-eval`：成本高，作为发布护栏和人工评估入口
- `make perf`：容量合成测试，按需触发

开发者应在本地提交 PR 前自行执行相关检查。

### 4.3 分层测试策略

| 层级 | LLM 调用 | 运行时机 | 测试重点 |
| :--- | :--- | :--- | :--- |
| **L1** 纯逻辑测试 | 无 | 每次 CI | 数据模型验证、状态机、DAG 依赖、API 路由、SQLite CRUD |
| **L2** 集成测试 (`@pytest.mark.integration`) | 真实调用 | 本地手动 | Agent 输出格式合规性、端到端推演 |
| **L3** 模型评估 (`@pytest.mark.eval`) | 真实调用 | 手动触发 | LLM-as-judge 双轴质量分数 |

L1 测试要求毫秒级运行，不得引入真实 LLM 调用。
L2/L3 的输出断言只校验**结构与关键字段**，不得断言具体文本内容。

### 4.4 覆盖率目标

- L1 覆盖率 > 80%，核心模型和工具函数力争 > 90%
- L2/L3 不设硬性指标，以场景覆盖和质量分数为主

---

## 5. 分支与提交规范

### 5.1 分支命名

采用简化的 GitHub Flow：

- `main`：永远保持可部署状态
- `feature/<短描述>`：新功能
- `bugfix/<短描述>`：Bug 修复
- `spike/<短描述>`：技术验证，不合并入主分支

### 5.2 提交信息

必须遵循 Conventional Commits：

- `feat:` 新功能
- `fix:` 修复 Bug
- `test:` 添加或修改测试
- `docs:` 文档更新
- `refactor:` 重构
- `chore:` 构建或辅助工具变动

---

## 6. Secrets 策略

### 6.1 Secret 分类

- **本地开发 secret**：`.env` 中的 `LLM_API_KEY` 等
- **CI secret**：GitHub Actions Secrets / Variables
- **平台环境 secret**：未来 staging / production 使用

### 6.2 当前登记项

| 名称 | 用途 | 存放位置 |
| :--- | :--- | :--- |
| `LLM_API_KEY` | 真实模型访问 | 本地 `.env` / GitHub Actions Secret |
| `LLM_BASE_URL` | 自定义模型网关 | 本地 `.env` / GitHub Actions Secret |
| `LLM_MODEL` | 模型名 | 本地 `.env` / GitHub Actions Variable |

### 6.3 强制规则

- 真实 secret 不得提交到 Git 仓库
- `.env.example` 只能放占位符
- 新增 secret 必须同步更新本文件或 `SECURITY.md`
- CI 中优先使用 GitHub Actions Secrets / Variables，不得硬编码到 workflow

### 6.4 轮换与泄露处置

`LLM_API_KEY` 应在以下场景轮换：

- 人员权限变化
- 可疑泄露
- provider 主动要求

若发生泄露：

1. 立即废弃旧密钥
2. 替换 CI / 本地环境密钥
3. 检查 Git 历史、Issue、PR、日志是否有外泄痕迹
4. 记录事件并评估影响范围

---

## 7. 推荐仓库设置

为了让文档、代码审查和 CI 真正形成闭环，建议在 GitHub 仓库开启：

- Branch protection：保护 `main`
- Required status checks：`backend-quality`、`frontend-quality`
- Require pull request reviews before merging
- Require review from Code Owners

---

## 8. 当前限制

- `make typecheck` 当前不会全绿（历史类型债务，见 `TYPECHECK_BASELINE.md`）
- `make model-eval` 为手动评估流程，需要可达的 LLM Provider 才能输出有效报告
- `make perf` 使用合成推演基线，不替代真实线上压测
- 默认 CI 仍以"快速反馈"优先，不承担长耗时 LLM 回归
- 尚无 staging / production 的 environment secret 分层
- 尚无自动化 secret inventory 校验

---

## 9. 相关文档

- [发布流程](RELEASE_PROCESS.md)
- [运行手册](RUNBOOK.md)
- [双循环灰度 Runbook](DUAL_LOOP_ROLLOUT.md)
- [类型检查基线](TYPECHECK_BASELINE.md)
- [敏捷开发指南](AGILE_GUIDE.md)
- [贡献指南](../../CONTRIBUTING.md)
- [安全策略](../../SECURITY.md)
