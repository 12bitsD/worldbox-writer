# 运行手册

**文档状态**：Active (v0.6.0+)  
**最后更新**：2026-04-22

本文档记录本地开发和联调中最常见的问题与处理方式。

## 1. 基本启动命令

后端：

```bash
make dev-api
```

前端：

```bash
make dev-web
```

常规检查：

```bash
make lint
make test
```

## 2. 常见问题

### 2.1 `make setup` 失败

排查顺序：

1. 检查 Python 是否为 3.11+
2. 检查 Node.js 是否可用，推荐 20
3. 检查 `corepack` 或 `pnpm` 是否可执行
4. 检查网络是否能访问 PyPI / npm registry

### 2.2 后端启动失败

重点检查：

- `.env` 是否存在
- `LLM_PROVIDER` / `LLM_API_KEY` 是否配置正确
- `worldbox.db` 是否有权限问题
- 端口 `8000` 是否已被占用

验证命令：

```bash
curl http://localhost:8000/api/health
```

### 2.3 前端启动但页面空白

重点检查：

- 后端是否正常启动
- 浏览器控制台是否有接口请求错误
- `frontend/src/types` 是否与后端返回结构漂移

### 2.4 SSE 流无数据

重点检查：

- 推演是否真实进入运行态
- `/api/simulate/{id}/stream` 是否返回 200
- 后端是否有异常中断

### 2.5 `make test` 失败

后端失败时先看：

- `artifacts/reports/backend/pytest.xml`
- `artifacts/reports/backend/coverage.xml`

前端失败时先看：

- `artifacts/reports/frontend/vitest.xml`
- `frontend` 构建错误输出

### 2.6 Sprint 8 分支能力需要紧急止损

Sprint 8 的 branching loop 由环境变量 `FEATURE_BRANCHING_ENABLED` 控制。

关闭方式：

```bash
FEATURE_BRANCHING_ENABLED=0 make dev-api
```

或在现有服务环境里显式注入：

```bash
export FEATURE_BRANCHING_ENABLED=0
```

关闭后的预期行为：

- `POST /api/simulate/{id}/branch`
- `POST /api/simulate/{id}/branch/switch`
- `POST /api/simulate/{id}/branch/pacing`
- `GET /api/simulate/{id}/branch/compare`

这些接口会返回可解释错误，系统退回单主线安全行为。

止损验证步骤：

1. 访问 `GET /api/health`，确认服务已重启且无启动错误。
2. 打开一个已有会话，确认 `GET /api/simulate/{id}` 仍可读取主线。
3. 调用任一 branch 接口，确认返回“分支功能当前已关闭”。
4. 继续执行一次普通单主线推演，确认 `start / intervene / export` 不受影响。

恢复方式：

```bash
export FEATURE_BRANCHING_ENABLED=1
make dev-api
```

### 2.7 Sprint 18 双循环链路需要紧急止损

双循环链路由环境变量 `FEATURE_DUAL_LOOP_ENABLED` 控制。

关闭方式：

```bash
FEATURE_DUAL_LOOP_ENABLED=0 make dev-api
```

或在现有服务环境里显式注入：

```bash
export FEATURE_DUAL_LOOP_ENABLED=0
```

关闭后的预期行为：

- 新推演退回 legacy Actor candidate event 路径
- 已有 `SceneScript` / `NarratorInput` / rendered text 不会被删除
- `/api/simulate/{id}/dual-loop/compare` 仍可读取已有证据，用于事故分析

止损验证步骤：

1. 访问 `GET /api/health`，确认服务已重启且无启动错误。
2. 新建一次普通推演，确认能生成故事节点和正文。
3. 对事故会话执行 `python -m worldbox_writer.evals.dual_loop_compare <sim_id>`，保存报告。
4. 若是模型质量问题，补跑 `make model-eval` 并记录 provider / model / route 信息。

完整灰度与恢复流程见 [Dual-loop Rollout Runbook](DUAL_LOOP_ROLLOUT.md)。

## 3. 数据与路径

当前默认数据文件：

- SQLite：`worldbox.db`
- 本地环境变量：`.env`
- CI 报告目录：`artifacts/reports/`

## 4. 已知告警

当前本地测试中已知但不阻塞的告警：

- FastAPI `on_event` deprecation warning
- coverage 的 `module-not-measured` warning

这些问题应在后续稳定性迭代中清理，但不属于当前最小落地包范围。
