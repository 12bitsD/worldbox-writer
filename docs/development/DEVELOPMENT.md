# 开发指南

**文档状态**：Active
**最后更新**：2026-05-11

本文档是本仓库本地开发、CI 门禁、测试分层、灰度回滚、发布、Secret 管理与类型基线的**单一入口**。
合并自原 `DEV_WORKFLOW.md` / `CI_SETUP.md` / `SECRETS_POLICY.md` / `AGILE_GUIDE.md` / `RUNBOOK.md` /
`RELEASE_PROCESS.md` / `TYPECHECK_BASELINE.md` / `DUAL_LOOP_ROLLOUT.md`。

---

## 目录

1. [环境准备](#1-环境准备)
2. [命令入口](#2-命令入口)
3. [日常开发流程](#3-日常开发流程)
4. [CI 门禁与分层测试](#4-ci-门禁与分层测试)
5. [分支与提交规范](#5-分支与提交规范)
6. [Secrets 策略](#6-secrets-策略)
7. [运行手册（故障排查）](#7-运行手册故障排查)
8. [Feature Flag 紧急止损](#8-feature-flag-紧急止损)
9. [发布流程](#9-发布流程)
10. [双循环灰度与运行手册](#10-双循环灰度与运行手册)
11. [类型检查基线](#11-类型检查基线)
12. [推荐仓库设置](#12-推荐仓库设置)

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
- `FEATURE_DUAL_LOOP_ENABLED`（双循环开关，默认 1，详见 §10）
- `FEATURE_BRANCHING_ENABLED`（分支能力开关，默认 1）
- `WB_COLLECT_SAMPLES`（中间节点样本采集开关，默认关闭；设为 `1` 时写入 `artifacts/intermediate_samples/`）

---

## 2. 命令入口

所有命令统一走根目录 `Makefile`：

| 命令 | 作用 |
| :--- | :--- |
| `make setup` | 安装后端 + 前端依赖 |
| `make lint` | `black --check` + `isort --check-only` + `eslint` |
| `make typecheck` | 运行 `mypy`（非阻塞，见 §11） |
| `make test` | 后端 L1 pytest + 前端 vitest + 前端 build |
| `make check` | `lint` + `typecheck` + `test` 合集 |
| `make integration` | 依赖真实 LLM 的集成测试（`-m integration`） |
| `make model-eval` | 多模型评估 harness（手动触发） |
| `make intermediate-eval` | 中间节点 LLM2LLM 评测 harness（手动触发，默认 P0 Critic + Actor） |
| `make perf` | 容量门禁合成推演（手动触发） |
| `make dev-api` | 启动 FastAPI 后端 |
| `make dev-web` | 启动 Vite 前端 dev server |

对应脚本：

- `scripts/ci/backend-quality.sh`
- `scripts/ci/frontend-quality.sh`
- `scripts/ci/model-eval.sh`
- `scripts/ci/perf-gate.sh`
- `scripts/eval/intermediate_eval.py`
- `scripts/e2e_judge.py`

本地开发、GitHub Actions 与后续任意 CI 平台都复用这套脚本，**不允许**把命令直接写死在 workflow YAML 里。

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

## 4. CI 门禁与分层测试

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

- `make typecheck`：仓库存在历史 mypy 债务，详见 §11
- `make integration`：需要真实 LLM API 密钥、耗时长、输出非确定
- `make intermediate-eval`：需要真实 LLM judge 和已采集/固化样本，作为中间节点质量诊断入口
- `make model-eval`：成本高，作为发布护栏和人工评估入口
- `make perf`：容量合成测试，按需触发

开发者应在本地提交 PR 前自行执行相关检查。

### 4.3 分层测试策略

| 层级 | LLM 调用 | 运行时机 | 测试重点 |
| :--- | :--- | :--- | :--- |
| **L1** 纯逻辑测试 | 无 | 每次 CI | 数据模型验证、状态机、DAG 依赖、API 路由、SQLite CRUD |
| **L2** 集成测试（`@pytest.mark.integration`） | 真实调用 | 本地手动 | Agent 输出格式合规性、端到端推演 |
| **L3** 模型评估（`@pytest.mark.eval` / eval runner） | 真实调用 | 手动触发 | Final judge、Intermediate judge、模型路由健康度 |

- L1 测试要求毫秒级运行，不得引入真实 LLM 调用。
- L2/L3 的输出断言只校验**结构与关键字段**，不得断言具体文本内容。
- L2 建议用小模型（MIMO / gpt-4o-mini / 本地 Ollama）降本。
- L3 runner 只能用 LLM judge 产生质量分数，本地代码只做格式校验、聚合、报告与阈值判断。

中间节点评测遵循同一分层（详见 [QUALITY_SPEC.md](../product/QUALITY_SPEC.md)）：

- P0 当前覆盖 `CriticAgent._call_llm_for_review` 与 `invoke_isolated_actor_intent`。
- 默认测试最多覆盖静态 / schema / fixture 结构检查，不用测试替身替代 Judge 或 Critic 的质量行为。
- 质量验收通过 `make intermediate-eval` 或 `python scripts/eval/intermediate_eval.py …` 真实调用 LLM 手动触发。
- runner 默认 `concurrency=1`，报告写入 `artifacts/reports/intermediate_eval/`。

### 4.4 覆盖率目标

- L1 覆盖率 > 80%，核心模型和工具函数力争 > 90%（LLM 调用路径不计入）
- L2 至少为每个 Agent 覆盖 1 个端到端场景
- L3 不设硬性指标，以质量分数为主，低于阈值自动降级告警

### 4.5 完成定义（DoD）

User Story 或 Task 必须同时满足：

1. 代码已推送到 feature 分支
2. L1 测试已编写并通过
3. 若涉及 Agent 行为变更，L2 集成测试已本地验证通过
4. PR 至少一名核心维护者 Approve
5. CI 默认门禁全绿
6. 文档同步更新：新增 API → Swagger；核心架构 / Agent 变更 → 设计文档；对应 Sprint 文档 + 根 README
7. 可在本地按 Acceptance Criteria 演示

涉及中间节点评测的 task 还必须满足：

1. 质量验收必须通过真实 LLM runner 完成，不能用测试替身替代 Judge 或 Critic 的质量行为
2. 红蓝队 fixtures 带 `manifest.json`，说明 policy source、规则 id、阈值和更新策略
3. 真实 LLM runner 默认 `concurrency=1`
4. 验收报告记录样本数、耗时、Top 失败维度和 recall / precision

### 4.6 Sprint 规则

- **周期**：2 周 / Sprint
- **规划层级**：`Product Vision → Release Goals → Epics → User Stories → Sprint`，每个 Sprint 目标必须从 Release Goal 和 Epic 自然推导
- **估算**：斐波那契（1/2/3/5/8/13/21）。超过 13 点必须拆分
- **每日异步站会**：昨日完成 / 今日计划 / 阻塞

---

## 5. 分支与提交规范

### 5.1 分支命名

采用简化的 GitHub Flow：

- `main`：永远保持可部署状态
- `feature/<短描述>` 或 `feature/US-{ID}-short-desc`：新功能
- `bugfix/<短描述>` 或 `bugfix/ISSUE-{ID}-short-desc`：Bug 修复
- `spike/<短描述>`：技术验证，不合并入主分支

### 5.2 提交信息

必须遵循 Conventional Commits：

- `feat:` 新功能
- `fix:` 修复 Bug
- `test:` 添加或修改测试
- `docs:` 文档更新
- `refactor:` 重构
- `chore:` 构建或辅助工具变动

示例：

```text
feat(api): add waiting-state world edit endpoint
```

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

## 7. 运行手册（故障排查）

### 7.1 基本命令

```bash
make dev-api       # 启动后端
make dev-web       # 启动前端
make lint          # 格式 + 静态检查
make test          # 默认测试（L1）
```

### 7.2 常见问题

#### `make setup` 失败

1. Python 是否为 3.11+
2. Node.js 是否可用（推荐 20）
3. `corepack` / `pnpm` 是否可执行
4. PyPI / npm registry 网络

#### 后端启动失败

- `.env` 是否存在
- `LLM_PROVIDER` / `LLM_API_KEY` 是否配置
- `worldbox.db` 权限
- 端口 `8000` 是否占用

验证：

```bash
curl http://localhost:8000/api/health
```

#### 前端启动但页面空白

- 后端是否正常
- 浏览器控制台接口请求错误
- `frontend/src/types` 是否与后端响应漂移

#### SSE 流无数据

- 推演是否真实进入运行态
- `/api/simulate/{id}/stream` 是否返回 200
- 后端异常中断日志

#### `make test` 失败

- 后端：`artifacts/reports/backend/pytest.xml`、`coverage.xml`
- 前端：`artifacts/reports/frontend/vitest.xml`

### 7.3 数据与路径

- SQLite：`worldbox.db`
- 环境变量：`.env`
- CI 报告：`artifacts/reports/`

### 7.4 已知告警（不阻塞）

- FastAPI `on_event` deprecation warning
- coverage `module-not-measured` warning

---

## 8. Feature Flag 紧急止损

核心能力由环境变量控制，出现事故时可快速关闭，系统退回安全路径。

| 能力 | Flag | 关闭后行为 |
| :--- | :--- | :--- |
| 双循环链路（Critic / GM / 分级 Narrator） | `FEATURE_DUAL_LOOP_ENABLED=0` | 退回 legacy Actor candidate event 路径；已有 SceneScript / 正文不删除 |
| Branching（分支并行推演） | `FEATURE_BRANCHING_ENABLED=0` | `/branch/*` 接口返回"功能已关闭"；主线推演不受影响 |

关闭示例：

```bash
FEATURE_DUAL_LOOP_ENABLED=0 make dev-api
# 或
export FEATURE_BRANCHING_ENABLED=0
```

事故响应步骤：

1. `GET /api/health` 确认服务重启无错
2. 打开任一已有会话，确认主线可读
3. 新建一次推演，确认 `start / intervene / export` 正常
4. 双循环事故补跑：`python -m worldbox_writer.evals.dual_loop_compare <sim_id>` 归档报告
5. 若为模型质量问题，补跑 `make model-eval` 记录 provider / model / route

完整灰度与恢复流程见 §10。

---

## 9. 发布流程

### 9.1 发布目标

当前发布流程的目标不是自动化部署，而是确保每次版本发布都有：

- 明确的版本号
- 明确的变更记录
- 明确的验证结果
- 明确的回滚依据

### 9.2 发布前检查

发布前至少完成以下动作：

1. `make lint`
2. `make test`
3. 如改动涉及类型结构，执行 `make typecheck`
4. 如改动涉及真实模型行为，执行 `make integration`
5. 更新 `CHANGELOG.md`
6. 更新 README 或相关设计文档

双循环链路发布前额外执行：

1. 对至少一个新会话生成 compare report：

```bash
python -m worldbox_writer.evals.dual_loop_compare <sim_id> --require-ready
```

2. 如涉及 provider、prompt 或路由策略，执行：

```bash
make model-eval
```

3. 确认回滚路径仍是 `FEATURE_DUAL_LOOP_ENABLED=0`，并检查 §10。

### 9.3 版本号更新位置

当前仓库至少涉及以下版本号：

- `pyproject.toml`
- `frontend/package.json`

如果两端同时对外发布，应保持版本号一致。

### 9.4 发布步骤

推荐流程：

1. 从 `main` 切发布分支或直接在发布 PR 中完成版本修改
2. 更新版本号
3. 更新 `CHANGELOG.md`
4. 合并到 `main`
5. 在 GitHub 打 tag，例如 `v0.6.0`
6. 创建 GitHub Release，并粘贴 changelog 摘要

当前仓库已经提供最小自动化：`.github/workflows/release.yml`。

推荐做法：

- 合并发布 PR 后，推送 tag，例如 `git tag v0.6.0 && git push origin v0.6.0`
- 由 GitHub Actions 自动创建 Release

### 9.5 发布说明模板

建议至少包含：

- 新增能力
- 修复项
- 是否有 breaking changes
- 升级注意事项
- 已知限制

### 9.6 回滚原则

若发布后出现严重问题：

- 先确认问题是否来自前端静态资源、后端接口还是模型配置
- 使用上一个稳定 tag 作为回滚基线
- 回滚后补一条修复 PR，而不是直接在生产问题上继续叠改

---

## 10. 双循环灰度与运行手册

### 10.1 Feature Flag

双循环链路由环境变量控制：

```bash
FEATURE_DUAL_LOOP_ENABLED=1
```

紧急回滚时关闭：

```bash
export FEATURE_DUAL_LOOP_ENABLED=0
make dev-api
```

关闭后的预期行为：

- 主图退回 legacy Actor candidate event 路径
- Inspector / compare API 仍可读取已有会话证据
- 已持久化的 `SceneScript`、`NarratorInput` 和 rendered text 不会被删除

### 10.2 Compare Report

API：

```bash
curl http://localhost:8000/api/simulate/<sim_id>/dual-loop/compare
```

CLI：

```bash
python -m worldbox_writer.evals.dual_loop_compare <sim_id>
```

强制 readiness 失败时返回非零退出码：

```bash
python -m worldbox_writer.evals.dual_loop_compare <sim_id> --require-ready
```

报告默认写入：

```text
artifacts/dual-loop-compare/<sim_id>.json
```

### 10.3 Readiness 判定

Required checks：

- `dual_loop_feature_flag`：`FEATURE_DUAL_LOOP_ENABLED` 必须开启
- `scene_script_lineage`：当前主线节点必须有 `SceneScript` metadata
- `narrator_input_v2`：SceneScript 节点必须由 `NarratorInput` v2 渲染
- `rollback_path`：报告必须带出回滚 flag 和 runbook

Optional checks：

- `critic_verdict_trace`：没有 verdict 只给 warning，不阻断旧会话排查
- `prompt_trace_visibility`：没有 PromptTrace 只给 warning，不阻断旧会话排查

### 10.4 回滚步骤

1. 设置 `FEATURE_DUAL_LOOP_ENABLED=0`
2. 重启 API 服务
3. 访问 `GET /api/health` 确认服务恢复
4. 新建一次普通推演，确认 legacy 路径能生成节点和正文
5. 对事故会话执行 compare report，保存 `artifacts/dual-loop-compare/<sim_id>.json`
6. 创建修复 issue，附上 compare report、integration/model-eval 结果和 provider 信息

### 10.5 恢复步骤

确认修复通过后：

```bash
export FEATURE_DUAL_LOOP_ENABLED=1
make dev-api
```

恢复后重新执行：

```bash
make lint
make test
make integration
```

然后对至少一个新会话生成 compare report，确认 readiness 为 `ready`。

---

## 11. 类型检查基线

### 11.1 当前状态

执行命令：

```bash
make typecheck
```

当前结果（2026-06-08，post-Round 4 cleanup）：

- `mypy 1.20.1`
- `6` 个错误
- 分布在 `6` 个文件
- 历史基线（Sprint 22）：27 个错误 / 9 个文件，含已删 `narrator.py` 的 3 个

### 11.2 文件分布

| 文件 | 错误数 | 主要问题 |
| :--- | ---: | :--- |
| （详见 `artifacts/reports/typecheck/*.txt` 最新报告） | | 详见 `make typecheck` 输出 |
| 注：`agents/narrator.py` 已在 Sprint 26 删除 | — | — |

### 11.3 当前治理规则

在类型债务清零前，执行以下规则：

1. 不要求默认 PR 门禁必须让 `make typecheck` 全绿
2. 新增改动不得引入新的 mypy 错误
3. 修改已在基线中的文件时，应优先顺手减少错误，而不是增加
4. 新模块、新文件原则上应做到 mypy 无错误

### 11.4 建议清理顺序

推荐从最小风险开始：

1. `core/models.py`
2. `utils/llm.py`
3. `agents/director.py`
4. `agents/actor.py`
5. `engine/graph.py`
6. 其余 `agents/*`

### 11.5 退出条件

满足以下条件后，可将 `make typecheck` 恢复为默认 CI 阻塞项：

- 基线错误数降为 `0`
- 新增类型检查 workflow 在 `main` 上连续稳定通过
- PR 模板和开发流程文档同步更新

---

## 12. 推荐仓库设置

为了让文档、代码审查和 CI 真正形成闭环，建议在 GitHub 仓库开启：

- Branch protection：保护 `main`
- Required status checks：`backend-quality`、`frontend-quality`
- Require pull request reviews before merging
- Require review from Code Owners

### 当前限制

- `make typecheck` 当前不会全绿（历史类型债务，见 §11）
- `make model-eval` 为手动评估流程，需要可达的 LLM Provider 才能输出有效报告
- `make perf` 使用合成推演基线，不替代真实线上压测
- 默认 CI 仍以"快速反馈"优先，不承担长耗时 LLM 回归
- 尚无 staging / production 的 environment secret 分层
- 尚无自动化 secret inventory 校验

---

## 13. 加一个新 Prompt（4 步，不改 Python 代码）

Prompt 现在以 **markdown + YAML frontmatter** 存放在 `src/worldbox_writer/prompts/<role>/<id>.md`，
agent ↔ prompt 映射在 `prompts/catalog.json`。加新 prompt **不需要改任何 Python 代码**。

### 13.1 标准流程

```bash
# 1. 在对应 role 子目录下创建 .md 文件
$EDITOR src/worldbox_writer/prompts/director/director_cool_mode.md
```

文件结构：

```markdown
---
id: director_cool_mode
version: 1.0
role: director
changelog:
  - v1.0 - 2026-06-09 - initial cool-mode prompt
default_variant: standard
variants:
  standard:
    description: standard cool-mode planning
    body: |
      你是 WorldBox Writer 的导演 Agent，目标是写一个**冷硬派**故事。
      强调冲突、个人代价、非典型主角。
---

主 body 内容。
可以是 markdown 格式（标题、列表、代码块都会保留）。
```

```bash
# 2. （可选）注册到 catalog.json
# 编辑 src/worldbox_writer/prompts/catalog.json，在 director 的 prompts 列表里加：
#   { "id": "director_cool_mode" }
# 不加也行：catalog 不存在时 catalog.json 是软依赖，agent 直接按 id 查文件即可
```

```python
# 3. agent 代码调
from worldbox_writer.prompting.registry import load_prompt_template

system = load_prompt_template("director_cool_mode")
# 或选 variant：
system = load_prompt_template("director_cool_mode", variant="standard")
```

```bash
# 4. 下次 LLM 调用时生效（mtime 缓存触发 reload）
# 不需要重启服务
make test-backend   # 跑测试确认没回归
git add src/worldbox_writer/prompts/director/director_cool_mode.md
git commit -m "prompt(director): add cool-mode variant"
```

### 13.2 本地试调（不进 git）

```bash
mkdir /tmp/prompts
cp src/worldbox_writer/prompts/director/director_cool_mode.md /tmp/prompts/
# 改 /tmp/prompts/director_cool_mode.md
PROMPT_TEMPLATE_DIR=/tmp/prompts make dev-api
```

### 13.3 Catalog 校验

启动时 `PromptCatalog.reload()` 校验：
- 每个 `*.md` 文件必须有合法 frontmatter（`id` / `version` / `role` / `changelog`）
- `catalog.json` 引用的每个 `id` 必须能在磁盘上找到对应 `.md`
- 启动失败会 fail-fast 并打印**哪个文件/字段**出错

### 13.4 注意事项

- **`_` 前缀的文件/目录被忽略** — 用 `_notes/` / `_examples/` 放本地笔记，不进 catalog
- **variant 两种形式**：`body:`（完整替换主 body）/ `patch:`（追加到主 body 后，空行分隔）
- **改 profile（temperature / max_tokens）要重启服务** — 见 gotcha #13。**改 prompt 内容**不需要重启
- **多个 variant 互不干扰**：每个 .md 文件独立 reload，跨文件不会相互污染

---

## 相关文档

- [架构设计](../architecture/DESIGN.md)
- [质量评测系统 SPEC](../product/QUALITY_SPEC.md) — 含中间节点 LLM2LLM 评测
- [产品策略](../product/PRODUCT_STRATEGY.md)
- [贡献指南](../../CONTRIBUTING.md)
- [安全策略](../../SECURITY.md)
