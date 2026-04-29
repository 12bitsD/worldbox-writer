# WorldBox Writer (创世神小说家)

> "人类提出需求，关注边界，控制关键节点；Agent 负责演化世界，书写故事。"

WorldBox Writer 是一款开源的**沙盒式 AI 小说生成系统**。它将多 Agent 大模型集群与《WorldBox》式的上帝视角沙盒游戏机制相结合，打造出一个具备高度自治与可干预性的虚拟创作世界。

[![CI](https://github.com/12bitsD/worldbox-writer/actions/workflows/ci.yml/badge.svg)](https://github.com/12bitsD/worldbox-writer/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 核心愿景

在传统 AI 写作工具里，人类是"主笔"，AI 是"代笔"。在 WorldBox Writer 里，**人类是"导演/创世神"，Agent 是"剧组/世界"**。

目标是解决 AI 长文写作中"一致性差"和"用户意图难以持久生效"的痛点：
底层用状态机 + 有向无环图承载世界演化，通过独立的边界守卫维护意图，
通过关键节点识别让用户以"降下神迹"的方式改变走向。

---

## 核心特性

- **意图持久化与边界控制**：独立的 GateKeeper + Critic 双层把关，确保用户约束与叙事品质贯穿始终。
- **双循环推演引擎**：Director 规划场景 → 隔离 Actor 产出意图 → Critic 审查 → GM 结算 → Narrator 渲染，逻辑事实与文本表达解耦。
- **角色自驱演化**：每个核心角色是独立的 Actor Agent，基于属性、目标与分层记忆自主决策。
- **关键节点与神级干预**：NodeDetector 自动识别剧情分歧点并暂停推演，用户可通过"神谕"改变走向。
- **分层记忆系统**：短期 / 长期 / 反思三层记忆 + 语义检索（ChromaDB），保障长篇一致性。
- **多分支推演**：历史节点分叉、分支切换与对比摘要，为蝴蝶效应式创作预留空间。
- **多格式导出**：TXT / Markdown / HTML / DOCX / PDF，附设定集、时间线与 manifest。

---

## 系统架构

```
用户输入（一句话前提）
        │
        ▼
┌───────────────────────────────────────────┐
│              Director                      │
│   意图解析 → 世界骨架 → ScenePlan 编排      │
└───────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────┐
│            WorldBuilder                    │
│   扩写规则 / 势力 / 地理 / 力量体系          │
└───────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────┐
│       LangGraph StateGraph 双循环           │
│                                            │
│   Actor(×N) → Critic → GM → NodeDetector  │
│       ↑         │      │         │         │
│       └─────────┘      │         ▼         │
│                        │   用户干预点       │
│                        ▼                   │
│                  SceneScript (事实源)       │
└───────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────┐
│               Narrator                     │
│   SceneScript → 高质量小说文本              │
└───────────────────────────────────────────┘
        │
        ▼
  导出：TXT / Markdown / HTML / DOCX / PDF / 设定 / 时间线
```

### Agent 职责一览

| Agent | 职责 |
| :--- | :--- |
| **Director** | 解析用户意图，初始化世界骨架，产出 ScenePlan 驱动每幕推演 |
| **WorldBuilder** | 扩写世界规则、势力、地理、力量体系，维护全局知识库 |
| **Actor × N** | 每个角色是独立 Agent，基于性格、目标与分层记忆产出 ActionIntent |
| **Critic** | 意图级质量与一致性审查，LLM 策略判断，出 intent-level verdict |
| **GateKeeper** | 独立边界层，校验候选事件是否违反活跃约束，HARD 违反阻断推演 |
| **GM** | 结算 Actor 意图，产出 branch-aware 的 SceneScript 事实源 |
| **NodeDetector** | 识别关键分歧节点，触发用户干预信号 |
| **Narrator** | 基于 SceneScript 渲染高质量小说文本 |

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- pnpm

### 安装

```bash
git clone https://github.com/12bitsD/worldbox-writer.git
cd worldbox-writer

# 一键安装后端 + 前端依赖
make setup
```

### 配置 LLM

在项目根目录创建 `.env` 文件（参考 `.env.example`）：

```env
# 推荐：Xiaomi MiMo (Token Plan)
LLM_PROVIDER=mimo
LLM_API_KEY=tp-your-token-plan-key-here
LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1

# 备选：Kimi Coding（Anthropic-compatible）
# LLM_PROVIDER=kimi
# LLM_API_KEY=sk-your-kimi-api-key
# LLM_BASE_URL=https://api.kimi.com/coding/

# 备选：OpenAI
# LLM_PROVIDER=openai
# LLM_API_KEY=sk-your-openai-api-key

# 备选：本地 Ollama
# LLM_PROVIDER=ollama
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_MODEL=qwen2.5:14b

# 可选：语义检索后端（默认 auto，优先使用 ChromaDB）
# MEMORY_VECTOR_BACKEND=auto
# MEMORY_VECTOR_PATH=./artifacts/chromadb
```

### 启动

```bash
# 启动后端
make dev-api

# 启动前端（新终端）
make dev-web
```

打开浏览器访问 `http://localhost:5173`。

### CLI 模式（无需前端）

```bash
python -m worldbox_writer.cli
```

---

## 项目结构

```
worldbox-writer/
├── src/worldbox_writer/
│   ├── agents/               # 八大 Agent 实现
│   │   ├── director.py       # 意图解析与场景规划
│   │   ├── world_builder.py  # 世界扩写与知识库维护
│   │   ├── actor.py          # 隔离角色决策
│   │   ├── critic.py         # 意图级审查
│   │   ├── gate_keeper.py    # 边界约束校验
│   │   ├── gm.py             # SceneScript 结算
│   │   ├── node_detector.py  # 关键节点识别
│   │   ├── narrator.py       # 文本渲染
│   │   └── narrator_iterative.py  # 迭代式渲染（预研）
│   ├── api/                  # FastAPI 后端（REST + SSE）
│   ├── core/                 # 核心模型与双循环契约
│   ├── engine/               # LangGraph StateGraph 推演引擎
│   ├── memory/               # 短期 / 长期 / 反思三层记忆
│   ├── prompting/            # Prompt registry 与模板管理
│   ├── prompts/              # 外部化 prompt 模板
│   ├── storage/              # SQLite 持久化
│   ├── exporting/            # 多格式导出
│   ├── evals/                # LLM-as-judge 评测基建
│   ├── perf/                 # 容量与性能门禁
│   └── utils/                # 可插拔 LLM 客户端工厂
├── frontend/                 # React + TypeScript + TailwindCSS 前端
├── tests/                    # pytest 测试套件
├── scripts/                  # CI 与 dev 脚本
└── docs/                     # 架构、开发、产品与 Sprint 文档
```

---

## 演进路径 (Roadmap)

WorldBox Writer 的演进被定义为一条**认知递进**的旅程：

1. **看见世界 (Observe)** — 用户先看懂 Agent 决策逻辑与关系网络，才能做出有意义的干预。
   关系图谱、Telemetry 面板、Prompt Inspector 已落地。
2. **掌控世界 (Control)** — 补齐"后悔药"与"平行宇宙"。
   历史节点分叉、多分支切换、对比摘要、分支级 pacing 已落地。
3. **创作作品 (Create)** — 将推演结果转化为专业作品。
   创作工作台、富文本润色、Wiki 设定集、多格式导出、智能记忆、模型路由已落地。
4. **质量治理 (Refine)** — 消除 Agent 模板化，冲击 L2 文学质量。
   双循环契约、LLM-as-judge 评测体系、Director/Actor/Critic/GM/Narrator 全链路治理进行中。

---

## 当前状态

**当前版本**：v0.5.0（详见 [CHANGELOG](CHANGELOG.md)）

**当前迭代**：Sprint 24 — 全链路 Agent 质量治理 + LLM-as-judge 评测基建。
详见 [docs/sprints/SPRINT_24.md](docs/sprints/SPRINT_24.md)。

**已沉淀的里程碑**：
- MVP 核心闭环（v0.5.0）：实时 SSE、SQLite 持久化、等待态编辑。
- 看见世界：结构化关系图谱、Telemetry 面板与过滤分组、Prompt Inspector。
- 掌控世界：历史节点分叉、branch-aware telemetry、pacing、rollback runbook。
- 创作作品：Creative Studio（Wiki + 富文本 + 草稿恢复）、TXT/MD/HTML/DOCX/PDF 导出、ChromaDB 向量检索、多模型路由。
- 双循环推演：Director ScenePlan、隔离 Actor runtime、Critic 审查、GM SceneScript 结算、NarratorInput v2、dual-loop compare/report 护栏。
- 工作台：关键节点 compact drawer、双视窗阅读/推演、关系图谱拖拽建边。
- 质量治理（进行中）：Agent prompt 去模板化、LLM-as-judge（prose 12 维 + story 12 维 + AI-issue 7 维）、真实 LLM E2E 评测 harness。

**测试状态**：`make lint` 通过；`make test` 通过；`make typecheck` 保持既有基线。
`make integration` 依赖真实 LLM Provider，需配置凭证后单独运行。

历史 Sprint 规划（SPRINT_0 到 SPRINT_23）已归档至 `docs/archive/sprints/`，
不再作为维护入口。

---

## API 文档

后端启动后访问 `http://localhost:8000/docs` 查看完整 Swagger 文档。

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `GET` | `/api/health` | 健康检查 + LLM 配置信息 |
| `POST` | `/api/simulate/start` | 启动新的故事推演 |
| `GET` | `/api/simulate/{id}` | 获取推演当前状态 |
| `GET` | `/api/simulate/{id}/stream` | 获取实时推演事件流 (SSE) |
| `POST` | `/api/simulate/{id}/intervene` | 提交用户干预指令 |
| `GET` | `/api/simulate/{id}/diagnostics` | 记忆、路由与成本估算诊断摘要 |
| `GET` | `/api/simulate/{id}/inspector` | Prompt Inspector：查看每次 LLM 调用的模板与输入输出 |
| `GET` | `/api/simulate/{id}/dual-loop/compare` | 双循环灰度上线对比报告 |
| `POST` | `/api/simulate/{id}/branch` | 从指定历史节点创建新分支并可选择立即续跑 |
| `POST` | `/api/simulate/{id}/branch/switch` | 切换当前活跃分支 |
| `GET` | `/api/simulate/{id}/branch/compare` | 查看主线/支线的基础对比摘要 |
| `POST` | `/api/simulate/{id}/branch/pacing` | 设置当前分支的节奏档位 |
| `GET` | `/api/simulate/{id}/export` | 导出故事 bundle（TXT/MD/HTML/DOCX/PDF + 设定 + 时间线 + manifest），支持 `branch` 查询参数 |
| `GET` | `/api/simulate/{id}/export/file` | 下载指定导出文件，支持 `novel_docx`、`novel_pdf` 等 artifact kind |
| `GET` | `/api/sessions` | 列出最近会话 |
| `PATCH` | `/api/simulate/{id}/characters/{char_id}` | 编辑角色属性（仅 waiting 状态） |
| `PATCH` | `/api/simulate/{id}/world` | 编辑世界设定（仅 waiting 状态） |
| `PATCH` | `/api/simulate/{id}/relationships` | 在可编辑阶段建立或修改角色关系边 |
| `POST` | `/api/simulate/{id}/constraints` | 添加新约束（仅 waiting 状态） |
| `PUT` | `/api/simulate/{id}/wiki` | 保存创作工作台中的设定 Wiki |
| `PATCH` | `/api/simulate/{id}/nodes/{node_id}/rendered-text` | 保存富文本润色后的正文节点 |

---

## 运行测试

```bash
# 本地可重复的非集成测试（无需 LLM API）
make test

# 依赖真实 LLM 的集成测试
make integration
```

集成测试依赖可达且未限流的真实 LLM Provider；网络受限、DNS 失败、超时或 429 限流都会导致失败。

---

## 文档索引

- [文档导航](docs/README.md)
- [Agent 执行契约](AGENTS.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [变更记录](CHANGELOG.md)
- [架构设计](docs/architecture/DESIGN.md)
- [双循环推演引擎设计](docs/architecture/DUAL_LOOP_ENGINE_DESIGN.md)
- [开发指南（环境 / 命令 / CI / 分支提交）](docs/development/DEVELOPMENT.md)
- [敏捷开发指南（测试分层 / DoD / Sprint）](docs/development/AGILE_GUIDE.md)
- [运行手册（故障排查 / Feature Flag 止损）](docs/development/RUNBOOK.md)
- [发布流程](docs/development/RELEASE_PROCESS.md)
- [产品策略](docs/product/PRODUCT_STRATEGY.md)
- [质量评估框架](docs/product/QUALITY_FRAMEWORK.md)
- [Orchestrator 总控手册](docs/orchestrator/README.md)

---

## LLM 配置说明

项目支持通过环境变量或 `.env` 文件配置不同的 LLM 后端。

支持的模型提供商：

1. **MIMO (Xiaomi MiMo)**（推荐）
   - `LLM_PROVIDER=mimo`
   - `LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1`
2. **Kimi Coding**（Anthropic-compatible）
   - `LLM_PROVIDER=kimi`
   - `LLM_BASE_URL=https://api.kimi.com/coding/`
3. **OpenAI**
   - `LLM_PROVIDER=openai`
4. **Ollama**（本地部署）
   - `LLM_PROVIDER=ollama`

完整字段详见 `.env.example`。

---

## 贡献

欢迎 PR 和 Issue。开始贡献前，请先阅读 [贡献指南](CONTRIBUTING.md)。

---

## License

MIT
