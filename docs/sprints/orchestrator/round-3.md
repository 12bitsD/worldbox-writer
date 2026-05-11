# Sprint 25 · Round 3 — Cleanup + Calibration Anchor 入库

**状态**：进行中
**分支**：`feature/sprint-25-r3-calibration-cleanup`
**主题**：把评测系统从"工具能跑"升级到"工具被外部基准锚定"。落地 calibration anchor 入库 + 排序一致性验证 + 旧文档合并 + schema 自动校验，是 Sprint 25 内第一个 cleanup round。

---

## 1. Review

R2 实测：committee API 在 A/B/C 三样本上 5/5 redesigned exit gates 通过；A 5/5 不 vetoed (overall 8.23 ± 0.119)，C 5/5 全 vetoed，B 4/5 ~6.6 ± 0.144。这意味着委员会在三种"刻意写出的"质量水平上能稳定打出可区分的分数。

但这里有一条**自指风险**：A/B/C 是我（Claude）按 head/mid/AI-water 的特征写的；委员会判官也是 Claude。如果委员会得分跟"我自己写时打的标签"一致，可能只是因为同一个模型对自己的 fingerprint 高度敏感，而不是真的捕捉到通用的网文质量信号。

R3 是这个问题的第一道防线：**用更广的样本谱 + authoring-intent 排序 + 自动 schema 校验**逼委员会在多样本上保持判别力。同时把 R2 暴露的两个细节问题（forced_stupidity 偶尔 applicable=true score=null / evidence_quote 没有真实性约束）修掉。

---

## 2. 北极星 3 问

1. **本轮选择的差距，是否直接影响小说爽度与留存？如何影响网文三轴？**
   不直接。R3 仍是元层。但若 calibration ranking 失败，意味着 R2 的"5/5 gates 通过"是窄样本上的过拟合，那 R4 重测当前生产系统拿到的 baseline 就不可信。这是 R3 必须先把住的关卡。
2. **本轮的可验证标准是什么？必须是数字或 pass/fail。**
   - (a) calibration_v1 至少 8 段样本入库，含 quality_label 排序与 expected_signals。
   - (b) judge_committee overall 在 calibration_v1 上的 Spearman rank correlation vs authoring-intent ≥ 0.95。
   - (c) 任意一对"authoring-intent A 应高于 B"的对比对在 committee 上反转 → 直接 fail。
   - (d) forced_stupidity schema 偏差通过 parser coercion 修掉；L1 测试覆盖。
   - (e) evidence_quote 自动子串校验上线；fabricated 引用被识别。
   - (f) 4 个 inconclusive/边界 dim 的触发样本上 applicability 行为正确。
   - (g) 旧文档（WEB_NOVEL_CRITERIA / QUALITY_FRAMEWORK / SPRINT_24）收敛为索引页或归档。
3. **如果本轮成功，三轴中哪一轴的哪个维度提升？当前在哪一档，目标爬到哪？**
   不是单 dim 提升。R3 把评测系统从"窄样本上稳"拓宽到"多样本上有可信判别力"。档位仍由 R4 决定。

---

## 3. 选题

> 三件事：(1) 写更多样本入库 + 排序验证；(2) 修两个 R2 schema 偏差；(3) 文档合并清理。

不在本轮做：
- 重测当前生产系统（R4）
- multi-chapter judge 与 cross-passage 维度（R5）
- 毒点注入回归集（R5）
- 删除 deprecation shim 旧 judge_prose / judge_story / etc.（R6）

---

## 4. 验证标准

| 步骤 | 输入 | 通过条件 |
|---|---|---|
| Calibration v1 | 11 段样本（A/B/C 已有 + 8 新） | manifest.json 含 quality_label 排序、expected_signals |
| Schema 修复 L1 | mock chat_completion 输出非法 JSON / 假 evidence | parser 正确降级 / coerce / 标错 |
| Real LLM ranking | judge_committee 在 calibration_v1 全集上 N=3 取均值 | Spearman ρ ≥ 0.95；无 mandatory ordering 反转 |
| 触发维度验证 | D/E/F 样本 × 5 次 | applicability 行为如 expected_signals |
| 文档合并 | 合并后跑 `make lint` + L1 套件 | 无回退；test_sprints_directory 通过 |

---

## 5. 实现

（R3.2-R3.8 增量更新此小节。）

### 5.1 calibration_v1 样本设计

> 见 R3.2 commit。

### 5.2 forced_stupidity schema 修复

> 见 R3.3 commit。

### 5.3 evidence_quote 子串校验

> 见 R3.4 commit。

### 5.4 旧文档合并

落地：
- `docs/product/WEB_NOVEL_CRITERIA.md` 改为指向 QUALITY_SPEC.md 的索引页
- `docs/product/QUALITY_FRAMEWORK.md` 改为指向 QUALITY_SPEC.md 的索引页
- 删除 `docs/sprints/SPRINT_24.md`（内容已被代码与新 spec 吸收）
- 同步：`CLAUDE.md` / `README.md` / `docs/README.md` / `docs/architecture/DESIGN.md` / `docs/orchestrator/README.md` / `src/worldbox_writer/evals/llm_judge.py` 的引用
- `tests/test_docs/test_sprints_directory.py` 白名单去掉 SPRINT_24

### 5.5 Real-LLM 排序验证

脚本：`scripts/eval/calibration_ranking.py`
artifact：`artifacts/eval/sprint-25/round-3/calibration_ranking.json`

10 样本 × 3 次 = 30 committee calls = 450 次底层 LLM 调用，耗时 982 s（16 分钟）。

**结果（详见 6.1）**：Spearman ρ = 0.5606，远低于 0.95 阈值；1 个 mandatory pair 反转（E_payoff_burst 排在 G2_tier2_midcommon 之下）。

### 5.6 触发维度验证

脚本：`scripts/eval/conditional_triggers.py`
artifact：`artifacts/eval/sprint-25/round-3/conditional_triggers.json`

5 样本 × 5 次 = 25 committee calls = 375 次底层 LLM 调用，耗时 868 s（14 分钟）。

**结果（详见 6.2）**：4/5 触发 gate 通过，1/5（F cost_paid）失败但失败原因揭示了一个新的 prompt rubric 缺陷。

---

## 6. 验证（结果）

### 6.1 Calibration ranking 失败的诚实读数

| Authoring intent rank | Sample | Committee mean | Committee rank | Δ |
|---|---|---|---|---|
| 1 | G4_tier4_topshelf | 6.157 | 5 | -4 |
| 2 | F_power_cost | 7.183 | 3 | +1 |
| 3 | E_payoff_burst | **2.133 (vetoed 2/3)** | **8** | **-5** |
| 4 | G3_tier3_solid | 7.357 | 2 | +2 |
| 5 | A_head_tier | 7.613 | 1 | +4 |
| 6 | D_mid_arc | 5.633 | 6 | 0 |
| 7 | B_mid_tier | 6.357 | 4 | +3 |
| 8 | G2_tier2_midcommon | 4.213 | 7 | +1 |
| 9 | C_ai_water | 0.0 (vetoed 3/3) | 9 | 0 |
| 10 | G1_tier1_severe | 0.0 (vetoed 3/3) | 10 | 0 |

**Spearman ρ = 0.5606**（要求 ≥ 0.95，**FAIL**）
**Mandatory pair violation**: `E_payoff_burst (2.133) < G2_tier2_midcommon (4.213)` ——爆发瞬间样本被打得低于普通中位样本。**FAIL**。

### 6.2 Conditional triggers 数据

| Sample | Target dim | Result | Pass |
|---|---|---|---|
| D_mid_arc | golden_start_density | applicable=false 4/5 | ✓ |
| E_payoff_burst | payoff_intensity | applicable=true 5/5, mean **8.4** | ✓ |
| F_power_cost | cost_paid | applicable=true 5/5, mean **5.0** (要求 ≥ 7) | ✗ |
| G4_tier4_topshelf | forced_stupidity 不误判 | applicable=false 5/5 | ✓ |
| G3_tier3_solid | forced_stupidity 不误判 | applicable=false 5/5 | ✓ |

**Critical 观察**：E 单独看 payoff_intensity 维度时 5/5 拿 8-9 分（完美触发），但在 calibration_ranking 整体跑里被 vetoed 2/3 次。说明 veto 不是来自 payoff 维度——是另一个维度误触发。

### 6.3 根因 1：forced_stupidity 把"反派合理崩溃"误判为降智

E 在 R3.7 第 5 次跑（5/5）被 vetoed，触发维度 = `forced_stupidity` score=9.0：

```
setup_quote: 他这辈子见过他们这位"七州之内无敌"的当家发怒、发狠、杀人，从没见过他这副样子
evidence_quote: 铁霸天的刀掉了
```

技术上 setup + evidence 双引文都满足 prompt 要求；但**语义错了**：
- 这段是主角揭底（一枚带白头发的铜钱 = 他遗孀的遗物）后反派合理崩溃
- 这是 payoff 段的标准结构——"反派被铺垫好的底牌击溃"
- prompt 的 forced_stupidity HIT 样例只列了"反派死于话多 / 主动嘲讽"，没有显式排除"反派被合理底牌击溃"

**这个误判概率 ~20%**（R3.6 是 2/3，R3.7 是 1/5）。它导致 calibration ranking 直接 fail：E 整体 mean 被 0 分稀释到 2.133。

### 6.4 根因 2：cost_paid rubric anchoring 失败

F 5 次跑分 [4, 4, 4, 4, 9]，4/5 给 4。但每次 reasoning 都精准命中 prompt 9-10 锚点的描述：

```
"每解一道封即对应不可逆身体损伤：左眼失明、三指瘫痪、舌根麻木、寿命骤减"
"代价与力量构成清晰规则博弈，且改变角色弧线"
```

prompt 9-10 anchor 原文：

```
9-10：代价惨烈到改变角色弧线；力量与代价构成清晰规则博弈
```

reasoning 里逐字命中"改变角色弧线 + 规则博弈"，但 score 落在 4 = "有代价但可恢复（短暂虚弱）"——和 reasoning **直接矛盾**。

**这是 rubric anchoring failure**：模型识别了所有正确信号但默认输出 4-6 mid tier 分。可能是评测模型对"打高分"有保守偏置。R4 prompt 修复方向：要么在 anchor 加"匹配 9-10 描述就必须给 9-10"的元规则，要么用 example-based scoring 而不是 description-based。

### 6.5 R3 的总结性判断

R3 设计目标是 "calibration anchor 入库 + 排序验证 + cleanup"。退出条件 (a)-(g) 中：

| ID | 标准 | 结果 |
|---|---|---|
| (a) calibration_v1 ≥ 8 段入库 | 10 段入库 | **✓** |
| (b) Spearman ρ ≥ 0.95 | ρ = 0.5606 | **✗** |
| (c) mandatory pairs 不反转 | 1 反转（E < G2） | **✗** |
| (d) forced_stupidity schema 偏差通过 coercion 修 | applicable=true score=null 自动 coerce 到 false（L1 测试覆盖） | **✓** |
| (e) evidence_quote 子串校验上线 | 假引用降分到 4，curly→straight 引号正常化（L1 测试覆盖） | **✓** |
| (f) 4 个 inconclusive/边界 dim 触发样本上 applicability 行为正确 | 5/5 中 4 通过；F cost_paid 失败但揭示 rubric anchoring 缺陷 | **部分 ✓** |
| (g) 旧文档收敛为索引页 | 完成 | **✓** |

**R3 的诚实状态**：
- 工程交付物（cleanup + schema fixes + 样本集 + 校验脚本）全部落地。
- **排序一致性 gate 失败，且失败信号有强诊断价值**——揭示了评测系统两个 prompt 级 bug（forced_stupidity reactive-villain 混淆 / cost_paid rubric anchoring）。
- 这是 R3 的最大价值：在 R4 用 committee 重测当前生产系统**之前**，把 committee 的盲区暴露出来。如果直接 re-baseline，旧 7.5 baseline 会被这两个 bug 系统性低估或扭曲。

不调阈值。R3 通过 partial（cleanup 完成 + 揭示问题），R4 第一件事是修这两个 prompt 再 re-baseline。

### 6.6 cleanup round 元层自检

按 Sprint 25 spec 定义，cleanup round 应该回答"是不是真清理了 stale，还是只产出了更多东西？"

本轮删除/清理：
- 删除 `SPRINT_24.md`（已归档）
- `WEB_NOVEL_CRITERIA.md` / `QUALITY_FRAMEWORK.md` 内容删除，改为单页索引
- llm_judge.py docstring 更新指向 QUALITY_SPEC.md
- 5 处文档引用从旧名指向新 spec

本轮新增：
- `calibration_v1/` 10 段样本 + manifest
- `dimension_prompts.py` forced_stupidity v0.2 prompt（更严）
- `llm_judge.py` 新增 _evidence_in_text / coercion 逻辑（必要新增）
- 2 个 eval runner 脚本（calibration_ranking + conditional_triggers）
- 2 个 artifact JSON
- 5 个 L1 测试

新增 / 删除 = 大致 1:0.5。新增的全是评测基建，不是临时性产出，符合 cleanup 定位。

---

## 7. 同步

### 改动文件清单（本轮）

- `docs/sprints/SPRINT_24.md` —— 删除（已归档）
- `docs/sprints/README.md` —— 移除 SPRINT_24 引用
- `tests/test_docs/test_sprints_directory.py` —— 白名单去掉 SPRINT_24
- `docs/product/WEB_NOVEL_CRITERIA.md` —— 改为指向 QUALITY_SPEC 的索引页
- `docs/product/QUALITY_FRAMEWORK.md` —— 改为指向 QUALITY_SPEC 的索引页
- `docs/product/QUALITY_SPEC.md` —— 第 4 章 calibration anchors 落地（v0.3）
- `CLAUDE.md` / `README.md` / `docs/README.md` / `docs/architecture/DESIGN.md` / `docs/orchestrator/README.md` —— 引用更新
- `src/worldbox_writer/evals/llm_judge.py` —— docstring 更新；`_evidence_in_text` / `_QUOTE_NORMALIZATION` / `_committee_call_one` 加 coercion 与子串校验逻辑
- `src/worldbox_writer/evals/dimension_prompts.py` —— forced_stupidity v0.2 prompt 强化（HARD RULES 重写）
- `tests/test_evals/test_committee.py` —— 新增 5 个 R3 schema-fix 测试（共 14 → 14 个，原 9 个调整）
- `tests/test_evals/fixtures/calibration_v1/{10 .txt files + manifest.json}` —— 新建
- `scripts/eval/calibration_ranking.py` / `scripts/eval/conditional_triggers.py` —— 新建
- `artifacts/eval/sprint-25/round-3/calibration_ranking.json` / `conditional_triggers.json` —— 新建
- `docs/orchestrator/round-3.md` —— 本文件
- `docs/orchestrator/state.json` —— 更新

### 测试结果

- L1 套件：214 passed / 57 deselected（无回退）。
- Real LLM calibration_ranking：450 次调用 / 0 错误 / Spearman 0.56 / 1 mandatory pair 反转 → **fail**。
- Real LLM conditional_triggers：375 次调用 / 0 错误 / 4/5 trigger 通过；F cost_paid 失败揭示 rubric anchoring 缺陷。

### state.json 更新内容（本轮）

- `sprint: 25, round: 3`
- `last_round_goal: "Cleanup round + calibration anchor 入库"`
- `last_round_action: "Sprint 25 R3 完成 partial — calibration_v1 (10 段) + schema 修复 + 旧文档合并；ranking gate fail (ρ=0.56)，但失败信号揭示 forced_stupidity 反派合理崩溃误判 + cost_paid rubric anchoring 两个 R4 必修 bug"`
- `evaluation_system.spec_version: v0.3`
- 新增 `evaluation_system.calibration_set: tests/test_evals/fixtures/calibration_v1/`
- gap_list 顶部插入两个 R4 必修项

### Commit / PR

- 分支：`feature/sprint-25-r3-calibration-cleanup`
- Commit + merge 见 R3.8。

---

## 下一轮预选题

R4 的优先级被 R3 数据**重新排序**：

1. **修 forced_stupidity prompt**：在 NOT-HIT 列表加"反派被合理底牌击溃 = payoff 段，不算降智"+ 反例对照样例。验证：E_payoff_burst 在 N=5 × 3 重测中 0 vetoed 由 forced_stupidity 触发。
2. **修 cost_paid prompt（或 anchor 设计）**：让 reasoning 命中 9-10 锚点描述时模型不再保守落在 4-6。可能需要 example-based scoring 替换 description-based。验证：F_power_cost mean ≥ 7。
3. **重跑 calibration_ranking**：Spearman ρ ≥ 0.95 + 0 mandatory pair reversal。
4. **再去 re-baseline 当前生产系统**（原 R4 主任务）。

如果 R4 prompt 修复后排序仍不达标，认真考虑：
- 评测系统是否对 网文紧致风格（A/G3）过度奖励 / 对 文学型（G4）过度惩罚？
- 是否需要在 spec 中加"文学型 head-tier"分类，与"网文紧致 head-tier"并列评测？

R3 的最重要 deliverable 是这份"评测系统的诚实自照"。

## 下一轮预选题

R4：用 R2 落地的 judge_committee + R3 落地的 calibration anchor 重测当前生产系统。跑 ≥ 3 个真实 simulation × 4 章；新基线写入 state.json；用基线 + calibration 重写 QUALITY_SPEC §3 档位章节（用相对盲测胜率 + calibration 排序一致性，不用旧的"全部维度 ≥ 阈值"绝对分）。
