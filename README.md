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
# 使用 Kimi（推荐，长上下文）
LLM_PROVIDER=kimi
LLM_API_KEY=your-kimi-api-key

# 或使用 OpenAI
LLM_PROVIDER=openai
LLM_API_KEY=your-openai-api-key

# 或使用本地 Ollama（完全私有）
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:14b
```

### 启动

```bash
# 启动后端（项目根目录）
python -m uvicorn src.worldbox_writer.api.server:app --host 0.0.0.0 --port 8000

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
├── tests/                    # TDD 测试套件（157 个测试，全部通过）
└── docs/
    ├── architecture/DESIGN.md
    ├── product/USER_STORIES.md
    ├── development/AGILE_GUIDE.md
    ├── development/CI_SETUP.md
    └── sprints/              # Sprint 0-4 完整记录
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

**当前版本：v0.4.0** — 完整可运行的端到端系统，157 个测试全部通过。

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

---

## 运行测试

```bash
# 运行全套测试（157 个，无需 LLM API）
pytest tests/

# 带覆盖率报告
pytest tests/ --cov=src/worldbox_writer
```

所有测试使用 MockLLM，无需真实 API 密钥，CI 环境下完整可运行。

---

## 文档索引

- [架构设计文档](docs/architecture/DESIGN.md)
- [用户故事与 Product Backlog](docs/product/USER_STORIES.md)
- [敏捷开发指南（TDD + 分支策略 + DoD）](docs/development/AGILE_GUIDE.md)
- [CI 配置说明](docs/development/CI_SETUP.md)
- [Sprint 0 记录](docs/sprints/SPRINT_0.md)
- [Sprint 1 记录](docs/sprints/SPRINT_1.md)
- [Sprint 2-4 记录](docs/sprints/SPRINT_2_4.md)

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
