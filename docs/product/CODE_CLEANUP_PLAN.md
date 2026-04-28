# WorldBox Writer 代码精简方案

**原则**：保留角色/设定/世界观编辑 + 多世界线能力，砍掉工程师玩具。

---

## 一、可直接删除的模块

### 后端（删除 ~1,368 行）

| 模块 | 行数 | 删除理由 |
|:---|---:|:---|
| `cli.py` | 291 | CLI 模式，非核心产品功能，SaaS 上线后无用 |
| `evals/dual_loop_compare.py` | 279 | 双循环对比报告，纯工程评估工具 |
| `evals/model_eval.py` | 242 | 多模型评估脚本，CI/工程工具 |
| `perf/load_gate.py` | 207 | 性能压测门禁，CI 工具 |
| `perf/__init__.py` | 1 | 配套 |
| `evals/__init__.py` | 1 | 配套 |

删除后保留 `evals/` 和 `perf/` 目录结构（空 `__init__.py`）以避免 import 报错，或者干脆从 `__init__.py` 中移除引用。

### 前端（删除 ~507 行 + 测试）

| 组件 | 行数 | 删除理由 |
|:---|---:|:---|
| `RelationshipPanel.tsx` | 507 | 关系图谱可视化，工程师玩具。角色关系在设定面板中以列表展示即可 |
| `RelationshipPanel.test.tsx` | 37 | 配套测试 |

### 可删除的 API 端点

| 端点 | 对应前端 | 删除理由 |
|:---|:---|:---|
| `GET /api/simulate/{id}/diagnostics` | 无（开发者用） | 诊断面板，开发者工具 |
| `GET /api/simulate/{id}/inspector` | 无（开发者用） | Prompt Inspector，开发者工具 |
| `GET /api/simulate/{id}/dual-loop/compare` | 无（开发者用） | 双循环对比报告 |
| `PATCH /api/simulate/{id}/relationships` | RelationshipPanel | 关系编辑（可后续在角色编辑中内联） |

---

## 二、可大幅简化的模块

### `api/server.py` (1825 行 → ~1000 行)

当前 server.py 包含了太多逻辑：
- SimulationSession 类定义（应抽到独立文件）
- Wiki 验证逻辑（应抽到独立文件）
- LLM diagnostics 收集（可删）
- Export bundle 构建（应抽到独立文件）
- 大量 `_helper` 函数

精简方向：
1. 将 SimulationSession 抽到 `api/session.py`
2. 将 Wiki 逻辑抽到 `api/wiki.py`
3. 将 Export 逻辑复用 `exporting/story_export.py`
4. 删除 diagnostics/inspector/dual-loop-compare 相关代码
5. 删除 relationship 相关端点

### `engine/graph.py` (1489 行 → ~800 行)

当前 graph.py 是单循环 + 双循环的混合体，包含大量兼容层和 adapter。

精简方向：
1. 删除 legacy 单循环路径（如果双循环已稳定）
2. 删除 `FEATURE_DUAL_LOOP_ENABLED` 开关（已确认双循环是主链）
3. 简化 GateKeeper 校验逻辑（当前有 self-heal 重试，可简化）
4. 删除 telemetry 相关的 helper（移到独立 telemetry 模块或直接删除）

### `memory/memory_manager.py` (971 行 → ~500 行)

当前包含 ChromaDB 向量检索 + SQLite 持久化 + 三层记忆 + 反思写回。

精简方向：
1. 删除 ChromaDB 向量检索（当前用 SQLite fallback 就够了，向量检索在小体量故事中没有优势）
2. 保留三层记忆结构（working/episodic/reflective）但简化实现
3. 简化反思写回流程

### `agents/critic.py` (485 行 → ~250 行)

当前 Critic 有完整的 intent-level 审查 + 详细的 rejection taxonomy。

精简方向：
1. 保留核心审查逻辑（角色是否越界、是否违反世界规则）
2. 简化 rejection 分类（不需要 10+ 种 reason_code，3-5 种够了）
3. 删除 verbose telemetry 事件

### `core/models.py` (391 行 → ~300 行)

保留所有核心模型（Character、StoryNode、WorldState、Constraint）。
可精简：
1. 删除 `TelemetrySpanKind`（不需要细分到 LLM/USER/SYSTEM）
2. 合并 `TelemetryLevel` 和 `TelemetrySpanKind` 为简单枚举

---

## 三、保留但需要重构的模块

### `agents/narrator.py` — 需要重写 prompt

这是**最紧急的修改**。当前输出是模板复读，不是小说。

问题根因：
- Narrator 输入是 Scene Script 的 summary/objective，不是结构化的事件+对话
- System prompt 要求 "200-400字"，太短
- 没有给 Narrator 足够的角色背景和前文摘要

修改方向：
1. 输入改为 SceneScript.beats（结构化事件列表）而非 summary
2. System prompt 增加角色卡信息、前章摘要、风格要求
3. 增大输出长度（800-1500 字/章）
4. 考虑换更强模型（当前用 gpt-4.1-mini，创意写作需要更强的模型）

### `agents/director.py` — 需要改善角色命名和标题生成

当前角色名是模板化的"流亡破局者"，标题是"第N幕：XX的局势推进"。

修改方向：
1. 角色初始化时调用 LLM 生成真实人名
2. 场景标题用 LLM 生成而非模板拼接
3. Scene objective 改为更具体的事件描述而非抽象目标

### `StartPanel.tsx` — 需要重新设计

当前是工程感很强的表单。需要改成：
1. 去掉"推演深度"的 tick 选择（4/6/8/12），改为"章节数"或直接默认值
2. 简化示例前提（保留 2-3 个，不要 4 个）
3. 增加"选择风格"（网文/文学/轻小说）

### `StoryFeed.tsx` — 需要简化

当前是双视窗（推演日志 + 故事正文），需要：
1. 默认只显示故事正文（去掉推演日志）
2. 去掉"工程呼吸灯"（harness chips）
3. 保留角色实体浮窗（有用）

---

## 四、保留不动的模块

| 模块 | 理由 |
|:---|:---|
| `agents/actor.py` | 角色决策核心，保留 |
| `agents/gate_keeper.py` | 约束校验核心，保留 |
| `agents/gm.py` | 冲突结算核心，保留 |
| `agents/world_builder.py` | 世界构建核心，保留 |
| `agents/node_detector.py` | 干预检测核心，保留（但干预频率需调整） |
| `engine/dual_loop.py` | 双循环引擎核心，保留 |
| `core/dual_loop.py` | 双循环数据模型，保留 |
| `storage/db.py` | 持久化核心，保留 |
| `utils/llm.py` | LLM 客户端核心，保留 |
| `exporting/story_export.py` | 导出核心，保留 |
| `api/core/branching.py` | 分支管理核心（多世界线），保留 |
| `api/core/serialization.py` | 序列化工具，保留 |
| `prompting/registry.py` | Prompt 模板管理，保留 |
| `components/BranchPanel.tsx` | 多世界线 UI，保留 |
| `components/EditPanel.tsx` | 编辑面板，保留 |
| `components/RichTextEditor.tsx` | 富文本编辑，保留 |
| `components/ExportPanel.tsx` | 导出面板，保留 |
| `components/WorldPanel.tsx` | 设定展示，保留 |
| `components/InterventionPanel.tsx` | 干预面板，保留但需重新设计 |

---

## 五、精简后的架构概览

```
src/worldbox_writer/
├── core/
│   ├── models.py          # 核心数据模型（精简版）
│   └── dual_loop.py       # 双循环契约
├── agents/
│   ├── director.py        # 意图解析 + 世界初始化（改 prompt）
│   ├── world_builder.py   # 世界扩写
│   ├── actor.py           # 角色决策
│   ├── critic.py          # 意图审查（精简版）
│   ├── gm.py              # 冲突结算
│   ├── gate_keeper.py     # 约束校验
│   ├── node_detector.py   # 干预检测
│   └── narrator.py        # 文本渲染（重写 prompt）
├── engine/
│   ├── graph.py           # 推演引擎（精简版）
│   └── dual_loop.py       # 双循环执行器
├── memory/
│   └── memory_manager.py  # 记忆系统（精简版，去掉 ChromaDB）
├── storage/
│   └── db.py              # SQLite 持久化
├── api/
│   ├── server.py          # FastAPI（精简版）
│   ├── session.py         # SimulationSession（从 server.py 抽出）
│   ├── wiki.py            # Wiki 逻辑（从 server.py 抽出）
│   ├── schemas.py         # Pydantic schemas
│   ├── state.py           # 全局状态管理
│   └── core/
│       ├── branching.py   # 分支管理
│       └── serialization.py
├── exporting/
│   └── story_export.py    # 多格式导出
├── prompting/
│   └── registry.py        # Prompt 模板
└── utils/
    └── llm.py             # LLM 客户端

frontend/src/
├── components/
│   ├── StartPanel.tsx      # 首页（重新设计）
│   ├── StoryFeed.tsx       # 故事阅读（简化版）
│   ├── BranchPanel.tsx     # 多世界线（保留）
│   ├── InterventionPanel.tsx # 干预（重新设计为选择题）
│   ├── EditPanel.tsx       # 编辑面板
│   ├── RichTextEditor.tsx  # 富文本编辑
│   ├── ExportPanel.tsx     # 导出
│   ├── WorldPanel.tsx      # 设定展示
│   └── Header.tsx          # 顶栏
├── hooks/
│   └── useSimulation.ts   # 核心 hook
├── utils/
│   └── api.ts             # API 客户端
└── types/
    └── index.ts            # 类型定义（精简版）
```

---

## 六、精简效果估算

| 维度 | 精简前 | 精简后 | 变化 |
|:---|---:|---:|:---|
| 后端代码行数 | ~11,658 | ~8,500 | -27% |
| 前端代码行数 | ~5,047 | ~3,800 | -25% |
| API 端点数 | 20 | 16 | -20% |
| 前端组件数 | 11 | 9 | -18% |
| Agent 数量 | 8 | 8 | 不变 |

**删除的主要是工程工具（evals/perf/cli）和过度工程化的模块（关系图谱/Inspector/Diagnostics），核心产品能力（Agent 编排、分支、记忆、导出）全部保留。**
