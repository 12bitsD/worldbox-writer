# Sprint 24: 全链路 Agent 质量治理 + LLM-as-judge 评测基建

**Sprint Goal**: 从 GM→Actor→Critic→Narrator→Director 全链路消除模板化/硬编码，建立 LLM-as-judge 评测体系，为冲击 L2 打好 Agent 层基础。

**验收标准**:
- 全链路 Agent prompt 消除模板短语、排比、概括性描述
- Critic 删除全部硬编码词表，改 LLM 策略判断
- LLM-as-judge 覆盖 prose 12 维 + story 12 维 + AI-issue 7 维
- 每轮 TDD：先写失败测试 → Codex 实现 → 验证
- 单元测试 206+ passed，lint OK

---

## 问题诊断

### 根因 1: GM 结算 SceneScript 模板化
- **位置**: `src/worldbox_writer/agents/gm.py`
- **问题**: summary 复述 objective 模板（"围绕XX承接上一幕..."），beats 抽象无具体动作
- **修复**: 新增 `_TEMPLATE_MARKERS` 检测 8 个模板句式，`_settle_summary` 过滤模板短语，`_build_beats` 每个 beat outcome 独立

### 根因 2: Actor 源头描述模板化
- **位置**: `src/worldbox_writer/agents/actor.py`
- **问题**: description 用概括性词汇（"处理危机""采取行动"），无具体动作+对象
- **修复**: prompt 负面约束（禁用模板/概括/排比/解释动机）+ 正面要求（具体动作+对象、时空信息、体现性格、一句话）

### 根因 3: Narrator 文笔模板化
- **位置**: `src/worldbox_writer/agents/narrator.py`
- **问题**: 过度比喻、排比、段落断裂、解释性对话、安全结尾
- **修复**: prompt 负面约束（禁用堆砌比喻/排比/断裂/解释/安全结尾）+ 正面要求（具体细节、动作先于情感、对话潜台词、段尾留钩子）

### 根因 4: Critic 硬编码检测
- **位置**: `src/worldbox_writer/agents/critic.py`
- **问题**: `_DENY_MARKERS` / `_MONITORED_DENIED_TERMS` / `_META_LEAK_TERMS` 共 30+ 硬编码词
- **修复**: 全部删除，改 LLM 策略判断，prompt 内嵌检测维度

### 根因 5: 评测体系缺失
- **位置**: 无
- **问题**: 质量靠人眼，无法量化追踪双轴提升
- **修复**: 新建 `src/worldbox_writer/evals/llm_judge.py`，prose 12 维 + story 12 维 + AI-issue 7 维

---

## Round 记录

| Round | 目标 | 改动文件 | 新增测试 | 验证结果 |
|-------|------|----------|----------|----------|
| 1 | GM Agent 模板过滤 | gm.py | 2 | 182 passed |
| 2 | LLM-as-judge 基建 | llm_judge.py (新建) | 6 | 188 passed, coverage 71% |
| 3 | Narrator 文笔提升 | narrator.py | 4 | 195 passed |
| 4 | Actor 源头治理 | actor.py, e2e_judge.py (新建) | 7 | 202 passed |
| 5 | 清理 + 评测数据 | docs/sprints/ 清理 | 2 | 204 passed, coverage 72% |
| 6 | Critic 硬编码治理 | critic.py | 2 | 206 passed, coverage 72% |
| 7 | Director 优化 + 真实验证 harness | director.py, dual_loop.py | 4 | 210 passed |
| 8 | 真实 LLM E2E 评测 Harness | e2e_judge.py, llm_judge.py | 3 | 213 passed |
| 9 | Iterative Narrator 预研原型 | narrator_iterative.py (新建) | 4 | 217 passed |

---

## 质量基线

### Mock 评测基线 (Round 6)
```json
{
  "scene_script_score": 5.0,
  "composite_score": 5.0,
  "story_avg": 5.8,
  "prose_avg": 5.7
}
```

### 双轴当前档位
- **故事力**: 5.8/10 (L1 及格线 6.0，差 0.2)
- **文笔**: 5.7/10 (L1 及格线 6.0，差 0.3)
- **综合**: L1 边缘，未达标

---

## 下一 Sprint 方向

**Sprint 25 候选**:
1. **GateKeeper Agent** — 与 Critic 职责合并评估，简化架构
2. **真实 LLM 端到端验证** — 跑完整 simulation，验证 mock 基线准确性
3. **前端体验** — Phase 0 能用→Phase 1 好用，富文本编辑器+选择题干预
4. **评测维度细化** — 增加更多 AI 写作问题检测维度

**推荐**: Sprint 25 先做 **真实 LLM 端到端验证** + **前端体验**，确认生成质量真实水平后再决定是否需要继续优化 Agent prompt。

---

## 文档同步

- `docs/orchestrator/state.json` — 每轮更新
- `docs/orchestrator/round-N.md` — 每轮详细日志
- `docs/orchestrator/baseline-mock-round6.json` — Mock 基线
- `docs/product/QUALITY_FRAMEWORK.md` — 评测体系
