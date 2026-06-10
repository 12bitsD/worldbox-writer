# Changelog

本文件记录面向版本发布的用户可见变更。

格式参考 Keep a Changelog，版本遵循语义化版本思路，但当前项目仍以迭代发布为主。

## [Unreleased]

### Added
- 统一的本地开发入口：`Makefile`
- 平台无关的 CI 脚本：`scripts/ci/*`
- 开发与治理文档：`CONTRIBUTING.md`、`SECURITY.md`、`DEV_WORKFLOW.md`
- 运行手册、发布流程和类型检查基线文档
- `CODEOWNERS` 代码归属定义
- Sprint 7 的关系图谱交互能力：节点聚焦、边详情、历史恢复后的稳定渲染
- Sprint 7 的 Telemetry 关联字段：`trace_id`、`request_id`、`parent_event_id`、`span_kind`、`provider`、`model`、`duration_ms`
- `useSimulation` 状态合并工具与对应前端回归测试

### Changed
- GitHub Actions 改为直接调用仓库脚本
- 默认 CI 门禁收敛为后端质量门禁和前端质量门禁
- README 文档导航改为更清晰的分层入口
- 实时 SSE、历史载荷和刷新恢复现在使用同一套稳定 ID 合并规则
- Telemetry 面板从简单倒序列表升级为可过滤、可分组、可关联阅读的日志视图
- GateKeeper 在拒绝候选事件后会基于 `revision_hint` 做有限次自愈重试

### Fixed
- 修复前端 Sprint 6 fixture 的类型漂移问题
- 修复仓库内现存的 `black` 格式化欠账
- 修复同一会话在实时运行、页面刷新和历史打开路径下的节点/遥测漂移
- 修复前后端 Telemetry schema 在 REST/SSE/持久化之间的不一致

### Added (Sprint 29)
- 自动从 FastAPI 生成 OpenAPI 快照（`make openapi-snapshot`）+ 前端 TS 类型（`pnpm run gen-types`），消除 REST/Pydantic/TypeScript 之间的静默漂移
- `tests/test_contracts/test_sse_strings.py` 守护后端 `SSE_EVENT_*` 常量与前端 transport if/else 链的字符串对齐
- LLM 非流式路径接入 tenacity 指数退避重试（5xx / 429 / timeout），流式路径不重试
- `LLMFailedReason` 枚举（`core/constants.py`）对所有 LLM 失败做分类（`timeout` / `5xx` / `4xx` / `429_rate_limit` / `parse_error` / `validation_error` / `unknown`），并写入 `last_llm_call` metadata
- `LLM_RETRY_MAX_ATTEMPTS` / `LLM_RETRY_BACKOFF_INITIAL_S` / `LLM_RETRY_BACKOFF_MAX_S` / `LLM_RETRY_RETRY_ON_4XX` 四个 env，纳入 `RuntimeSettings`
- `tests/conftest.py` 自动加载 `tests/.env.test`（gitignored，模板 `tests/.env.test.example` 入仓），只注入 `LLM_*` 前缀变量
- 补齐前端 `simulationTransport.ts` 对 `narrator_end` 事件（之前后端发了前端忽略）

### Added (Sprint 30)
- 新增 `ApiSettings` 类（4 个 CORS 字段）+ `api/server.py` CORS lockdown：`allow_origins` / `allow_credentials` / `allow_methods` / `allow_headers` 全部从 env 读（之前是 hardcoded `["*"]`，生产环境不安全）
- 新增 `PromptBudgetSettings` 类（13 个字段）：把 actor / narrator prompt 的 `[..3]` / `[:5]` / `[:80]` / `max_entries=6/4` 等魔法数字收进 settings，运维可调 token 预算
- 新增 `core/metadata_keys.py` 模块（9 个 metadata key 常量）：把散落在 9 个文件里的 `metadata["reflection_notes"]` 等字符串集中到一处；任何 rename 是 breaking change，有单一真相源守护
- 新增 `LLMFailedReason` / 5 个 drift 修复（settings 已存在但 call site 硬编码）：
  - `simulation_service.py:303` `time.sleep(0.2)` → `runtime.intervention_poll_interval_s`
  - `utils/llm.py:638,668` `httpx.Client(timeout=120.0)` → `runtime.llm_call_timeout_s`
  - `workspace_service.py:276` `affinity clamp -100..100` → `simulation.affinity_min/max`
  - `intermediate_judge.py:321` `score >= 5 → 4.0` → `judge.fabricated_evidence_demote_min/to`（与主判路径一致）
  - `config/settings.py:355` `user_agent = "worldbox-writer/0.5.0"` → 派生自 `app.app_version`，env 覆盖仍生效
- 删除 5 个 shadowed 常量（`DEFAULT_SELF_HEAL_ATTEMPTS`, `INTERVENTION_FREQUENCY_MODULUS/REMAINDER`, `DEFAULT_CHROMA_COLLECTION/DIMENSIONS`），settings 是单一真相源

### Changed
- `character_summary_lines` / `named_context` 默认参数从字面量改为 `None`，调用时读 `prompt_budget.*`

## [0.5.0] - 2026-04-17

### Added
- 实时事件流
- 本地 SQLite 持久化
- 等待态编辑能力
- Sprint 6 的关系图谱和 Telemetry 面板
