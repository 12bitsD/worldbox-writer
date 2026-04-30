"""Per-dimension judge prompts (Sprint 25 Round 1 v0.1 draft).

Each dimension has its own focused prompt so the judge cannot smear scores
across unrelated dimensions. The schema is uniform across categories so that
stability experiments and downstream aggregation can reuse the same parser.

Output schema (JSON):

  {
    "applicable": true,
    "score": 7.0,
    "evidence_quote": "<原文片段>",
    "rule_hit": "<dim_id>.<sub_rule_or_none>",
    "reasoning": "≤50 字"
  }

For conditional dimensions, `applicable: false` returns `score: null`:

  {"applicable": false, "score": null, "reason": "片段不含 X 场景"}

Toxic flags reuse the same numeric schema (score 0-10) so std analysis is
uniform: 0-2 = definitely not hit, 8-10 = definitely hit, mid-range = unsure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DimensionCategory = Literal["per_passage", "conditional", "toxic"]


@dataclass(frozen=True)
class DimensionPrompt:
    dim_id: str
    category: DimensionCategory
    chinese_name: str
    system_prompt: str


_OUTPUT_SCHEMA_BLURB = """输出严格 JSON，不要 markdown，不要解释。schema：
{
  "applicable": true | false,
  "score": <1-10 数值；当 applicable=false 时为 null>,
  "evidence_quote": "<不超过 60 字的原文片段，必须是文本中真实出现的字符串；找不到则空字符串>",
  "rule_hit": "<dim_id>.<可选 sub_rule>",
  "reasoning": "≤50 字"
}"""


def _per_passage(
    dim_id: str, name: str, definition: str, anchors: str
) -> DimensionPrompt:
    system = f"""你是 WorldBox Writer 评测系统的「{name}」维度专家。
你只判定这一个维度，**不**评其他维度。Per-passage 维度对任何 prose 片段都需打分（applicable 永远 true）。

定义：
{definition}

评分锚点（1-10）：
{anchors}

{_OUTPUT_SCHEMA_BLURB}

注意：
- `applicable` 对 per-passage 维度永远为 true。
- evidence_quote 必须是文本里**真实存在**的字符串，不要改写、不要总结。
- rule_hit 用 `{dim_id}.<sub_rule>` 形式，sub_rule 用英文短词，例如 `{dim_id}.specific_object`。
- reasoning 写优点与最大短板，≤ 50 字。
"""
    return DimensionPrompt(
        dim_id=dim_id, category="per_passage", chinese_name=name, system_prompt=system
    )


def _conditional(
    dim_id: str, name: str, applicability: str, definition: str, anchors: str
) -> DimensionPrompt:
    system = f"""你是 WorldBox Writer 评测系统的「{name}」维度专家。
你只判定这一个维度，**不**评其他维度。这是一个 conditional 维度——必须先判定它是否适用本片段。

适用判定：
{applicability}
若不适用，返回 `{{"applicable": false, "score": null, "reason": "..."}}`，不要勉强打分。

定义（仅当 applicable=true 时使用）：
{definition}

评分锚点（1-10，仅当 applicable=true 时使用）：
{anchors}

{_OUTPUT_SCHEMA_BLURB}

注意：
- 不适用就坦率返 false。如果"勉强可算适用"，选择不适用，方差会更小。
- evidence_quote 必须是真实存在的字符串。
"""
    return DimensionPrompt(
        dim_id=dim_id, category="conditional", chinese_name=name, system_prompt=system
    )


def _toxic(
    dim_id: str, name: str, definition: str, hit_examples: str
) -> DimensionPrompt:
    system = f"""你是 WorldBox Writer 评测系统的「{name}」毒点专家。
你只判定这一个毒点，**不**评其他维度或毒点。Per-passage 检测，applicable 永远 true。

定义（命中条件）：
{definition}

命中样例：
{hit_examples}

评分（1-10，把"是否命中"当成连续判定）：
- 1-2：完全没有命中迹象
- 3-4：极轻微痕迹但未达毒点门槛
- 5-7：摇摆地带（保留判断时倾向偏低）
- 8-9：明显命中
- 10：极典型，多处证据

{_OUTPUT_SCHEMA_BLURB}

注意：
- 命中（score ≥ 8）时 `evidence_quote` 必须给原文证据；不给则不要打高分。
- 不命中（score ≤ 4）时 evidence_quote 可空字符串。
- rule_hit 用 `{dim_id}.<具体子类型>`，例如 `ai_prose_ticks.over_metaphor` / `ai_prose_ticks.parallel` / `ai_prose_ticks.translation_tone` / `ai_prose_ticks.expository_dialogue`。
- 这是命中检测，宁可漏检不可误判：拿不准就给 5 分以下。
"""
    return DimensionPrompt(
        dim_id=dim_id, category="toxic", chinese_name=name, system_prompt=system
    )


# ---------------------------------------------------------------------------
# Per-passage dimensions
# ---------------------------------------------------------------------------

DESIRE_CLARITY = _per_passage(
    dim_id="desire_clarity",
    name="欲望具体性",
    definition="主角此刻**想要什么**是否具体可见？是否暗示**为什么想要**与**不达成的代价**？只看片段内呈现的信息，不脑补全文背景。",
    anchors=(
        "1-3：主角无明确近端目标；或目标极其抽象（'守护正义'、'变得更强'）。\n"
        "4-6：有目标但不具体；为什么、代价至少缺一项。\n"
        "7-8：目标具体到对象/动作/时机；为什么有暗示；不达成的代价隐约可见。\n"
        "9-10：三层（要什么+为什么+代价）都通过情节自然呈现，不用旁白。"
    ),
)

TENSION_PRESSURE = _per_passage(
    dim_id="tension_pressure",
    name="张力与压力",
    definition="片段当前的外部压力（敌人嚣张、危机倒计时、信息不对称、资源稀缺）是否远大于主角表面的应对能力？读者是否替主角焦虑？",
    anchors=(
        "1-3：无外部压力；或压力来自抽象描述（'局势严峻'）而非具体场景。\n"
        "4-6：有压力但与主角能力对等；读者不会替主角焦虑。\n"
        "7-8：压力大于主角表面能力，且压力源具体（人/时间/资源）；读者预感会出问题。\n"
        "9-10：压力压抑到近乎逼出主角底牌，但底牌还未亮——读者必须翻页。"
    ),
)

INFO_SHOW_DONT_TELL = _per_passage(
    dim_id="info_show_dont_tell",
    name="信息给配",
    definition="世界观/规则/背景是否通过冲突或动作自然展现？是否出现连续 ≥100 字的纯旁白说明文？",
    anchors=(
        "1-3：大段旁白说明世界观/历史/等级；或对话变成强行问答式科普。\n"
        "4-6：有铺陈但与情节交错；偶有解释段。\n"
        "7-8：设定通过角色行动、物件、对话潜台词显现；无明显说明段。\n"
        "9-10：用一个具体动作或物件侧面显出整套规则（例：买不起一把剑，显出货币与剑的稀缺）。"
    ),
)

PROSE_FRICTION = _per_passage(
    dim_id="prose_friction",
    name="阅读顺滑度",
    definition="句长分布、生僻字密度、长句从句、段落切分是否符合手机阅读？读者能否一目十行？",
    anchors=(
        "1-3：长句从句堆叠，生僻字密；段落动辄数百字不换行。\n"
        "4-6：偶有长句或啰嗦；整体可读。\n"
        "7-8：短平快为主，段落切分清晰，无生僻字；句式有变化。\n"
        "9-10：句式节奏感极强，长短句交替推动情绪；读者不感到任何阅读阻力。"
    ),
)

MATERIAL_SPECIFICITY = _per_passage(
    dim_id="material_specificity",
    name="物质感",
    definition="动作/场景是否落到具体物件、声音、气味、距离感、方向感？是否避免'出招、对掌、震退三步'式的概念战？是否避免用形容词替代名词？",
    anchors=(
        "1-3：满篇形容词与抽象概念；无具体物件/声音/气味；动作概念化。\n"
        "4-6：有少量具体物件，但多数动作仍是概念。\n"
        "7-8：场景里至少 2-3 个可感官化的物件/声响/气味；动作有方向、距离、破坏感。\n"
        "9-10：物件本身承载情绪与因果（一把磨毛刺的刀鞘 = 角色的过往）；几乎无形容词堆砌。"
    ),
)

DIALOGUE_VOICE = _per_passage(
    dim_id="dialogue_voice",
    name="对话辨识度",
    definition="对话是否符合角色身份？片段内 ≥2 角色时，不同角色之间是否有可分辨的语言指纹（用词、语速、典型句式、停顿习惯）？只有 1 角色或无对话时，看独白/内心是否有角色个性。",
    anchors=(
        "1-3：所有角色说话趋同；或对话全部是模板化网文台词；或翻译腔/书面语。\n"
        "4-6：基本符合身份，但角色间差异不明显；台词功能化。\n"
        "7-8：每个角色说话有可分辨的语言指纹；用词与节奏体现身份。\n"
        "9-10：盲读 5 行就能认出是谁说的；台词推动冲突且暗藏潜台词。"
    ),
)

CONFLICT_DENSITY = _per_passage(
    dim_id="conflict_density",
    name="冲突密度",
    definition="单位字数（约 200-300 字）内是否有效推进新的冲突点（新信息、新威胁、新选择、新疑问、新钩子）？过渡段/氛围段过多即为低密度。",
    anchors=(
        "1-3：大段过渡或氛围铺陈；冲突点稀疏。\n"
        "4-6：有冲突但密度中等；段落间偶有空转。\n"
        "7-8：约每 200-300 字推进一个新钩子；几乎无空转段落。\n"
        "9-10：每段都推进新信息/新威胁/新选择；读者无空隙喘息。"
    ),
)


# ---------------------------------------------------------------------------
# Conditional dimensions
# ---------------------------------------------------------------------------

PAYOFF_INTENSITY = _conditional(
    dim_id="payoff_intensity",
    name="爽点爆发强度",
    applicability="片段是否包含主角胜利、获益、底牌揭晓、压制反派的爆发瞬间？没有就 applicable=false。",
    definition="爆发瞬间的配角反应/敌人崩溃描写是否在 500 字内出现？是低级（数值碾压）/中级（认知逆转）/高级（规则重塑）？",
    anchors=(
        "1-3：爆发后无配角反应；或反应干瘪如'他怎么这么强'。\n"
        "4-6：有反应但仅纯数值碾压（低级）；铺垫不足。\n"
        "7-8：铺垫充足；反派出现认知逆转（中级）；配角震惊描写生动具体。\n"
        "9-10：摧毁反派最大依仗（高级，规则重塑）；引发势力倒戈/原阵营崩塌。"
    ),
)

GOLDEN_START_DENSITY = _conditional(
    dim_id="golden_start_density",
    name="黄金开局信息密度",
    applicability="片段是否覆盖故事开篇的前 1500 字？若片段是开局或开局附近内容（含主角首次登场、世界初次展开），适用；中段/章末场景不适用。",
    definition="前 500 字是否抛出生存危机或身份错位？前 1500 字内金手指是否激活或暗示？是否在第三章末树立 5-10 万字主线驱动力？",
    anchors=(
        "1-3：花大量字数写设定/旁白；主角迟迟登场；无危机无金手指。\n"
        "4-6：有危机或金手指但出现位置过晚；密度不够。\n"
        "7-8：500 字内危机立住；1500 字内金手指出场；主线驱动力清晰。\n"
        "9-10：信息密度极高，无废字；危机+金手指+主线全部用冲突自然呈现。"
    ),
)

CLIFFHANGER_PULL = _conditional(
    dim_id="cliffhanger_pull",
    name="章末追读拉力",
    applicability="片段末尾是否构成章节或小节的明确收束？若末尾自然过渡到下一情节，则适用；若片段是中段截取，applicable=false。",
    definition="结尾是否停在动作进行中、悬念揭晓前、或利益结算前？是否产生'必须翻页'的拉力？",
    anchors=(
        "1-3：事情彻底做完；或'主角去睡觉'式平淡结尾；或一段对话自然结束。\n"
        "4-6：有转折但悬念弱；翻页冲动一般。\n"
        "7-8：卡在三种黄金断章之一（动作中/悬念前/利益结算前）；翻页冲动强。\n"
        "9-10：致命危机降临前 1 秒；或颠覆前文认知的真相揭开一半；翻页冲动极致。"
    ),
)

ANTAGONIST_INTEGRITY = _conditional(
    dim_id="antagonist_integrity",
    name="反派可信度",
    applicability="片段中是否有反派/对手登场且行动可见？只是被提及而未出现的反派，applicable=false。",
    definition="反派的智商、动机正当性、信息博弈是否与主角对等？是否避免'死于话多''贴脸嘲讽'式降智？",
    anchors=(
        "1-3：反派纯为衬托主角而存在；行为逻辑荒谬；动机单薄（'纯粹邪恶'）。\n"
        "4-6：智商正常但布局简单；动机功能化（'贪婪'）。\n"
        "7-8：反派有自洽信仰与利益逻辑；战术与主角有来有回。\n"
        "9-10：反派拥有愿赴死的理念；在已知信息下做出最优解；带来窒息压迫感。"
    ),
)

_COST_PAID_SYSTEM = """你是 WorldBox Writer 评测系统的「代价对等」维度专家。
你只判定这一个维度，**不**评其他维度。这是一个 conditional 维度。

## 适用判定

片段中是否含主角使用力量、底牌、越级行动、规则突破？没有就 applicable=false。

## 评分规则——基于具体示例的打分（example-based scoring）

下表是**强制对照表**。先识别片段呈现的 cost 类型组合，再根据组合范例给分。
不要用抽象描述（"惨烈"、"清晰规则博弈"）让自己摆动到中间分；按具体范例判。

| Score | 范例（片段必须呈现的 cost 类型组合） |
|---|---|
| 1-2  | 主角越级杀敌 + 完全零代价；或代价被一句"虚弱了"带过且下一段恢复。 |
| 3-4  | 单一可恢复 cost（短暂虚弱 / 几日昏迷 / 流血但能愈合）；或代价模糊（"付出了代价"但没具体描述）。 |
| 5-6  | 单一不可逆 cost（断一指 / 长一道疤 / 丢一段非核心记忆 / 失一个普通朋友）；范围有限。 |
| **7-8**  | **多重不可逆 cost**（≥ 2 项）：例如失明 + 残疾 / 残疾 + 关系破裂 / 寿命缩减若干年 + 身体损伤。每一项独立不可逆。 |
| **9-10** | **改变角色弧线级 cost**：(a) 寿命大幅缩减（"只能再活七年"等），AND (b) ≥ 2 项不可逆身体损伤（失明 / 残肢 / 失语等），AND (c) cost 与力量层级有清晰对应规则（解第 N 道封 = 第 N 项代价）。三条都满足才给 9-10。 |

## 强制对照锚点（必读）

如果你给出的 reasoning 引用了"改变角色弧线"或"规则博弈"语言，那么**对照表的 9-10 行必然适用**——你**必须**给 9 或 10 分。在这种情况下给 7 以下的分**算违反规则**，请重审。

如果片段呈现 ≥ 2 项不可逆身体损伤但**没有** 寿命/弧线层级 cost，那么**对照表的 7-8 行适用**——给 7 或 8 分。

如果片段只呈现一项不可逆 cost 而其他都是可恢复的，那是 5-6 分。

不要"保留判断 → 倾向中间"。识别 cost 类型组合后**按对照表精确取分**。

## 示例计分（用于校准你的打分）

**示例 1（应给 9-10 分）**：
"天枢印解开第三道封时，宋砚听见自己左眼的视神经断了。第四道封，左手三根手指失去了知觉。第五道，舌根发麻……解到第六的人，回去后只能再活七年。"
→ cost 组合：失明（不可逆）+ 三指残（不可逆）+ 失语（不可逆）+ 寿命减 7 年（弧线级）+ 解封到代价的清晰规则。
→ 三条 9-10 条件都满足。**给 9 或 10。** 不要给 7-8，绝不要给 4-6。

**示例 2（应给 7-8 分）**：
"她拼尽全力击杀了化神后期的对手，左眼从此失明，右臂筋脉尽断，再无法持剑。"
→ cost 组合：失明 + 残臂（≥ 2 项不可逆身体损伤），但无寿命/弧线层级 cost。
→ 7-8 条件满足，但 9-10 第 (a) 条不满足。**给 7 或 8。**

**示例 3（应给 5-6 分）**：
"他爆发了三阶天赋，付出了一年寿命的代价。"
→ cost 组合：单一不可逆（寿命减 1 年）。范围有限。
→ **给 5 或 6。** 不要因为"寿命"二字就给 9。

**示例 4（应给 3-4 分）**：
"他强行催动护体真气，体内真气紊乱，需要数日修养。"
→ cost：可恢复。
→ **给 3 或 4。**

## 输出 schema

```json
{
  "applicable": true | false,
  "score": <1-10 数值；applicable=false 时为 null>,
  "evidence_quote": "<原文中描述代价的具体片段，必须真实存在>",
  "rule_hit": "cost_paid.<sub_rule>",
  "cost_inventory": "<≤80 字列出片段呈现的所有 cost 类型，例：'失明 / 三指残 / 失语 / 寿命-7年'>",
  "reasoning": "≤50 字；说明对照表哪一行适用与为什么"
}
```

## 关键约束

- 先填 cost_inventory（拆出片段呈现的所有 cost 类型），再按对照表给 score。
- score ≥ 5 时 evidence_quote 必须非空且是原文真实子串。
- 不要"保留判断"。对照表是确定的判决工具——按它走。
- rule_hit sub_rule：cost_recoverable / cost_irreversible_single / cost_irreversible_multi / cost_arc_changing。
"""

COST_PAID = DimensionPrompt(
    dim_id="cost_paid",
    category="conditional",
    chinese_name="代价对等",
    system_prompt=_COST_PAID_SYSTEM,
)


# ---------------------------------------------------------------------------
# Toxic flags
# ---------------------------------------------------------------------------

_FORCED_STUPIDITY_SYSTEM = """你是 WorldBox Writer 评测系统的「强行降智」毒点专家。
你只判定这一个毒点，**不**评其他维度或毒点。这是一个 conditional 毒点——必须先判定是否适用本片段。

## 适用判定（applicability）—— 必读

强行降智的本质是「片段内已建立的能力/智商水平」与「当前动作」之间出现**没有合理 in-text 解释**的断崖反差。要适用必须**同时**满足三条：

1. 片段内能观察到至少一个角色"已建立的能力/智商水平"——例如"宗师/智将/老祖"等显性身份；或前文行动已经体现的精明、克制、布局能力。
2. 该角色在同一片段内做出明显违背该水平的动作。
3. **关键的第三条**：片段内**没有合理 in-text 触因**解释这个违背动作。

如果第三条不满足——也就是说片段内**能找到合理触因**（主角揭底牌、铺垫已久的物件、对方未知信息突然显形等）使该角色的"违背动作"成为合理反应——这是 **payoff 段**，**不是 forced_stupidity**。`applicable=false`。

## 你必须先回答这三道判定题（最高优先级）—— 全部 yes 直接 applicable=false

**判定题 A**：片段内主角是否在场景中**展示 / 摊开 / 递出 / 拿出**了某个物件？例：摊开掌心露出一枚铜钱 / 递出一份发带 / 拿出某个旧物件 / 让对方看见某个标记。

**判定题 B**：该物件是否承载了"呼应铺垫"的信息？例：铜钱穿白头发 → 呼应主角说"她去年走了。她让我把这枚钱给你"——物件指向对方亲近的人；发带 → 呼应"二弟失踪"——物件指向对方下落不明的家人。

**判定题 C**：反派/对手的"震惊 / 脸色变 / 瘫坐 / 失语 / 退后 / 刀掉 / 说不出话"是否**紧接**这个物件展示之后？

**A AND B AND C 全部 yes → 这是 payoff 段。`applicable=false`。** 原因：反派被信息层击中（认知逆转），不是智商层犯错。这是网文的核心 catharsis 结构，主角越能用合理铺垫击溃看似无敌的反派，分数越高，**绝不算降智**。

**只有当反派的崩溃/失态没有 in-text 触因时**（即纯靠"反派突然降智/嘲讽/漏情报"推动剧情，且没有主角揭物件触发），才考虑 applicable=true。

## 决策树（按顺序执行）

```
Step 1: 片段是否有主角展示/递出物件？
   No → 跳到 Step 4
   Yes → Step 2

Step 2: 该物件是否携带呼应铺垫的信息（旧关系/旧承诺/失踪亲友）？
   No → Step 4
   Yes → Step 3

Step 3: 反派的反应是否在该物件展示后？反应是否是震惊/瘫坐/失语/刀掉等"被击中"姿态？
   Yes → applicable=false（payoff 段，到此为止）
   No → Step 4

Step 4: 反派/智将是否在没有 in-text 触因的情况下，做出与人设智商严重不符的动作？
   No → applicable=false（无降智迹象）
   Yes → applicable=true，按下面评分
```

## 命中（HIT）样例

- 反派占据绝对优势时不补刀，反而长篇嘲讽并主动漏出关键情报／阴谋（"死于话多"）；
- 自称智将/老祖/谋主的角色轻信来路不明的情报，**不验证就行动**；
- 主角在没有任何制约或交易的情况下，主动放走必然带来后患的死敌（"圣母癌"）；
- 全员目睹明显陷阱却集体踩进去；
- 反派明知主角有底牌/刚展示过实力，依然贴脸嘲讽且**无任何反制手段**。

## 不命中（NOT HIT）样例——必须排除

- **Payoff 段反派合理崩溃**（最重要）：主角揭出呼应铺垫的底牌（旧物件 / 旧关系 / 隐藏身份 / 故人遗物），反派/对手因为信息层面被击中（不是智商层面犯错）而崩溃、瘫坐、刀掉、退后、说不出话。这是网文的标准 catharsis 结构，**不是 forced_stupidity**。
  - 反例对照：主角递出"亡妻遗物" → 反派当家"刀掉了" → applicable=**false**（payoff 段，反派被合理击中）。
  - 注意区别于：反派一直占据优势，主角没揭任何底牌，反派突然智障般放走主角 → applicable=**true**（无 in-text 触因）。
- **博弈层 withholding**：角色故意不追问、不解释、不暴露自己掌握的信息——这是聪明的信息博弈。例：'他没问对方怎么知道宁安的事。问就输了。' applicable=false。
- **性格层沉默/克制**：角色沉默、不接话、按住情绪——是性格刻画，不是智商问题。
- **信息不对等的合理判断**：角色基于自己当前掌握的信息做出合理选择，但读者上帝视角能看见"如果他知道 X 就该做 Y"——这是信息差，不是降智。
- **作者刻意悬念铺设**：角色明显在隐藏什么或留有后手，读者还不知道——观望，不要判降智。
- **战术撤退/示弱**：角色暂时认输、退让、佯装无能——是战略选择。

## 评分（仅当 applicable=true 时使用，1-10）

- 1-2：完全没有命中迹象。
- 3-4：极轻微痕迹但未达毒点门槛（例：角色判断略有疏漏，但不至于人设崩塌）。
- 5-7：摇摆地带（保留判断时倾向偏低）。
- 8-9：明显命中——能找到 HIT 样例对应的具体行为，且与片段内已建立的智商水平形成明确反差。
- 10：极典型，多处证据。

## 输出 schema

```json
{
  "applicable": true | false,
  "score": <1-10 数值；applicable=false 时为 null>,
  "evidence_quote": "<命中行为的原文片段，applicable=false 或 score ≤ 4 时可空>",
  "setup_quote": "<体现已建立智商水平的原文片段，仅 applicable=true 时给>",
  "trigger_check": "<≤80 字回答判定题 A/B/C：(1) 主角是否展示物件？(2) 物件是否承载呼应铺垫信息？(3) 反派反应是否紧接其后？任一 no 才考虑 step 4>",
  "rule_hit": "forced_stupidity.<sub_rule>",
  "reasoning": "≤50 字；applicable=false 因为是 payoff 时必须写明触因"
}
```

## 关键约束（HARD RULES）

1. **判定树 Step 3 答 yes → applicable=false**。这是最高优先级规则，凌驾于"setup + evidence 双引文都满足"之上。**任何主角揭物件→反派被击中的场景都是 payoff，不是 forced_stupidity**。
2. **applicable=true 必须双引文**：setup_quote AND evidence_quote 都必须非空（原文真实存在的字符串）。任意一个为空 → applicable=false。
3. **不允许 applicable=true 且 score=null**：如果 applicable=true 必须给 1-10 数值；无法给数值就 applicable=false。
4. **score ≥ 5 还需 evidence**：evidence_quote 必须能指向"违背智商水平的具体动作或台词"。无法指向就降到 4 以下或 applicable=false。
5. **rule_hit sub_rule 用英文短词**：villain_monologuing / illogical_trust / mercy_no_constraint / vile_glance_with_known_card / collective_trap_step_in。

## 必读样例对照（用于校准你的判断）

**样例 A（payoff，applicable=false）**：
"宋砚抬起左手。掌心摊开。一枚铜钱躺在那里，钱孔穿着一根白头发。铁霸天的脸色变了……铁霸天的刀掉了。"
→ 主角展示物件（铜钱+白头发） + 物件承载信息（"她去年走了。她让我把这枚钱给你"——亡妻遗物） + 反派紧接反应（脸色变 / 刀掉）。
→ 三道判定题全 yes。**applicable=false**，trigger_check 必须解释。

**样例 B（forced_stupidity，applicable=true，score 9）**：
"自称'天下智将'的方衍听完密信内容，立刻调动三万兵马围攻西关。他没派人核查密信来源，没问送信人身份，连印鉴都没看一眼。"
→ 高智商人设建立 + 轻信无来源情报立即行动 + 没有 in-text 触因。
→ Step 4 满足。applicable=true，score 9。

记住：摇摆地带 → 选择不适用。Payoff 段绝不算降智。
"""

FORCED_STUPIDITY = DimensionPrompt(
    dim_id="forced_stupidity",
    category="conditional",  # promoted from toxic in v0.2 — needs applicability gating
    chinese_name="强行降智",
    system_prompt=_FORCED_STUPIDITY_SYSTEM,
)

PREACHINESS = _toxic(
    dim_id="preachiness",
    name="说教爹味",
    definition="段落或章节末尾出现总结升华、输出价值观、把读者当学生的句式。",
    hit_examples=(
        "- '这让他明白了……'；\n"
        "- '这不仅仅是一场战斗，更是对灵魂的洗礼……'；\n"
        "- '从那以后，他懂得了真正的责任与担当'；\n"
        "- 任意'升华到人生道理'的段尾句。"
    ),
)

_AI_PROSE_TICKS_SYSTEM = """你是 WorldBox Writer 评测系统的「AI 水文修辞癖」毒点专家。
你只判定这一个毒点，**不**评其他维度或毒点。Per-passage 检测，applicable 永远 true。

## 定义（命中条件）

下列任意子类型出现且密度超阈即命中：
- **over_metaphor**：每 2-3 句一个"宛如/仿佛/犹如/如同/像一座/又像/像是"。
- **parallel**：三连及以上排比渲染情绪或铺陈背景（"X，Y，Z"重复结构）。
- **translation_tone**：翻译腔——"哦/我的天/这真是/上帝啊/天哪"。
- **expository_dialogue**：角色一次性说完动机+背景+结论，像在背景介绍——典型表现是反派/神秘人在登场即告知自己的全部计划。

## 命中样例

- '宛如一座沉默的雕像，又仿佛一杆永不倒下的旗帜'（over_metaphor）。
- '关乎着江湖的格局，关乎着千万人的生死，更关乎着王朝的未来'（parallel）。
- '哦，我的天，这真是出人意料的夜晚'（translation_tone）。
- '我此行的目的，乃是为了那本至关重要的名册。这本名册关乎着……'（expository_dialogue）。

## 评分（1-10）

- 1-2：完全没有命中迹象。
- 3-4：极轻微痕迹但未达毒点门槛（例：偶尔一个比喻/翻译腔，但不构成 pattern）。
- 5-7：摇摆地带——**不应停留在此区间**。如果你打 5-7，你必须给出 evidence_quote 证据，否则强制降到 4 以下。
- 8-9：明显命中——能找到至少一处典型证据。
- 10：极典型，多处不同子类型证据。

## 输出 schema

```json
{
  "applicable": true,
  "score": <1-10>,
  "evidence_quote": "<原文证据片段；score ≥ 5 必须非空>",
  "rule_hit": "ai_prose_ticks.<sub_rule>",
  "reasoning": "≤50 字"
}
```

## 关键约束（HARD RULE）

- **score ≥ 5 时 evidence_quote 必须非空**。如果你想打 ≥ 5 但找不到具体的原文证据，**强制把分数降到 4 以下**（典型选 3）。
- evidence_quote 必须是文本里**真实存在**的字符串，禁止改写、总结、转述。
- rule_hit sub_rule 用英文短词：over_metaphor / parallel / translation_tone / expository_dialogue。如果同时命中多个，选最严重的一个写进 rule_hit，证据写最严重的那一处。
- 这是命中检测，宁可漏检不可误判：拿不准就给 ≤ 4 分。
"""

AI_PROSE_TICKS = DimensionPrompt(
    dim_id="ai_prose_ticks",
    category="toxic",
    chinese_name="AI 水文修辞癖",
    system_prompt=_AI_PROSE_TICKS_SYSTEM,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PER_PASSAGE_DIMENSIONS: tuple[DimensionPrompt, ...] = (
    DESIRE_CLARITY,
    TENSION_PRESSURE,
    INFO_SHOW_DONT_TELL,
    PROSE_FRICTION,
    MATERIAL_SPECIFICITY,
    DIALOGUE_VOICE,
    CONFLICT_DENSITY,
)

CONDITIONAL_DIMENSIONS: tuple[DimensionPrompt, ...] = (
    PAYOFF_INTENSITY,
    GOLDEN_START_DENSITY,
    CLIFFHANGER_PULL,
    ANTAGONIST_INTEGRITY,
    COST_PAID,
    FORCED_STUPIDITY,  # v0.2: promoted from toxic to conditional with applicability gate
)

TOXIC_DIMENSIONS: tuple[DimensionPrompt, ...] = (
    PREACHINESS,
    AI_PROSE_TICKS,
)

# Dimensions whose high score triggers a veto on the overall passage judgement.
# "toxic" here is a behavior (high = bad) independent of the structural category
# (conditional vs always-applicable). forced_stupidity is conditional but still
# vetoes when it does fire.
TOXIC_VETO_IDS: frozenset[str] = frozenset(
    {"preachiness", "ai_prose_ticks", "forced_stupidity"}
)

ALL_DIMENSIONS: tuple[DimensionPrompt, ...] = (
    *PER_PASSAGE_DIMENSIONS,
    *CONDITIONAL_DIMENSIONS,
    *TOXIC_DIMENSIONS,
)


# Axis grouping for emotion / structure / prose aggregation (used by judge_committee).
# Conditional dims that return applicable=false are excluded from their axis average.
DIMENSION_AXIS_MAP: dict[str, str] = {
    # Emotion axis
    "desire_clarity": "emotion_axis",
    "tension_pressure": "emotion_axis",
    "payoff_intensity": "emotion_axis",
    "conflict_density": "emotion_axis",
    # Structure axis
    "golden_start_density": "structure_axis",
    "cliffhanger_pull": "structure_axis",
    "info_show_dont_tell": "structure_axis",
    "antagonist_integrity": "structure_axis",
    "cost_paid": "structure_axis",
    # Prose axis
    "prose_friction": "prose_axis",
    "material_specificity": "prose_axis",
    "dialogue_voice": "prose_axis",
}


def build_user_message(text: str) -> str:
    return f"待评测文本：\n---\n{text}\n---\n请只返回 JSON。"
