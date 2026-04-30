# QUALITY_SPEC — WorldBox Writer 评测系统单一真相源

**文档状态**：v0.4（Sprint 25 Round 4 完成；R3 两个 prompt bug 修复，calibration ρ=0.9848 通过；当前生产系统取得首份可信 baseline；档位 L1-L4 阈值落地）
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

R3+ 各轮的 exit gate 都应按这个 framework 设计：测下游使用层的可靠性，不要测 prompt 噪声底。详见 `docs/orchestrator/round-2.md` §6.4。

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

R6 完成后 Sprint 26 的第一个 round 应攻这个：Narrator prompt 加 ai_prose_ticks 子类显式禁用 + 失败回退（比如检测到 over-metaphor 后强制重写）。预期收益：veto_rate 46% → ≤ 10%，overall_mean 3.728 → 6.5+ = 直接从 L0 跨到 L2 边界。

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

### 4.3 已知 calibration 限制（R3 实测）

**重要**：当前 calibration set 是 Claude 自己写的——同一个模型既写样本又写判官 prompt。这意味着：

- 排序一致性通过（Spearman ≥ 0.95）是**必要条件**，不是**充分条件**。
- 通过未必证明判官在外部数据上有判别力，可能只是 AI fingerprint 自匹配。
- R6+ 必须引入**外部人工标注样本**（猫腻 / 烽火 / 起点头部 真实片段）才能真正打破自循环偏差。

R3 实测排序 Spearman ρ = 0.5606（远低于阈值），说明即使在自写样本上 calibration 也没通过——这反而是好消息：评测系统暴露了自己的盲区，不是过拟合到自己写的样本。

**已知 prompt-级 bug（R3 揭示，R4 优先修）**：
1. `forced_stupidity` 把"反派被合理底牌击溃"误判为降智（~20% 概率）。
2. `cost_paid` rubric anchoring failure：reasoning 命中 9-10 锚点描述时仍默认输出 4-6 mid tier 分。

详细 root cause 见 `docs/orchestrator/round-3.md` §6.3 / §6.4。

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

R3 cleanup round 完成时，`WEB_NOVEL_CRITERIA.md` 与 `QUALITY_FRAMEWORK.md` 改为单页索引指向本 spec。
