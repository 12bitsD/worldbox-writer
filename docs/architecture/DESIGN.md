# WorldBox Writer 架构设计与技术选型

**文档状态**：Active (Sprint 1 Updated)
**作者**：Manus AI

## 1. 系统核心理念 (Core Architecture Principles)

本系统不再是一个单纯的"文本生成器"，而是一个"事件推演引擎"。
所有的故事发展，首先在底层数据结构中以**有向无环图（DAG）**的形式推演并固化，然后才交由大语言模型（LLM）进行文学性渲染。

这种架构设计的目的是为了解决长篇小说生成中的**逻辑一致性**与**用户干预持久性**问题。

## 2. 核心模块与组件

系统分为三个主要层级：**世界推演层（World Simulation Layer）**、**边界与意图层（Constraint & Intent Layer）**、**表现与渲染层（Presentation Layer）**。

### 2.1 世界推演层 (World Simulation Layer)

负责维护世界的物理规律、历史背景以及角色的自主行动。

- **World Builder (世界构建师 Agent)**：
  - 维护全局知识库（Global Context）。
  - 当新区域被探索或新势力出现时，动态生成设定并存入向量数据库（Vector DB）。
- **Actor (角色扮演者 Agent 集群)**：
  - 每个核心角色是一个独立的 Agent 实例。
  - 维护个人的属性面板、好感度矩阵以及短期/长期记忆。
  - 基于当前世界状态和自身目标，向调度中心提交"行动意图"（Action Proposal）。

### 2.2 边界与意图层 (Constraint & Intent Layer)

这是系统的"大脑"和"裁判"，负责处理人类干预，并确保世界不会崩溃。

- **Gate Keeper (边界守卫 Agent)**：
  - 接收并解析用户的"神谕"（自然语言干预指令）。
  - 将用户意图转化为硬性约束（Hard Constraints）或软性倾向（Soft Preferences）。
  - 拦截所有违反世界规则或叙事红线的 Actor 行动意图。
- **Logic Manager (逻辑校验者 Agent)**：
  - 维护事件的有向无环图（Event DAG）。
  - 确保因果关系成立（例如：A 必须先获得钥匙，才能打开宝箱）。
  - 解决并发冲突（例如：两个 Actor 同时试图杀死同一个目标）。

### 2.3 表现与渲染层 (Presentation Layer)

负责将底层的结构化数据转化为人类可读的内容。

- **Narrator (叙述者 Agent)**：
  - 读取已确认的 Event DAG 节点序列。
  - 结合参与角色的性格和历史记忆，将结构化事件渲染为带有对话、心理活动和环境描写的文学正文。
- **Dashboard API (前端接口)**：
  - 提供实时更新的事件流（Event Stream）、人物关系图谱数据和全局状态快照。

## 3. 核心数据流转 (Data Flow)

1. **初始化**：Director Agent 接收用户的一句话需求，生成初始世界设定（存入 Vector DB）和初始矛盾（生成首个 DAG 节点）。
2. **提议阶段**：Actor Agents 观察当前 DAG 末端节点，结合自身记忆，各自生成下一步行动提议。
3. **校验阶段**：Gate Keeper 和 Logic Manager 对所有提议进行审查，剔除不合逻辑或违背用户意图的行动。
4. **决议阶段**：系统根据权重或随机概率，从合法提议中选出一个或多个，固化为新的 DAG 节点。
5. **渲染阶段**：
   - **精细模式**：Narrator Agent 立即将新节点渲染为小说正文。
   - **快进模式**：跳过 Narrator，直接进入下一轮提议，仅输出结构化摘要。
6. **干预中断**：当系统检测到即将生成的节点属于"关键分歧点"（如主角生死、重大结盟）时，暂停推演，向用户发起交互请求（Prompt for Intervention）。

## 4. 技术栈选型 (Tech Stack Selection)

### 4.1 后端与 Agent 编排 (Backend & Orchestration)
- **语言**：Python 3.11+
- **Agent 框架**：LangGraph（Sprint 1 Spike 选型确认）。
  - *理由*：LangGraph 提供有状态的图执行模型，天然支持循环、条件分支和人机交互暂停（`interrupt_before`），完全契合本项目的"推演-校验-干预"循环。相比之下，CrewAI 偏向线性任务流，AutoGen 状态管理复杂度过高。
- **API 框架**：FastAPI。
  - *理由*：支持异步非阻塞 I/O，适合处理长时间运行的 Agent 推演任务和 Server-Sent Events (SSE) 流式输出。

### 4.2 数据存储 (Data Storage)
- **图数据库 (Graph DB)**：Neo4j。
  - *用途*：存储事件的有向无环图（Event DAG）以及动态更新的人物关系网络（Social Graph）。
- **向量数据库 (Vector DB)**：Chroma 或 Milvus。
  - *用途*：存储世界观设定集（Wiki）、角色的长期记忆（Long-term Memory），支持语义检索（RAG）。
- **关系型数据库 (RDBMS)**：PostgreSQL 或 SQLite。
  - *用途*：存储用户账户、项目元数据、存档快照（Save States）。

### 4.3 大语言模型接入 (LLM Integration)
- **云端 API**：OpenAI (GPT-4o), Anthropic (Claude 3.5 Sonnet)。
  - *用途*：用于复杂的逻辑推理、边界校验和高质量文本渲染。
- **本地部署**：Ollama + Llama 3 / Qwen 2。
  - *用途*：为关注隐私的用户提供纯本地运行方案，用于轻量级的 Actor 决策和意图提议。

### 4.4 前端 (Frontend - 规划中)
- **框架**：React 18+ (Vite)
- **状态管理**：Zustand
- **可视化库**：
  - React Flow：用于展示事件 DAG 和故事树。
  - ECharts / D3.js：用于渲染人物好感度矩阵和势力分布图。
