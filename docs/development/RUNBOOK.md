# 运行手册

本地开发与联调中常见问题的处理方式。

---

## 基本命令

```bash
make dev-api       # 启动后端
make dev-web       # 启动前端
make lint          # 格式 + 静态检查
make test          # 默认测试（L1）
```

---

## 常见问题

### `make setup` 失败
1. Python 是否为 3.11+
2. Node.js 是否可用（推荐 20）
3. `corepack` / `pnpm` 是否可执行
4. PyPI / npm registry 网络

### 后端启动失败
- `.env` 是否存在
- `LLM_PROVIDER` / `LLM_API_KEY` 是否配置
- `worldbox.db` 权限
- 端口 `8000` 是否占用

验证：

```bash
curl http://localhost:8000/api/health
```

### 前端启动但页面空白
- 后端是否正常
- 浏览器控制台接口请求错误
- `frontend/src/types` 是否与后端响应漂移

### SSE 流无数据
- 推演是否真实进入运行态
- `/api/simulate/{id}/stream` 是否返回 200
- 后端异常中断日志

### `make test` 失败
- 后端：`artifacts/reports/backend/pytest.xml`、`coverage.xml`
- 前端：`artifacts/reports/frontend/vitest.xml`

---

## 紧急止损：Feature Flags

核心能力由环境变量控制，出现事故时可快速关闭，系统退回安全路径。

| 能力 | Flag | 关闭后行为 |
|----|----|----|
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

完整灰度与恢复流程见 [DUAL_LOOP_ROLLOUT.md](./DUAL_LOOP_ROLLOUT.md)。

---

## 数据与路径

- SQLite：`worldbox.db`
- 环境变量：`.env`
- CI 报告：`artifacts/reports/`

---

## 已知告警（不阻塞）

- FastAPI `on_event` deprecation warning
- coverage `module-not-measured` warning
