# Sprint 2-4 交付报告

## Sprint 2：端到端推演引擎

**Sprint Goal**：完成 LangGraph 编排图、Actor Agent、Narrator Agent，实现第一个可运行的端到端 Demo。

**完成时间**：Sprint 2

### 交付内容

| 模块 | 文件 | 说明 |
| :--- | :--- | :--- |
| LangGraph 编排图 | `engine/graph.py` | StateGraph 推演循环，集成所有 Agent，支持 `interrupt_before` 干预暂停 |
| Actor Agent | `agents/actor.py` | 角色自主决策，基于性格/目标/记忆生成行动，支持可注入 MockLLM |
| Narrator Agent | `agents/narrator.py` | 将结构化 StoryNode 渲染为高质量小说文本 |
| LLM 工厂 | `utils/llm.py` | 可插拔 LLM 客户端，支持 Kimi / OpenAI / Ollama / 沙盒内置接口 |
| FastAPI 后端 | `api/server.py` | REST + SSE 实时推流，支持启动/状态查询/干预/导出 |
| CLI Demo | `cli.py` | 命令行端到端 Demo，无需前端即可体验完整推演 |

### 端到端测试结果

成功推演"废土剑客的复仇"故事：
- 自动生成 4 个势力、4 个地点、3 个角色
- 推演 3 个故事节点后在关键分歧点暂停
- 用户干预后继续推演
- 导出完整小说文本（约 1500 字）

### 关闭的 Issues

- #8 LangGraph StateGraph 编排图
- #12 Actor Agent
- #14 Narrator Agent

---

## Sprint 3：记忆系统与 WorldBuilder

**Sprint Goal**：实现分层记忆系统和 WorldBuilder Agent，保障长篇一致性。

### 交付内容

| 模块 | 文件 | 说明 |
| :--- | :--- | :--- |
| 分层记忆系统 | `memory/memory_manager.py` | 短期滑动窗口上下文 + 长期摘要压缩，防止 Token 溢出 |
| WorldBuilder Agent | `agents/world_builder.py` | 扩写世界规则/势力/地理/力量体系，维护全局知识库 |

### 记忆系统设计

```
短期记忆（Short-term）
  └── 最近 N 个 StoryNode 的完整内容
  └── 当前活跃角色状态

长期记忆（Long-term）
  └── 历史节点摘要（LLM 压缩）
  └── 角色关系变化记录
  └── 世界状态快照
```

### 关闭的 Issues

- #10 分层记忆系统
- #11 WorldBuilder Agent

---

## Sprint 4：前端可视化面板

**Sprint Goal**：实现 React 前端，提供游戏化的上帝视角沙盒体验。

### 交付内容

| 组件 | 文件 | 说明 |
| :--- | :--- | :--- |
| 主应用 | `App.tsx` | 三栏布局，状态机驱动的页面切换 |
| 启动面板 | `StartPanel.tsx` | 一句话前提输入，支持示例快速填充 |
| 世界面板 | `WorldPanel.tsx` | 实时展示角色状态、势力关系、活跃约束 |
| 故事流 | `StoryFeed.tsx` | 故事节点时间线，支持 SSE 实时更新 |
| 干预面板 | `InterventionPanel.tsx` | 关键节点暂停时的用户干预输入界面 |
| 导出面板 | `ExportPanel.tsx` | 多格式导出（小说文本/世界设定/时间线） |
| API 工具 | `utils/api.ts` | REST + SSE 客户端封装 |
| 状态 Hook | `hooks/useSimulation.ts` | 推演状态管理，SSE 事件订阅 |

### 设计风格

参考小米 MiMo 网站设计语言：
- 暖白底色（`#FAFAF8`）+ 纯黑主文字
- 超大无衬线字体，字重建立层次
- "WORLD BOX" 重复文字水印背景纹理
- 极简细边框卡片，大量留白
- 无彩色装饰，靠空间和字重传达信息层次

### 关闭的 Issues

- #13 Fast-Forward Mode（前端快进推演按钮）
- #7 Gate Keeper 集成（前端展示约束违反警告）

---

## 全项目测试覆盖

| 测试模块 | 测试数 | 覆盖率 |
| :--- | :--- | :--- |
| `test_core/` | 24 | 100% |
| `test_agents/` | 52 | ~95% |
| `test_engine/` | 32 | ~90% |
| `test_memory/` | 49 | ~94% |
| **总计** | **157** | **~67%（含 LLM 调用路径）** |

> LLM 调用路径（`utils/llm.py` 的真实 API 分支）因沙盒网络限制无法在 CI 中测试，覆盖率 27%，其余模块均在 90%+ 以上。

---

## Sprint 5（待规划）

下一步可能的方向：

1. **角色关系图谱可视化**：用 React Flow 或 D2 渲染角色关系 DAG
2. **故事分支与撤销**：把推演历史做成树而不是线，支持回退到任意节点
3. **大纲导入**：支持用户导入已有大纲初始化 DAG
4. **本地向量库**：集成 ChromaDB 实现真正的长期语义记忆检索
5. **多语言支持**：英文/日文故事生成
