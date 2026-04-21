# WorldBox Writer (创世神小说家)

> "人类提出需求，关注边界，控制关键节点；Agent 负责演化世界，书写故事。"

WorldBox Writer 是一款开源的**沙盒式 AI 小说生成系统**。它将多 Agent 大模型集群与《WorldBox》式的上帝视角沙盒游戏机制相结合，打造出一个具备高度自治与可干预性的虚拟创作世界。

[![CI](https://github.com/12bitsD/worldbox-writer/actions/workflows/ci.yml/badge.svg)](https://github.com/12bitsD/worldbox-writer/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 核心愿景

在传统的小说辅助工具中，人类是"主笔"，AI 是"代笔"。而在 WorldBox Writer 中，**人类是"导演/创世神"，Agent 是"剧组/世界"**。

我们的目标是解决当前 AI 写作中"长文本一致性差"和"人类干预难以持久生效"的痛点。通过底层的状态机与有向无环图（DAG），让世界在逻辑框架内自主推演；通过关键节点的识别，让用户以"降下神迹"的方式改变世界走向。

---

## 核心特性

- **意图持久化与边界控制**：独立的 Gate Keeper 负责维护世界规则与叙事边界，确保用户意图贯穿始终。
- **角色自驱演化**：每个核心角色都是独立的 Actor Agent，基于自身属性与记忆在沙盒中自由行动、结盟或背叛。
- **故事节点与神级干预**：在关键剧情分歧点，系统自动暂停，允许用户通过自然语言指令（"神谕"）干预事件走向。
- **快速推演与精细渲染**：支持在数秒内推演故事骨架，确认可行后再逐章渲染高质量文本。
- **分层记忆系统**：短期上下文 + 长期摘要，保障长篇小说的角色一致性与事件连贯性。
- **多格式导出**：小说正文、Markdown、HTML、DOCX、PDF、世界设定集、故事时间线与 manifest 清单可独立导出。

---

## 系统架构

```
用户输入（一句话前提）
        │
        ▼
┌─────────────────────────────────────────────┐
│              Director Agent                  │
│  意图解析 → 世界骨架初始化 → 约束持久化      │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│           WorldBuilder Agent                 │
│  扩写世界规则 / 势力 / 地理 / 力量体系       │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  LangGraph StateGraph 推演循环               │
│                                             │
│  Actor(×N) → GateKeeper → NodeDetector     │
│      ↑              │           │           │
│      └──────────────┘           │           │
│                                 ▼           │
│                          用户干预点          │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│             Narrator Agent                   │
│  结构化事件 → 高质量小说文本渲染             │
└─────────────────────────────────────────────┘
        │
        ▼
  导出：TXT / Markdown / HTML / DOCX / PDF / 设定集 / 时间线
```

### Agent 职责一览

| Agent | 职责 |
| :--- | :--- |
| **Director** | 解析用户意图，初始化世界骨架，将用户需求持久化为 Constraint |
| **WorldBuilder** | 扩写世界规则、势力、地理、力量体系，维护全局知识库 |
| **Actor × N** | 每个角色是独立 Agent，根据性格、目标、记忆自主决策行动 |
| **GateKeeper** | 独立边界层，校验每个节点是否违反活跃约束，HARD 违反阻断推演 |
| **NodeDetector** | 识别关键分歧节点，触发用户干预信号 |
| **Narrator** | 将结构化事件渲染为高质量小说文本 |

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- pnpm

### 安装

```bash
# 克隆仓库
git clone https://github.com/12bitsD/worldbox-writer.git
cd worldbox-writer

# 一键安装后端 + 前端依赖
make setup
```

### 配置 LLM

在项目根目录创建 `.env` 文件：

```env
# 使用 MIMO（推荐）
LLM_PROVIDER=mimo
LLM_API_KEY=tp-your-token-plan-key-here
LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1

# 或使用 Kimi Coding（Anthropic-compatible）
# LLM_PROVIDER=kimi
# LLM_API_KEY=sk-your-kimi-api-key
# LLM_BASE_URL=https://api.kimi.com/coding/

# 或使用 OpenAI
# LLM_PROVIDER=openai
# LLM_API_KEY=sk-your-openai-api-key

# 或使用本地 Ollama（完全私有）
# LLM_PROVIDER=ollama
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_MODEL=qwen2.5:14b

# 可选：语义检索后端（默认 auto，会优先使用 ChromaDB）
# MEMORY_VECTOR_BACKEND=auto
# MEMORY_VECTOR_PATH=./artifacts/chromadb
```

### 启动

```bash
# 启动后端（项目根目录）
make dev-api

# 启动前端（新终端）
make dev-web
```

打开浏览器访问 `http://localhost:5173`

### CLI 模式（无需前端）

```bash
python -m worldbox_writer.cli
```

---

## 项目结构

```
worldbox-writer/
├── src/worldbox_writer/
│   ├── agents/               # 六大 Agent 实现
│   │   ├── director.py       # 意图解析与世界初始化
│   │   ├── world_builder.py  # 世界扩写与知识库维护
│   │   ├── actor.py          # 角色自主决策
│   │   ├── gate_keeper.py    # 边界约束校验
│   │   ├── node_detector.py  # 关键节点识别
│   │   └── narrator.py       # 文本渲染
│   ├── core/
│   │   └── models.py         # 核心数据结构
│   ├── engine/
│   │   └── graph.py          # LangGraph StateGraph 推演引擎
│   ├── memory/
│   │   └── memory_manager.py # 分层记忆系统
│   ├── api/
│   │   └── server.py         # FastAPI 后端（REST + SSE）
│   └── utils/
│       └── llm.py            # 可插拔 LLM 客户端工厂
├── frontend/                 # React + TypeScript + TailwindCSS 前端
├── tests/                    # TDD 测试套件（模型 / 存储 / API / 集成）
└── docs/
    ├── architecture/DESIGN.md
    ├── architecture/RELATIONSHIP_SCHEMA_V1.md
    ├── architecture/TELEMETRY_SCHEMA_V1.md
    ├── product/USER_STORIES.md
    ├── development/AGILE_GUIDE.md
    ├── development/CI_SETUP.md
    ├── sprints/              # 历史 Sprint 文档与后续计划
```

---

## 演进路径 (Roadmap)

在经过深度的产品评审后，WorldBox Writer 的演进路径被定义为一条**认知递进**的旅程：

1. **Release 2: 看见世界 (Observe)**
   - *核心逻辑*：用户必须先看懂 Agent 的决策逻辑和关系网络，才能做出有意义的干预。
   - *核心交付*：动态关系图谱、Agent 遥测日志面板。
2. **Release 3: 掌控世界 (Control)**
   - *核心逻辑*：在看懂世界后，用户需要"后悔药"和"平行宇宙"，对比不同干预带来的蝴蝶效应。
   - *核心交付*：时间线回溯、多分支并行推演（已在底层架构预留 `branch_id` 和合并空间）。
3. **Release 4: 创作作品 (Create)**
   - *核心逻辑*：在拥有强大的推演掌控力后，补齐生产力闭环，将推演结果转化为专业作品。
   - *核心交付*：大纲导入、交互式 Wiki、长文富文本编辑器、多模型智能路由、专业格式导出。

## 开发状态

| Sprint | 目标 | 状态 |
| :--- | :--- | :--- |
| Sprint 0-5 | MVP 核心能力闭环（推演引擎、UI、持久化、干预编辑） | ✅ 已发布 (v0.5.0) |
| Sprint 6 | 看见世界：关系图谱 + 遥测基础 | ✅ 完成（P0 闭环已交付） |
| Sprint 7 | 可视化补齐与稳定性加固 | ✅ 完成（v0.6.x 范围已交付） |
| Sprint 8 | 掌控世界：时间线分叉与多分支控制 | ✅ 完成（branching loop 已交付） |
| Sprint 9 | 创作作品：智能记忆、多模型路由与创作工作台 | ✅ P0 落地（ChromaDB deferred） |
| Sprint 10-11 | 双循环基础：契约冻结 + Director Scene Planner | ✅ 完成（ScenePlan 已进主链） |
| Sprint 12 | 隔离 Actor 运行时 v1 | ✅ 完成（spotlight fan-out / fan-in 已接入） |
| Sprint 13 | Critic 审查链路 | ✅ 完成（intent-level verdict 已接入） |
| Sprint 14 | GM 结算与 Scene Script 提交 | ✅ 完成（SceneScript 已成为逻辑事实源） |
| Sprint 15 | 认知记忆流 v2 | ✅ 完成（三层记忆与反思写回已接入） |
| Sprint 16 | Inspector 与 PromptOps | ✅ 完成（Prompt Inspector 与模板 registry 已接入） |
| Sprint 17 | SceneScript 驱动 Narrator 渲染 | ✅ 完成（NarratorInput v2 已接入） |

**当前版本**：v0.5.0

- 已发布能力（v0.5.0）：实时事件流、本地 SQLite 持久化、等待态编辑能力。
- 已完成的 Sprint 6 交付：结构化关系 schema、Telemetry v1、关系图谱面板、Telemetry 面板、历史会话恢复、最近会话入口、前端 fixtures 自动化验证、telemetry 恢复和关系推断的数据正确性修复。
- 已完成的 Sprint 7 交付：关系图谱聚焦与边详情、Telemetry 按 Agent/Stage 过滤与分组、统一 LLM 调用元数据、Telemetry 关联字段、实时/历史/刷新一致性修复、GateKeeper 拒绝自愈、长日志可读性与最小性能护栏。
- 已完成的 Sprint 8 交付：历史节点分叉与续跑、Branch Seed Snapshot v1、多分支查看与切换、基础 compare 摘要、分支级 pacing 控制、branch-aware telemetry、Feature Flag + rollback runbook。
- 已完成的 Sprint 8.5 交付：初始化阶段进度可见化、SSE 首包优化、首个正文关键路径裁剪、主区域 progressive feedback 面板。
- 已完成的 Sprint 9 P0 交付：SQLite 持久化记忆与摘要归档、logic/creative 多模型路由与 fallback 钩子、Creative Studio（Wiki + 富文本编辑 + 草稿恢复）、诊断 API、model-eval 与 perf gate 脚本/工作流。
- 已完成的 Sprint 13 交付：`IntentCritique` 契约、`CriticAgent` 意图级审查、accepted / rejected intent 诊断、Critic telemetry 和前端诊断摘要。
- 已完成的 Sprint 14 交付：`GMAgent` 结算层、branch-aware `SceneScript`、StoryNode metadata 持久化、diagnostics 复用已结算场景脚本。
- 已完成的 Sprint 15 交付：`reflection` 记忆层、SceneScript accepted beat 反思写回、三层 `MemoryRecallTrace` 诊断、Creative Studio 反思记忆计数。
- 已完成的 Sprint 16 交付：Inspector API、Creative Studio Prompt Inspector、Actor prompt 模板外部化、Prompt registry hot reload contract。
- 已完成的 Sprint 17 交付：`NarratorInput` v2、SceneScript 渲染适配、rejected intent 防写入 prompt guard、StoryFeed lineage 展示与导出兼容回归。
- 已完成的 Sprint 9 增量推进：真实 ChromaDB 向量检索已接线并成为默认 `auto` 路径；导出链路已升级为 TXT / Markdown / HTML / DOCX / PDF / JSON manifest bundle。
- 已完成的 Sprint 10-11 交付：双循环契约冻结、compatibility adapter、diagnostics 暴露、Director scene planner、`ScenePlan` graph state 持久化和 legacy actor prompt 接入。
- 已完成的 Sprint 12 交付：隔离 Actor runtime v1、spotlight actor fan-out / fan-in、私有 `PromptTrace` / `MemoryRecallTrace`、真实 `ActionIntent` 产出和 legacy candidate bridge。
- 架构预留：`StoryNode` 和 `WorldState` 已预留 `branch_id` 和 `merged_from_ids`，为未来的分支管理奠定基础。
- 测试状态：`make lint` 通过；`make test` 通过；`make typecheck` 通过。`make integration` 依赖可达且未限流的真实 LLM Provider；网络受限、DNS 失败、超时或 429 限流都会导致失败。
- 当前迭代状态：Sprint 17 已落地；下一阶段聚焦 Sprint 18 的 dual-loop rollout compare、eval guardrails 与 rollback runbook。

---

## API 文档

后端启动后访问 `http://localhost:8000/docs` 查看完整 Swagger 文档。

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `POST` | `/api/simulate/start` | 启动新的故事推演 |
| `GET` | `/api/simulate/{id}` | 获取推演当前状态 |
| `POST` | `/api/simulate/{id}/branch` | 从指定历史节点创建新分支并可选择立即续跑 |
| `POST` | `/api/simulate/{id}/branch/switch` | 切换当前活跃分支 |
| `GET` | `/api/simulate/{id}/branch/compare` | 查看主线/支线的基础对比摘要 |
| `POST` | `/api/simulate/{id}/branch/pacing` | 设置当前分支的节奏档位 |
| `POST` | `/api/simulate/{id}/intervene` | 提交用户干预指令 |
| `GET` | `/api/simulate/{id}/export` | 导出故事 bundle，返回 TXT / Markdown / HTML / DOCX / PDF 元数据、设定 JSON、时间线 JSON、manifest，并支持按 `branch` 查询参数导出指定世界线 |
| `GET` | `/api/simulate/{id}/export/file` | 下载指定导出文件，支持 `novel_docx`、`novel_pdf` 等 artifact kind |
| `GET` | `/api/simulate/{id}/diagnostics` | 查看记忆、路由与成本估算诊断摘要 |
| `PUT` | `/api/simulate/{id}/wiki` | 保存创作工作台中的设定 Wiki |
| `PATCH` | `/api/simulate/{id}/nodes/{node_id}/rendered-text` | 保存富文本润色后的正文节点 |
| `GET` | `/api/health` | 健康检查 + LLM 配置信息 |
| `GET` | `/api/simulate/{id}/stream` | 获取实时推演事件流 (SSE) |
| `PATCH` | `/api/simulate/{id}/characters/{char_id}` | 编辑角色属性（仅 waiting 状态） |
| `PATCH` | `/api/simulate/{id}/world` | 编辑世界设定（仅 waiting 状态） |
| `POST` | `/api/simulate/{id}/constraints` | 添加新约束（仅 waiting 状态） |

---

## 运行测试

```bash
# 运行本地可重复的非集成测试（无需 LLM API）
make test

# 运行依赖真实 LLM 的集成测试
make integration
```

当前仓库在本地已验证 `pytest -m "not integration"` 为 `74 passed, 57 deselected`；集成测试依赖真实 LLM API Key，适合在配置好凭证后单独运行。

---

## 文档索引

- [文档导航](docs/README.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [变更记录](CHANGELOG.md)
- [架构设计文档](docs/architecture/DESIGN.md)
- [开发流程说明](docs/development/DEV_WORKFLOW.md)
- [CI 配置说明](docs/development/CI_SETUP.md)

---

## 贡献

欢迎 PR 和 Issue。开始贡献前，请先阅读 [贡献指南](CONTRIBUTING.md)。

---

## License

MIT

## LLM 配置说明

项目支持通过环境变量或 `.env` 文件配置不同的 LLM 后端。目前默认推荐使用 Xiaomi MiMo (Token Plan)。

支持的模型提供商：
1. **MIMO (Xiaomi MiMo)** (推荐)
   - `LLM_PROVIDER=mimo`
   - `LLM_API_KEY=tp-...`
   - `LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1`
2. **Kimi Coding** (Anthropic-compatible，备选)
   - `LLM_PROVIDER=kimi`
   - `LLM_BASE_URL=https://api.kimi.com/coding/`
3. **OpenAI** (备选)
   - `LLM_PROVIDER=openai`
4. **Ollama** (本地部署)
   - `LLM_PROVIDER=ollama`

详见 `.env.example` 文件。
 
