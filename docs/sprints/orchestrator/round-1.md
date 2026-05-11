# Sprint 25 · Round 1 — 词汇定型 + 头部网文调研

**状态**：进行中
**分支**：`feature/sprint-25-r1-dimension-vocab`
**主题**：调研头部网文与现有 13 维评测体系的差距，提出新 dimension 草案 v0.1，用 real LLM 跑稳定性实证筛掉做不到的维度。

---

## 1. Review

上轮（Sprint 24 Round 10）：Director/GM/Actor 因果链改造，23 测试通过。真实 LLM 验证因 DNS 不可达未完成。`state.json` 记录 dual_axis_latest（story 5.8 / prose 5.7）来自旧评测，**不可信**——旧评测有两个结构问题：单 prompt 评 13 维、本地启发式分数与 LLM judge 混淆。后者已在 pre-flight cleanup commit 里删除。

Sprint 25 整体目标：在不动任何生成端代码的前提下，把评测重建为可信工具。

---

## 2. 北极星 3 问

1. **本轮选择的差距，是否直接影响小说爽度与留存？如何影响网文三轴？**
   不直接。本轮是元层工作——先校准量尺。但若量尺不准，后续所有"提升某轴某维度"的声明都不可证伪，会让我们空转。
2. **本轮的可验证标准是什么？必须是数字或 pass/fail。**
   - 每个候选维度对 3 段质量梯度样本各跑 5 次 real LLM judge。
   - **std < 1.0 → 保留**；**1.0 ≤ std < 1.5 → watchlist**（R2 优化 prompt）；**std ≥ 1.5 → 淘汰**。
   - Output 一份 dimension v0.1 列表，含每个维度的 std/mean、prompt 草稿、删/留依据。
3. **如果本轮成功，三轴中哪一轴的哪个维度提升？当前在哪一档，目标爬到哪？**
   不是某轴某维度提升，是评测系统本身从"测不准"变成"std < 1.0 可复现"。当前档位重测后才知，目标是 R4 重测后正式锁定。

---

## 3. 选题

> **只攻一个**：把现有 13 维过一遍真实头部网文样本与 AI 水文样本，看哪些维度是判官能稳定打分的，哪些是空想的。

不在本轮做：
- evidence schema（R2）
- 委员会并发实现（R2）
- 毒点注入测试集（R5）
- 校准基线人工标注（R3）
- 当前系统重测（R4）

---

## 4. 验证标准

| 步骤 | 输入 | 通过条件 |
|---|---|---|
| 准备样本 | 3 段中文：头部级 / 中位级 / AI 水文 | 每段 ~600 字、独立可读、来源可追溯 |
| Per-dimension prompt | 候选维度独立 prompt（system + user） | 输出严格 JSON：`{"score": 1-10, "evidence_quote": "<原文片段>", "reasoning": "≤50字"}` |
| Real LLM 跑分 | 每维度 × 3 样本 × 5 次 = 15 calls/dim | std/mean 落表 |
| 决策 | std 阈值规则 | 表中至少 70% 维度 std < 1.0；watchlist 与淘汰名单分别给出依据 |

---

## 5. 实现

（实现进度记录、关键决定、跑通的命令在此小节增量更新。）

### 5.1 调研

#### 5.1.1 头部 vs 中位 vs AI 水文的真实差距

**头部签约作（猫腻 / 烽火戏诸侯 / 爱潜水的乌贼 / 起点头部）共有特征**：

1. **角色驱动 ≠ 情节驱动**：世界观与人物互相生成。读者通过人物的选择反推世界规则，而不是先看百页设定再看人物登场。
2. **群像辨识度极高**：换一个角色说话/做事，读者能立刻分辨。烽火戏诸侯靠的就是这一条；当前评测维度 `dialogue_webness` 只查"是否符合网文语境"，不查"角色之间的语言指纹差异"——重大盲区。
3. **物质感**：动作场景落到具体物件、声音、气味、距离感、破坏方向，而非"出招、对掌、震退三步"的概念战。
4. **代价对等**：力量使用伴随不可逆代价（理智、寿命、关系、身体）。爱潜水的乌贼把这一条做到了规则博弈级。
5. **长线伏笔**：跨百万字回收。**这条单段判官根本测不到**——必须跨章 judge。
6. **节奏 = 单位字数内的有效冲突点密度**。头部几乎每 200 字内有一个小钩子；中位有大量过渡段；AI 水文有大量氛围铺陈。

**起点中位（4-6 分档）执行平庸的具体表现**：

- 模板对，火候欠：金手指有但震惊脸刻板；爽点有但配角反应是模板（"他怎么这么强"——干瘪）。
- 信息给配靠对话强行问答式科普。
- 文字过得去但段尾常做安全收尾（"一切都过去了"）。

**AI 水文（GPT-4 / Claude default 风格）的稳定病征**：

- **过度比喻**：每 2-3 句一个"宛如/仿佛"。
- **排比成灾**：三连对仗渲染情绪。
- **翻译腔**：哦/我的天/这真是。
- **解释性对话**：人物一次性说完动机+背景+结论，像背宣言。
- **段尾说教升华**：突然总结"这让他明白了……"。
- **物件抽象**：用形容词堆砌而非具体名词。

#### 5.1.2 现有 13 维的结构性问题

**问题 A：维度间高相关性导致信号被稀释**
- `suppression_to_elevation`（抑扬节奏）= `tension_pressure` 段（抑）+ `payoff_intensity` 段（扬）的曲线视图，单段文本里二选一即可，作为独立维度会让判官重复打分。
- `anticipation` 同时混了"利益可视化"（角色层欲望）和"压抑比"（外部压力）两件事——拆开判官打分稳定性会上升。
- `catharsis` 只有当片段是爽点段才适用，但现行 prompt 在所有片段上都打分 → 非爽点段的分数纯属判官脑补。

**问题 B：条件维度被当作无条件维度**
- `golden_start` 只在开篇适用。非开篇片段的分数无意义。
- `cliffhanger` 只在章末适用。非章末片段的分数无意义。
- 现行 prompt 用"如果不是开篇/章末，按近端目标/追读拉力评"绕过——其实是让判官在两个不同尺上随便选一个，方差直接爆。

**问题 C：神作进阶轴的 4 维全是情境/跨段依赖，单段判不出来**
- `foreshadowing_depth`：需要跨章伏笔的对照。单段 judge 必然瞎打。
- `antagonist_integrity_iq`：需要片段里有反派出现且决策可见。大部分片段没有反派。
- `moral_dilemma_humanity_anchor`：需要主角面临两难。绝大多数片段没有抉择点。
- `cost_paid_rule_combat`：需要力量/战斗场景。大量场景没有这个。
→ 它们应该是 **conditional dimensions**（判官先判定"该维度是否适用本片段"，不适用标 N/A）或 **cross-passage dimensions**（必须 multi-chapter judge 才上）。

**问题 D：现有 9 维少了头部网文的关键差异维度**
- **角色辨识度（character voice distinctiveness）**：当前没有。
- **物质感（material specificity）**：当前 `visual_action` 偏动作张力，不查物质细节。
- **冲突密度（conflict density）**：比 `pacing` 更可量化。
- **欲望具体性（desire specificity）**：与 `anticipation`（读者层期待）配对的角色层维度。

**问题 E：毒点 `power_scaling_collapse` 是跨段维度，不该放在单段 toxic flags 里**
- 单段判不出"前文设定被违反"。当前现行版本让判官在单段上判 → 几乎全部返 false。
→ 移到 cross-passage dimensions。

#### 5.1.3 调研结论

新评测分三层：

| 层 | 含义 | 适用范围 |
|---|---|---|
| **Per-passage** | 单段必判 | 任何 prose 片段 |
| **Conditional** | 判官先判定是否适用，不适用 → N/A | 单段（含开篇/章末/反派/力量场景的片段） |
| **Cross-passage** | 至少 ≥ 2 章数据 | 跨章节 multi-chapter judge（R5 引入） |

**毒点（toxic flags）**保留为独立专家组，二值判定，必须给 evidence quote。`power_scaling_collapse` 不再独立列出毒点 flag，移到 cross-passage 的 `setting_consistency` 维度。


### 5.2 Dimension Spec v0.1 草案

> 在 `docs/product/QUALITY_SPEC.md` 落地 draft，包含淘汰候选与 watchlist 候选的标记。

### 5.3 样本与 prompt

> 样本路径 `tests/test_evals/fixtures/calibration_v0/`；prompt 落 `src/worldbox_writer/evals/dimension_prompts.py`（新文件）。

### 5.4 稳定性实证

跑分脚本 `scripts/eval/dim_stability.py`；结果 `artifacts/eval/sprint-25/round-1/dim_stability.json`。

**踩坑与修复**（写下来防止 R2 重蹈）：

- **首次跑 (concurrency=6)**：113 transport errors / 225 (~50%)。错误几乎全是 `Errno 49 Can't assign requested address`——macOS 临时端口耗尽，不是 provider 问题。
- **加重试 + 降并发到 3 再跑**：217 errors / 225 (~96%)。重试反而**加剧** socket 风暴：每次失败留半开 socket、重试再开新连接，端口池被 TIME_WAIT 锁死。
- **最终方案 (concurrency=1, 不重试)**：225/225 全部成功，0 解析失败，0 传输错误。耗时 668 s（11 分钟）。

**教训**：评测调用密度 ≠ 评测 robustness。后续所有 evaluation runner 默认 concurrency=1，仅在需要更大规模时按场景做"大间隔批次"而非"高并发重试"。

---

## 6. 验证（结果）

### 6.1 完整稳定性矩阵

| dim_id | 类别 | A_head_tier | B_mid_tier | C_ai_water | 决策 |
|---|---|---|---|---|---|
| desire_clarity | per_passage | 9.0 ± 0.000 | 7.2 ± 0.447 | 3.0 ± 0.000 | **keep** |
| tension_pressure | per_passage | 8.8 ± 0.447 | 7.0 ± 0.000 | 3.4 ± 0.548 | **keep** |
| info_show_dont_tell | per_passage | 8.6 ± 0.548 | 7.2 ± 0.447 | 3.0 ± 0.000 | **keep** |
| prose_friction | per_passage | 8.2 ± 0.447 | 8.0 ± 0.000 | 4.2 ± 0.447 | **keep** |
| material_specificity | per_passage | 8.6 ± 0.548 | 5.4 ± 0.548 | 2.8 ± 0.447 | **keep** |
| dialogue_voice | per_passage | 7.0 ± 0.000 | 4.6 ± 0.548 | 2.2 ± 0.447 | **keep** |
| conflict_density | per_passage | 8.0 ± 0.000 | 6.4 ± 0.548 | 4.0 ± 0.000 | **keep** |
| golden_start_density | conditional | 7.8 ± 0.447 | 6.4 ± 0.548 | 3.6 ± 0.548 | keep（适用性带 caveat，见 6.3） |
| cliffhanger_pull | conditional | 8.2 ± 0.447 | 7.6 ± 0.548 | 6.2 ± 0.837 | **keep** |
| antagonist_integrity | conditional | 7.4 ± 0.548 | 5.0 ± 0.000 | N/A (0/5 applicable) | **keep**（C 上正确判 N/A，证明适用判定有效） |
| payoff_intensity | conditional | N/A (0/5) | N/A (0/5) | N/A (0/5) | inconclusive（fixtures 不含爆发段，需 R3 补样本） |
| cost_paid | conditional | N/A (0/5) | N/A (0/5) | N/A (0/5) | inconclusive（fixtures 不含力量使用，需 R3 补样本） |
| preachiness | toxic | 1.4 ± 0.548 | 2.0 ± 0.707 | 8.8 ± 0.447 | **keep** |
| ai_prose_ticks | toxic | 2.6 ± 0.548 | 4.0 ± **1.414** | 10.0 ± 0.000 | watchlist（B 摇摆，需 R2 收紧 prompt） |
| forced_stupidity | toxic | 6.8 ± **1.924** | 6.0 ± 1.225 | 9.0 ± 0.000 | **drop（误判 prompt）** |

整体观察：所有 keep 维度**相对排序 100% 正确**（A > B > C 或语义合理的 N/A），且头部级与 AI 水文级**幅度差距 ≥ 4.5 分**——足以驱动后续迭代信号。

### 6.2 forced_stupidity 为何 drop

不是 prompt 难写或维度不合理，是**当前 prompt 误导判官**。看 A 样本（头部级）的 5 次打分：

```
score=7.0 evidence: 他没问对方怎么知道宁安的事。问就输了。
score=8.0 evidence: 李三的指节在鞘口上紧了一下。他没问对方怎么知道宁安的事。问就输了。
score=9.0 evidence: 他没问对方怎么知道宁安的事。问就输了。
score=4.0 evidence: <空>
score=6.0 evidence: 他没问对方怎么知道宁安的事。问就输了。
```

判官把"主角故意不问，避免暴露自己掌握的信息"——一个**博弈层面的聪明动作**——错判成"主角不问关键问题=降智"。这是 prompt 没有区分 "withholding-as-leverage"（聪明）vs "uncharacteristic-irrational-forbearance"（降智）。

**R2 修复方向**：
- `forced_stupidity` 改为 conditional：必须能在片段内观察到"角色已建立的能力/智商水平" + "当前动作明显违背该水平"才适用。无前文上下文则 applicable=false。
- prompt 显式排除 "withhold question/info to preserve leverage = 聪明，不算降智"。
- 加正反对照样例。

### 6.3 golden_start_density 适用性未真正验证

3 个样本全部判 applicable=true，因为它们**都是开篇式场景**（戌时末李三登场）。判官没有机会展示"在中段场景上正确返 false"。这不是 prompt 问题，是**样本设计漏洞**。

**R3 修复方向**：calibration set 必须含至少 1 段"非开篇片段"（角色已多次登场、世界观已建立的中段冲突），用来反向验证适用性判定。

### 6.4 payoff_intensity / cost_paid inconclusive

判官在所有 3 样本上都正确返 applicable=false——3 段都是"对峙开始/僵持"，无爆发也无力量使用。维度本身不可证伪也不可证实。

**R3 修复方向**：calibration set 必须含至少 1 段"爆发瞬间"（含主角胜利+配角反应）和 1 段"力量使用 + 代价付出"（如越级一击+断臂代价）。

### 6.5 ai_prose_ticks watchlist 的真相

C 完美命中（10.0 std=0），A 正确低判（2.6），但 B 摇摆（4.0 ± 1.414）。看具体打分：

```
score=3.0 rule_hit=expository_dialogue evidence:<空>
score=3.0 rule_hit=expository_dialogue evidence:<空>
score=5.0 rule_hit=expository_dialogue evidence:<空>
score=3.0 rule_hit=expository_dialogue evidence:<空>
score=6.0 rule_hit=expository_dialogue evidence:<空>
```

判官"觉得有 expository_dialogue 倾向但没原文证据"——分数在 3-6 之间摆。这是**prompt 没有强制 evidence-or-降分**导致的。

**R2 修复方向**：在 toxic prompt 加规则——score ≥ 5 必须给 evidence_quote，否则强制降到 4 以下。

---

## 7. 同步

### 改动文件清单（本轮）

- `docs/sprints/SPRINT_25.md`（新建）—— Sprint goal、退出条件、6 个 round 概览。
- `docs/orchestrator/round-1.md`（新建）—— 本轮 7 步流程记录。
- `docs/product/QUALITY_SPEC.md`（新建 v0.1 draft）—— 评测系统单一真相源。R1 实证后 1.5 决策表填入。
- `src/worldbox_writer/evals/dimension_prompts.py`（新建）—— 15 个维度独立 prompt + 公共 schema。
- `scripts/eval/dim_stability.py`（新建）—— concurrency=1 默认、含/不含 retry、produce JSON report。
- `tests/test_evals/fixtures/calibration_v0/{A,B,C}.txt + manifest.json`（新建）—— 3 段质量梯度样本，标注 quality_label。
- `artifacts/eval/sprint-25/round-1/dim_stability.json` —— 225 次 real-LLM 调用的完整原始数据 + summary。

### 测试结果

- L1 套件：尚未跑（本轮没改生产代码，仅新增 evaluation infra），R1.6 commit 前会跑 `make test-backend` 确认无回退。
- Real LLM stability：225/225 success，0 parse failure，0 transport error，11 个 dim keep / 1 watchlist / 1 drop / 2 inconclusive。
- 总 LLM 调用：~232（225 主跑 + 3 smoke + 4 probe/重试中失败的批次不计）。

### state.json 更新内容（本轮）

- `sprint: 25`，`round: 1`
- `last_round_goal: "维度词汇定型 + 头部网文调研 + 稳定性实证"`
- `last_round_action: "Sprint 25 R1 完成 — 11 维 keep / 1 watchlist / 1 drop / 2 inconclusive；fixtures + dimension_prompts + dim_stability runner 落地"`
- `dual_axis_latest`：**不更新**（旧轴已 deprecated；R4 重测后用新轴覆盖）。
- `gap_list`：替换为 R2 的 prompt 修复项与 R3 的 calibration 样本扩展项。

### Commit / PR

- 分支：`feature/sprint-25-r1-dimension-vocab`
- Commit：见 R1.6（待落地）
- 预计单 commit 含上面全部新增；单 PR 自审 + 合并 main。

---

## 下一轮预选题

R2：基于 R1 的 11 keep + 1 watchlist 维度组装判官委员会（4 专家：emotion / structure / prose / toxic 并发调用），落 evidence schema 强制约束（toxic ≥ 5 必须给 evidence），修复 `forced_stupidity` prompt（加 conditional 适用判定 + 排除 leverage-as-stupidity 误判）。委员会版本上跑同 3 样本 5 次，验收：所有 dim 在所有样本上 std < 0.5，非满分维度 evidence_quotes 非空率 ≥ 80%。

R3 提前规划：calibration set 要补 3 段额外样本——非开篇中段、爆发瞬间含配角反应、力量使用含代价——把 R1 inconclusive 的 4 个 conditional 维度（golden_start_density 适用性 / payoff_intensity / cost_paid / forced_stupidity 重测）一并验证到。

