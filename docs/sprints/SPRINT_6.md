# Sprint 6 Planning: 深度世界构建与资产管理 (Deep Worldbuilding)

**文档状态**：Active (Planning)
**版本目标**：v0.6.0
**作者**：Manus AI

---

## 1. 回顾与现状 (Context)

在 Sprint 5 (v0.5.0) 中，我们成功实现了底层基建的飞跃：
- **实时性**：从轮询升级为 SSE 实时推流。
- **持久化**：引入 SQLite 实现零依赖的数据库存储，支持会话恢复。
- **可干预性**：在干预暂停期间，允许用户通过 `EditPanel` 修改角色属性、世界设定和新增约束。

**当前痛点**：
尽管用户可以修改设定，但**设定的可视化展示**仍然非常简陋。随着推演的进行，人物关系会发生变化，势力范围会变动，但用户无法直观地看到这些变化。这正是我们在 `USER_STORIES.md` 中积压的 `US-05.02`（动态人物关系图谱）。

此外，当前的世界初始化完全依赖 AI 黑盒生成，不支持用户导入已有的大纲或设定（Roadmap 中的 2.2 节）。

---

## 2. Sprint 6 目标 (Sprint Goal)

**"让世界观可见且可控"**

本轮 Sprint 的核心是将 WorldBox Writer 从一个纯文本流工具，升级为一个**带有可视化资产管理能力的世界引擎**。我们将补齐遗留的关系图谱功能，并增加对专业小说导出的支持（PDF/Word），以满足真实作家的交付需求。

### 核心交付物 (Deliverables)
1. **动态人物关系图谱 (Social Graph)**：前端集成 ECharts/React Flow，实时渲染角色间的关系网络。
2. **关系推演逻辑 (Relationship Evolution)**：后端 Actor Agent 在生成事件时，必须动态更新角色间的关系（好感度/敌对状态），并在状态中持久化。
3. **专业导出能力 (Professional Export)**：将渲染完成的小说导出为排版精美的 PDF 和 Word (Docx) 格式。

---

## 3. 用户故事拆解 (User Stories & Tasks)

### Epic 05: 可视化沙盒面板 (Visual Sandbox Dashboard)

#### US-05.02: 动态人物关系图谱 (Priority: P0)
*作为创世神，我希望能查看动态更新的人物关系图谱，以便掌握全局势力变化。*

- **Task 1 (Backend)**: 扩展 `Character.relationships` 字典，明确存储格式（如 `{ target_id: {"affinity": 80, "type": "ally"} }`）。
- **Task 2 (Backend)**: 修改 `ActorAgent`，在每次事件发生后，根据事件性质自动更新相关角色的 relationships 数据。
- **Task 3 (API)**: 在 SSE 流中，确保每次 `node` 事件都携带最新的 relationships 状态。
- **Task 4 (Frontend)**: 引入图表库（推荐 `react-force-graph` 或 `echarts`），新增 `NetworkPanel` 组件。
- **Task 5 (Frontend)**: 根据 SSE 数据实时重绘图谱，节点大小反映重要性，连线颜色/粗细反映好感度。

### Epic 06: 专业交付与资产管理 (Professional Export) *(New Epic)*

#### US-06.01: 多格式专业导出 (Priority: P1)
*作为创作者，我希望能将推演完成的小说导出为 PDF 和 Word 格式，以便直接交付或在其他软件中继续排版。*

- **Task 1 (Backend)**: 引入 `fpdf2` (PDF) 和 `python-docx` (Word) 库。
- **Task 2 (Backend)**: 新增 `/api/simulate/{sim_id}/export/pdf` 端点，生成包含封面、目录、正文的排版 PDF。
- **Task 3 (Backend)**: 新增 `/api/simulate/{sim_id}/export/docx` 端点，生成结构化的 Word 文档。
- **Task 4 (Frontend)**: 在 `ExportPanel` 中增加 "导出为 PDF" 和 "导出为 Word" 的下载按钮。

#### US-06.02: 大纲与设定导入 (Priority: P2)
*作为世界构建师，我希望能上传预先写好的世界观设定，而不是让系统从零生成，以便延续我现有的创作。*

- **Task 1 (API)**: 扩展 `/api/simulate/start` 的 Payload，允许传入可选的 `initial_world_state` (JSON 格式)。
- **Task 2 (Backend)**: 修改 `graph.py` 中的 `director_node` 和 `world_builder_node`，如果检测到传入了预设数据，则跳过生成或仅做增量补全。
- **Task 3 (Frontend)**: 在 `StartPanel` 增加 "导入设定 (JSON)" 的高级选项。

---

## 4. 技术决策与依赖 (Technical Decisions)

1. **图表库选择**：前端采用 `react-force-graph-2d`（基于 D3.js），因为它对动态力导向图（Force-directed graph）支持极好，且轻量级，非常适合表现人物关系。
2. **导出库选择**：
   - PDF: `fpdf2`（沙盒已预装 `fpdf2` 和 `weasyprint`，推荐 `fpdf2` 因其纯 Python 实现且易于控制分页）。
   - Word: 需要在后端 `pip install python-docx`。
3. **关系演化逻辑**：为了不增加过多的 LLM 成本，关系更新可以通过简单的规则引擎实现，或者在 Actor 生成提议时，让 LLM 顺便输出一个 JSON Patch 来描述关系变化。

---

## 5. 验收标准 (Definition of Done)

- [ ] 所有新端点和功能必须有对应的 `pytest` 单元测试。
- [ ] 前端图谱必须能随 SSE 事件流实时跳动更新，无明显卡顿。
- [ ] 导出的 PDF 和 Word 必须包含：书名（Title）、前提（Premise）、角色表（Characters）和分章节的正文（Narrative）。
- [ ] README.md 和 API 文档必须同步更新到 v0.6.0。
