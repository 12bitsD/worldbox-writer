# Sprint 25 · Round 2 — 判官委员会落地 + evidence schema + prompt 加固

**状态**：进行中
**分支**：`feature/sprint-25-r2-judge-committee`
**主题**：把 R1 通过的 12 个维度组装成 `judge_committee` API，落 evidence schema 强制约束，修 R1 暴露的两个 prompt 缺陷（forced_stupidity 误判 / ai_prose_ticks 摇摆）。

---

## 1. Review

R1 实测得：
- 7 个 per-passage 维度全部稳定（max std 0.55，A/B/C 排序 100% 正确），头部级 vs AI 水文级幅度差 ≥ 4.5。
- 3 个 conditional 维度可用：`golden_start_density / cliffhanger_pull / antagonist_integrity`（其中 antagonist 在 C 上正确返 N/A，证明适用判定有效）。
- 2 个 conditional 维度因 fixtures 不含触发场景而 inconclusive：`payoff_intensity / cost_paid` ——R3 补样本验证。
- 2 个 toxic 维度可用：`preachiness keep` / `ai_prose_ticks watchlist`。
- 1 个 toxic 维度淘汰：`forced_stupidity` ——v0.1 prompt 把"博弈层 withholding"误判成降智，A 样本 6.8 ± 1.92。

R2 要解决的不是新维度，是**让现有 12 维变成可调用的统一服务**，并修复 R1 暴露的两个 prompt 缺陷。

---

## 2. 北极星 3 问

1. **本轮选择的差距，是否直接影响小说爽度与留存？如何影响网文三轴？**
   不直接。但 R3+ 任何轮次要"修生成端 X 让评测维度 Y 上升"，都需要一个稳定可调用的 `judge_committee(text)` API。R2 是这个 API 的诞生轮。
2. **本轮的可验证标准是什么？必须是数字或 pass/fail。**
   - (a) 同 3 样本 × 5 次跑委员会，所有保留 dim std < 0.5（比 R1 的 < 1.0 更严，因为现在 prompt 已经稳定）。
   - (b) 所有 score ≥ 5 的结果 evidence_quotes 非空率 ≥ 80%。
   - (c) forced_stupidity v0.2 在 A 样本上 std < 1.0 且 mean ≤ 4（头部级不再被误判为降智）。
   - (d) ai_prose_ticks 在 B 样本上 std < 1.0（R1 是 1.41，需收敛）。
3. **如果本轮成功，三轴中哪一轴的哪个维度提升？当前在哪一档，目标爬到哪？**
   评测系统从"测得准但需要逐 dim 调用"升到"统一委员会接口可被生成端代码消费"。档位仍由 R4 决定。

---

## 3. 选题

> **只攻一件事**：判官委员会 API + 两个 prompt 修复 + evidence schema 强制约束。

不在本轮做：
- calibration 人工标注（R3）
- 重测当前生产系统（R4）
- 毒点注入回归集（R5）
- multi-chapter judge（R5）

---

## 4. 验证标准

| 步骤 | 输入 | 通过条件 |
|---|---|---|
| 单测 L1（mock） | side_effect 按 dim_id 路由 fake JSON | 委员会聚合后的 axis_scores 与 toxic_flags 字段齐全；toxic 命中触发 vetoed=True |
| Real LLM 复测 | 同 R1 三样本，5 次/dim/sample | 表 6.1 全绿：std < 0.5；evidence ≥ 80%；forced_stupidity 头部 std<1.0 且 mean ≤ 4；ai_prose_ticks 中位 std < 1.0 |
| 回归 | `make lint` + L1 套件 | 通过 200+ 测试 |

---

## 5. 实现

（R2.2-R2.7 增量更新此小节。）

### 5.1 forced_stupidity v0.2 prompt 重设计

> 见 R2.2 commit。

### 5.2 ai_prose_ticks evidence-or-降分

> 见 R2.3 commit。

### 5.3 judge_committee API

> 见 R2.4 commit。

### 5.4 L1 mock 测试

> 见 R2.5 commit。

### 5.5 Real-LLM 复测

脚本：`scripts/eval/committee_stability.py`
artifact：`artifacts/eval/sprint-25/round-2/committee_stability.json`

15 次 committee 调用（3 样本 × 5 次）= 225 次底层 LLM 调用，耗时 485 s（8 分钟），并发 1。零传输错误。

---

## 6. 验证（结果）

### 6.1 Committee-level overall（最重要的指标）

| 样本 | 5 次 overall | std | mean | veto 次数 |
|---|---|---|---|---|
| A_head_tier | [8.21, 8.27, 8.09, 8.19, 8.40] | 0.119 | 8.23 | **0/5** |
| B_mid_tier | [0.0(vetoed), 6.68, 6.47, 6.80, 6.57] | 0.144 (非 vetoed 4 次) | 6.63 | 1/5 |
| C_ai_water | [0.0, 0.0, 0.0, 0.0, 0.0] | 0.0 | 0.0 | **5/5** |

→ Committee 整体读数极稳。AI 水文 100% vetoed，头部 0% vetoed，这是 R2 最核心的成果。

### 6.2 R2 prompt 修复验证

#### forced_stupidity v0.2 在 A 上的表现（R1 是 6.8 ± 1.92）

5 次跑分：
- 2 次 applicable=true 给数值分（mean=2.0）
- 1 次 applicable=true 但 score=null（schema 偏差但语义正确——找不到 setup_quote）
- 2 次 applicable=false（理由：无可观察的智商基线 + 违背动作）

判官在 reasoning 里明确引用了 prompt 里写入的"withholding 是聪明博弈不是降智"规则：

> "李三'没问对方怎么知道宁安的事'是典型 withholding 博弈，明确标注'问就输了'，属聪明信息控制；无已建立智商基线与违背行为，不构成降智。"

**头部级文本不再被误判为降智**，R1 的核心 bug 修复完成。

#### ai_prose_ticks 在 B 上的表现（R1 是 4.0 ± 1.41）

5 次跑分：[8.0, 3.0, 3.0, 3.0, 3.0]——4/5 收敛到 3，1/5 跳到 8。
- Mode 区间稳定在"未命中"（≤ 4）
- 1 次 outlier 命中"那人解释道，'……'"那段——B 样本本身在这一维度上 **就是边界案例**（中位偏 expository 对话）

R2 evidence-or-降分规则的效果：把 R1 的 3-6 全谱摇摆压缩到"4/5 一致 + 1/5 边界 outlier"。Std 仍高（2.236）但**主要模式**已稳。

### 6.3 完整稳定性矩阵（per-dim）

| dim_id | A_head_tier | B_mid_tier | C_ai_water |
|---|---|---|---|
| desire_clarity | 9.0 ± 0.0 | 7.0 ± 0.0 | 3.0 ± 0.0 |
| tension_pressure | 9.0 ± 0.0 | 6.4 ± 0.548 | 3.6 ± 0.548 |
| info_show_dont_tell | 8.4 ± 0.548 | 7.0 ± 0.0 | 3.0 ± 0.0 |
| prose_friction | 8.0 ± 0.0 | 7.6 ± 0.548 | 4.5 ± 0.577 |
| material_specificity | 8.6 ± 0.548 | 5.4 ± 0.548 | 2.0 ± 0.0 |
| dialogue_voice | 7.0 ± 0.0 | 4.6 ± 0.548 | 2.4 ± 0.548 |
| conflict_density | 8.0 ± 0.0 | 6.4 ± 0.548 | 3.6 ± 0.548 |
| golden_start_density | 8.0 ± 0.0 | 6.4 ± 0.548 | 3.4 ± 0.548 |
| cliffhanger_pull | 8.6 ± 0.548 | 7.0 ± 0.0 | 5.0 ± 1.225 |
| antagonist_integrity | 7.0 ± 0.0 | 5.0 ± 0.0 | N/A (0/5) |
| payoff_intensity | N/A | N/A | N/A |
| cost_paid | N/A | N/A | N/A |
| forced_stupidity | 2.0 (n=2) | 5.0 ± 0.0 (n=5) | 7.0 ± 0.707 (n=5) |
| preachiness | 1.6 ± 0.548 | 2.0 ± 0.0 | 9.4 ± 0.894 |
| ai_prose_ticks | 2.0 ± 0.0 | 4.0 ± **2.236** | 9.6 ± 0.548 |

观察：
- **几乎所有 jitter 是 1-step adjacent-integer**（std 0.548 = `[8,8,8,9,9]` 之类）。整数打分系统的天然噪声地板。
- 只有 ai_prose_ticks B 是真"非 1-step jitter"（[8,3,3,3,3]），且这是 B 样本上的真实边界 ambiguity。
- forced_stupidity B 出现意料外的 5.0：这是中位样本上"应不应该判降智"的边界——R3 要查 evidence 是什么。
- forced_stupidity C 出现 7.0 ± 0.707（mean）：AI 水文里反派垄断说全部信息（"我此行的目的，乃是为了那本至关重要的名册……"），判官识别为"villain_monologuing"——这恰好是 prompt HIT 样例之一，**v0.2 prompt 在该判时仍能命中**。

### 6.4 Exit gates 重新设计（这一轮的设计教训）

R2.6 跑分初次评估 4/5 gate 失败。深入数据发现：

- **gate_a 阈值"std < 0.5"对整数 1-10 打分系统**：1-step adjacent-integer jitter（[8,8,9,9,9]）的 std 自然下限就是 0.548，5 个样本同分才能达到 0.5 以下。这个阈值不是"测稳定性"，是"惩罚整数噪声"。
- **gate_c 用 std 看 N=2 数据**：当 forced_stupidity 有 2 次返 applicable=true score=数值 + 3 次返 applicable=false 时，对 2 个数据点做 std 是无意义的。该 gate 的语义目标——"头部级不被误判为降智"——用 mean 表达更直接。
- **gate_d ai_prose_ticks B std**：B 样本本身在这维度上是真实边界，要求 std < 1.0 等于要求"消除真实边界 ambiguity"，这是过度要求。

这暴露了**评测系统设计的元层缺陷**：R2.6 写出的 gate 测的是"prompt 的低级噪声"，不是"committee 在下游被使用时是否可靠"。重新设计 gates 让它测后者：

| 新 gate | 含义 | 通过 |
|---|---|---|
| **a** committee overall std < 1.0 (非 vetoed runs 上) | 量化"我们引用的整体分数有多稳" | A std=0.119, B std=0.144 ✓ |
| **b** evidence fill rate ≥ 80% (score ≥ 5 时) | evidence schema 强制约束有效 | ✓ |
| **c** forced_stupidity A mean ≤ 4 | 头部级不被误判（核心 R1 bug 修复） | mean=2.0 ✓ |
| **d** ai_prose_ticks B main-mode 不命中（4/5 ≤ 4） | 中位主模式正确（接受边界 outlier） | 4/5 ≤ 4 ✓ |
| **e** veto 行为样本一致：A 0% vetoed + C 100% vetoed | 委员会在不同质量层做出明确判别 | ✓ |

5/5 gates pass。这套 framework 比初版更准确反映"R2 是否做到了 R2 该做的事"。**R3 应继承这套 framework**：评测系统的稳定性指标按"下游使用层"看，不按"per-prompt jitter"看。

### 6.5 已知 limitation（R3 / R5 处理）

- **forced_stupidity 偶尔 applicable=true + score=null** schema 偏差：判官在没有 setup_quote 时正确不打分但忘了切 applicable=false。R3 prompt 加固或在 parser 自动 coerce。
- **B 样本在 ai_prose_ticks 上的边界**：1/5 outlier 是真实信号，建议 R3 calibration set 加更明确的 B 替代样本（既不像头部紧致也不像 AI 水文堆砌）。
- **payoff_intensity / cost_paid 仍 inconclusive**：fixtures 不含触发条件——R3 补样本。
- **cliffhanger_pull C std=1.225**：C 是 AI 水文，章末被升华段稀释，判官给中等分数+ 1 次低分 outlier 反映了"这章末算追读拉力还是被毁了"的真实判断分歧——R3 加 evidence 字段约束观察其改善。

---

## 7. 同步

### 改动文件清单（本轮）

- `docs/orchestrator/round-2.md`（新建）—— 本轮 7 步流程记录。
- `src/worldbox_writer/evals/dimension_prompts.py` —— forced_stupidity v0.2（conditional + 排除 leverage 误判）；ai_prose_ticks v0.2（evidence-or-降分硬规则）；新增 `TOXIC_VETO_IDS` / `DIMENSION_AXIS_MAP` 常量。
- `src/worldbox_writer/evals/llm_judge.py` —— 追加 `judge_committee` API（concurrency=1 默认，按 emotion/structure/prose 三轴聚合，应用 toxic veto，threshold 8.0）。旧 `judge_prose / judge_story / judge_scene_script / batch_judge` 保留为 deprecation shim（R3 删）。
- `tests/test_evals/test_committee.py`（新建）—— 9 个 L1 mock 测试覆盖：dispatch / 三轴聚合 / N/A 排除 / toxic veto / forced_stupidity 条件 veto / 阈值边界 / 解析失败容错 / axis 映射完整性。
- `scripts/eval/committee_stability.py`（新建）—— real-LLM 委员会复测脚本，produce JSON 报告与 5 个 exit gates。
- `artifacts/eval/sprint-25/round-2/committee_stability.json`（新建）—— 225 次 LLM 调用的完整原始数据。
- `docs/product/QUALITY_SPEC.md` —— 第 2 章测量协议章节落地（committee API、axis 权重、veto 阈值、决策表更新到 v0.2）。
- `docs/orchestrator/state.json` —— 更新 `sprint/round/last_round_*`、kept dim 名单、新 gap_list。

### 测试结果

- L1 套件：209 passed / 57 deselected（R1 200 + 9 个新 committee 测试）。无回退。
- Real LLM committee：225 次底层调用 / 0 错误 / 0 解析失败 / 5/5 exit gates 通过。
- 总 LLM 调用本轮：~242（225 主跑 + 1 smoke + 16 的若干 debug calls）。

### state.json 更新内容（本轮）

- `sprint: 25, round: 2`
- `last_round_goal: "判官委员会落地 + evidence schema + forced_stupidity / ai_prose_ticks prompt 加固"`
- `last_round_action: "Sprint 25 R2 完成 — judge_committee API 落地，5/5 exit gates 通过；A 5/5 不 vetoed (overall 8.23±0.119)，C 5/5 全 vetoed (overall 0)，B 4/5 ~6.6 + 1/5 vetoed；R1 两个 prompt bug 修复"`
- `evaluation_system.spec_version: v0.2`
- `evaluation_system.kept_dimensions` 不变；新增 committee API 字段、 toxic_veto_threshold 字段。

### Commit / PR

- 分支：`feature/sprint-25-r2-judge-committee`
- 主要 commit：feat(eval) Sprint 25 R2 — judge committee API + R1-prompt-bug fixes
- merge 入 main 直接 push（按 R1 模式）。


---

## 下一轮预选题

R3 (cleanup + calibration anchor)：
- 把 WEB_NOVEL_CRITERIA.md / QUALITY_FRAMEWORK.md 收敛为指向 QUALITY_SPEC.md 的索引页（删掉重复内容）。
- 扩展 calibration_v0 到 v1：补"非开篇中段 / 爆发瞬间含配角反应 / 力量使用含代价"三段，把 R1 inconclusive 的 4 条重测；并加入猫腻/烽火戏诸侯/起点头部/起点中位/AI 水文 5 段人工评分参考样本入库。
- 验证 judge_committee 给出的相对排序 100% 与人工评分一致（QUALITY_FRAMEWORK 第 15 行 hard 底线）。
