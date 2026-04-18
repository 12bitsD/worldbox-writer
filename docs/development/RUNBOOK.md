# 运行手册

**文档状态**：Active (v0.6.0+)  
**最后更新**：2026-04-18

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
