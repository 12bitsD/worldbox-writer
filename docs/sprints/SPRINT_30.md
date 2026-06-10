# Sprint 30: 配置治理收口 — drift 修复 + CORS lockdown + PromptBudgetSettings + metadata_keys

> 起草时间：2026-06-09
> 所属：Sprint 28（统一配置治理）+ Sprint 29（端到端契约护栏）的接续
> 主类：🛠 PLAT 100%

---

## 一、整体感观（先看系统，再看动作）

### 1.1 当前系统是什么

Sprint 28 把所有可调参数收进了 `core/constants.py` + `config/settings.py`。Sprint 29 给前后端契约加了护栏（OpenAPI snapshot + TS gen + SSE contract）。Sprint 30 收的是 Sprint 28+29 暴露出来的"设置已定义但没人读"和"魔法字符串/数字仍在代码里"两类债务。

```
┌─────────────────────────────────────────────────────────────┐
│  ① 配置层  core/constants.py + config/settings.py           │
│     Sprint 28 定义了 Runtime / Simulation / Judge /          │
│     MemoryRuntime / LLMRouting / App 等域                   │
├─────────────────────────────────────────────────────────────┤
│  ② 调用层  utils/llm.py + engine/services/* + api/server.py │
│     Sprint 28 后仍有5个 site 在硬编码已存在的设置值          │
│     4个 service 文件里有 [:3]/[:5]/[:80] 等12处魔法数字     │
│     14处 metadata key 字符串散落在 engine/ + memory/ + api/  │
├─────────────────────────────────────────────────────────────┤
│  ③ 安全层  api/server.py                                     │
│     CORSMiddleware 完全 wildcard，prod 部署会泄露              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 系统当前的"瑕疵"

| 暗坑 | 位置 | 后果 |
|---|---|---|
| `time.sleep(0.2)` 硬编码 | `api/services/simulation_service.py:303` | `INTERVENTION_POLL_INTERVAL_S` 设了白设 |
| `httpx.Client(timeout=120.0)` 硬编码 | `utils/llm.py:638,668` | `LLM_CALL_TIMEOUT_S` 设了白设 |
| `max(-100, min(100, …))` 硬编码 | `api/services/workspace_service.py:276` | `SIM_AFFINITY_MIN/MAX` 设了白设 |
| `if score >=5: score = 4.0` 硬编码 | `evals/intermediate_judge.py:321` | 与主判 `llm_judge.py` 路径不一致 |
| `user_agent = "worldbox-writer/0.5.0"` 硬编码 | `config/settings.py:355` | 跟 `app.app_version` 漂移 |
| `allow_origins=["*"]` + `allow_credentials=True` | `api/server.py:97-100` | prod 部署 CORS 漏洞 |
| `character.goals[:2]` / `[:5]` / `[:3]` 散落 | `actor_event_service.py` 5处 | 调 actor prompt token 预算要改 .py |
| `character.memory[-3:]` / `max_entries=6/4` / `[-6:]` | `actor_prompt_context_service.py` 4处 | 调 memory recall 要改 .py |
| `confidence=0.35` 硬编码 | `isolated_actor_service.py:337` | fallback confidence 不可调 |
| `character_ids[:3]` / `max_entries=5` / `locations[:2]` | `narration_service.py` 4处 | 调 narrator prompt 要改 .py |
| `metadata["reflection_notes"]` / `["narrator_input"]` 散落 | 9个文件14处 | 改 key 名是 breaking change，没人守 |

### 1.3 Sprint 30 收口什么

1. **drift 修复**：把已存在的设置接到它们的 call site 上，env 真正生效。
2. **CORS lockdown**：新增 `ApiSettings` 类，4个 CORS 字段从 env 读。
3. **PromptBudgetSettings**：12 个 prompt/token 魔法数字收进新类。
4. **metadata_keys**：14 处 metadata key 字符串集中到新模块，单一真相源。
5. **dead-constant 清理**：5 个 shadowed 模块级常量删除。

---

## 二、目标（可验证）

### 2.1 一次性目标

| ID | 目标 | 验证方式 |
|---|---|---|
| G1 | 5个 drift site 改为读 `get_settings()` | `grep -nE "time.sleep\(0\.2\)\|timeout=120\.0\|max\(-100|user_agent.*0\.5\.0"` 全部0匹配 |
| G2 | CORS lockdown：`allow_origins` 从 env 读 | 新 `ApiSettings` 类 + `api/server.py` 重接线 |
| G3 | PromptBudgetSettings：12 字段 default 匹配当前字面量 | 379 tests pass（行为零变化） |
| G4 | metadata_keys：14 处字符串 → `META.META_<KEY>` | `grep` 在 engine/memory/api/evals 下0匹配 |
| G5 | dead-constant 删除5个 | `grep -n DEFAULT_SELF_HEAL_ATTEMPTS|INTERVENTION_FREQUENCY_|DEFAULT_CHROMA_` 全部0匹配 |
| G6 | 零新增 mypy 错误 | `mypy src` 6/6 基线 |
| G7 | 所有现成测试通过 | `pytest -m "not integration" -q` ≥ 379 passed |

### 2.2 显式非目标

- 不做 LLM 路由 carve-out（Sprint 27 已 defer，留 Sprint 31+）
- 不做 clustering / 索引 hot path 的 prompt budget（域启发式不在 audit 范围）
- 不改 frontend metadata key 比较
- 不删 `DEFAULT_JUDGE_MODEL`（是 `ModelEvalSettings.judge_model` 的默认值）
- 不改 `director.py:170-171` 的 `world_builder_completed` 字面量（在发给 LLM 的 JSON 里，会破坏 LLM 可见契约）

---

## 三、关键决策记录

### 3.1 `LLMRoutingSettings.user_agent` 派生不用 `get_settings()`（防递归）

**问题**：`LLMRoutingSettings` 在 `Settings.__init__` 第399行构造，**先于** `AppSettings`（第400行）。`get_settings()` 会重新构造整个 `Settings`，触发 `LLMRoutingSettings.model_validator` → `get_settings()` → 无限递归。

**方案**：在 validator 里直接读 `os.environ.get("APP_VERSION", "0.5.0")`。call-time 读取，monkeypatch 可测。

### 3.2 CORS list 字段用 `Annotated[List[str], NoDecode]`

**问题**：pydantic-settings v2.13.1 会在 `field_validator(mode="before")` 之前先 JSON-decode 复杂类型。`field_validator` 看到的是 list，不是 CSV 字符串，没法 split。

**方案**：`Annotated[List[str], NoDecode]` 让字段跳过 JSON pre-decode，validator 直接拿到原始 env 字符串，CSV split 工作正常。

### 3.3 `character_summary_lines` 默认参数从 `4` 改成 `None`

**问题**：默认参数 `4` 字面量无法读设置。改成 `None` 让函数内部分支读 `prompt_budget.actor_prompt_char_limit`。

**风险**：直接 import 这个函数的外部 caller 会看到 signature 变化（`limit: int | None = None` 而不是 `limit: int = 4`）。Sprint 30 内的调用方都是 in-tree，grep 确认无外部依赖。

### 3.4 `metadata_keys` 不动 `director.py:170-171`

**问题**：这个 `world_builder_completed` 字面量在一个 dict 里，dict 被 JSON 序列化后作为 LLM 输入的一部分发给模型。改字面量 = 改发给 LLM 的契约 = LLM 行为变化。

**方案**：明确 out-of-scope。在文件里加注释指向 `core.metadata_keys` 给将来的人。

---

## 四、实施 Wave 划分

| Wave | 内容 | 任务 |
|---|---|---|
| **Wave 1** | settings + dead-constant cleanup | T1.1-T1.4 (4 parallel) |
| **Wave 2** | drift fixes | T2.1-T2.5 (5 parallel) |
| **Wave 3** | CORS lockdown + metadata_keys | T3.1-T3.2 (2 parallel) |
| **Wave 4** | PromptBudgetSettings migration | T4.1-T4.6 (6 tasks, settings first) |
| **Wave 5** | squash + push | T5.1 |

每个 wave 结束 run `pytest -m "not integration"` + `mypy src`，gate 全绿再 commit。

---

## 五、影响面

| 模块 | 影响 |
|---|---|
| `config/settings.py` | +`ApiSettings` (4 fields) + `PromptBudgetSettings` (13 fields) + 4 rows in `ENV_EXAMPLE_ROWS`; `user_agent` 派生 validator; `_non_empty_string` 接受 `None` |
| `api/server.py` | CORSMiddleware 读 `get_settings().api` |
| `api/services/simulation_service.py` | `time.sleep(0.2)` → `runtime.intervention_poll_interval_s` |
| `api/services/workspace_service.py` | affinity clamp 读 `simulation.affinity_min/max` |
| `utils/llm.py` | `httpx.Client(timeout=120.0)` → `runtime.llm_call_timeout_s` |
| `evals/intermediate_judge.py` | demote threshold 读 `judge.fabricated_evidence_demote_min/to` |
| `engine/graph.py` | `_GATE_KEEPER_SELF_HEAL_ATTEMPTS` 读 `simulation.default_self_heal_attempts` |
| `engine/services/{boundary_validation,node_lifecycle}` | dead constants 删除 |
| `engine/services/{actor_event,actor_prompt_context,isolated_actor,narration}_service.py` | 12 处 prompt/token 字面量 → `prompt_budget.*` |
| `memory/memory_manager.py` | `DEFAULT_CHROMA_*` 删除/改造 |
| 新文件 `core/metadata_keys.py` | 9 个 metadata key 常量 |
| 新文件 `tests/test_core/test_metadata_keys.py` | 2 个测试 |
| 9 source files + 10 test files | `metadata["key"]` → `metadata[META.META_KEY]` |
| `.env.example` | +4 (CORS) +13 (PROMPT_*) rows |

---

## 六、不在 Sprint 30 范围 / 留给后续

- LLM 路由 carve-out（`utils/llm.py` 的 provider alias maps、URL substrings）— Sprint 27 defer，Sprint 31+ 处理
- Cluster 5/7 域启发式（climax/branch/relationship keywords、affinity deltas、HTML/PDF typography）— backlog
- Makefile / Dockerfile / docker-compose port env — backlog
- frontend `world_builder_completed` 字段引用清理 — Sprint 31+（目前 frontend 不按字面量比对，不影响）
- Per-LLM-call timeout granularity — 不在 audit 范围

---

## 七、退出标准（Definition of Done）

- [x] `pytest -m "not integration"` → **379 passed**（baseline 354 → 379，+25 regression tests）
- [x] `mypy src` → **6 errors / 78 files**（baseline 6/6 不变）
- [x] Plan `docs/proposals/sprint-30-config-promotion.md` 已存
- [x] 5 wave commits on `sprint-30-config-promotion`
- [x] 不删除 `DEFAULT_JUDGE_MODEL`（明确决策）
- [x] `director.py:170-171` 明确 out-of-scope
- [x] 0 secrets in any commit

---

## 八、经验沉淀（给 Sprint 31 的人）

1. **drift bug 是最危险的一类**：设置定义好了但没人读。Code review 必须查 `get_settings()` 的消费者。
2. **late import 在 Pydantic 里有 cycle 风险**：`Settings` 的 domain 字段构造顺序决定 validator 里能不能调 `get_settings()`。读 `os.environ` 是兜底。
3. **`field_validator(mode="before")` 在 pydantic-settings v2.13 上对 list 字段无效**：必须 `Annotated[list, NoDecode]`。
4. **metadata key 必须集中**：14 处散落字符串是 breaking-change 风险源，任何 rename 都需要 grep14 个 site + 修改测试。新建 `core/metadata_keys.py` 是最低成本护栏。
5. **`get_settings()` 每次都重新构造**：monkeypatch-friendly；不要 `lru_cache` 它。
6. **死常量删除前必须 grep 全部 caller**：Sprint 30 踩到一次（`graph.py:92` 通过 `_boundary_validation.DEFAULT_SELF_HEAL_ATTEMPTS` 间接引用），先 rewire 再 delete。