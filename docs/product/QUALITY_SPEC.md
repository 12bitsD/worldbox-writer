# QUALITY_SPEC — WorldBox Writer 评测系统单一真相源

**文档状态**：DRAFT v0.1.1（Sprint 25 Round 1 完成；维度集合经 225 次 real-LLM 跑分稳定性验证）
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

### 1.5 维度选择决策表（R1.5 实测）

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
| `preachiness` | toxic | 1.4 | 2.0 | 8.8 | 0.707 | **keep** | C 上明显命中，A/B 低判 |
| `ai_prose_ticks` | toxic | 2.6 | 4.0 | 10.0 | **1.414** | **watchlist** | B 摇摆 3-6——R2 prompt 强制 evidence-or-降分 |
| `forced_stupidity` | toxic | 6.8 | 6.0 | 9.0 | **1.924** | **drop（误判 prompt）** | 把"博弈层 withholding"误判成降智——R2 改 conditional + 排除 leverage 误判 |

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

> 占位。R2 委员会落地时填充：调用方式（4 专家并发：emotion / structure / prose / toxic）、参数（温度、max_tokens、并发度）、评分聚合规则、conditional dimension 的 applicable 处理规则。

---

## 3. Tiers（档位定义）

> 占位。R4 用新评测重测当前系统取得真实基线后填充：L1–L4 用相对量（盲测胜率 + calibration 排序一致性）+ 必要的绝对阈值。

---

## 4. Calibration Anchors（校准基线指针）

> 占位。R3 完成 5–10 段人工标注样本入库后填充：样本路径、人工评分结构、judge 排序一致性的验证脚本。

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
