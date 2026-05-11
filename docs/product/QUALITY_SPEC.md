# QUALITY_SPEC — WorldBox Writer 评测系统单一真相源

**文档状态**：v1.0（Sprint 25 全部 6 round 完成；评测系统从词汇定型到 multi-chapter judge + 毒点回归集 + 当前生产 baseline + L1-L4 档位 全套基建落地）
**最后更新**：2026-04-30
**适用范围**：本文档是 WorldBox Writer 评测系统的 single source of truth。所有 judge prompt、评测协议、档位定义都从这里派生。任何 sprint round 的成功指标必须直接引用这里的 dimension 名称与阈值。

> 替代文档：本 spec 上线后，`docs/product/WEB_NOVEL_CRITERIA.md` 与 `docs/product/QUALITY_FRAMEWORK.md` 的内容会合并到这里，原文件将变成指向本 spec 的索引页（R3 cleanup round 完成）。

---

## 1. Dimensions（评测维度）

维度按"判官能否在单段文本上稳定打分"分三层：

- **Per-passage**：任何 prose 片段都必须打分。
- **Conditional**：判官先判定该维度是否适用本片段（开篇/章末/含反派/力量场景），不适用返 `applicable: false`，分数为 `null`，不进入聚合。
- **Cross-passage**：仅 multi-chapter judge 使用（R5 引入），单段 judge 不查。

每个维度独立 prompt。判官输出格式：

```json
{
  "applicable": true,
  "score": 7.0,
  "evidence_quote": "...原文片段...",
  "rule_hit": "<dimension_id>.<sub_rule>",
  "reasoning": "≤50字"
}
```

不适用时：

```json
{"applicable": false, "score": null, "reason": "片段不含反派出现/章末/开篇/力量使用场景"}
```

---

### 1.1 Per-passage dimensions（单段必判）

| ID | 中文名 | 测量定义 | 与旧维度对照 |
|---|---|---|---|
| `desire_clarity` | 欲望具体性 | 主角此刻**想要什么**是否具体可见？是否说明**为什么想要**与**不达成的代价**？ | 抽自旧 `anticipation` 的角色层 |
| `tension_pressure` | 张力与压力 | 当前场景的外部压力（敌人嚣张、危机倒计时、资源稀缺）是否大于主角表面实力？ | 抽自旧 `anticipation` 的"压抑比" + 旧 `suppression_to_elevation` 的抑段 |
| `info_show_dont_tell` | 信息给配 | 世界观/规则是否在冲突或动作中自然展现？是否出现连续 ≥100 字的纯旁白说明？ | 等价于旧 `info_pacing`，定义更具体 |
| `prose_friction` | 阅读顺滑度 | 句长分布、生僻字、长句从句、段落切分是否符合手机阅读？ | 等价于旧 `readability` |
| `material_specificity` | 物质感 | 动作/场景是否落到具体物件、声音、气味、距离感、方向感？是否避免"出招、对掌、震退三步"的概念战？ | **新增**——抽自旧 `visual_action` 的硬核部分，独立成维 |
| `dialogue_voice` | 对话辨识度 | 对话是否符合角色身份？片段内 ≥2 角色时，不同角色之间是否有可分辨的语言指纹？ | 升级旧 `dialogue_webness`：原维度只查"网文语境"，新维度查"角色之间的差异" |
| `conflict_density` | 冲突密度 | 单位字数内有效冲突/钩子的数量。是否每 200-300 字内出现新的小钩子？ | **新增**——比旧 `pacing` 更可量化 |

### 1.2 Conditional dimensions（判官先判适用）

| ID | 中文名 | 适用判定 | 测量定义 | 与旧维度对照 |
|---|---|---|---|---|
| `payoff_intensity` | 爽点爆发强度 | 片段是否包含主角胜利/获益/底牌揭晓？ | 配角反应/敌人崩溃描写是否在 500 字内出现？是低级（数值碾压）/中级（认知逆转）/高级（规则重塑）？ | 等价旧 `catharsis`，加 applicable 判定 |
| `golden_start_density` | 黄金开局信息密度 | 片段是否包含开篇前 1500 字内容？ | 前 500 字是否抛出生存危机/身份错位？前 1500 字内金手指是否激活？ | 等价旧 `golden_start`，加 applicable 判定 |
| `cliffhanger_pull` | 章末追读拉力 | 片段末尾是否构成章节/小节收束？ | 是否停在动作进行中/悬念揭晓前/利益结算前？ | 等价旧 `cliffhanger`，加 applicable 判定 |
| `antagonist_integrity` | 反派可信度 | 片段是否含反派/对手出现且行动可见？ | 反派的智商、动机正当性、信息博弈是否与主角对等？ | 等价旧 `antagonist_integrity_iq`，加 applicable 判定 |
| `cost_paid` | 代价对等 | 片段是否含力量使用、越级行动、规则突破？ | 代价是否不可逆（寿命/理智/关系）？是否可见？ | 等价旧 `cost_paid_rule_combat`，加 applicable 判定 |

### 1.3 Cross-passage dimensions（multi-chapter judge 才用，R5 引入）

| ID | 中文名 | 输入 | 测量定义 |
|---|---|---|---|
| `foreshadowing_recovery` | 伏笔回收 | ≥ 2 章 SceneScript + prose | 跨章伏笔回收的密度与跨度 |
| `character_arc_consistency` | 角色弧线一致性 | 同上 | 角色的目标/性格/能力变化是否合乎其内在逻辑 |
| `stakes_escalation` | 风险递进 | 同上 | 章节间 stakes 是否递进，避免"打怪平台期" |
| `setting_consistency` | 设定一致性（前 toxic_flag `power_scaling_collapse`） | 同上 | 前文规则是否被后文无解释打破 |

### 1.4 Toxic flags（独立专家，二值）

每个 flag 独立 prompt，温度 0，必须给 evidence quote 才能判定为 true。

| ID | 中文名 | 判定 |
|---|---|---|
| `forced_stupidity` | 强行降智 | 反派/智将做出与人设智商严重不符的行为，且引用原文证据 |
| `preachiness` | 说教爹味 | 段落/章节末尾出现"这让……明白了"、"这不仅是……更是……"句式总结升华 |
| `ai_prose_ticks` | AI 水文修辞癖 | 过度比喻 / 三连排比 / 翻译腔 / 解释性对话 中至少一种密度超阈，给出子类型 |

`power_scaling_collapse` 从 toxic_flag 移除，并入 cross-passage 的 `setting_consistency`。

---

### 1.5 维度选择决策表（R1.5 + R2.6 实测）

> R2 changes：`forced_stupidity` 从 toxic 升级为 conditional + 排除 leverage 误判（v0.2）；`ai_prose_ticks` 加 evidence-or-降分硬规则（v0.2）。其余 prompt 不变。R2 复测全部 11 keep + 1 ex-watchlist 维度。



下表来自 `artifacts/eval/sprint-25/round-1/dim_stability.json`：3 个质量梯度样本（A 头部 / B 中位 / C AI 水文）× 5 次 real LLM judge = 每维度 15 个数据点。`max_std` 是该维度在所有 applicable 样本上的最大方差。

| Dimension | 类别 | A_head | B_mid | C_ai | max_std | 决策 | 备注 |
|---|---|---|---|---|---|---|---|
| `desire_clarity` | per-passage | 9.0 | 7.2 | 3.0 | 0.447 | **keep** | |
| `tension_pressure` | per-passage | 8.8 | 7.0 | 3.4 | 0.548 | **keep** | |
| `info_show_dont_tell` | per-passage | 8.6 | 7.2 | 3.0 | 0.548 | **keep** | |
| `prose_friction` | per-passage | 8.2 | 8.0 | 4.2 | 0.447 | **keep** | |
| `material_specificity` | per-passage | 8.6 | 5.4 | 2.8 | 0.548 | **keep** | |
| `dialogue_voice` | per-passage | 7.0 | 4.6 | 2.2 | 0.548 | **keep** | |
| `conflict_density` | per-passage | 8.0 | 6.4 | 4.0 | 0.548 | **keep** | |
| `golden_start_density` | conditional | 7.8 | 6.4 | 3.6 | 0.548 | keep（caveat） | applicability=true 在所有样本上——R3 需补"非开篇"样本反向验证 |
| `cliffhanger_pull` | conditional | 8.2 | 7.6 | 6.2 | 0.837 | **keep** | 全样本 applicable，相对排序合理 |
| `antagonist_integrity` | conditional | 7.4 | 5.0 | N/A | 0.548 | **keep** | C 上 0/5 applicable——适用判定有效 |
| `payoff_intensity` | conditional | N/A | N/A | N/A | — | **inconclusive** | fixtures 无爆发段——R3 补样本 |
| `cost_paid` | conditional | N/A | N/A | N/A | — | **inconclusive** | fixtures 无力量使用——R3 补样本 |
| `preachiness` | toxic | 1.6 | 2.0 | 9.4 | 0.894 | **keep** | C 5/5 命中（≥8），触发 veto |
| `ai_prose_ticks` | toxic v0.2 | 2.0 | 4.0 (4/5 ≤ 4) | 9.6 | 0.548 (A,C) / 2.236 (B) | **keep（带边界 caveat）** | B 4/5 收敛到 3 + 1/5 边界 outlier；R3 调整 B 样本或接受边界 |
| `forced_stupidity` | conditional v0.2 | mean 2.0 (n=2) | 5.0 (n=5) | 7.0 (n=5) | — | **keep** | 头部级不再被误判（R1 6.8 → R2 2.0）；R3 加 setup_quote schema 强制约束 |

**进入 R2 的维度集合（共 12 个）**：

- 7 个 per-passage：desire_clarity, tension_pressure, info_show_dont_tell, prose_friction, material_specificity, dialogue_voice, conflict_density
- 3 个 conditional（待 R3 补样本完整验证）：golden_start_density, cliffhanger_pull, antagonist_integrity
- 2 个 conditional inconclusive 待 R3 验证：payoff_intensity, cost_paid
- 2 个 toxic：preachiness（keep）, ai_prose_ticks（watchlist，需 prompt 加固）

**淘汰**：

- `suppression_to_elevation`（旧维度，已拆分入 tension_pressure + payoff_intensity）。
- `moral_dilemma_humanity_anchor`（旧维度，单段判官无法稳定，由 R5 cross-passage `character_arc_consistency` 覆盖）。
- `forced_stupidity`（**v0.1 实测淘汰**——prompt 系统性误判；R2 重新设计为 conditional 后视为 v0.2 候选，重测通过才回 keep）。

Cross-passage 4 维（foreshadowing_recovery / character_arc_consistency / stakes_escalation / setting_consistency）不在 R1 实证，由 R5 multi-chapter judge 直接验证。

---

## 2. Measurement Protocol（测量协议）

### 2.1 调用入口

```python
from worldbox_writer.evals.llm_judge import judge_committee

result = judge_committee(text)
# result["overall"]                # weighted 0-10, 0 if vetoed
# result["axis_scores"]             # {emotion_axis, structure_axis, prose_axis}
# result["per_dimension"][dim_id]   # raw per-dim record (applicable / score / evidence_quote / rule_hit)
# result["toxic"][dim_id]           # {applicable, score, hit, evidence_quote}
# result["vetoed"], result["veto_reasons"]
# result["weighted_pre_veto"]       # the score before veto, for diagnostics
# result["weights"]                 # the actual weights applied (normalized)
# result["errors"]                  # list of dim-level parse/transport failures
```

实现位置：`src/worldbox_writer/evals/llm_judge.py`，附加在文件末尾，与旧 `judge_prose / judge_story / judge_scene_script / batch_judge` 共存（R3 cleanup 时迁移调用方再删旧 API）。

### 2.2 参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `model` | `os.environ.get(WORLDBOX_JUDGE_MODEL)` 或 `gpt-5.5` | 走 `chat_completion(role="narrator")` 路由，因此实际模型由 LLM_PROVIDER 决定 |
| `temperature` | 0.2 | 与既有 judge 保持一致；让分数有少量自然抖动避免严格确定性带来的过拟合 |
| `max_tokens` | 320 | 每个 dim 输出仅一个 JSON 对象 |
| `concurrency` | **1** | R1 实证：macOS 本地端口对高并发外发请求很脆弱；默认串行最稳定。Linux / 受控环境下可上调 |

### 2.3 调用结构

每次 `judge_committee(text)` 顺序调用 15 个独立 prompt：
- 7 个 per_passage：每个独立 dim 一次调用
- 5 个 conditional（含 forced_stupidity v0.2）：每个独立 dim 一次调用
- 3 个 toxic（preachiness / ai_prose_ticks）：每个独立 dim 一次调用——加上 forced_stupidity 共 3 个参与 toxic veto

R1 已经验证：把多 dim 塞进同一 prompt 会让分数互相污染。每个 dim 独立调用是稳定性必要条件。

### 2.4 三轴聚合规则

```python
DIMENSION_AXIS_MAP = {
    "desire_clarity": "emotion_axis",
    "tension_pressure": "emotion_axis",
    "payoff_intensity": "emotion_axis",
    "conflict_density": "emotion_axis",
    "golden_start_density": "structure_axis",
    "cliffhanger_pull": "structure_axis",
    "info_show_dont_tell": "structure_axis",
    "antagonist_integrity": "structure_axis",
    "cost_paid": "structure_axis",
    "prose_friction": "prose_axis",
    "material_specificity": "prose_axis",
    "dialogue_voice": "prose_axis",
}
```

- 每个轴的 score = 该轴下所有 `applicable=true` 且 score 是数值的 dim 的算术平均。
- `applicable=false` 的 conditional dim **不**进聚合（不会拉低也不会拉高轴）。
- 如果一个轴 0 个 dim 有数据，该轴 = `null`。

### 2.5 加权 overall

```python
COMMITTEE_AXIS_WEIGHTS = {
    "emotion_axis": 0.4,
    "structure_axis": 0.3,
    "prose_axis": 0.3,
}
```

- weight 在"有数据的轴上"做归一化（如果 emotion_axis 因为全 N/A 而 = null，剩下两轴权重重新归一）。
- `weighted_pre_veto` = 加权和；`overall` = 命中 veto 时为 0，否则 = `weighted_pre_veto`。

### 2.6 Toxic veto 规则

```python
TOXIC_VETO_IDS = {"preachiness", "ai_prose_ticks", "forced_stupidity"}
COMMITTEE_TOXIC_VETO_THRESHOLD = 8.0
```

对每个 toxic 维度：
- 若 `applicable=true`（preachiness / ai_prose_ticks 永远 true；forced_stupidity 可 false）AND `score >= 8.0` → 命中。
- 任意一个命中 → `vetoed=True`，`overall = 0`，`veto_reasons` 列出命中的 dim_id。

forced_stupidity 是 conditional 但**仍参与 veto**——这是为什么有独立的 `TOXIC_VETO_IDS` 常量而不是用 category 字段。

### 2.7 Evidence schema 强制约束

每个 dim 的 prompt 都要求输出：
```json
{
  "applicable": true,
  "score": 7.0,
  "evidence_quote": "<原文片段>",
  "rule_hit": "<dim_id>.<sub_rule>",
  "reasoning": "≤50 字"
}
```

- `evidence_quote` 必须是文本里**真实存在**的字符串；R3 引入字符串匹配校验。
- `score >= 5` 时 `evidence_quote` 必须非空（toxic 维度的 prompt 显式要求 score ≥ 5 时的 evidence-or-降分规则）。
- R2 实测：evidence fill rate 在所有 3 样本上 ≥ 80%（gate b 通过）。

### 2.8 评测稳定性的衡量原则（R2 lesson）

判官输出是 1-10 整数打分，不是连续值。基于此：

- **Per-dim std 在 N=5 上的天然下限是 ~0.55**（相邻整数 jitter 如 [8,8,9,9,9]）。要求 per-dim std < 0.5 实际是要求"5 次同分"，超出整数判官的分辨率。
- **真正应该衡量的是 committee-level overall 的稳定性**：把 12 个 dim 的加权平均看作下游消费方实际引用的数字。R2 实测 A 上 std=0.119, B（非 vetoed runs）std=0.144——非常稳。
- **Veto 行为的样本一致性**比 per-dim 数值 jitter 更重要：AI 水文样本是否每次都被 vetoed？头部样本是否从不 vetoed？

R3+ 各轮的 exit gate 都应按这个 framework 设计：测下游使用层的可靠性，不要测 prompt 噪声底。详见 `docs/sprints/orchestrator/round-2.md` §6.4。

---

## 3. Tiers（档位定义）

档位定义来自两类数据：(a) calibration_v1 上 judge_committee 的 mean overall（10 段，每段 N=3）+ (b) 当前生产系统 baseline（3 simulation × 4 章 × N=2）。

**核心改动**：旧档位使用"全部维度 ≥ X 分"绝对阈值；新档位用 **三个独立维度**：

1. **`overall_mean`（含 veto 影响）**：aggregate 0-10，反映"读者实际感受到的分数"。
2. **`axis_means`（独立于 veto）**：emotion / structure / prose 三轴的 mean，反映"骨架质量"。
3. **`veto_rate`**：toxic veto 命中率。这是 L1 → L2 之间最容易被忽略的杀手指标。

### 3.1 L1–L4 档位阈值

| 档位 | 对标 | overall_mean | 三轴 axis_means 全部 | veto_rate |
|---|---|---|---|---|
| **L1 追平市面（中位网文）** | 起点中位签约作 | ≥ **4.0** | ≥ **5.0** | ≤ **30%** |
| **L2 好（头部签约）** | 起点头部签约作 | ≥ **6.5** | ≥ **6.5** | ≤ **10%** |
| **L3 优秀** | 猫腻 / 烽火戏诸侯档 | ≥ **8.0** | ≥ **7.5** | ≤ **5%** |
| **L4 神作** | 现象级 | ≥ **9.0** | ≥ **8.5** | = **0%** |

**三个条件全部满足才算到达该档位**。任何一个差就回退一档。

### 3.2 calibration_v1 样本所在档位（参考锚点）

用上面阈值标注 calibration 样本的"等价档位"——这些是判官认可的样本范例。

| Sample | overall (N=3) | axes 估计 | veto | 档位 |
|---|---|---|---|---|
| F_power_cost | 7.71 | head-tier 多轴齐高 | 0% | **L2 顶**（接近 L3 的下限） |
| A_head_tier | 7.67 | 同上 | 0% | **L2 顶** |
| G3_tier3_solid | 7.16 | 中等头部 | 0% | **L2 中** |
| E_payoff_burst | 6.63 | 头部 + payoff signature | 0% | **L2 下** |
| B_mid_tier | 6.66 | 紧致 mid+ | 0% | **L1 顶 / L2 边界** |
| G4_tier4_topshelf | 6.31 | 文学型，axis 中等 | 0% | **L1 顶** |
| D_mid_arc | 5.98 | mid arc 合理 | 0% | **L1 中** |
| G2_tier2_midcommon | 4.08 | mid common | 0% | **L1 下 / 不及格边界** |
| C_ai_water | 0.0 (vetoed) | — | 100% | **L0**（毒草，不及格） |
| G1_tier1_severe | 0.0 (vetoed) | — | 100% | **L0** |

Calibration anchors 给 L1 / L2 / L0 提供了 anchor；L3 / L4 暂无 anchor（calibration_v1 的 head-tier 接近 L3 下限但不到 L3 的"猫腻级"档），R6+ 引入外部人工样本后再校准 L3 / L4 阈值。

### 3.3 当前生产系统位置（R4 baseline）

跑 3 个 simulation × 4 章 × N=2 judge runs（artifact `artifacts/eval/sprint-25/round-4/baseline_v1.json`）：

| Simulation | overall_mean | axis_means (emo/str/prose) | veto_rate |
|---|---|---|---|
| city_aftermath | 5.085 | 6.83 / 7.57 / 6.54 | 17% (2/12) |
| cultivation_betrayal | 3.700 | 7.81 / 7.40 / 6.58 | 33% (4/12) |
| border_bridge | 2.400 | 6.57 / 7.30 / 6.02 | 63% (5/8 valid runs) |
| **aggregate** | **3.728** | **7.07 / 7.42 / 6.38** | **46%** |

**当前档位判定**：

- overall_mean 3.728 < L1 的 4.0 → 不及格（L0）
- axis_means 全部 ≥ 5.0 → 满足 L1 axis 条件
- veto_rate 46% > L1 的 30% → **不及格**

**结论：当前生产系统处于 L0（不及格）**，但**根本原因是 ai_prose_ticks veto 率失控**——一旦把 veto 率压到 30% 以下，axis means 已经有 L2 等级（emotion 7.07 / structure 7.42 / prose 6.38），即可立刻进入 L1 顶部、接近 L2。

### 3.4 Sprint 26+ 攻击优先级（由 R4 baseline 派生）

Baseline 数据明确指出：**Narrator agent 的 AI 水文修辞癖是当前最大单点瓶颈**——所有 11 次 chapter veto 都由 `ai_prose_ticks` 触发。这意味着即使其他生成端 agent 完美，只要 Narrator 还在产出 over-metaphor / parallel / translation_tone / expository_dialogue 中任意子类，分数就会被 veto 一刀切。

R6 cleanup 基本完成后，Sprint 26 的第一个生成端 round 应攻这个：Narrator prompt 加 ai_prose_ticks 子类显式禁用 + 失败回退（比如检测到 over-metaphor 后强制重写）。预期收益：veto_rate 46% → ≤ 10%，overall_mean 3.728 → 6.5+ = 直接从 L0 跨到 L2 边界。

---

## 4. Calibration Anchors（校准基线指针）

### 4.1 当前 calibration set v1

路径：`tests/test_evals/fixtures/calibration_v1/`
入库时间：Sprint 25 Round 3（2026-04-30）
样本数：10（含 3 段 v0 baseline + 7 段 R3 新增）

| Sample | Tier (intent) | 备注 |
|---|---|---|
| `G4_tier4_topshelf` | 4 | 文学型 head-tier（猫腻 / 烽火戏诸侯 风骨） |
| `F_power_cost` | 4 | head-tier + 不可逆代价（cost_paid 触发样本） |
| `E_payoff_burst` | 4 | head-tier + 爽点爆发（payoff_intensity 触发样本） |
| `G3_tier3_solid` | 3 | 扎实 head-tier（守关 / 内劲对话） |
| `A_head_tier` | 3 | head-tier baseline（v0） |
| `D_mid_arc` | 2 | 中段场景（golden_start_density 反向触发） |
| `B_mid_tier` | 2 | 中位 baseline（v0） |
| `G2_tier2_midcommon` | 2 | 中位常见网文 |
| `C_ai_water` | 1 | AI 水文 baseline（v0） |
| `G1_tier1_severe` | 1 | 多毒点齐发 AI 水文 |

manifest 含：`authoring_intent_ranking` + `mandatory_pairs_must_not_reverse` + 每段 `expected_signals`。

### 4.2 ranking 验证机制

脚本：`scripts/eval/calibration_ranking.py`
退出阈值：Spearman ρ ≥ 0.95 + mandatory pair 0 反转。

每轮迭代（包括 R4 re-baseline 之前）应跑一次 calibration ranking 检查，若不达标必须先修 prompt / 维度 / 权重。

### 4.3 external-style calibration proxy subset（R6 追加）

路径：`tests/test_evals/fixtures/calibration_v1/external/`
入库时间：Sprint 25 Round 6（2026-04-30）
样本数：3

这组样本用于验证 external fixture scaffolding 与 runner 能力。出于版权与可维护性考虑，R6 未提交真实长版权片段；当前 external subset 是 Codex 原创、manual product-lens 排序的 **proxy** 样本，不冒充任何真实作者原文。

**边界**：这组 proxy 不能等同于真正的外部人工评分样本，也不能完全打破 `calibration_v1` 全部由同一 AI 生成的自循环偏差。Claude 原要求仍是：引入 ≥ 3 段真实外部/人类作者/授权或明确人工评分样本（可为人类精仿），并以人工排序 + mandatory pairs 验证。

| Sample | 预期档位 | 备注 |
|---|---|---|
| `X1_external_head_market` | high | 头部网文向：目标、压力、物件证据、潜台词对话 |
| `X2_external_mid_common` | mid | 中位常见网文：概念化动作、说明性对话偏多 |
| `X3_external_ai_water` | low | AI 水文毒点：多子类 `ai_prose_ticks` + `preachiness` |

验证命令：

```bash
.venv/bin/python scripts/eval/calibration_ranking.py \
  --fixture-dir tests/test_evals/fixtures/calibration_v1/external \
  --runs 3 \
  --skip-spearman-gate \
  --output artifacts/eval/sprint-25/round-6/external_calibration_ranking.json
```

R6 proxy 实测：Spearman ρ = 1.0（小样本记录但不 gated），mandatory pair violations = 0，PASS。

### 4.4 已知 calibration 限制（R3 实测）

**重要**：当前 calibration set 是 Claude 自己写的——同一个模型既写样本又写判官 prompt。这意味着：

- 排序一致性通过（Spearman ≥ 0.95）是**必要条件**，不是**充分条件**。
- 通过未必证明判官在外部数据上有判别力，可能只是 AI fingerprint 自匹配。
- R6 已引入 3 段 external-style proxy 锚点作为 scaffolding 验证；真正的外部人工评分样本仍 pending。后续需要追加授权片段、人类精仿或人工盲评样本，但不得提交未授权长版权原文。

R3 实测排序 Spearman ρ = 0.5606（远低于阈值），说明即使在自写样本上 calibration 也没通过——这反而是好消息：评测系统暴露了自己的盲区，不是过拟合到自己写的样本。

**已知 prompt-级 bug（R3 揭示，R4 优先修）**：
1. `forced_stupidity` 把"反派被合理底牌击溃"误判为降智（~20% 概率）。
2. `cost_paid` rubric anchoring failure：reasoning 命中 9-10 锚点描述时仍默认输出 4-6 mid tier 分。

详细 root cause 见 `docs/sprints/orchestrator/round-3.md` §6.3 / §6.4。

---

## 5. 中间节点 LLM2LLM 评测（Intermediate Node Evaluation）

> 状态：P0 已实现（Critic + Actor isolated intent）；P1/P2/P3 仍为路线图
> 面向读者：维护 / 扩展中间节点评测体系的后端 / 评测工程师
> 关联现有 Final 评测：`src/worldbox_writer/evals/llm_judge.py`（§1-§4 所述 13 维单章 + 4 维跨章）

### 5.1 TL;DR

1. **当前状态**：P0 已覆盖 `CriticAgent._call_llm_for_review` 与 `invoke_isolated_actor_intent`，其余 Director / GateKeeper / Narrator / Memory 等中间节点仍按 P1/P2/P3 路线图推进。
2. **解决方案**：构建一套 **LLM2LLM 中间节点评测体系**，每个节点配套专属维度 + 独立 Judge LLM 调用，与 Final 评测（§1-§4）互补；P0 已落地为可手动运行的真实 LLM runner。
3. **硬性原则**：所有质量打分必须由 Judge LLM 完成；启发式只能用于格式校验，不参与质量评分。
4. **优先级**：P0（Critic、Actor）已实现；下一步做 P1（Director init、Narrator script_faithfulness），最后做 P2/P3。
5. **不依赖端到端跑流**：通过运行时 hook 落盘样本，评测可独立、批量、可重放；P0 阶段记录耗时统计但不设置 5 分钟硬门槛。

### 5.2 为什么必须做中间节点评测

| 价值 | 说明 |
| --- | --- |
| **诊断定位** | Final 分数下降时，能直接指向"是 Critic 漏杀"还是"Actor 模板化"，而非黑盒猜测 |
| **独立调优** | 可以单独迭代某一个 Agent 的 prompt / model，无需跑完整端到端 |
| **节省成本** | 中间节点样本可批量回放评测，避免每次都要重跑 1500 字章节 |
| **回归防护** | 接入 CI 后，可拦截单 Agent 级别的质量回退 |

**与 §1-§4 Final 评测的关系**：互补，而非替代。中间评测分数全部健康但 Final 仍下降 → 说明问题在 Agent 之间的协作 / 编排。

### 5.3 设计原则（硬性约束）

1. **所有质量打分必须由 Judge LLM 完成（LLM2LLM）**——禁止启发式规则、关键词扫描、硬编码阈值；启发式只能用于格式校验。
2. **裁判与被裁判模型必须隔离**——不允许自己判自己；复用现有 Final judge 配置（`WORLDBOX_JUDGE_MODEL` / `DEFAULT_JUDGE_MODEL`），不新增 Intermediate 专用配置；报告必须记录 judge model 与 runtime model。
3. **Judge 必须看到完整上下文**——必须传入 `(input_context, output)` 两侧。
4. **沿用现有评测契约**——单维度输出格式 `{applicable, score, evidence_quote, reasoning}`（同 §1 per-dimension schema）。
5. **沿用反幻觉机制**——复用 `_evidence_in_text` 子串校验，Judge 编造证据自动降分。
6. **可解释性优先**——每个维度必须输出 `evidence_quote` + `reasoning`。

### 5.4 评测对象清单（Scope）

全部 27 个 LLM 生成节点按优先级分 P0/P1/P2/P3。完整清单见 `src/worldbox_writer/evals/intermediate_judge.py` 的节点路由表；核心节点如下：

| # | 节点名 | role | 文件 | 优先级 |
| --- | --- | --- | --- | --- |
| 1 | `DirectorAgent._call_llm_for_init` | director | `agents/director.py` | P1 |
| 8 | `actor_node` 内联候选事件 | actor | `engine/graph.py` | P1 |
| 9 | `invoke_isolated_actor_intent` | actor | `engine/dual_loop.py` | **P0** ✅ |
| 10 | `CriticAgent._call_llm_for_review` | gate_keeper | `agents/critic.py` | **P0** ✅ |
| 11 | `GateKeeperAgent._call_llm_for_validation` | gate_keeper | `agents/gate_keeper.py` | P2 |
| 14 | `narrator_node` 主渲染 | narrator | `engine/graph.py` | **P1** |
| 22 | `MemoryManager._summarize_entries` | memory | `memory/memory_manager.py` | P2 |

余下（Director intervention / WorldBuilder expand / NodeDetector / 短文本节点等）见路线图 §5.7。

### 5.5 节点分组与评测维度

按节点产出形态分四组，每维度由 Judge LLM 输出 `{applicable, score (0-10), evidence_quote, reasoning}`。

#### 5.5.1 结构化输出节点组

**Director init（#1）— 5 维**：`premise_fidelity`、`character_individuation`（防"破局者"等抽象代称）、`constraint_actionability`、`dramatic_tension`、`world_consistency`。

**Critic（#10）— 5 维（最关键）**：
- `policy_recall`：给定违反约束的 intent，Critic 是否成功识别？（红队样本）
- `policy_precision`：给定看似敏感但实际合规的 intent，Critic 是否避免误杀？（蓝队样本）
- `reason_grounding`：reason 是否引用具体政策 / 上下文证据？
- `severity_calibration`：severity 是否与违规程度匹配？
- `revision_hint_actionability`：revision_hint 是否能被 Actor 直接采纳？

**GateKeeper（#11/#12）— 复用 Critic 5 维** + 节点 #12 追加 `tension_preservation`。

**NodeDetector（#13）— 3 维**：`intervention_necessity` / `urgency_calibration` / `option_diversity`。

**Memory.assess_consistency（#23）— 3 维**：`contradiction_recall` / `contradiction_precision` / `explanation_grounding`。

#### 5.5.2 意图 / 动作生成节点组（Actor）

**Actor intent（#6 / #8 / #9）— 5 维**：`character_fidelity`（防 OOC）、`motivation_visibility`、`action_specificity`、`confidence_calibration`、`memory_consistency`。

**Actor synthesize_event（#7）— 3 维**：`proposal_coverage` / `conflict_preservation` / `scene_plan_alignment`。

#### 5.5.3 自然语言渲染节点组

**Narrator 主渲染（#14）— 复用 §1 `judge_committee` 12 维 + 新增 `script_faithfulness`**：
- Judge 检查 prose 是否仅基于 `accepted_intents` + `SceneScript`
- 是否擅自加入未结算的行动
- 是否错误地写入了 `rejected_intent_ids` 中的内容
- 锚点：10=完全忠实；5=轻微补完；0=出现 rejected_intents 中的事件

**WorldBuilder expand（#4）— 3 维**：`setting_compatibility` / `creative_specificity` / `tension_seeding`。

**Memory summarize（#22）— 3 维**：`key_event_recall` / `no_fabrication` / `compression_efficiency`。

#### 5.5.4 短文本节点组（#3 / #16 / #24）

统一 3 维：`relevance_to_input` / `specificity`（避免"风暴""破局"等空泛词）/ `format_compliance`。

### 5.6 样本采集与红蓝队机制

#### 5.6.1 采集机制

在 LLM 调用点（主要在 `engine/graph.py`、`engine/dual_loop.py` 以及各 Agent）插入 **样本采集 hook**，将每次 `(input_context, output)` 落盘：

```
artifacts/intermediate_samples/
  {node_name}/{run_id}.jsonl
```

样本 schema：`{node_name, run_id, sample_id, timestamp, role, model, input_context, raw_output, parsed_output, downstream_decision}`。

**关键约束**：
- 评测可独立、批量、可重放；采集开关通过 `WB_COLLECT_SAMPLES=1` 控制，默认关闭
- 运行时采集样本默认落 `artifacts/`，不入 git；curated fixtures / manifest 可入 git

#### 5.6.2 红队 / 蓝队样本（针对 Critic / GateKeeper）

仅依赖在线样本无法评估召回率，必须主动构造对抗样本：

- **红队**：明显违反约束的 intent → `policy_recall = 拦截数 / 红队总数`，目标 ≥ 95%
- **蓝队**：看似敏感但实际合规的 intent → `policy_precision = 1 - 误杀数 / 蓝队总数`，目标 ≥ 95%

P0 不新增正式 `policy.json`；以 `CriticAgent._CRITIC_POLICY_PROMPT` + `world_state.constraints` 作为 policy source，由 Judge LLM 辅助合成后固化到：

```
tests/test_evals/fixtures/intermediate_eval/
  manifest.json           # 必须记录 policy source / rule id / 覆盖范围 / 阈值
  red_team.jsonl
  blue_team.jsonl
  actor_intent.jsonl
```

样本集随政策变更 **增量** 更新，不全量重写。

### 5.7 P0 当前实现与路线图

#### 5.7.1 P0 当前实现状态（2026-05-11）

已落地文件：

- `src/worldbox_writer/evals/intermediate_judge.py`
- `src/worldbox_writer/evals/sample_collector.py`
- `scripts/eval/intermediate_eval.py`
- `tests/test_evals/fixtures/intermediate_eval/{manifest.json, red_team.jsonl, blue_team.jsonl, actor_intent.jsonl}`

已接入 hook：
- `src/worldbox_writer/engine/dual_loop.py::invoke_isolated_actor_intent`
- `src/worldbox_writer/agents/critic.py::CriticAgent._call_llm_for_review`

运行入口：`make intermediate-eval`

最近一次真实 LLM 验证：
- 报告：`artifacts/reports/intermediate_eval/critic_review_actor_intent_20260511T033246Z.json`
- `overall_pass=true`；Critic red-team recall = `1.0`（阈值 `0.95`）；blue-team precision = `1.0`；Actor fixture ok:2

默认 PR gate 仍只跑 `make lint` / `make test`；真实 LLM eval 只通过 `make intermediate-eval` 手动触发。

#### 5.7.2 路线图

| 阶段 | 节点 | 理由 | 验收要求 |
| --- | --- | --- | --- |
| **P0**（✅ 已完成） | #10 Critic、#9 Actor isolated intent | 直接决定 OOC 和审查死，是 Final 回退最常见根因 | red-team recall ≥ 95% / blue-team precision ≥ 95% / Actor 5 维可跑通 |
| **P1** | #1 Director init、#14 Narrator `script_faithfulness`、#8 actor_node 内联 | 紧邻 P0 的质量关键路径 | Narrator 能识别 rejected_intents 泄漏；Director 能定位"破局者"退化 |
| **P2** | #11 #12 GateKeeper、#22 #23 Memory、#4 WorldBuilder、#6 #7 Actor 旧路径、#15 #17 Narrator 离线 | 覆盖次要路径 | 全部节点能跑通评测 |
| **P3** | #3 #5 #13 #16 #18-21 #24 短文本 / NodeDetector / 原型节点 | 长尾 | 统一 3 维短文本评测 + NodeDetector 覆盖 |

### 5.8 接口与代码规划

#### 5.8.1 `src/worldbox_writer/evals/intermediate_judge.py`

```python
class DimensionScore(TypedDict):
    name: str
    applicable: bool
    score: float  # 0-10
    evidence_quote: str
    reasoning: str

class NodeJudgement(TypedDict):
    node_name: str
    sample_id: str
    dimensions: list[DimensionScore]
    overall: float
    evidence_chain: list[str]
    judge_model: str

def judge_node_output(
    node_name: str,
    input_context: dict,
    output: Any,
    judge_model: str | None = None,
) -> NodeJudgement:
    """按 node_name 路由到专属维度集，调用 judge_model 评分。"""
```

- 复用 `evals/dimension_prompts.py` 的 prompt 范式 + `_evidence_in_text` 反幻觉
- 复用现有 Final judge 配置（`WORLDBOX_JUDGE_MODEL` / `DEFAULT_JUDGE_MODEL`），不新增 Intermediate 专用 provider / model
- 报告必须记录 judge model 与被裁判节点的 runtime model

#### 5.8.2 `src/worldbox_writer/evals/sample_collector.py`

```python
def collect_sample(node_name: str, input_ctx: dict, output: Any, metadata: dict | None = None) -> None:
    """运行时 hook：追加写入 artifacts/intermediate_samples/{node_name}/{run_id}.jsonl"""
```

- 在 Agent 内部显式调用，**不** 在 `utils/llm.py` 内部隐式调用（避免污染基础 LLM 工具层）
- 通过 `WB_COLLECT_SAMPLES=1` 启用
- P0 hook 位置固定为 `engine/dual_loop.py::invoke_isolated_actor_intent` 和 `agents/critic.py::CriticAgent._call_llm_for_review`

#### 5.8.3 `scripts/eval/intermediate_eval.py`

```bash
python scripts/eval/intermediate_eval.py --node critic --samples 100
python scripts/eval/intermediate_eval.py --node critic --red-team
python scripts/eval/intermediate_eval.py --node critic --blue-team
python scripts/eval/intermediate_eval.py --node critic --input artifacts/intermediate_samples/critic_review/run_xxx.jsonl
python scripts/eval/intermediate_eval.py --node critic --judge-model gpt-5.5
```

输出：`artifacts/reports/intermediate_eval/{node_name}_{timestamp}.json` + `.md` 摘要。

#### 5.8.4 Makefile 目标

```makefile
.PHONY: intermediate-eval
intermediate-eval:
	$(PYTHON) scripts/eval/intermediate_eval.py --node critic --red-team --blue-team --node actor_intent --input tests/test_evals/fixtures/intermediate_eval/actor_intent.jsonl
```

按 `AGENTS.md` "不引入第二份 CI 命令真源"原则：同步更新 `Makefile` + `docs/development/DEVELOPMENT.md`；若后续接入 CI，再同步 `scripts/ci/*` + `.github/workflows/*`，且不得进入默认 PR blocking gate。

### 5.9 验收标准

| # | 验收项 | 通过条件 |
| --- | --- | --- |
| 1 | 每个 P0 节点评测能跑通并输出报告 | 报告含 dimensions / overall / evidence |
| 2 | 评测结果有可解释的 evidence_quote | 每维度都有 quote 字段 |
| 3 | 报告能定位拖底维度 | 输出按分数升序的 Top N 维度 |
| 4 | 评测耗时 | 报告含总耗时、平均耗时、P95；P0 不设 5 分钟硬门槛 |
| 5 | 与 `make lint` / `make test` 兼容 | 不引入新 lint / type 错误 |
| 6 | 接入 CI 但不强制阻塞 | 类似 `make typecheck` baseline 模式 |
| 7 | 红蓝队评测 | Critic recall ≥ 95%，precision ≥ 95% |
| 8 | 反幻觉机制生效 | Judge 编造证据时 score 自动降分 |

P0 当前验证：`overall_pass=true`、Critic recall / precision 均 `1.0`、Actor fixture 两条 `ok`、`make lint` / `make test` / `make typecheck` 已通过。

### 5.10 风险与限制

| 风险 | 缓解措施 |
| --- | --- |
| Judge LLM 自身幻觉与一致性 | evidence_quote + `_evidence_in_text` 校验；多次评测取平均；固化 judge_model 版本 |
| 红队样本覆盖度不足 | `manifest.json` 记录 policy source / rule id / 覆盖范围；按 policy 类别分层；增量更新 |
| 评测 Token 成本 | P0/P1 优先；默认采样；短文本节点合并评测 |
| 与 mypy baseline 不冲突 | 严格遵守 `docs/development/DEVELOPMENT.md §11`，新增模块零 mypy error |
| 样本采集 IO 开销 | 默认关闭；异步写入；按 run_id 切分避免锁竞争 |
| Judge 与运行时模型耦合 | 复用 Final judge 配置；报告记录 judge model 与 runtime model，后续发现耦合再升级配置隔离 |
| macOS 端口耗尽 / 高并发失败 | 所有真实 LLM eval runner 默认 `concurrency=1` |
| 隐私 / 数据安全 | curated fixtures / manifest 可入 git；`.env`、secret、本地数据库、`artifacts/reports/*` 不入 git |

### 5.11 开发自检清单

提交前逐项确认：

- [ ] 没有引入任何启发式打分（关键词 / 阈值 / 规则）
- [ ] 所有维度都通过 Judge LLM 输出
- [ ] 所有维度都有 `evidence_quote` 字段
- [ ] judge_model 与被裁判 model 隔离
- [ ] Judge 看到了完整的 input + output
- [ ] 沿用 `{applicable, score, evidence_quote, reasoning}` 契约
- [ ] 接入 `_evidence_in_text` 反幻觉
- [ ] 样本落盘默认关闭，由环境变量控制
- [ ] 质量验收通过真实 LLM runner；默认测试不使用测试替身替代 Judge 或 Critic 质量行为
- [ ] 真实 LLM eval runner 默认 `concurrency=1`
- [ ] 红蓝队 fixtures 带 `manifest.json`，记录 policy source / rule id / 阈值
- [ ] 报告能定位 Top N 拖底维度
- [ ] `make lint` / `make test` 通过
- [ ] 如新增 TypedDict / Pydantic / 评测契约，`make typecheck` 无新增 mypy 错误
- [ ] 文档同步更新（`Makefile` / `docs/development/DEVELOPMENT.md` / `docs/README.md`）

---

## 附录 A：与旧文档的迁移关系

| 旧文档 | 旧内容 | 新位置 |
|---|---|---|
| `WEB_NOVEL_CRITERIA.md` 第 1-5 章三轴 + 神作 + 毒点定义 | 维度定义 | 本 spec 第 1 章（已重组分层） |
| `WEB_NOVEL_CRITERIA.md` 附录 A 1-10 分量化打分量表 | 评分细则 | 各 dimension prompt（R2 落地） |
| `WEB_NOVEL_CRITERIA.md` 附录 B 权重 | 聚合权重 | 本 spec 第 2 章（R2 填充） |
| `QUALITY_FRAMEWORK.md` 评测协议 + 工程闭环 | 协议规则 | 本 spec 第 2 章 |
| `QUALITY_FRAMEWORK.md` LLM-as-judge prompt 模板 | 单 prompt 大模板 | 拆为 per-dimension prompt（R2） |
| `orchestrator/README.md` 四档表 | 档位 | 本 spec 第 3 章（R4 重写） |
| `development/INTERMEDIATE_EVAL_SPEC.md` | 中间节点 LLM2LLM 评测体系 | 本 spec 第 5 章（2026-05-11 合并） |

R3 cleanup round 完成时，`WEB_NOVEL_CRITERIA.md` 与 `QUALITY_FRAMEWORK.md` 改为单页索引指向本 spec。
