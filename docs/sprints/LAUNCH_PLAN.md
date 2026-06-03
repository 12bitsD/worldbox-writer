# 上线计划：Sprint 26 → 30

> 起草时间：2026-05-11
> 目标：5 个 sprint 后发布 **v0.1.0-beta**（Closed Beta，约 50 名用户）
> 当前位置：Sprint 25 R6 收尾，生产基线 L0（`overall_mean=3.73 / veto=46% / axis_means≈[7.07,7.42,6.38]`）
> 评测体系：QUALITY_SPEC v1.0 已就绪，Spearman=0.98，红蓝队 1.0/1.0

---

## 1. 上线门 (Definition of Launch-Ready)

| 维度 | 指标 | 阈值 |
|---|---|---|
| 🎯 EVAL | calibration mandatory pairs | 0 反转 |
| 🎯 EVAL | toxic_injection 总 recall / FP | ≥ 95% / ≤ 10% |
| 🎯 EVAL | 真实外部 calibration 样本 | ≥ 3 段授权 |
| 🎨 CRAFT | overall_mean | ≥ 6.5（L2） |
| 🎨 CRAFT | axis_min | ≥ 6.5（L2） |
| 🎨 CRAFT | veto_rate | ≤ 10%（L2） |
| 🛠 PLAT | 改一次 prompt 成本 | 1 行 yaml diff |
| 🛠 PLAT | 改一次 temperature 成本 | 1 行 yaml diff |
| 🛠 PLAT | 加一个 Agent 成本 | ≤ 30 行 |
| ⚙️ STAB | 进程崩溃后 session 恢复 | ✅ |
| ⚙️ STAB | API 鉴权 + 限流 + CORS 收紧 | ✅ |
| ⚙️ STAB | structlog + Sentry | ✅ |
| 🚀 RLS | tag → 镜像 → staging → smoke → 灰度 | 全自动 |

不达成不上线。

---

## 2. 五类标签

所有任务按以下 5 类标注：

| Code | 名称 | 衡量指标 | 关注点 |
|---|---|---|---|
| 🎯 **EVAL** | 评测可信度 | mandatory pair 反转 / Spearman / recall / FP | 评测系统本身值不值得信 |
| 🎨 **CRAFT** | 产出质量 | overall_mean / axis_means / veto_rate | 生成的小说本身好不好看 |
| 🛠 **PLAT** | Agent 平台基建 | 改 prompt / temp / 加 Agent 的成本 | 让 EVAL 与 CRAFT 迭代变快的 enabler |
| ⚙️ **STAB** | 工程稳定性 | 崩溃恢复率 / 鉴权 / 可观测覆盖率 | 上线后不出事故的保命底盘 |
| 🚀 **RLS** | 上线 / 发布工程 | tag → 镜像 → 灰度 → rollback 自动化 | 让产品按下按钮就发版 |

---

## 3. Trade-off：明确放弃的 todo（避免后续抖动）

为了 5 sprint 内做到上面这些，**主动放弃**（v1.0 后再做）：

| 放弃项 | 类 | 原因 | 预期再做时间 |
|---|---|---|---|
| 冲 L3（≥ 8.0） | 🎨 CRAFT | 需要 Memory v2 + Editor Agent + N-best，至少 +3 sprint | v1.0 之后 |
| Memory v2（场景 retrieval + rerank） | 🎨 CRAFT | cross-passage 4 维有上限但 L2 够用 | v1.0 之后 |
| Editor / Reviewer Agent（章末净化） | 🎨 CRAFT | ai_prose_ticks 修在 Narrator 内即可达 L2 | v1.0 之后 |
| Self-consistency / N-best | 🎨 CRAFT | Token 成本翻 N 倍，beta 阶段不值 | v1.0 之后 |
| Web playground（产品自助调 prompt） | 🛠 PLAT | beta 阶段研发自己改即可 | v1.0 之后 |
| 多副本 / API 进程无状态化 | ⚙️ STAB | 50 人 beta 单副本够用 | 用户量 > 200 |
| Redis / Postgres（替换 SQLite） | ⚙️ STAB | 50 人 beta SQLite 够用 | 用户量 > 500 |
| OTel HTTP trace | ⚙️ STAB | structlog + Sentry 已能覆盖 | v1.0 之后 |
| ThreadPoolExecutor → 持久 task queue | ⚙️ STAB | 单进程 ThreadPool 在 50 人量级稳 | 用户量 > 200 |
| `forced_stupidity` 完美 recall | 🎯 EVAL | R5 trade-off 难点，95% 已够 beta | v1.0 之后 |
| 多区域 / CDN / 多语言 | 🚀 RLS | 50 人 beta 不需要 | v1.0 之后 |

---

## 4. 五类预算分布

| 类 | Sprint 占比 | 备注 |
|---|---|---|
| 🛠 PLAT | **2.2 sprint** | 最大头：连续 3 sprint 砸基建是能不能 5 轮上线的关键 |
| 🚀 RLS | 1.0 sprint | 最后一轮专门做 |
| 🎯 EVAL | 0.9 sprint | 分布在 S27/S28/S29 |
| ⚙️ STAB | 0.7 sprint | 集中在 S29，只做最低门槛 |
| 🎨 CRAFT | 0.7 sprint | 跟随 PLAT，靠 A/B + Temp 扫频自动驱动 |

**核心原则**：
1. PLAT 基建优先，让后续 sprint 的迭代速度提 5-10 倍
2. CRAFT 不靠手工调 prompt，全部用 A/B + Temp 扫频自动驱动
3. STAB 只做能不能上线的最低门槛，不过度工程化
4. 每个 sprint 主攻 1-2 类，避免任何一类长时间不动

---

## 5. Sprint 大节奏

```
S26 ──▶ S27 ──▶ S28 ──▶ S29 ──▶ S30
PLAT    PLAT    PLAT     STAB    RLS
+CRAFT  +EVAL   +CRAFT   +EVAL
                +EVAL
```

| Sprint | 主题 | 主类 | 次类 | 关键产出 |
|---|---|---|---|---|
| **S26** | 平台基建 I：Prompt + Sampling + Settings 三件套 | 🛠 PLAT | 🎨 CRAFT | prompts yaml 化；agent_profiles.yaml；Pydantic Settings；ai_prose_ticks 修复 → L2 边界 |
| **S27** | 平台基建 II：Agent 抽象 + 数据驱动迭代工具 | 🛠 PLAT | 🎯 EVAL | BaseAgent + 注册表；Prompt A/B 框架；Temp 扫频脚本；P1 中间评测 |
| **S28** | 平台基建 III：A/B 驱动质量优化 + 评测 dashboard | 🛠 PLAT | 🎨 CRAFT / 🎯 EVAL | Prompt 多变体批跑；评测 dashboard；axis ≥ 7.0；毒点回归收口 |
| **S29** | STAB 最低门槛 + 真实外部 calibration | ⚙️ STAB | 🎯 EVAL | session 落 SQLite；API 鉴权 + 限流；router 拆分；structlog + Sentry；外部 calibration 入库 |
| **S30** | 上线 dress rehearsal | 🚀 RLS | — | release.yml 自动出镜像；staging；smoke；灰度 + rollback drill；CHANGELOG / runbook |

---

## 6. Sprint 详细计划

### S26 — 平台基建 I：Prompt + Sampling + Settings 三件套

> **目的**：让"改 prompt / 改 temperature / 加 env" 三件事从工程任务降级为配置任务，为后 4 个 sprint 提速。

**预算分配**：🛠 PLAT 90% + 🎨 CRAFT 10%

| 类 | 任务 | 退出门 |
|---|---|---|
| 🛠 PLAT | `prompts/*.yaml` 目录化所有 system prompt（version、frontmatter、changelog 字段），废 11+ 处 hardcode | 8 个 Agent prompt 全部 yaml 化；prompt 改动 git diff 可读 |
| 🛠 PLAT | `config/agent_profiles.yaml`：每个 Agent 集中管理 model / temperature / top_p / max_tokens；调用层只接 `(profile_id, prompt_template_id)` | 改 narrator 温度 = 改 1 行 yaml |
| 🛠 PLAT | Pydantic `BaseSettings` 统一 39 处 `os.environ.get`；`.env.example` 补齐 FEATURE_/WB_/PERF_/MODEL_EVAL_ 全量；启动 fail-fast | 配错 env 启动直接报错；新人 cp .env.example 即跑通 |
| 🎨 CRAFT | Narrator ai_prose_ticks 修复（同时验证新 prompt 体系）—— 4 子类禁用 + 自检回路 | `veto_rate ≤ 10%` & `overall_mean ≥ 6.5`（L0 → L2 边界） |

**Sprint 退出门**：上述 4 项全过 + `make lint` / `make test` 全绿。

---

### S27 — 平台基建 II：Agent 抽象 + 数据驱动迭代工具

> **目的**：上线 Prompt A/B 与 Temperature 扫频两个工具，让 S28 之后的所有质量优化变成数据驱动而非靠手感。

**预算分配**：🛠 PLAT 70% + 🎯 EVAL 30%

| 类 | 任务 | 退出门 |
|---|---|---|
| 🛠 PLAT | `BaseAgent` 抽象基类（`__init__/invoke/parse/collect_sample`） + Agent 注册表 | 新加 Agent ≤ 30 行 |
| 🛠 PLAT | `WB_COLLECT_SAMPLES=1` 自动覆盖 9 个 Agent（依托 BaseAgent） | 9 节点自动落盘 |
| 🛠 PLAT | **Prompt A/B 框架**：同节点跑 A/B 两个 prompt 模板，自动用 judge_committee 比 axis_means + veto_rate，输出带置信区间报告 | A/B 报告能识别 v1 vs v2 哪个胜，含 p-value/CI |
| 🛠 PLAT | **Temperature 扫频脚本**：单 Agent 在 [0.0, 0.3, 0.5, 0.7, 0.9] 5 档跑 baseline，输出 axis × veto 热图 | 跑出 narrator / director / actor 推荐温度 |
| 🎯 EVAL | P1 中间节点评测：Director init / Narrator script_faithfulness / actor_node 内联（依托 BaseAgent） | 三节点 runner 可跑 + 各 5 维 evidence_quote |

**Sprint 退出门**：上述 5 项全过；`make intermediate-eval` 覆盖 P0+P1 五个节点。

---

### S28 — 平台基建 III：A/B 驱动质量优化 + 评测 dashboard

> **目的**：把 S27 工具开火，自动驱动质量提升；用评测 dashboard 让 A/B 数据有可消费的视图，避免 JSON 文件无人看。

**预算分配**：🛠 PLAT 50% + 🎨 CRAFT 30% + 🎯 EVAL 20%

| 类 | 任务 | 退出门 |
|---|---|---|
| 🛠 PLAT | **Prompt 多变体批跑工具**：基于 S27 A/B 框架升级，一次跑 4-6 个变体，自动出 leaderboard | 一晚跑 20 个变体能产生选优报告 |
| 🛠 PLAT | **评测 dashboard（轻量）**：streamlit / gradio 单页，渲染 artifacts/eval/sprint-*/round-* 趋势 + Top-N 拖底维度 | 浏览器打开能看到所有历史评测对比 |
| 🎨 CRAFT | 用 A/B 工具优化 Director / GM scene-level prompt | `axis_means` 三轴 ≥ 7.0 |
| 🎨 CRAFT | 用 Temp 扫频结果调优 actor / world_builder 温度 | 单 Agent 调优后 baseline 不退步 |
| 🎯 EVAL | 毒点回归收口：`forced_stupidity` recall ≥ 95% / FP ≤ 10%；`ai_prose_ticks` recall ≥ 83% | 回归 gate 全绿 |

**Sprint 退出门**：上述 5 项全过；baseline 重测 axis 三轴均 ≥ 7.0。

---

### S29 — STAB 最低门槛 + 真实外部 Calibration

> **目的**：补齐"上线前必须有"的工程稳定性最低门槛，并关闭 R6-residual-1（真实外部样本）。

**预算分配**：⚙️ STAB 70% + 🎯 EVAL 30%

| 类 | 任务 | 退出门 |
|---|---|---|
| ⚙️ STAB | **SimulationSession 落 SQLite**（不做多副本，只做单副本崩溃恢复） | 杀进程后 `/api/simulate/{id}` 仍能恢复 |
| ⚙️ STAB | **API 防护最低门槛**：API key 鉴权 + slowapi 限流（60 req/min/user）+ CORS 白名单 | 401 / 429 行为正确；CSRF 不可达 |
| ⚙️ STAB | **api/server.py 拆 router**：1880 行 → `routers/{auth,sim,branch,export,diagnostics}.py` | 单文件 ≤ 500 行 |
| ⚙️ STAB | **可观测性最小集**：structlog（带 sim_id / round_id）+ Sentry SDK | Sentry 收到第一条事件；按 sim_id 能 grep 全链路 |
| 🎯 EVAL | 真实外部 calibration 入库（R6-residual-1）：≥ 3 段授权片段，mandatory_pairs 0 反转 | 独立 ranking 通过 |

**Sprint 退出门**：上述 5 项全过；崩溃恢复演练通过。

---

### S30 — 上线 dress rehearsal

> **目的**：把发布流程跑通一遍，包括镜像产出、staging、smoke、灰度、rollback。

**预算分配**：🚀 RLS 100%

| 类 | 任务 | 退出门 |
|---|---|---|
| 🚀 RLS | release.yml 升级：`git tag` → 自动 docker build & push 镜像；SBOM 生成 | tag 后 30 分钟内镜像出现在 registry |
| 🚀 RLS | staging 环境部署（docker-compose + cloudflare tunnel） | staging URL 可访问 |
| 🚀 RLS | smoke test pipeline：staging 部署后自动跑 1 个 10 章 sim + 评测，达 L2 才 promote | smoke 报告 L2 通过 |
| 🚀 RLS | 双循环灰度 + rollback drill（5% / 50% / 100% / rollback）按 [DEVELOPMENT.md §10](../development/DEVELOPMENT.md#10-双循环灰度与运行手册) | 4 阶段全跑通 |
| 🚀 RLS | CHANGELOG / runbook / on-call 流程 | v0.1.0-beta release notes 完成 |

**Sprint 退出门**：所有上线门 (§1) 全部达成；可以对外发邀请码。

---

## 7. 五 Sprint 后能力对照

| 能力 | 进入时（S25 R6） | S30 上线时 |
|---|---|---|
| 改 1 次 prompt | 改 .py 文件 + 测试 + 发版 | 改 1 行 yaml + git diff + A/B 自动验证 |
| 改 1 次 temperature | 改 8 个 .py 文件 | 改 1 行 yaml；扫频脚本一晚出最优 |
| 加 1 个 Agent | ~80 行样板 | ≤ 30 行（BaseAgent 自动注入） |
| Prompt A/B 验证 | 无 | 一次跑 N 个变体出 leaderboard |
| 评测可视化 | 看 JSON | streamlit dashboard 看趋势 |
| 中间节点评测覆盖 | P0 (2/27) | P0+P1 (5/27)，9 Agent 全自动落盘 |
| 单维质量 | L0 (overall 3.73) | L2 (≥ 6.5) |
| 进程崩溃 | session 全丢 | SQLite 恢复 |
| API 安全 | CORS * + 无鉴权 | API key + 限流 + 白名单 |
| 可观测性 | print + 控制台 | structlog + Sentry |
| 上线流程 | 手工 docker build | tag → 镜像 → staging → smoke → 灰度 |

---

## 8. 风险与应对

| 风险 | 触发场景 | 应对 |
|---|---|---|
| S26 prompt 目录化造成行为漂移 | yaml 加载与原 hardcode 不严格等价 | 迁移时跑 baseline 对比；二者必须 byte-identical |
| S27 A/B 框架 token 成本激增 | 每个 A/B 跑 N 章 × 2 prompt | 默认 N=5 章；CI 不强制；只人工触发 |
| S28 dashboard 维护成本失控 | streamlit 越写越复杂 | 死守"单页 ≤ 300 行"红线；不上鉴权、不上数据库 |
| S29 SQLite 持久化引入 schema 迁移痛 | 字段变更需要迁移 | 用 alembic；schema 先冻结再上 STAB |
| S30 灰度 / rollback 演练失败 | dual-loop 切换有副作用 | S30 第一周做演练，留第二周修；CHANGELOG 写明已知限制 |
| 整体 5 sprint 进度超期 | 任一 sprint 退出门 fail | 优先牺牲 CRAFT 进入 v1.0；STAB / RLS 不可让步（影响上线） |

---

## 9. 决策记录（拍板纪要）

> 记录本计划成型过程中关键拍板，便于后续质疑回溯。

- 2026-05-11：上线目标 = Closed Beta 50 人，**质量门 L2**（放弃 L3）—— 用户拍板
- 2026-05-11：**5 类标签**采用 EVAL / CRAFT / PLAT / STAB / RLS —— 用户拍板
- 2026-05-11：**STAB 预算从 1.5 sprint 压到 0.7 sprint**，释放预算砸 PLAT —— 用户拍板
- 2026-05-11：S28 **保留评测 dashboard**（streamlit/gradio 轻量） —— 用户拍板
- 2026-05-11：S26 三件套（Prompt + Sampling + Settings）合并为单一 sprint 做完 —— 用户拍板
- 2026-05-11：新系统尝试明确 **Prompt A/B 框架** + **Temperature 扫频脚本**两项，其余推迟 —— 用户拍板

---

## 10. 关联文档

- 评测 spec：[QUALITY_SPEC.md](../product/QUALITY_SPEC.md)（含 §5 中间节点评测）
- 产品策略：[PRODUCT_STRATEGY.md](../product/PRODUCT_STRATEGY.md)
- 架构设计：[DESIGN.md](../architecture/DESIGN.md)
- 开发流程：[DEVELOPMENT.md](../development/DEVELOPMENT.md)（含 §10 双循环灰度 / §11 类型基线）
- Sprint 25 历史：[SPRINT_25.md](./SPRINT_25.md)
- Orchestrator 状态：[orchestrator/state.json](./orchestrator/state.json)
