# WorldBox Writer: Future Roadmap (v1.0 演进规划)

**文档状态**：Active (Post-MVP Planning)
**作者**：Manus AI

在成功交付 v0.5.0（端到端推演引擎、SSE 实时流、SQLite 持久化、等待态编辑）之后，WorldBox Writer 已经证明了"沙盒式多 Agent 协作"在长篇小说生成中的可行性。

为了将系统从一个"技术演示（Tech Demo）"升级为真正能够帮助创作者、甚至具备商业化潜力的"生产力工具（Productivity Tool）"，本路线图结合了当前 AI 写作工具（如 Sudowrite、Novelcrafter）的最佳实践与用户痛点，规划了未来的核心演进方向。

---

## 1. 核心痛点与产品差异化

当前市面上的 AI 写作工具普遍面临以下痛点：
- **长篇一致性差**：即使有 Story Bible，AI 在生成长文时仍容易遗忘细节、角色崩坏。
- **线性叙事束缚**：大部分工具只能"往前写"或"重写当前段落"，缺乏对复杂分支和世界线变动的管理。
- **缺乏"涌现性"**：AI 只是被动执行人类的扩写指令，缺乏真正鲜活的、能够自主推动剧情的虚拟世界。

**WorldBox Writer 的核心差异化优势**在于：
**从"文本编辑器"升维到"世界引擎"。** 
通过底层的有向无环图（DAG）和多 Agent 状态机，我们将故事的逻辑推演与文本渲染解耦。未来的迭代将进一步放大这一优势，让用户真正体验到"创世神"的乐趣。

---

## 2. 产品功能演进 (Product Features)

### 2.1 多世界线与分支管理 (Branching Narratives & Timeline Control)
当前 MVP 的推演是单向线性的。未来的核心是将 DAG 的优势发挥到极致，支持多分支推演。

- **时间线回溯与分叉 (Undo & Branching)**：允许用户在任意历史节点（StoryNode）"存档"，并在该节点引入新的干预指令，从而衍生出平行世界线（如："如果主角在这里选择背叛会怎样？"）。
- **多分支对比评估**：系统可同时推演 2-3 条分支，用户可以在面板中对比不同走向的结构化大纲，选择最满意的一条进行精细渲染。
- **版本控制系统**：引入类似 Git 的概念，支持 `commit`（固化章节）、`checkout`（回退状态）、`merge`（收束支线）。

### 2.2 深度世界构建与资产管理 (Deep Worldbuilding & Asset Management)
当前 MVP 的设定是自动生成且只读的，缺乏深度可控性。

- **交互式设定集 (Interactive Wiki)**：将 `WorldBuilder` 生成的势力、地点、角色面板开放给用户进行增删改查。用户修改设定后，自动触发全局一致性校验。
- **导入大纲与预设 (Import Outline)**：支持用户上传现有的世界观设定或故事大纲，`Director Agent` 解析后直接初始化 DAG，而非从零生成。
- **关系图谱增强 (Social Graph Visualization+)**：在 Sprint 6 已落地的关系图谱 v1 基础上，继续补齐节点聚焦、关系过滤、时间维度回放和更强的可视化表达。

### 2.3 细粒度干预与节奏控制 (Granular Intervention & Pacing)
当前 MVP 的干预是简单的文本输入，缺乏结构化引导。

- **干预类型模板库**：提供"降下天灾"、"赐予神器"、"挑起纷争"、"托梦启示"等结构化干预模板，降低用户的认知负荷。
- **叙事节奏控制器 (Pacing Control)**：允许用户设置当前阶段的"基调"（如：平缓日常、紧张战斗、悬疑解密），`GateKeeper` 会据此调整 Agent 提议的通过率。
- **角色心智锁定 (Mind Override)**：在关键节点，用户可以直接接管某个 Actor Agent 的决策权，手动指定其下一步行动。

---

## 3. 使用体验优化 (User Experience & UX)

### 3.1 工作流与生产力增强
- **持久化工作区 (Workspace Persistence)**：在已落地的 SQLite 持久化基础上，继续扩展多项目管理、自动保存和断点续传。
- **富文本编辑器集成**：在当前的等待态编辑能力基础上，补齐更完整的正文润色与反向同步工作流。
- **多格式专业导出**：除了 TXT 和 JSON，支持一键导出排版精美的 EPUB、PDF，以及分章节的 Markdown 归档。

### 3.2 前端表现层升级
- **沉浸式沙盒体验**：深化小米 MiMo 风格的极简设计，增加平滑的状态过渡动画。
- **事件流增强 (Rich Event Feed)**：在故事时间线中引入节点折叠/展开、按角色过滤、高亮关键转折点等功能，解决长篇推演时的信息过载。
- **真实 Agent 遥测 (Live Telemetry)**：在 Sprint 6 已落地的 Telemetry v1 基础上，继续增强关键决策、拒绝原因、干预结果和历史回放的可读性，不暴露完整 chain-of-thought。

---

## 4. 技术底座升级 (Technical Foundations)

- **持久化存储层**：引入关系型数据库管理会话和元数据，引入 ChromaDB/Milvus 替代当前的内存向量库，实现真正的长期语义记忆检索。
- **LLM 路由与成本优化**：
  - 将逻辑推演（Actor/GateKeeper）交给快速、低成本的模型（如 Qwen-2.5-14B 本地部署，或 GPT-4o-mini）。
  - 将最终的文学渲染（Narrator）交给擅长长文本和创意写作的模型（如 Kimi、Claude 3.5 Sonnet、MIMO Pro）。
- **异步任务队列**：引入 Celery 或 Redis 队列，将耗时的渲染任务与前端 API 解耦，彻底解决当前基于线程池的轮询机制带来的性能瓶颈。

---

## 5. 阶段性里程碑 (Milestones)

- **v0.5.0 (Streaming, Persistence & Live Editing)**：实现 SSE 实时事件流、SQLite 持久化、等待态角色/世界编辑。
- **v0.6.x (Visibility)**：补齐动态人物关系图谱、Agent 遥测日志和推演链路可视化。
- **v0.7.x (Control)**：实现时间线分叉、回溯与多分支控制能力。
- **v0.8.x - v1.0.0 (Productivity)**：开放交互式设定集、导入大纲、多格式导出与多模型路由。
