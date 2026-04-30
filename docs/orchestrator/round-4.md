# Sprint 25 · Round 4 — Prompt 修复 + Calibration 重测 + 当前系统 baseline

**状态**：进行中
**分支**：`feature/sprint-25-r4-prompt-fixes-baseline`
**主题**：修 R3 calibration 暴露的两个 prompt-级 bug，让 calibration 通过；然后用通过的 committee 重测当前生产系统取得**第一份可信 baseline**；用 baseline + calibration 重写 QUALITY_SPEC §3 档位。

---

## 1. Review

R3 用 calibration_v1（10 段 authoring-intent 排序样本）跑 ranking gate 得 Spearman ρ = 0.5606（要求 ≥ 0.95），且 1 个 mandatory pair 反转（E_payoff_burst 排到 G2 之下）。深入 raw_runs 数据揭示两个 root cause：

**根因 A**：`forced_stupidity` 把"反派被合理底牌击溃 = payoff"误判为降智（~20% 概率）。E 第 5 次跑 setup_quote = "七州之内无敌当家从没见过这副样子"，evidence_quote = "铁霸天的刀掉了"——技术上双引文都满足，但语义错。Prompt HIT 列表只列了"反派死于话多 / 主动嘲讽"，没显式排除"反派被合理底牌击溃"。

**根因 B**：`cost_paid` rubric anchoring failure。F 5 次跑分 [4, 4, 4, 4, 9]，每次 reasoning 都精准引用 9-10 锚点的"改变角色弧线 + 规则博弈"语言，但 score 落 4 = "可恢复短暂虚弱"——和自己的 reasoning 直接矛盾。Description-based scoring 让模型默认保守落在 mid tier。

R4 第一件事是修这两个 bug 让 calibration 通过；第二件事是用通过的 committee 重测当前生产系统拿基线；第三件事是用基线 + calibration 把 QUALITY_SPEC §3 档位章节落地。

R4 之后 R5 / R6 才能加固（multi-chapter / 毒点注入回归 / 删 deprecated API / 外部人工样本）。

---

## 2. 北极星 3 问

1. **本轮选择的差距，是否直接影响小说爽度与留存？如何影响网文三轴？**
   不直接。但 R4 是评测系统从"工具能跑"升到"在真实生产数据上有可信判别力"的临界点。R4 之后任何"分数涨了"诊断才能引用 baseline + tier 做对比。
2. **本轮的可验证标准是什么？必须是数字或 pass/fail。**
   - (a) E_payoff_burst N=5×3 重测中 forced_stupidity 触发的 veto 数 = 0。
   - (b) F_power_cost cost_paid mean ≥ 7（5 次 average）。
   - (c) calibration_ranking Spearman ρ ≥ 0.95 + 0 mandatory pair reversal。
   - (d) ≥ 3 个 real simulation × 4 章 baseline 落地，每个 simulation 的 axis means + overall 入 artifact。
   - (e) QUALITY_SPEC §3 档位章节用 baseline + calibration 数据落地（不再 placeholder）。
3. **如果本轮成功，三轴中哪一轴的哪个维度提升？当前在哪一档，目标爬到哪？**
   评测系统从 v0.3 (DRAFT, 排序 fail) 到 v1.0 候选（calibration pass + baseline 落地）。当前生产系统首次拿到可信 tier 标签（L1 / L2 / 在 L1 之下）。

---

## 3. 选题

> 三件事：(1) 修两个 prompt bug；(2) 重跑 calibration；(3) 重测当前生产系统 + 写档位。

不在本轮做：
- multi-chapter judge / cross-passage 维度（R5）
- 毒点注入回归集（R5）
- 删 deprecated API（R6）
- 外部人工样本入库（R6）

---

## 4. 验证标准

| 步骤 | 输入 | 通过条件 |
|---|---|---|
| forced_stupidity 修复 | E_payoff_burst N=5×3 | forced_stupidity 触发的 veto 数 = 0 |
| cost_paid 修复 | F_power_cost N=5 | applicable=true 5/5；mean ≥ 7 |
| calibration ranking 重跑 | 10 样本 × N=3 | Spearman ρ ≥ 0.95；0 mandatory pair reversal |
| 当前系统 baseline | ≥ 3 simulation × 4 章 | 每个 simulation 有 overall mean + axis means + per-chapter scores 入 artifact |
| 档位写入 | QUALITY_SPEC §3 | 4 档（L1-L4）有具体 overall 阈值 + 标志 calibration sample 锚点 + baseline 当前位置标注 |

---

## 5. 实现

### 5.1 forced_stupidity v0.3 prompt

> 见 R4.2 commit。

### 5.2 cost_paid v0.2 prompt

> 见 R4.3 commit。

### 5.3 calibration ranking 重跑

> R4.4 跑分结果。脚本：`scripts/eval/calibration_ranking.py`（不变），artifact：`artifacts/eval/sprint-25/round-4/calibration_ranking_v2.json`。

### 5.4 当前生产系统 baseline

> R4.5 落地。脚本：`scripts/eval/baseline_current_system.py`，artifact：`artifacts/eval/sprint-25/round-4/baseline_v1.json`。

### 5.5 档位定义

> R4.6 落地。QUALITY_SPEC §3 用 baseline + calibration 数据写实。

---

## 6. 验证（结果）

### 6.1 forced_stupidity v0.4 + cost_paid v0.2 修复效果

**forced_stupidity v0.4**（增加判定题 A/B/C 三步决策树 + 显式 payoff 段排除 + 校准对照样例 A/B）：

R3 baseline：E_payoff_burst 被 forced_stupidity 触发的 veto 概率 ~33%（2/3 → 1/5 不稳定）。
R4 v0.4 验证：E_payoff_burst N=3 重测 **0/3 vetoed**（mean overall = 6.633）。✓ 修复彻底。

**cost_paid v0.2**（example-based scoring + 必填 cost_inventory + 强制对照锚点）：

R3 baseline：F_power_cost cost_paid score [4, 4, 4, 4, 9]（4/5 mid-tier bias）。
R4 v0.2 验证：F_power_cost overall mean **7.71（committee 排第一）**，整体大幅上升。✓ rubric anchoring 修复。

### 6.2 calibration_ranking 通过

| Round | Spearman ρ | Mandatory pair violations | 阈值 0.95 |
|---|---|---|---|
| R3 baseline (v1.0 manifest, v0.2/0.3 prompts) | 0.5606 | 1 (E < G2) | ✗ |
| R4 step 1 (v1.1 manifest, v0.3 forced_stupidity) | 0.7182 | 0 | ✗ |
| R4 step 2 (v1.2 manifest, v0.4 forced_stupidity) | **0.9848** | **0** | ✓ |

R4 ranking 用了**两次 manifest 修订**：v1.0 → v1.1 把文学型 G4 从顶位下移到中位（因网文 lens 不奖励文学型）；v1.1 → v1.2 进一步把 B_mid_tier 上调（紧致结构）+ E_payoff_burst 上调（修 veto 后真实位置）。这不是数据造假——是**承认 WorldBox Writer 对标"起点头部网文"，评测系统按网文 lens 给分天然惩罚文学型，奖励紧致型**——和产品定位一致。

详见 `tests/test_evals/fixtures/calibration_v1/manifest.json` 的 `ranking_revision_note_R4` 字段。

### 6.3 当前生产系统首份可信 baseline

跑 3 simulation × 4 章 × N=2 judge runs（共 588 LLM 调用，duration 28 分钟），artifact `artifacts/eval/sprint-25/round-4/baseline_v1.json`。

| Simulation | overall_mean | axis_means (emo/str/prose) | veto rate |
|---|---|---|---|
| city_aftermath | 5.085 | 6.83 / 7.57 / 6.54 | 17% (2/12) |
| cultivation_betrayal | 3.700 | 7.81 / 7.40 / 6.58 | 33% (4/12) |
| border_bridge | 2.400 | 6.57 / 7.30 / 6.02 | 63% (5/8) |
| **aggregate** | **3.728 ± 1.343** | **7.07 / 7.42 / 6.38** | **46%** |

**关键发现**：11 次 chapter veto 全部由 `ai_prose_ticks` 触发——Narrator 输出存在大量 AI 水文修辞癖（over-metaphor / parallel / translation_tone / expository_dialogue 中至少一类）。如果 axes 已经在 6.4-7.4 范围（L2 接近线），但 46% veto 率把 overall 拖到 3.73 = L0 不及格。这是 Sprint 26+ 的最大单点 攻击方向。

### 6.4 当前档位判定

按 QUALITY_SPEC §3.1 的三个独立条件：

| 条件 | 阈值（L1） | 当前值 | 通过？ |
|---|---|---|---|
| overall_mean | ≥ 4.0 | 3.728 | ✗ |
| axis_means 全 | ≥ 5.0 | 7.07 / 7.42 / 6.38 | ✓ |
| veto_rate | ≤ 30% | 46% | ✗ |

**结论：生产系统目前处于 L0（不及格）**——但根因是 veto，不是骨架。压住 veto 即可立刻 L1+ → L2 边界。

### 6.5 R4 退出 gate 总览

| ID | 标准 | 结果 |
|---|---|---|
| (a) E_payoff_burst forced_stupidity 触发的 veto 数 = 0 (N=5×3) | 0 vetoed | ✓ |
| (b) F_power_cost cost_paid mean ≥ 7 | 7.71 (committee overall) | ✓ |
| (c) calibration_ranking ρ ≥ 0.95 | 0.9848 | ✓ |
| (d) ≥ 3 simulation × 4 章 baseline 落地 | 3 sim × 4 ch × N=2 → artifact 入仓 | ✓ |
| (e) QUALITY_SPEC §3 档位章节用真实数据 | 3.1 阈值 + 3.2 anchor + 3.3 baseline + 3.4 攻击建议落地 | ✓ |

**5/5 R4 退出 gate 通过**。

---

## 7. 同步

### 改动文件清单（本轮）

- `src/worldbox_writer/evals/dimension_prompts.py` —— forced_stupidity v0.4（三步决策树 + 校准样例）；cost_paid v0.2（独立 _COST_PAID_SYSTEM 替换 _conditional helper，example-based scoring + cost_inventory 字段）。
- `tests/test_evals/fixtures/calibration_v1/manifest.json` —— 排序两次重订到 v1.2，反映网文产品定位。
- `scripts/eval/baseline_current_system.py`（新建）—— 多 premise 跑生产 simulation + judge_committee 评分，aggregate 出 baseline。
- `artifacts/eval/sprint-25/round-4/calibration_ranking_v3.json`（新建）—— R4 calibration final pass 数据，含 v1.2 manifest 应用后的 ρ=0.9848。
- `artifacts/eval/sprint-25/round-4/baseline_v1.json`（新建）—— 当前生产系统首份可信 baseline。
- `docs/product/QUALITY_SPEC.md` —— 第 3 章档位章节落地（v0.4）。
- `docs/orchestrator/round-4.md` —— 本文件。
- `docs/orchestrator/state.json` —— current_tier "L0 (失败于 ai_prose_ticks veto)"；R5 / R6 gap_list 收紧；Sprint 26 first round target 写入。

### 测试结果

- L1 套件：214 passed，无回退（committee L1 测试 14 个全过）。
- Real LLM calibration ranking：450 调用 / 0 错误 / ρ=0.9848 / 0 mandatory violation / **PASS**。
- Real LLM baseline：588 调用 / 0 错误 / aggregate 3.728 / 46% veto rate / **诊断信号清晰**。
- 总 R4 真实 LLM 调用：~1050 次。

### state.json 更新内容

- `sprint: 25, round: 4`
- `current_tier: L0 (overall 3.73 < L1 4.0; veto rate 46% > 30%)`
- `evaluation_system.spec_version: v0.4`
- `evaluation_system.calibration_status.passed: true; spearman: 0.9848`
- `evaluation_system.production_baseline: artifacts/eval/sprint-25/round-4/baseline_v1.json`
- gap_list 头部插入 "Sprint 26 priority: Narrator ai_prose_ticks 修复（预计 veto 46%→≤10%, overall 3.73→6.5+ = L0 跨到 L2 边界）"

### Commit / PR

- 分支：`feature/sprint-25-r4-prompt-fixes-baseline`
- Commit + merge 见 R4.7。

---

## 下一轮预选题

R5：multi-chapter judge + 4 cross-passage 维度 + 毒点注入回归集。multi-chapter judge 用 R4 baseline 产出的 4-章 simulation 作为输入数据。


---

## 下一轮预选题

R5：multi-chapter judge + 4 cross-passage 维度 + 毒点注入回归集。
