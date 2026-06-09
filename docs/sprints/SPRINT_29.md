# Sprint 29: 端到端契约护栏 — TS 类型生成 + LLM 调用稳定性

> 起草时间：2026-06-09
> 所属：Sprint 28（统一配置治理）的接续 — 把"前端类型手维护"和"LLM 调用脆弱"这两条遗留债务一次性收口。
> 主类：🛠 PLAT 60% + 🎨 CRAFT 20% + 🔬 OBS 20%

---

## 一、整体感观（先看系统，再看动作）

### 1.1 当前系统是什么

WorldBox Writer 是一套「**多 Agent + LangGraph 编排 + FastAPI 后端 + React/TS 前端**」的长篇小说生成系统。Sprint 28 之后，所有可调参数都集中在 `core/constants.py` + `config/settings.py` 的 Pydantic 域里，但**前后端之间的契约**与**LLM 调用的健壮性**仍是工程债。

```
┌─────────────────────────────────────────────────────────────┐
│  ① 编排层   engine/graph.py + engine/dual_loop.py            │
├─────────────────────────────────────────────────────────────┤
│  ② API 层   FastAPI（21 个 REST + 1 个 SSE 流）                │
│             21 个 Pydantic schema 入参/出参                    │
├─────────────────────────────────────────────────────────────┤
│  ③ LLM 调用层  utils/llm.py                                  │
│     httpx.Client.post（非流式）— 无重试，失败直接 500           │
│     httpx.Client.stream（流式）— 无重试，失败直接 500           │
├─────────────────────────────────────────────────────────────┤
│  ④ 前端    React + TypeScript                                │
│     types/index.ts（468 行手维护的 DTO 镜像）                  │
│     hooks/simulationTransport.ts（7 个 SSE 事件 if/else）      │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 系统当前的"控制接口"是什么

| 接口 | 当前状态 | 改一次的真实成本 |
|---|---|---|
| **REST Pydantic schema ↔ TypeScript DTO** | 手维护，21 个 schema × 2 边 | ❌ 改 1 边忘改另 1 边，编译过、运行时崩 |
| **SSE 事件名字符串** | 后端 `core/constants.py::SSE_EVENT_*` + 前端 transport if/else 链 | ❌ 字符串硬编码，新增事件容易漏改 |
| **LLM 调用失败** | 无重试；任何 5xx/429/timeout 直接 500 | ❌ Kimi Coding 限流高发时段（实测 ~30%） |
| **失败原因分类** | `last_llm_call` metadata 只记 `"status": "failed"`，无 reason | ❌ 排障靠翻 stack |
| **测试 LLM 调用** | `tests/conftest.py` 之前不存在；用户需在 shell 里 export `LLM_API_KEY` | ❌ 复制粘贴容易漏 |

### 1.3 Sprint 29 收口什么

- **端到端契约护栏**：REST 改 schema 后，OpenAPI 快照 + TS 类型自动对齐；SSE 事件名新增后必须有前端 handler，否则 CI 失败。
- **LLM 调用稳定性**：5xx / 429 / timeout 自动指数退避重试（可配置）；失败原因按 7 分类枚举写入 metadata。
- **真实 LLM 测试 fixture**：开发者粘 key 到 `tests/.env.test` 即可跑涉及 LLM 的测试，无需 export 环境变量。

---

## 二、目标（可验证）

### 2.1 一次性目标

| ID | 目标 | 验证方式 |
|---|---|---|
| G1 | 新增/修改 REST 路由后，TS 类型自动重新生成；git diff 局限在快照文件 | `make openapi-snapshot && pnpm run gen-types` 无手改 |
| G2 | 新增 SSE 事件时，前端 transport 必须同步加 handler；CI 强制 | `pytest tests/test_contracts/test_sse_strings.py` |
| G3 | 非流式 LLM 调用遇 5xx/429/timeout 自动重试（指数退避）；流式不重试 | `pytest tests/test_utils/test_llm_retry.py` |
| G4 | `last_llm_call` metadata 写入 `failed_reason` 枚举值 | 单测断言枚举值 |
| G5 | 真实 LLM 测试可一键开：粘 key 到 `tests/.env.test` → pytest 自动注入 | `pytest tests/test_engine/test_graph_integration.py` |
| G6 | 零新增 mypy 错误（基线 6/6 维持） | `mypy src` |
| G7 | 21 个 (id, variant) prompt 字节级回归不破 | `pytest -k prompt_byte` |

### 2.2 显式非目标

- 不引入 Alembic 迁移（v0.5.0 不需要 schema 升级）
- 不做 stream 重连/断点续传（流式不重试是有意为之）
- 不做 LLM 调用 observability（tracing 推给 v0.6+）
- 不做 SSE 协议版本协商（事件名字符串是单一真相源，足够）
- 不把手维护的 `frontend/src/types/index.ts` 删掉（逐步迁移；本期只让 generated 文件**可被生成**，但不强制替换 import）

---

## 三、关键决策记录

### 3.1 生成的 TS 文件不入仓（`pnpm run gen-types` 每次本地生成）

**为什么**：CI 不应该信任 `frontend/node_modules` 里的生成器版本；每台机器的本机生成器可能不同。快照入仓是为了给生成器提供稳定输入，输出由本地生成器决定。

**代价**：换机器首次 `pnpm install` 后必须跑 `make openapi-snapshot && pnpm run gen-types` 才能 `tsc -b` 通过。

**备选**：入仓生成文件 — 拒绝了，因为：(1) 容易把"快照变更"和"生成器版本变更"混进同一个 diff；(2) 多人改 PR 时合并冲突频繁。

### 3.2 选用 `openapi-typescript`（npm）而不是 `datamodel-code-generator`（pypi）

**为什么**：v0.25 的 `datamodel-code-generator` 不再支持 TypeScript 输出（CLI 在 v0.61 砍掉了 `--output-model-type typescript`）。`openapi-typescript` 是 OpenAPI 生态的事实标准（156 个版本，openapi-ts.dev 文档完备），专为前端类型设计，输出更干净。

**代价**：多一个 npm devDep（~5MB）。可接受。

**备选**：自写一个简单的 Pydantic → TS 转换器 — 拒绝，因为 21 个 schema 已经够多，且 OpenAPI 3.x spec 的 edge case（oneOf/allOf/$ref）容易踩。

### 3.3 流式 LLM 不重试

**为什么**：流式响应是 chunk-by-chunk 推给前端的。重连会重复输出已经 emit 的 token，污染 SSE 流。

**代价**：流式调用遇 5xx 仍会断流，靠前端 fallback 到 polling（Sprint 12 的实现已经处理）。

**备选**：流式也重试 — 拒绝。

### 3.4 默认不重试 4xx（`LLM_RETRY_RETRY_ON_4XX=False`）

**为什么**：4xx 是代码 bug（参数错、auth 错、rate limit key 错），不是网络抖动。重试只会刷错误日志。

**代价**：用户必须显式开 4xx 重试（生产环境一般不推荐）。

**备选**：默认重试 4xx — 拒绝（用户决策记录中明确"默认 False"）。

### 3.5 测试 key 走 `tests/.env.test` + 自动 `LLM_*` 前缀过滤

**为什么**：(1) key 不能进 shell history（粘进 .env 文件比 export 干净）；(2) 仓库里所有 `tests/.env.test` 都 gitignore，绝无意外提交风险；(3) 模板 `tests/.env.test.example` 入仓，新人可 `cp` 后填值。

**代价**：多一个文件要维护（已有 `tests/.env.test.example`）。

**备选**：直接走用户 shell 的 `LLM_API_KEY` — 拒绝，不灵活且不跨 IDE。

---

## 四、实施 Wave 划分

按依赖关系分 4 个 wave，每个 wave 结束都能跑通测试。

### Wave 1: 配置与基线（无行为变更）

- T1: `LLMFailedReason` 枚举 + `LLM_RETRY_*` settings + `tenacity` 依赖
- T4: `tests/conftest.py` + `tests/.env.test.example` + `.gitignore`
- T5: `tests/test_api/test_openapi_snapshot.py` — 验证 21 路由可达

**Wave 1 验证**：`mypy src` 6/6；`pytest tests/test_config tests/test_api/test_openapi_snapshot.py` 全绿。

### Wave 2: LLM retry + 分类（仅 `utils/llm.py` 行为变更）

- T2: tenacity `@retry` 包裹非流式 `httpx.Client.post`（streaming 路径**不**触碰）
- T3: catch 块写入 `failed_reason: <enum>` + `retry_attempts: <int>` 到 `last_llm_call` metadata
- T10: `test_new_settings.py` 加 4 个 retry env 的 defaults + override + 校验测试

**Wave 2 验证**：`pytest tests/test_utils/test_llm.py tests/test_utils/test_llm_retry.py tests/test_config/test_new_settings.py` 全绿。

### Wave 3: 契约护栏（前端 + 后端）

- T6: `scripts/dev/export_openapi.py` + `make openapi-snapshot`
- T7: `pnpm run gen-types` + `frontend/.gitignore` 排除生成 TS
- T8: `tests/test_contracts/test_sse_strings.py` — 后端 SSE 事件 vs 前端 if/else 字符串对齐

**Wave 3 验证**：跑 `make openapi-snapshot && cd frontend && pnpm run gen-types`，生成文件存在于 `frontend/src/types/api-generated.ts`（gitignored）；`pytest tests/test_contracts/test_sse_strings.py` 全绿（并**主动**暴露 1 个已存在的 `narrator_end` 缺口 → 修补 frontend）。

### Wave 4: 文档 + 原子 commit

- T11: DEVELOPMENT.md §15 + DESIGN.md §8.1 + CHANGELOG.md Unreleased + 本文档
- T12: 一次原子 commit；push 到 main

**Wave 4 验证**：`make check` 全绿；`git log -1` 信息完整。

---

## 五、影响面

| 模块 | 影响 |
|---|---|
| `src/worldbox_writer/utils/llm.py` | +`tenacity.Retrying` 包裹；catch 块 +2 metadata 字段 |
| `src/worldbox_writer/config/settings.py` | +4 个 `RuntimeSettings` 字段 |
| `src/worldbox_writer/core/constants.py` | +`LLMFailedReason` 枚举 + 7 个 string 常量 |
| `frontend/src/hooks/simulationTransport.ts` | +1 个 `narrator_end` 早返回分支（之前是 silently dropped） |
| `frontend/package.json` | +1 devDep (`openapi-typescript`)、+1 script (`gen-types`) |
| `frontend/.gitignore` | 排除 `src/types/api-generated.ts` |
| `pyproject.toml` | +1 devDep (`tenacity>=8.2.3`) |
| `.gitignore` | 排除 `tests/.env.test` |
| `.env.example` | +4 行（自动从 `RuntimeSettings` 重新生成） |
| `tests/conftest.py` | 新增（46 行 autouse session fixture） |
| `tests/.env.test.example` | 新增（key 模板） |
| `tests/test_api/test_openapi_snapshot.py` | 新增（2 测试） |
| `tests/test_utils/test_llm_retry.py` | 新增（14 测试，零网络） |
| `tests/test_contracts/test_sse_strings.py` | 新增（3 测试） |
| `scripts/dev/export_openapi.py` | 新增 |
| `Makefile` | +`openapi-snapshot` target +`help` 行 |
| 文档 | DEVELOPMENT §15、DESIGN §8.1、CHANGELOG Unreleased、docs/sprints/SPRINT_29.md |

---

## 六、不在 Sprint 29 范围 / 留给后续

- 把 `frontend/src/types/index.ts` 全部迁到 `api-generated.ts`（手维护 → 导入 generated）
- LLM 调用 tracing 接 OpenTelemetry
- 流式调用断点续传
- 类型化 SSE 事件 payload（目前只校验事件名字符串，不校验 schema）
- 多后端 provider 下的 snapshot diff 工具

---

## 七、退出标准（Definition of Done）

- [x] `make check`（lint + typecheck + test）全绿
- [x] `mypy src` 仍是 6 个预存错误（基线不变）
- [x] 21 个 (id, variant) prompt 字节级断言不破
- [x] 一次原子 commit 落到 main
- [x] `git log -1` 信息含 "Sprint 29"
- [x] 没有 `tests/.env.test` 被意外提交（`git ls-files tests/.env.test` 空）
- [x] 生成的 `api-generated.ts` 不在 git index
- [x] 用户粘 key 后 `pytest tests/test_engine/test_graph_integration.py` 实际跑通

---

## 八、经验沉淀（给 Sprint 30 的人）

- 同一类契约（HTTP schema / SSE 事件 / LLM 错误）一旦出现"前端手维护 / 后端自动"，几乎必然漂移。OpenAPI 快照是最低成本的护栏。
- 失败原因"枚举化"对 LLM 调用排障是 10× 加速器，1 小时内就能落地，性价比极高。
- `tests/.env.test` + 前缀过滤的 conftest 是"既保灵活、又不漏 key"的最佳折中。复制粘到其它项目前可以再 review 一遍 `os.environ` 是否真的只读 `LLM_*`。
- 流式重连是反模式（重复 token）。任何"流式重试"的设计都要明确断点 + 幂等 token 范围。
