# WorldBox Writer (创世神小说家)

> "人类提出需求，关注边界，控制关键节点；Agent 负责演化世界，书写故事。"

WorldBox Writer 是一款开源的**沙盒式 AI 小说生成系统**。它将多 Agent 大模型集群与《WorldBox》式的上帝视角沙盒游戏机制相结合，打造出一个具备高度自治与可干预性的虚拟创作世界。

## 🌟 核心愿景 (Product Vision)

在传统的小说辅助工具中，人类是"主笔"，AI 是"代笔"。而在 WorldBox Writer 中，**人类是"导演/创世神"，Agent 是"剧组/世界"**。

我们的目标是解决当前 AI 写作中"长文本一致性差"和"人类干预难以持久生效"的痛点。通过底层的状态机与有向无环图（DAG），让世界在逻辑框架内自主推演；通过关键节点的识别，让用户以"降下神迹"的方式改变世界走向。

## ✨ 核心特性 (Key Features)

- **意图持久化与边界控制**：独立的 Gate Keeper 负责维护世界规则与叙事边界，确保用户意图贯穿始终。
- **角色自驱演化**：每个核心角色都是独立的 Agent，基于自身属性与记忆在沙盒中自由行动、结盟或背叛。
- **故事节点与神级干预**：在关键剧情分歧点，系统自动暂停，允许用户通过自然语言指令（"神谕"）干预事件走向。
- **快速推演与精细渲染**：支持在数秒内推演故事骨架（Fast-Forward），确认可行后再逐章渲染高质量文本。
- **分层记忆系统**：保障长篇小说的角色一致性与事件连贯性。

## 🏗️ 架构概览 (Architecture Overview)

系统采用"好莱坞编剧室"式的多 Agent 协作架构，核心由以下组件构成：

| 模块 | 核心职责 |
| :--- | :--- |
| **Director (架构师)** | 接收初始需求，拆解核心矛盾，初始化故事 DAG。 |
| **Gate Keeper (边界守卫)** | 维护世界规则、叙事红线与风格边界，校验所有事件。 |
| **World Builder (世界构建师)** | 扩写与维护全局知识库（地理、势力、设定）。 |
| **Actor (角色扮演者)** | 驱动个体行为与决策，维护个人记忆与好感度。 |
| **Logic Manager (逻辑校验者)** | 维护因果 DAG，防止逻辑漏洞与时间悖论。 |
| **Narrator (叙述者)** | 将结构化事件节点渲染为文学小说文本。 |

## 📚 文档索引 (Documentation)

- [产品需求文档 (PRD)](docs/product/PRD.md)
- [架构设计与技术选型](docs/architecture/DESIGN.md)
- [敏捷开发指南与规范](docs/development/AGILE_GUIDE.md)
- [用户故事与 Backlog](docs/product/USER_STORIES.md)
- [Sprint 0 计划与 DoD](docs/sprints/SPRINT_0.md)

## 🛠️ 技术栈 (Tech Stack)

- **Backend & Agent Orchestration**: Python, CrewAI / AutoGen
- **LLM Integration**: OpenAI, Anthropic, Ollama (Local)
- **Data Storage**: Neo4j (Graph for DAG & Relations), Chroma/Milvus (Vector for Memory)
- **Frontend (Phase 2)**: React, React Flow (DAG Visualization), ECharts

## 🚀 快速开始 (Getting Started)

*(开发中，敬请期待 Sprint 1 发布)*

## 📄 开源协议 (License)

MIT License
