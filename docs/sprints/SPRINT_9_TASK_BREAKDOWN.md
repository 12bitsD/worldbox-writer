# Sprint 9 开发任务拆解

**文档状态**：Delivered (P0 Landing)  
**适用 Sprint**：Sprint 9 / v0.8.x  
**最后更新**：2026-04-19

本文档用于承接 Sprint 8.5 的体验补强，并把 Sprint 9 从“计划中的大拼盘”收口为一版可落地、可验证、可继续演进的生产力闭环。

---

## 1. Sprint 9 的核心目的

Sprint 9 的核心目的不是继续增加“可玩功能”，而是把 WorldBox Writer 从 **Observe / Control 阶段的可操控沙盒**，推进到 **Create 阶段的可长期使用创作工具**。

对当前仓库来说，这个目标具体落在 4 件事上：

1. **记忆变成 durable contract**  
   长篇创作不能继续依赖纯内存记忆；需要有 SQLite 持久化、可归档、可恢复、可诊断的记忆真相源。
2. **模型调用从单一路径变成可路由系统**  
   逻辑链路和创意链路需要可配置分流，同时保留评估门禁和降级回退空间。
3. **创作工作台必须真正可用**  
   用户不仅能看推演结果，还能在 Wiki 和正文编辑器里继续整理设定、润色正文，并在异常关闭后恢复草稿。
4. **发布护栏补齐到可演进状态**  
   Sprint 9 新增了持久化记忆、路由和工作台，必须同时补齐评估脚本、容量门禁和诊断入口。

---

## 2. 为什么原始 Sprint 9 需要重排

原始计划里最大的问题不是方向错，而是 **把不同成熟度的任务并列成同权 P0**：

- `S9-01a` SQLite 持久化记忆是当前代码基线上能稳落的
- `S9-01b` ChromaDB / 向量库是真正的下一阶段能力，不应压在同一期与工作台并行落地
- `S9-02` 多模型路由如果没有评估报告和回退钩子，会把 Sprint 9 变成高风险发布
- `S9-03/04/05` 工作台相关需求必须共享同一套 API 契约和草稿恢复机制，不能各自孤立推进
- `S9-06/07` 若没有自动化脚本，只写在计划里就不算护栏

因此 Sprint 9 的合理收口是：

- **P0 当期交付**
  - `S9-01a` 记忆持久化 + 摘要归档
  - `S9-02` 路由配置 + 诊断 + 评估/回退脚手架
  - `S9-03/04/05` Wiki + 富文本工作台 + 端侧草稿恢复
  - `S9-06/07` 容量门禁脚本 + CI 工作流 + API 诊断面板
- **P1 明确后移**
  - `S9-01b` ChromaDB / 外部向量检索

---

## 3. 本次 Sprint 9 实际交付范围

### 3.1 AI 系统与后端

| ID | 条目 | 收口方式 | 状态 |
| :--- | :--- | :--- | :--- |
| **S9-01a** | 记忆持久化 + 摘要归档 | `memory_entries` 升级为 branch-aware durable store；`MemoryManager` 支持 SQLite 加载、归档摘要、恢复过滤 | ✅ Done |
| **S9-02** | 多模型智能路由 | `logic / creative / role` 三级路由配置；评估报告驱动的 fallback 钩子；LLM 调用估算 token/cost 元数据 | ✅ Done |
| **S9-07** | 线上诊断闭环 | 新增 `/api/simulate/{id}/diagnostics`，聚合 memory footprint 与 LLM route 统计 | ✅ Done |

### 3.2 创作工作台

| ID | 条目 | 收口方式 | 状态 |
| :--- | :--- | :--- | :--- |
| **S9-03** | 交互式设定 Wiki | 新增 `PUT /api/simulate/{id}/wiki`；支持角色/势力/地点/规则保存与校验 | ✅ Done |
| **S9-04** | 富文本编辑器集成 | `CreativeStudio` + lazy-loaded `RichTextEditor`；正文可回写到节点持久化数据 | ✅ Done |
| **S9-05** | 端侧草稿恢复 | IndexedDB 优先、本地存储兜底的草稿快照恢复机制 | ✅ Done |

### 3.3 护栏与交付

| ID | 条目 | 收口方式 | 状态 |
| :--- | :--- | :--- | :--- |
| **S9-06** | 压测与容量门禁 | `make perf` + `scripts/ci/perf-gate.sh` + 手动 GitHub Actions workflow | ✅ Done |
| **S9-07** | 模型评估与 CI 闭环 | `make model-eval` 改为真实评估脚本；产出 report artifact；支持 route score threshold | ✅ Done |
| **S9-01b** | 向量检索集成 | 真实 ChromaDB 已接线；默认 `auto` 路由优先启用 ChromaDB，失败时回退内置检索 | ✅ Done (Increment) |

---

## 4. 任务拆分与依赖顺序

### Track A：先把记忆做成真相源

1. 升级 `storage/db.py` 的 `memory_entries` 契约  
2. 让 `MemoryManager` 能从 SQLite 恢复并按 branch lineage 过滤  
3. 增加摘要归档逻辑，避免长篇上下文无限膨胀  
4. 增加 memory diagnostics

### Track B：再把 LLM 调用做成可路由系统

1. 引入 `logic / creative / role` 三层路由优先级  
2. 为每次调用记录 route group、估算 token 与 fallback 信息  
3. 让 `model-eval` 产出可被 runtime 读取的 report  
4. 当 report 低于阈值时自动回退到全局默认路由

### Track C：最后补创作工作台

1. 统一世界设定保存入口：`/wiki`  
2. 增加正文润色保存入口：`/nodes/{id}/rendered-text`  
3. 在前端接入 `CreativeStudio`  
4. 编辑器草稿先落本地，再按需回写后端

### Track D：同步收口护栏

1. `make model-eval` 不再是 placeholder  
2. `make perf` 用合成推演跑容量基线  
3. GitHub Actions 上传 model-eval / perf artifacts  
4. README / DEV_WORKFLOW / CI_SETUP / USER_STORIES 同步更新

---

## 5. 退出标准

Sprint 9 在本仓库中的退出标准调整为：

- 关键记忆能在重开会话后恢复，并且旧记忆可被摘要归档
- 路由配置可通过环境变量按 role / logic / creative 覆盖
- 路由评估结果可生成 report，并可触发 fallback
- Wiki 与富文本编辑器能完成“修改 -> 保存 -> 刷新回显”
- 本地草稿在关闭页面后仍可恢复
- 仓库存在可运行的 `make model-eval` 与 `make perf`
- 默认门禁仍通过：`make lint`、`make test`

---

## 6. 非承诺范围

本期与 Sprint 9 后续增量仍明确不承诺：

- 全量协同编辑
- PR 默认门禁直接跑真实 LLM eval

说明：

- 已补充真实 ChromaDB 检索接线，并保留回退到内置检索后端的诊断信息。
- 已补充 `TXT / Markdown / HTML / DOCX / PDF + manifest` 的 export bundle，用于继续润色、审阅、打印预览和外部交付。
- 后续仍需继续打磨的是更高质量的 embedding 模型与更专业的版式模板，而不是“有没有这条链路”。

这些方向不是不重要，而是都应该建立在本次已落地的 durable memory / routing / workspace contract 之上。
