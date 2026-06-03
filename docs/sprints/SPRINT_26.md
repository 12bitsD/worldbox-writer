# Sprint 26 — 平台基建 I：让"改 prompt / 改 temp / 改 env"变成配置任务

> 起草时间：2026-05-11
> 所属：[v0.1.0-beta 上线计划](./LAUNCH_PLAN.md) 第 1 个 sprint
> 主类：🛠 PLAT 90% + 🎨 CRAFT 10%

---

## 一、整体感观（先看系统，再看动作）

### 1.1 当前系统是什么

WorldBox Writer 是一套「**多 Agent + LangGraph 编排 + LLM-as-Judge 评测**」的长篇小说生成系统。从控制论视角看，它由三层组成：

```
┌─────────────────────────────────────────────────────────────┐
│  ① 编排层  engine/graph.py + engine/dual_loop.py             │
│  Director → Actor → Critic → GM → GateKeeper → Narrator     │
├─────────────────────────────────────────────────────────────┤
│  ② Agent 层  agents/{director,actor,critic,...}.py（9 个）  │
│  每个 Agent = system prompt + user prompt + 调 LLM           │
├─────────────────────────────────────────────────────────────┤
│  ③ LLM 调用层  utils/llm.py::chat_completion                 │
│  + provider/model 三层 env 路由                              │
│  + temperature / top_p / max_tokens 调用点 hardcode          │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 系统当前的"控制接口"是什么

| 调什么 | 当前接口 | 改一次的真实成本 |
|---|---|---|
| 模型（哪个 LLM） | `LLM_MODEL_{ROLE}` / `_{GROUP}` / `LLM_MODEL` 三层 env | ✅ 改 env 即可 |
| Provider | `LLM_PROVIDER_{ROLE}` / `_{GROUP}` / `LLM_PROVIDER` 三层 env | ✅ 改 env 即可 |
| **Prompt 内容** | 硬编码字符串散落在 9 个文件 + `engine/graph.py` 内联 + `prompts/actor_system.txt` 三套不一致版本 | ❌ 改 .py + 测试 + 跑 LLM 验证 |
| **Temperature / top_p / max_tokens** | 每个 chat_completion 调用点 hardcode（共 21 处，0.0–0.8 散落） | ❌ 改 N 个文件 |
| **Feature Flag / 行为开关** | 39 处 `os.environ.get` 散落，2 处 FEATURE 重复定义 | ❌ 全局 grep |
| **新人能否一行起项目** | `.env.example` 缺 25+ 变量，无 startup 校验 | ❌ 改错没报错 |

> **诊断**：模型选型可以一行改（已经做对了），但**「Prompt + Sampling + 行为开关」三大类配置仍然是工程任务**。这意味着 Sprint 27 上线 Prompt A/B 框架、Temp 扫频脚本、BaseAgent 抽象之前——这些工具拿什么作为「标准化的可配置目标」？没有。所以 S26 必须先把这三类配置「物化」为可序列化、可版本化、可校验的资产，否则后 4 个 sprint 全是工程任务，5 sprint 上线必然超期。

### 1.3 系统当前的"瑕疵"是什么（被前轮调研暴露的暗坑）

| 暗坑 | 位置 | 影响 |
|---|---|---|
| **生产 narrator prompt 不在 `agents/narrator.py`，在 `engine/graph.py:1158-1219` 内联** | [graph.py](file:///Users/bytedance/Desktop/CodeSpace/worldbox-writer/src/worldbox_writer/engine/graph.py#L1158-L1219) | 任何"改 narrator.py"工作都不会改善生产指标 |
| **`agents/actor.py` 的 37 行 prompt 与 `prompts/actor_system.txt` 的 3 行 fallback 并存且分叉**，dual-loop 用前者，生产用后者 | [actor.py](file:///Users/bytedance/Desktop/CodeSpace/worldbox-writer/src/worldbox_writer/agents/actor.py#L41-L77) vs [actor_system.txt](file:///Users/bytedance/Desktop/CodeSpace/worldbox-writer/src/worldbox_writer/prompts/actor_system.txt) | 同一 Agent 走两套 prompt，评测无法定位回退 |
| **`agents/critic.py` 调用 LLM 时 `role="gate_keeper"`** 借用 logic 路由 | [critic.py:120](file:///Users/bytedance/Desktop/CodeSpace/worldbox-writer/src/worldbox_writer/agents/critic.py#L120) | 加 per-agent profile 时会出现"critic 拿到 gate_keeper profile"的歧义 |
| **`evals/llm_judge.py` 用 `role="narrator"` 调 LLM**，judge 与 narrator 共用 creative 路由 | [llm_judge.py:157,465](file:///Users/bytedance/Desktop/CodeSpace/worldbox-writer/src/worldbox_writer/evals/llm_judge.py#L157) | judge 行为与 narrator 路由耦合，无法独立配 model |
| **生产 narrator prompt 完全不提 ai_prose_ticks 的 4 子类**（over_metaphor / parallel / translation_tone / expository_dialogue） | [graph.py:1158-1219](file:///Users/bytedance/Desktop/CodeSpace/worldbox-writer/src/worldbox_writer/engine/graph.py#L1158) | baseline_v1.json 11/11 veto **100%** 由 ai_prose_ticks 触发，是 L0→L2 的唯一拦路虎 |
| **GM 完全不调 LLM**（确定性结算器） | [agents/gm.py](file:///Users/bytedance/Desktop/CodeSpace/worldbox-writer/src/worldbox_writer/agents/gm.py) | "8 Agent prompt 文件"实际是 7 个，验收口径要先确认 |

> **结论**：**S26 不是一次普通 refactor，是 5 sprint 上线计划的"地基浇筑"**。地基里如果不顺手把暗坑一并修了（特别是 graph.py 内联 prompt、actor 双套 prompt、critic role 误用），后续 sprint 每跑一个 A/B / 扫频脚本都会遇到"为什么数据不一致"的归因黑洞。

### 1.4 那么 S26 要做什么

**一句话**：把系统的「控制面」(control plane) 从代码里抽出来，物化为 3 份配置资产；同时把暗坑顺路修掉；最后用「修 Narrator ai_prose_ticks」作为新基建的端到端验收。

```
   控制面         = ① Prompt registry  +  ② Sampling profile  +  ③ Settings
   端到端验收     = ④ Narrator ai_prose_ticks 修复 → veto 46% → ≤ 10%
   Sprint 退出门  = baseline 重测 overall ≥ 6.5（L0 → L2 边界）
```

---

## 二、S26 的 4 个主任务（自上而下拆解）

### S26-T1: Prompt Registry —— 让 prompt 成为可版本化的 yaml 资产

**当前问题**：8 个 Agent + graph.py + actor_system.txt 三处 prompt 共存且分叉；改 prompt = 改 .py + 测试 + 跑 LLM 验证。

**目标**：所有生产 prompt 唯一来源 = `prompts/*.yaml`；改 prompt = 改 1 行 yaml + git diff + A/B 验证。

**子任务**：

| # | 子任务 | 输出 |
|---|---|---|
| T1.1 | 设计 prompt yaml schema：`id / version / role / changelog / system / user_template`（user template 可选，先保 system 即可） | `prompts/_schema.md` |
| T1.2 | **暗坑修复 1**：把 `engine/graph.py:1158-1219` 内联的两段 narrator prompt 抽出 → `prompts/narrator_system.yaml`（合并 scene_script 与 legacy 两个分支为一段，差异部分用 user_template 区分） | graph.py 不再有内联 system prompt |
| T1.3 | **暗坑修复 2**：合并 `agents/actor.py::_ACTOR_SYSTEM_PROMPT`（37 行）与 `prompts/actor_system.txt`（3 行）为单一 `prompts/actor_system.yaml` v2，废弃 .txt | 双套 actor prompt 收敛为一套 |
| T1.4 | 把其余 6 个 LLM Agent（critic / director / gate_keeper / narrator_iterative / node_detector / world_builder）的 system prompt 全部 yaml 化，agents/*.py 里只保留 `prompt_id` 引用 | 7 个 prompt yaml + 7 个 agents 改造 |
| T1.5 | 升级 `prompting/registry.py`：支持 yaml 加载、version/changelog 字段、文件 mtime 缓存（解决 hot reload 高 IO 风险）；保留 .txt 兼容路径以便回滚 | registry v2 + 单测 |
| T1.6 | 迁移验证：跑 baseline，**新 prompt 读取路径 vs 老路径 byte-identical**（同 seed、同 temp、同 model） | 迁移验证报告 |

**验收**：
- ✅ 全仓库 `grep _SYSTEM_PROMPT` 仅命中 prompts/*.yaml；agents/*.py 与 graph.py 不再硬编码 system prompt 字符串
- ✅ prompts/ 下每个 yaml 含 `version` + `changelog` 字段
- ✅ 迁移前后 baseline 一致（验收的强约束，不允许行为漂移）

---

### S26-T2: Sampling Profile —— 让 temperature 成为可扫频的 yaml 资产

**当前问题**：21 处 chat_completion 调用点 hardcode temperature / max_tokens；调一次温度要改 N 个文件；无法做扫频。

**目标**：所有 sampling 参数集中到 `config/agent_profiles.yaml`；调用层只接 `(profile_id, prompt_id)` 二元组。

**子任务**：

| # | 子任务 | 输出 |
|---|---|---|
| T2.1 | 设计 agent_profiles yaml schema：每条 = `{profile_id, role, model_override?, temperature, top_p?, max_tokens, notes}` | `config/_schema.md` |
| T2.2 | 把 21 处 hardcode 数值映射成 profile 条目：`director_init / director_intervention / director_title / actor_propose / actor_synthesize / critic_review / gate_keeper_validate / narrator_render / narrator_fast_forward / narrator_title / narrator_iterative_{skeleton,expansion,polish,judge} / node_detector / world_builder_expand / world_builder_location / judge_committee / judge_multi_chapter` | `config/agent_profiles.yaml` |
| T2.3 | **暗坑修复 3**：给 critic 配独立 profile `critic_review`（不再借用 gate_keeper role） + 给 judge 配独立 profile `judge_committee` / `judge_multi_chapter`（不再借用 narrator role） | critic / judge 路由独立 |
| T2.4 | 扩展 `utils/llm.py::ResolvedLLMRoute` 增加 sampling 字段；新增 `chat_completion_with_profile(profile_id, messages)` 入口；老 `chat_completion(temperature=...)` 保留但废弃警告 | utils/llm.py 新增入口 + 单测 |
| T2.5 | 迁移所有调用点：`chat_completion(role=..., temperature=0.x, max_tokens=...)` → `chat_completion_with_profile("xxx", messages)` | 全仓 21 处改造 |
| T2.6 | 迁移验证：profile 数值与原 hardcode byte-identical | 验证报告 |

**验收**：
- ✅ 全仓 `grep "temperature=0\\."` 仅命中 `config/agent_profiles.yaml` + utils/llm.py 默认值 + 测试
- ✅ profile 文件覆盖 21 个调用点
- ✅ critic / judge 不再 role-hijack
- ✅ 迁移前后 baseline byte-identical

---

### S26-T3: Settings —— 让 env 成为可校验的 Pydantic Schema

**当前问题**：39 处 `os.environ.get` 散落 7 个模块；`.env.example` 缺 25+ 变量；启动期无校验，配错 env 不报错。

**目标**：单一 `config/settings.py` Pydantic `BaseSettings` 集中所有 env；启动期 fail-fast；`.env.example` 与代码 1:1。

**子任务**：

| # | 子任务 | 输出 |
|---|---|---|
| T3.1 | 列出全仓 env 变量清单（已由调研提供 25+ 项），按域分组：LLM / FEATURE / WB（采样）/ DB / MEMORY / PERF / MODEL_EVAL / PROMPT | `config/_env_inventory.md` |
| T3.2 | 设计 `config/settings.py`：Pydantic v2 `BaseSettings`，每域一个嵌套 model（`LLMSettings`、`FeatureSettings`、`SampleSettings` …）；带类型校验、默认值、validators | `config/settings.py` |
| T3.3 | **暗坑修复 4**：消除 `api/server.py` 与 `api/state.py` 的 `FEATURE_BRANCHING_ENABLED` 重复定义 | 单一定义点 |
| T3.4 | 渐进式迁移：先把高频 env（FEATURE_*, WB_*, MEMORY_*, DB_PATH, PROMPT_TEMPLATE_DIR）切到 settings；utils/llm.py 的 LLM_* 路由保留原状（路由逻辑复杂，单独排第二批） | settings.py 覆盖 60% env |
| T3.5 | FastAPI startup lifespan：启动时调用 `Settings()` 触发校验，失败直接进程退出 + 清晰错误 | 配错 env 启动失败而非跑出错结果 |
| T3.6 | `.env.example` 由 settings.py 自动生成（`python -m worldbox_writer.config.settings --emit-env-example`）；CI 跑 diff 防止漂移 | `.env.example` 与代码同步 |

**验收**：
- ✅ FEATURE / WB / MEMORY / DB / PROMPT 类 env 全部走 settings
- ✅ FastAPI 启动配错 env → 进程退出 + 明确错误
- ✅ `cp .env.example .env && make dev-api` 能直接起进程
- ✅ CI gate：`.env.example` 与 settings.py 自动 diff 不一致即 fail

---

### S26-T4: Narrator ai_prose_ticks 修复 —— 用新基建跑通端到端

**当前问题**：baseline_v1.json **11/11 chapter veto 100% 由 ai_prose_ticks 触发**；生产 narrator prompt 不提 4 个子类。这是 L0 → L2 的唯一拦路虎。

**目标**：用 T1 新 prompt registry + T2 新 profile 完成 narrator 修复，证明新基建端到端可用。

**子任务**：

| # | 子任务 | 输出 |
|---|---|---|
| T4.1 | 在 `prompts/narrator_system.yaml` 内增加 4 子类**显式禁用规则**（over_metaphor / parallel / translation_tone / expository_dialogue），bump version 到 v2，写 changelog | narrator_system.yaml v2 |
| T4.2 | 增加 narrator **自检回路**：渲染后调 `judge_committee` 仅检查 ai_prose_ticks 维度；若命中（score ≥ 8.0）则用 v2-strict prompt 重渲一次（最多 1 次重试） | engine/graph.py::narrator_node 改造 |
| T4.3 | 跑 baseline_current_system.py 重测：`veto_rate` 与 `overall_mean` 与 baseline_v1.json 对比 | `artifacts/eval/sprint-26/round-1/baseline_v2.json` |
| T4.4 | 跑 toxic_injection_regression：preachiness recall 100% **不能下跌**（守门） | toxic_injection 报告 |

**验收**：
- ✅ `veto_rate ≤ 10%`（从 46%）
- ✅ `overall_mean ≥ 6.5`（从 3.73）
- ✅ axis_means 三轴不退步（仍 ≥ 6.0）
- ✅ preachiness recall 100% 守住

---

## 三、Sprint 退出门（这 4 项缺 1 都不算 done）

| # | 验收项 | 通过条件 |
|---|---|---|
| 1 | T1 全仓 prompt yaml 化 | `grep _SYSTEM_PROMPT` 不再命中 agents/*.py 与 graph.py |
| 2 | T2 全仓 sampling profile 化 | `grep "temperature=0\\."` 仅命中 yaml / 默认值 / 测试 |
| 3 | T3 startup fail-fast 生效 | 故意错配 env → 进程退出且错误清晰；`.env.example` 与 settings.py CI diff 通过 |
| 4 | T4 baseline 跨档 | `overall_mean ≥ 6.5` & `veto_rate ≤ 10%` & axis 不退；preachiness recall 100% |
| 5 | 行为不漂移 | T1 + T2 迁移前后 baseline byte-identical（或差异 < 0.5% 且 axis 不退） |
| 6 | CI 全绿 | `make lint` / `make test` / `make typecheck` 不增 mypy 错 |

---

## 四、推荐执行节奏（2 周 sprint，按 PR 切分）

| 周次 | 任务并行度 | 关键 PR | 风险点 |
|---|---|---|---|
| **W1 第 1-2 天** | T1.1 + T2.1 + T3.1 三个 schema 设计并行（轻量，不写代码） | PR-01 schema docs | schema 设计错会拖累 W2，需要先 review |
| **W1 第 3-4 天** | T1.2 + T1.3（两个暗坑修复）+ T1.5（registry v2） | PR-02 prompts/{narrator,actor}.yaml + registry v2 | graph.py 改动需 baseline 验证 |
| **W1 第 5 天 - W2 第 1 天** | T1.4 其余 7 个 prompt 迁移 + T1.6 验证 | PR-03 全 prompt 迁移 | byte-identical 验证可能反复 |
| **W2 第 2-3 天** | T2.2 + T2.4 + T2.5 sampling profile 落地 | PR-04 agent_profiles.yaml + chat_completion_with_profile | T2.3 critic/judge 解耦可能触发评测路径 model 变化，需要 calibration 重跑 |
| **W2 第 4 天** | T3.2 + T3.4 + T3.5 settings 渐进迁移 | PR-05 settings + startup fail-fast | LLM_* 留到 v2 不动，避免影响路由 |
| **W2 第 5 天** | T4.1 + T4.2 narrator 修复 + T4.3 + T4.4 baseline 重测 | PR-06 narrator v2 prompt + 自检回路 + baseline_v2 报告 | T4.2 自检回路 token 成本评估，若翻倍要预警 |

---

## 五、明确放弃 / 推迟（trade-off 透明）

| 推迟项 | 推到 | 原因 |
|---|---|---|
| LLM_* 路由层迁移到 settings | S27 | 路由逻辑复杂，本 sprint 优先把行为开关类 env 收编 |
| user prompt template 化（除 system 外） | S27 | 21 处 user prompt 全是 f-string 拼接，迁移成本高，本 sprint 只统一 system |
| GM 加占位 prompt | 不做 | GM 是确定性结算器，不需要 prompt |
| narrator_iterative 接入新体系 | S27 | 非生产路径，与 BaseAgent 抽象一起做 |
| Prompt A/B 框架 | S27 | 本 sprint 只做"可配置"，A/B 框架是 S27 主任务 |
| Temperature 扫频脚本 | S27 | 同上 |
| 评测 dashboard | S28 | 本 sprint 不需要 |
| BaseAgent 抽象 | S27 | 与 sample_collector 推广一起做 |

---

## 六、风险与应对

| 风险 | 触发场景 | 应对 |
|---|---|---|
| **行为漂移**：T1/T2 迁移后 baseline 偏移 | yaml 加载顺序、空格、换行被修改 | 强约束 byte-identical；首次跑 baseline 对比通不过就回滚 |
| **graph.py 拆 prompt 引入回归** | scene_script 与 legacy 两分支合并不当 | T1.2 单独一个 PR，含 baseline 对比报告；不通过不合 |
| **T2.3 critic/judge 解耦改变 calibration** | 路由变了 → judge model 变了 → calibration 反转 | T2.3 后立即重跑 calibration_ranking，mandatory pairs 必须 0 反转 |
| **T3 startup fail-fast 砸生产** | 旧部署机器 env 不全 | 给所有有默认值的字段配默认值；fail 仅限 LLM_API_KEY 等"无默认就死"的字段 |
| **T4 自检回路 token 成本翻倍** | 每章 narrator 多调 1 次 judge + 可能 1 次重渲 | 自检只跑 ai_prose_ticks 单维（不跑 13 维 committee）；命中率统计纳入 baseline 报告 |
| **Sprint 25 锁定 agents/*** | SPRINT_25.md §X 写明禁动 agents/* | S26 启动公告解锁；本计划即解锁公告 |

---

## 七、开发规范（S26 落地后，新代码必须遵守）

> 本规范从本 sprint 起生效；旧代码迁移由 T1/T2/T3 负责，迁移后 CI gate 强制约束新增代码。

### 7.1 Prompt 规范

- **禁止**在 `agents/*.py`、`engine/*.py`、`evals/*.py` 中以字符串字面量定义 system prompt；新增 system prompt 必须放进 `prompts/<role>_system.yaml`。
- yaml 必填字段：`id` / `version`（语义化：major.minor）/ `role` / `changelog`（每次改动追加一行：`vX.Y - YYYY-MM-DD - 改动摘要`）/ `system`。
- 改 prompt = bump `version` + 追加 `changelog` + PR 描述附带 baseline 对比（任何 prompt 变动必须跑 baseline，差异 > 0.5% 需 reviewer 显式确认）。
- user prompt 暂允许 f-string 拼接，但 **变量名必须与 yaml 中声明的 `user_template_vars` 对齐**。
- CI gate：`grep -rn "_SYSTEM_PROMPT\\s*=" src/` 命中即 fail。

### 7.2 Sampling 规范

- **禁止**在 `chat_completion(...)` 调用点直接传 `temperature=` / `top_p=` / `max_tokens=` 字面量；必须走 `chat_completion_with_profile(profile_id, messages)`。
- 新增 LLM 调用点 = 新增一条 `config/agent_profiles.yaml` 条目；profile 命名规范：`<agent>_<purpose>`（如 `narrator_render` / `actor_propose`）。
- 调温度 = 改 yaml 一行 + PR 描述说明扫频结果（不允许"凭手感"调温度，必须有数据支撑）。
- CI gate：`grep -rn "temperature=0\\." src/` 仅允许命中 `config/`、`utils/llm.py` 默认值、`tests/`。

### 7.3 配置（env）规范

- **禁止**在业务代码里直接 `os.environ.get(...)`；所有 env 必须通过 `from worldbox_writer.config.settings import settings` 注入。
- 新增 env = 同时改 3 处：`config/settings.py`（加字段 + 类型 + 默认值）、`.env.example`（自动生成器会处理）、对应文档（如 `DEVELOPMENT.md` 环境变量节）。
- 启动期 fail-fast：无默认值的字段（如 `LLM_API_KEY`）缺失必须让进程退出，不允许 silent fallback。
- CI gate：`grep -rn "os.environ" src/worldbox_writer/` 排除 `config/settings.py` 后命中即 fail。

### 7.4 Agent role 规范

- `chat_completion_with_profile(profile_id=...)` 中 profile_id 必须与 Agent 真实身份一致；**禁止**借用其他 agent 的 role 走路由（消除 critic→gate_keeper、judge→narrator 这类 hijack）。
- 新增 Agent / 新增 LLM 调用方 = 显式新增 profile + 显式新增 `LLM_MODEL_<ROLE>` env 选项。

### 7.5 禁止 mock 规范

- **禁止**在生产代码（`src/worldbox_writer/**`）里出现任何形式的 mock / stub / 假数据 fallback：
  - 不允许 `if not api_key: return MOCK_RESPONSE`；
  - 不允许 `try: call_llm() except: return fixture_data`；
  - 不允许"开发模式下返回硬编码字符串"这类条件分支；
  - 不允许给 LLM 输出写"如果解析失败就返回默认 dict"的兜底假数据（解析失败必须 raise，让上层决定重试 / 退出）。
- 缺依赖（如 `LLM_API_KEY` 未配）= **fail-fast**（与 §7.3 一致），让进程退出，不允许返回假数据让上层误判系统在工作。
- 测试代码（`tests/**`）允许 mock，但**必须显式 import `unittest.mock` / `pytest-mock`**，禁止自己手搓 fake class 充当生产对象；且 fixture 必须命名以 `mock_` / `fake_` 开头，避免误用。
- Eval / baseline 跑不通 = 必须查清原因后修，不允许"为了让 CI 过先 mock 一下"。
- 评测代码（`evals/**`）尤其禁止：评测一旦 mock，所有 baseline 数字都失去意义。
- CI gate：`grep -rnE "\\b(mock|fake|dummy|stub)\\w*\\s*=" src/worldbox_writer/` 命中需 reviewer 显式签字（白名单：纯命名巧合，如 prompt 文本里的"mock"字样）。

### 7.6 验收强约束

- 任何「基建类」改动（prompt 迁移、profile 重构、settings 重构）合入主干前，必须满足：
  - **byte-identical** 或差异 < 0.5% 且 axis 不退步（带 baseline 对比报告）；
  - `make lint` / `make test` 全绿；
  - 不新增 mypy 错（沿用 typecheck 基线）。
- PR 描述模板必须包含：① 涉及哪些控制面（prompt / profile / settings）② baseline 对比数字 ③ 是否触发 calibration 重跑 ④ 是否引入 mock（必须明确"无"）。

---

## 八、与 LAUNCH_PLAN 的对照

| LAUNCH_PLAN.md S26 行 | 本计划对应 |
|---|---|
| `prompts/*.yaml` 目录化 | T1（含两个暗坑修复） |
| `config/agent_profiles.yaml` | T2（含 critic/judge 解耦） |
| Pydantic `BaseSettings` 统一 39 处 env | T3（FEATURE/WB/MEMORY/DB/PROMPT 全收，LLM_* 推到 S27） |
| Narrator ai_prose_ticks 修复 | T4（端到端验收） |
| `veto_rate ≤ 10%` & `overall_mean ≥ 6.5` | 退出门 #4 |

---

## 九、关联文档

- 上线计划全景：[LAUNCH_PLAN.md](./LAUNCH_PLAN.md)
- 评测 spec：[QUALITY_SPEC.md](../product/QUALITY_SPEC.md)
- 架构设计：[DESIGN.md](../architecture/DESIGN.md)
- 开发流程：[DEVELOPMENT.md](../development/DEVELOPMENT.md)
- Sprint 25 历史：[SPRINT_25.md](./SPRINT_25.md)
- Orchestrator 状态：[orchestrator/state.json](./orchestrator/state.json)
