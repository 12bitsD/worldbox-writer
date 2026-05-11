# WorldBox Writer Orchestrator 总控手册

> 本手册是迭代编排的单一真相源。停机后恢复、新 session 接入，先读本文件。

***

## 北极星

> 最终目标：让 Agent 写出 **L2（好产品）** 级别的长篇小说。
> 对标：起点头部签约作 / 一般传统出版小说。

核心差异化：**逻辑层先于文字层**（Scene Script → Actor → Critic → GM → Narrator）。

一句话定位：**写长篇小说时，AI 不会忘记前面写了什么。**

***

## 评估体系（网文三轴 + 毒点红线）

为对标"起点头部网文"，评测系统的 single source of truth 是 [QUALITY_SPEC.md](../product/QUALITY_SPEC.md)（Sprint 25 R3 起合并旧 WEB_NOVEL_CRITERIA / QUALITY_FRAMEWORK）。

### 1. 情绪与爽点轴（核心动力）

- **期待感建立**：画饼能力、目标迫切度
- **爽点爆发**：情绪释放、收益获取、打脸爽感
- **抑扬节奏**：吃瘪与反击的比例是否健康

### 2. 网文结构轴（留存与追读）

- **黄金开局**：前 1 万字人设、金手指、主线危机的确立
- **断章艺术**：章末悬念、情绪高潮的卡点
- **信息给配**：世界观设定的自然融入（拒绝对话/旁白强行科普）

### 3. 商业文笔轴（低门槛与画面感）

- **阅读顺滑度**：短平快，低阅读门槛，无生僻字
- **画面感/张力**：战斗与场景的动作描写
- **对话网感**：符合网文语境，拒绝翻译腔/说教味

### 4. 毒点与 AI 味红线（一票否决）

一旦命中以下任何一条，该段落评分为 0，必须发回重写：

- 强行降智
- 战力/设定崩坏
- 说教味/爹味
- 典型 AI 幻觉修辞（排比泛滥、过度比喻）

### 四档标准（对标网文市场）

| 档位      | 对标      | 情绪爽点  | 结构    | 文笔    | 毒点命中率 | 盲测胜率            |
| ------- | ------- | ----- | ----- | ----- | ----- | --------------- |
| L1 追平市面 | 起点中位网文  | ≥ 6.0 | ≥ 6.0 | ≥ 6.0 | 0%    | vs 起点中位 ≥ 40%   |
| L2 好    | 起点头部签约作 | ≥ 7.0 | ≥ 7.0 | ≥ 7.0 | 0%    | vs 起点头部 ≥ 45%   |
| L3 优秀   | 猫腻/烽火级  | ≥ 8.0 | ≥ 8.0 | ≥ 8.0 | 0%    | vs 头部 ≥ 50%     |
| L4 无敌   | 余华/麦家级  | ≥ 9.0 | ≥ 9.0 | ≥ 9.0 | 0%    | vs Claude ≥ 50% |

**当前基线**：Sprint 23 后 \~7.5/10（L1 接近达标，L2 差距明确）

***

## 每轮自检 3 问（强制，任一模糊则重选题）

1. **本轮选择的差距，是否直接影响"小说爽度与留存"？如何影响网文三轴？**
2. **本轮的可验证标准是什么？必须是数字或 pass/fail。**
3. **如果本轮成功，三轴中哪一轴的哪个维度提升？当前在哪一档，目标爬到哪？**

***

## 迭代流程（每轮 7 步）

```
1. Review: 读 state.json + 上轮 round-N.md + 产品最终目的
2. 自检: 北极星 3 问，写入 round-(N+1).md
3. 选题: 从 gap list 挑 1 个最影响双轴的差距。一次只攻一个
4. 设计验证标准: 本轮要让哪些 eval 指标从 X → Y？写下来
5. 实现: 组织 Codex（TDD + harness eng）
6. 验证: 跑 eval + 客观指标，与第 4 步对比
7. 文档同步: 更新 state.json + round-N.md + Sprint 文档
```

### Review 顺序（每次迭代开始时）

1. Review 产品最终目的（北极星 + 双轴 + 四档）
2. 拆解到当前 Phase 的具体目标
3. 规划这次提升的预期（哪个维度从哪到哪）
4. 最后才是提升手段（怎么实现）

***

## Codex 调度规则

### 实施任务

- **一个 Codex 只做一件事**，不捆绑多任务
- Prompt 给具体文件路径和行号
- 明确说"不要读 README/CONTRIBUTING/SECURITY，直接改代码"
- 末尾附验收命令：`Run: make test && make lint`
- **可并行**：不同文件的独立任务可启动多个 Codex 实例

### 架构任务

- **Codex 不做架构级改动**：超出"实施"范畴 → 我来设计 → RFC → Codex 实施
- 架构变更必须有 RFC（docs/architecture/rfc-N.md）

### 监控

- Codex 可能跳步（不写测试直接实现、跳过 lint），需要及时干涉
- 用 process(poll/log) 监控，发现违规立即 kill 重来

***

## 评测方法：LLM-as-judge

**硬编码公式评不了文笔和故事力，必须用模型评。**

### 流程

1. 功能生成内容 → 保存本地文件
2. 单独发 request 给 LLM 评委会（用 QUALITY\_FRAMEWORK.md 的 prompt 模板）
3. 模型配置和生产一致（同一个 LLM\_PROVIDER / LLM\_API\_KEY）
4. 解析 JSON 分数 → 断言阈值

### pytest marker

- `@pytest.mark.eval` — 需要真实 LLM 的评测
- `@pytest.mark.integration` — 需要真实 LLM 的集成测试
- 默认 `make test` 只跑非 eval/integration 测试

### 评测 prompt

参考 [`QUALITY_SPEC.md §2 测量协议`](../product/QUALITY_SPEC.md#2-measurement-protocol测量协议) 与 `src/worldbox_writer/evals/dimension_prompts.py`。

### AI 写作常见问题（必须检测）

| 问题   | 判定标准         | 阈值  |
| ---- | ------------ | --- |
| 过度比喻 | 比喻密度 > 3次/千字 | ≥ 6 |
| 过度排比 | 排比结构 > 2次/千字 | ≥ 6 |
| 段落断裂 | 前后段无因果/时间连接  | ≥ 7 |
| 陈词滥调 | cliché > 5%  | 扣分  |
| 注水废句 | 重复/空洞/废话     | 扣分  |

***

## 清理策略（每 2-3 轮一次）

项目没上线，不兼容旧内容。定期清理保持代码库干净。

### 清理清单

- 旧的硬编码质量测试 → 替换为 LLM-as-judge 评测
- 弃用的代码/模块 → 直接删除，不留 deprecated 注释
- 无用的文档 → 归档到 docs/archive/ 或直接删除
- 弃用的数据库 schema/migration → 直接覆盖，不做向后兼容
- 过时的 Sprint 文档 → 合并关键信息到当前文档，旧文档归档

### 清理原则

- 不保留"以后可能用到"的代码
- 不保留 deprecated 注释（直接删）
- 文档只保留当前有效的，旧的归档或删除
- 测试只保留有价值的，冗余的合并或删除

***

## 守护栏（任何时候不能违反）

- 不跳 TDD / 不跳 eval 直接合并
- 一切以 eval 数字为准，"看起来好了"不算通过
- 一轮一个差距，不允许同时攻多点
- 不伪造或猜测指标，不知道就跑 eval
- Codex 不做架构级改动（超出"实施"范畴 → 拒绝）

***

## 停机条件（满足任一即停，等用户确认）

- 连续 **3 轮**双轴均无可量化提升
- 当前 Phase 完成，准备进入下一 Phase（进 Phase 必须用户确认）
- 跨档前需要真人评委校准（L1→L2 / L2→L3 / L3→L4 边界）
- 需要架构级决策且置信度 < 70%
- make eval 或 make test 失败 3 次后无法恢复
- 轮数达到 **50 轮**（硬上限）

### 停机时输出

1. 当前档位 + 当前 Phase 完成度
2. 双轴最新分数趋势
3. 下一步建议路线 + 是否需要真人评委校准
4. 需要用户决策的 open question（每条带推荐 + 置信度）

***

## 项目约定

```
项目路径: /Users/bytedance/Desktop/CodeSpace/worldbox-writer
Python: 3.11+ (仓库内 .venv)
前端: Node.js 20 + pnpm
命令入口: Makefile
  make lint         ← black/isort + eslint
  make test         ← pytest + vitest + build
  make typecheck    ← mypy（非阻塞，历史债务）
  make integration  ← 真实 LLM 调用
  make check        ← lint + typecheck 合集
```

***

## 文档与状态同步（每轮必做）

| 文件                                  | 内容                                          |
| ----------------------------------- | ------------------------------------------- |
| `docs/orchestrator/state.json`      | 当前 Phase / 档位 / 双轴最新分数 / gap list / 连续无提升计数 |
| `docs/orchestrator/round-N.md`      | 自检 + 选题 + eval 前后 + 反思（历史 round 已归档）        |
| `docs/orchestrator/README.md`       | **本文件** — 总控手册                              |
| `AGENTS.md`                         | 执行契约变更                                      |
| `docs/sprints/SPRINT_N.md`          | Sprint 计划                                   |
| `docs/sprints/SPRINT_N_PROGRESS.md` | Sprint 进度                                   |

***

## 产品演进路径

- **Phase 0 能用**：修好输出质量 + UI bug → 当前阶段
- **Phase 1 好用**：富文本编辑器 + 选择题干预 + 章节化组织
- **Phase 2 想用**：编辑 AI 文本 + 大纲导入 + 模板市场
- **Phase 3 离不开**：SaaS + 长篇完整章节 + 社区

***

## 当前状态

- Sprint 23 已完成（Narrator 质量突破，基线 \~7.5/10）
- Sprint 24 进行中：全链路 Agent 质量治理 + LLM-as-judge 评测基建
- Round 10 已完成：SceneScript 因果性优化
- 历史 round 记录（1–9）已归档至 `docs/archive/orchestrator/`

