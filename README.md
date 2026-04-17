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
- **多格式导出**：小说正文、世界设定集、故事时间线均可独立导出。

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
  导出：小说文本 / 世界设定集 / 时间线
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

# 安装 Python 依赖
pip install -e ".[dev]"

# 安装前端依赖
cd frontend && pnpm install
```

### 配置 LLM

在项目根目录创建 `.env` 文件：

```env
# 使用 MIMO（推荐）
LLM_PROVIDER=mimo
LLM_API_KEY=tp-your-token-plan-key-here
LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1

# 或使用 Kimi（长上下文）
# LLM_PROVIDER=kimi
# LLM_API_KEY=sk-your-kimi-api-key
# LLM_BASE_URL=https://api.moonshot.cn/v1

# 或使用 OpenAI
# LLM_PROVIDER=openai
# LLM_API_KEY=sk-your-openai-api-key

# 或使用本地 Ollama（完全私有）
# LLM_PROVIDER=ollama
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_MODEL=qwen2.5:14b
```

### 启动

```bash
# 启动后端（项目根目录）
python -m uvicorn worldbox_writer.api.server:app --host 0.0.0.0 --port 8000

# 启动前端（新终端）
cd frontend && pnpm dev
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

## 开发状态

| Sprint | 目标 | 状态 |
| :--- | :--- | :--- |
| Sprint 0 | 基础设施、文档体系、CI/CD、仓库配置 | ✅ 完成 |
| Sprint 1 | 核心数据结构 + Director + GateKeeper + NodeDetector | ✅ 完成 |
| Sprint 2 | LangGraph 编排图 + Actor + Narrator，端到端 Demo | ✅ 完成 |
| Sprint 3 | 分层记忆系统 + WorldBuilder Agent | ✅ 完成 |
| Sprint 4 | 前端可视化面板（React + 实时事件流） | ✅ 完成 |
| Sprint 5 | 持久化存储与实时编辑 (SQLite + SSE) | ✅ 完成 |
| Sprint 6 | 看见世界（首个交付）：关系图谱 + 遥测基础 | 🟡 进行中（基础闭环已落地） |
| Sprint 7 | 可视化补齐与稳定性加固 | 📋 已批准计划 |
| Sprint 8 | 时间线分叉与多分支控制 | 📋 已批准计划 |
| Sprint 9 | 长篇记忆、智能路由与创作工作台 | 📋 已批准计划 |

**当前版本**：v0.5.0

- 已发布能力（v0.5.0）：实时事件流、本地 SQLite 持久化、等待态编辑能力。
- 主干已落地的 Sprint 6 基础能力：结构化关系 schema、Telemetry v1、关系图谱面板、Telemetry 面板、历史会话恢复与最近会话入口。
- 当前测试状态：本地已验证 `pytest -m "not integration"` 为 `74 passed, 57 deselected`；`integration` 用例依赖真实 LLM API Key。
- 当前迭代状态：主干正在推进 Sprint 6，最小可见性闭环已可演示；图谱交互补齐、日志筛选分组、统一调用链与稳定性护栏仍留在 Sprint 7。
- Sprint 7 前必须先解决的 TODO：修复中断会话恢复时的 telemetry 保留问题，以及关系推断在匿名事件和多角色混合场景下的数据正确性问题。

---

## Roadmap

接下来的路线图已经明确为“看见世界 → 掌控世界 → 创作作品”三段式推进。

| 阶段 | 对应 Sprint | 目标 | 核心交付 |
| :--- | :--- | :--- | :--- |
| 看见世界 | Sprint 6-7 | 让推演过程可见且稳定 | 关系图谱、遥测日志、统一调用链、可靠性护栏 |
| 掌控世界 | Sprint 8 | 让用户能回溯并分叉世界线 | `fork_at_node()`、多分支时间线、节奏控制、灰度回滚 |
| 创作作品 | Sprint 9 | 让系统支持长篇创作与生产力闭环 | 智能记忆、多模型路由、Wiki、富文本、容量门禁 |

**版本演进**：

- v0.6.x：补齐可视化与稳定性短板。
- v0.7.x：上线分支推演核心能力。
- v0.8.x：补齐长篇创作工作台能力。

---

## API 文档

后端启动后访问 `http://localhost:8000/docs` 查看完整 Swagger 文档。

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `POST` | `/api/simulate/start` | 启动新的故事推演 |
| `GET` | `/api/simulate/{id}` | 获取推演当前状态 |
| `POST` | `/api/simulate/{id}/intervene` | 提交用户干预指令 |
| `GET` | `/api/simulate/{id}/export` | 导出故事内容 |
| `GET` | `/api/health` | 健康检查 + LLM 配置信息 |
| `GET` | `/api/simulate/{id}/stream` | 获取实时推演事件流 (SSE) |
| `PATCH` | `/api/simulate/{id}/characters/{char_id}` | 编辑角色属性（仅 waiting 状态） |
| `PATCH` | `/api/simulate/{id}/world` | 编辑世界设定（仅 waiting 状态） |
| `POST` | `/api/simulate/{id}/constraints` | 添加新约束（仅 waiting 状态） |

---

## 运行测试

```bash
# 运行本地可重复的非集成测试（无需 LLM API）
python -m pytest -m "not integration"

# 运行依赖真实 LLM 的集成测试
python -m pytest -m integration
```

当前仓库在本地已验证 `pytest -m "not integration"` 为 `74 passed, 57 deselected`；集成测试依赖真实 LLM API Key，适合在配置好凭证后单独运行。

---

## 文档索引

- [架构设计文档](docs/architecture/DESIGN.md)
- [关系结构协议 v1](docs/architecture/RELATIONSHIP_SCHEMA_V1.md)
- [Telemetry 协议 v1](docs/architecture/TELEMETRY_SCHEMA_V1.md)
- [产品演进规划](docs/product/PRODUCT_PLANNING.md)
- [长期路线图](docs/product/FUTURE_ROADMAP.md)
- [用户故事与 Product Backlog](docs/product/USER_STORIES.md)
- [敏捷开发指南（TDD + 分支策略 + DoD）](docs/development/AGILE_GUIDE.md)
- [CI 配置说明](docs/development/CI_SETUP.md)
- [Sprint 0 记录](docs/sprints/SPRINT_0.md)
- [Sprint 1 记录](docs/sprints/SPRINT_1.md)
- [Sprint 2-4 记录](docs/sprints/SPRINT_2_4.md)
- [Sprint 6 计划](docs/sprints/SPRINT_6.md)
- [Sprint 6 Demo Script](docs/sprints/SPRINT_6_DEMO_SCRIPT.md)
- [Sprint 7-9 批准版计划](docs/sprints/FINAL_SPRINT_7_8_9_PLAN.md)

---

## 贡献

欢迎 PR 和 Issue！请先阅读 [敏捷开发指南](docs/development/AGILE_GUIDE.md) 了解分支策略和提交规范。

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
2. **Kimi** (备选，适合长上下文)
   - `LLM_PROVIDER=kimi`
3. **OpenAI** (备选)
   - `LLM_PROVIDER=openai`
4. **Ollama** (本地部署)
   - `LLM_PROVIDER=ollama`

详见 `.env.example` 文件。
 
