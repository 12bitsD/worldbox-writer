# Codex 接力手册 — Sprint 25 → Sprint 26+

**目标读者**：接手 WorldBox Writer 迭代的 Codex agent
**前置阅读（必读，按顺序）**：

1. 本文件（先读）
2. `docs/orchestrator/state.json` 的 `handoff_to_codex` 字段——任务清单
3. `docs/product/QUALITY_SPEC.md` v1.0——评测系统 single source of truth
4. `CLAUDE.md`——仓库导览
5. `AGENTS.md`（root + `src/worldbox_writer/AGENTS.md` + `frontend/AGENTS.md`）——执行契约

不读完 1+2 就开干会浪费 2-4 round 重新发现已经踩过的坑。

***

## 一、绝对禁止（违反这些 = 工作直接作废）

### 1.1 评测纪律

- **不准为了让 gate 通过而调阈值**。失败 gate 是诊断信号，不是要被绕过的障碍。Sprint 25 R3 ranking ρ=0.56 时我没调到 0.5，而是修 prompt 让分数自然涨到 0.985。
- **不准把 calibration manifest 排序"调成跟委员会输出一致"以提升 Spearman**。这叫 commit-fit / 数据造假。manifest 排序必须有 in-text 可辩护的理由（产品定位 / 网文 lens 等）。R4 重排 G4 文学型从顶位下移有理由（产品对标起点头部，文学型本就该被网文 lens 打中位）；如果你想动 manifest，先在 PR 描述里写清产品逻辑。
- **不准在** **`make test`** **/ 默认 PR 门禁里跑真实 LLM**。L1 必须毫秒级、纯 mock。真实 LLM 跑分用 `scripts/eval/*.py` 直接调用，artifact 落 `artifacts/eval/sprint-N/round-M/`。
- **不准用** **`pytest`** **跑真实 LLM 验证**。`@pytest.mark.integration` 是 manual 触发的（`make integration`），不要把它纳入回归集 mock。L1 mock 与 real LLM eval 是两个独立通道。
- **不准删除** **`artifacts/eval/sprint-25/*`** **的任何文件**。这些是 Sprint 25 的实证数据，是后续轮次回头比对的基准。`.gitignore` 的 `!artifacts/eval/` 例外是有意为之。

### 1.2 macOS 网络硬约束

- **任何真实 LLM eval 默认** **`concurrency=1`**。R1 用 concurrency=6 时 50% 调用挂在 `Errno 49 Can't assign requested address`（macOS 临时端口耗尽）。这不是 provider 问题，是 OS 限制。如果你看到大量 `Errno 49`，立即降到 1，**不要加重试**——重试会放大 socket 风暴让情况更糟（R1 教训：concurrency=3 + 重试导致 96% 失败率）。
- 如果 Codex 在 Linux 容器里跑，concurrency 可调高，但**不要修改默认值**——其他人本地仍在 macOS。

### 1.3 Git 纪律

- **不准** **`git push --force`**。
- **不准** **`git commit --amend`**（pre-commit hook 失败时也用新 commit 修复，不要 amend）。
- **不准** **`--no-verify`** **跳 hook**。如果 hook 失败，修根因。
- **不准修改** **`.github/workflows/*`** **与** **`Makefile`** **的 CI 命令路径**——CI 单一入口约定（root `AGENTS.md` 第 60 行）。
- **不准提交** **`.env`** **/** **`worldbox.db`** **/** **`artifacts/reports/*`** **/** **`frontend/artifacts/`**——已 gitignore，不要白名单。
- **commit 必须用 Conventional Commits**：`feat(eval): ...` / `fix: ...` / `docs: ...` / `chore: ...` / `test: ...`。

  <br />

### 1.4 评测 API 纪律

- **不准重新引入 deprecated judge API**：`judge_prose / judge_story / judge_scene_script / batch_judge / aggregate_judge_results / build_*_judge_prompt`——这些在 R6 已删除。所有评测必须走 `judge_committee` + `judge_multi_chapter`。
- **不准把 single-prompt 多维度评测路径加回来**——R1 实证证明它在 12 维上 score 互相污染。
- **不准在** **`judge_committee`** **调用上不传** **`concurrency=1`**（除非你在 Linux 容器跑）。
- **不准在 evaluation runner 里用启发式打分**（关键词命中 / 字数 / 比喻密度等）——`docs/product/QUALITY_FRAMEWORK.md`（已变索引）和 `QUALITY_SPEC §2.7` 明令禁止。

### 1.5 Schema 纪律

- **不准默修** **`core/models.py`** **的 WorldState / StoryNode / SceneScript / Character 字段**——前后端契约（`frontend/src/types/index.ts`）会断。要修先看 `CLAUDE.md` 的 high-risk 文件清单。
- **不准默修** **`engine/graph.py`**——LangGraph 状态图是 dual-loop 的核心。
- **不准默修** **`utils/llm.py`** **的 provider routing**。

***

## 二、强制工作流（按这个流程，否则信号噪声大）

### 2.1 每轮 7 步（Sprint 25 沿用至今）

1. **Review**：读 `state.json` + 上轮 `round-(N-1).md`，对齐当前差距
2. **自检**：北极星 3 问，写入 `round-N.md`
3. **选题**：从 gap\_list 挑 1 个，**只攻一个**
4. **设标**：写下"X 指标从 A → B"。**必须是数字或 pass/fail，不准写"提升流畅度"这种**
5. **实现**：先写 L1 mock 测试 → 写代码 → 跑 real LLM eval
6. **验证**：跑完 eval 对比基线，结果写进 `round-N.md` §6 — 包括失败
7. **同步**：`state.json` + `round-N.md` + sprint 文档 + git commit + merge + push

每轮交付物：

- `artifacts/eval/sprint-N/round-M/<runner>.json`：本轮 eval 报告
- `docs/orchestrator/round-N.md`：完整 7 步流程记录
- `docs/orchestrator/state.json`：current\_phase / spec\_version / gap\_list / handoff\_to\_codex 更新
- 1 个 commit（或 PR）

### 2.2 分支与提交

- 分支：`feature/sprint-N-rM-<topic>`，例：`feature/sprint-26-r1-narrator-ai-tics`
- 跑 `make lint` + `make test-backend` 通过才 commit
- 如果 black 抱怨 `would reformat`，跑 `.venv/bin/python -m black <file>` 再 lint
- merge 用 `--no-ff`（保留分支拓扑）：`git merge --no-ff feature/... -m "Merge — ..."`
- merge 后 `git branch -d` 删本地分支，`git push origin main`

### 2.3 真实 LLM eval 调用方式

```bash
# 跑当前生产 baseline（Sprint 26 改 Narrator 后必跑）
.venv/bin/python scripts/eval/baseline_current_system.py --chapters 4 --judge-runs-per-chapter 2

# 跑毒点注入回归（fast feedback，每次改 narrator/agent prompt 必跑）
.venv/bin/python scripts/eval/toxic_injection_regression.py --runs 3

# 跑 calibration ranking（修维度 prompt 后必跑）
.venv/bin/python scripts/eval/calibration_ranking.py --runs 3

# 跑 cross-passage 验证（修 multi-chapter 维度后必跑）
.venv/bin/python scripts/eval/cross_passage_validation.py --runs 3
```

**所有 runner 写 artifact 到** **`artifacts/eval/sprint-N/round-M/`**——记得提前 mkdir + 改 default output 路径。

### 2.4 验证前不能宣告完成

每轮 §6 必须填**真实数据**：

- ✗ "看起来工作正常"
- ✗ "测试通过"（默认空话）
- ✓ "L1 211 → 217 passed，无回退；real LLM baseline overall 3.73 → 6.4，veto rate 46% → 8%"

如果你跑了 real LLM 验证然后 gate 失败，**先把失败诊断写进 §6**，再决定是修问题还是接受 trade-off 文档化。**不要瞒报**。

***

## 三、容易踩的坑（Sprint 25 的累积教训）

### 3.1 整数 1-10 打分系统的 std 自然下限

5 次跑分在 1-10 整数轴上，相邻 2 个值（如 \[8,8,9,9,9]）的 std = **0.548**。这是数学下限，不是判官不稳。如果你写 gate "std < 0.5"，等于强制"5 次同分"。

**正确做法**：

- 单 dim std 阈值用 0.6 或 1.0（按 dim 容忍度）
- 委员会整体 overall std 用 1.0
- 边界样本（mid-tier）允许 std < 2.0

R2 §6.4 / R5 §6.3 有详细推导。

### 3.2 vetoed 与非 vetoed runs 不能混算 std

如果一个样本 5 次跑分中 2 次 vetoed = 0，3 次正常 = 6.4-6.8，混着算 std 是**虚高**（0 与 6.x 拉远了 stdev）。**正确做法**：

- 算 stability 指标时只看非 vetoed runs
- veto 行为单独看 veto\_rate / veto\_count 指标

R5 cross\_passage\_validation.py 的 gate 逻辑就这么写的。

### 3.3 `judge_committee` 的 toxic veto 是**OR**逻辑

- `preachiness ≥ 8` → veto
- `ai_prose_ticks ≥ 8` → veto
- `forced_stupidity ≥ 8 AND applicable=true` → veto

**任何一个**命中就 veto，不需要全部。`forced_stupidity` 是 conditional（applicable 可 false），但**仍参与 veto**——这是 `TOXIC_VETO_IDS` frozenset 的设计。看 `dimension_prompts.py` 末尾的常量定义。

### 3.4 `evidence_quote` 必须是原文真实子串

判官给的引用如果不在原文里（fabricated），`_committee_call_one` 会自动降分到 4 以下。**不要绕过这个校验**。如果你看到一个 evidence 应该匹配但被标 invalid，问题大概是判官改写了引用——这本身就是 bug 信号。

`forced_stupidity` 还要校验 `setup_quote`（智商基线引用）。两个 quote 都需要在原文里。

### 3.5 normalization 限于引号字符

`_QUOTE_NORMALIZATION` 把 curly 引号 `"" ''` 归一化到 straight `" '`。**不要**把它扩展成 Chinese 标点 ↔ English 标点的全套互译——那会让判官伪造的引用通过。

### 3.6 forced\_stupidity v0.4 的 trade-off

R4 强化 prompt 防 payoff 段误判（"反派被合理底牌击溃" 不算降智），副作用是 R5 毒点回归集上 hit\_1（反派死于话多）召回 0/3。如果 Codex 想提升 recall，**先确认改完不会让 R5 clean\_3 (payoff\_with\_trigger) 重新被误判**——那是 R3 痛点的 regression test。

### 3.7 cost\_paid v0.2 的 example-based scoring

R4 实测：description-based scoring（"代价惨烈"等抽象词）让模型默认落 4-6 mid。改成 example-based + cost\_inventory 后从 \[4,4,4,4,9] 升到 7+。**不要回退到抽象描述 anchor**。如果加新 anchor，**给具体范例 + 对照表**。

### 3.8 calibration manifest 必须双更新

- `authoring_intent_ranking` 是 ordered list
- `mandatory_pairs_must_not_reverse` 是 list of \[high, low] tuples

任何一个改了，另一个要同步。`mandatory_pairs` 是更严的约束（强制 high>low），ranking 是 Spearman 计算用的整体序。R4 v1.2 的两次重排可作为参考模式。

### 3.9 Sprint docs 白名单

`tests/test_docs/test_sprints_directory.py` 锁了 `docs/sprints/` 的白名单。新增 SPRINT\_N.md 时**同步加白名单**否则 L1 测试挂。

### 3.10 跨章节 judge 输入 ≥ 2

`judge_multi_chapter([single_chapter])` 直接返 `applicable=false` 不调 LLM。这是设计——单章用 `judge_committee`，多章用 multi-chapter。两者结构不同，不要混用。

***

## 四、Sprint 26 第一个 round 的具体实施建议

**任务 S26-R1**：Narrator AI 水文修辞癖修复

具体步骤（你可以按这个走，每步都有验证）：

### 步骤 1：开分支 + round-1.md

```bash
git checkout main && git pull
git checkout -b feature/sprint-26-r1-narrator-ai-tics
mkdir -p artifacts/eval/sprint-26/round-1
```

写 `docs/orchestrator/round-1.md`（**注意**：是 sprint-26 的 round-1，不是覆盖 sprint-25 的 round-1.md。你需要改 round 文件命名约定，例如 `docs/orchestrator/sprint-26/round-1.md`，或者加 sprint 前缀）。

### 步骤 2：分析当前 Narrator prompt

`src/worldbox_writer/agents/narrator.py` 的 `_NARRATOR_SYSTEM_PROMPT`。已经有"负面约束"段，但显然不够具体（baseline 上 46% chapter 还是被 ai\_prose\_ticks 抓住）。

阅读 `src/worldbox_writer/evals/dimension_prompts.py` 的 `_AI_PROSE_TICKS_SYSTEM` —— 它列了 4 个子类（over\_metaphor / parallel / translation\_tone / expository\_dialogue）+ 阈值。Narrator prompt 必须**显式禁用这 4 子类的具体形式**，并给反例对照。

### 步骤 3：先写 L1 mock 测试

在 `tests/test_agents/test_narrator.py` 加一个测试（如果文件不存在，新建），mock chat\_completion 返回带 AI 水文 tics 的 prose。验证：

- Narrator 检测到 toxic 后会调用 `judge_committee` 自检（如果你加了自检回路）
- 或：Narrator 输出在跑 toxic\_injection\_regression 上 score < 8

### 步骤 4：改 Narrator prompt

加 4 个子类的显式禁用 + 对照样例。可参考 `dimension_prompts.py::_AI_PROSE_TICKS_SYSTEM` 的命中样例（直接复用）。

### 步骤 5：跑 baseline\_current\_system.py

```bash
.venv/bin/python scripts/eval/baseline_current_system.py \
    --chapters 4 --judge-runs-per-chapter 2 \
    --output artifacts/eval/sprint-26/round-1/baseline_v2.json
```

预计跑 25-30 分钟。完成后看 aggregate.veto\_rate（目标 ≤ 0.10）和 overall\_mean（目标 ≥ 6.5）。

### 步骤 6：跑毒点注入回归确认没破坏

```bash
.venv/bin/python scripts/eval/toxic_injection_regression.py \
    --runs 3 \
    --output artifacts/eval/sprint-26/round-1/toxic_injection_post_narrator_fix.json
```

确保 preachiness 100% recall 守住，FP rate 仍 0%。

### 步骤 7：填 round-1.md §6 + commit

写实测数据（不要写"看起来好"），commit + merge + push。

### 步骤 8：更新 state.json

- `current_tier` 从 `L0` 改为新档（按 baseline\_v2 的 overall\_mean / axis\_means / veto\_rate）
- `last_round_action` 写实测增益
- 新 gap\_list（下一个 round 选题）

***

## 五、不确定时的默认行为

- **不确定要不要做 X**：在 round-N.md §3 选题里写"不在本轮做 X (理由：Y)"，跳过。Sprint 25 每个 round 都列了"不在本轮做"——明确边界。
- **不确定 prompt 改对没**：跑 toxic\_injection\_regression 看是否 false positive，跑 calibration\_ranking 看 Spearman 是否退步。两条不退步就算改对。
- **不确定 baseline 数据可不可信**：跑两遍取均值。R4 baseline 跑了一遍但 std 在 simulation 内可对照。
- **看到自己写的"应该 work"**：跑实证确认。Sprint 25 全程"实证 > 直觉"。

***

## 六、当 Codex 撞墙时

如果你遇到：

- macOS 端口耗尽 → 降 concurrency 到 1，**不要重试**
- Spearman 上不去 → 看 mandatory\_pair\_violations，定位具体反转，决策修 prompt 还是接受 trade-off 文档化
- Toxic recall 上不去 → 看哪个 hit 样本被漏检，定位 prompt 哪条规则太保守
- L1 测试挂在 deprecated import → 不要恢复 deprecated API，改测试用 judge\_committee
- 看到自己写的代码不知道为啥 work / 不 work → **跑实证再说**

***

## 七、需要人类协助的 escalation 信号

以下情况停下来等人类决定：

- 维度集合需要增 / 删（已经第二次重排 manifest）
- 评测系统从单审美扩到双审美（网文 + 文学）
- 引入新的 evaluation provider / 切换 LLM 模型
- 重大架构变更（碰 high-risk files: `core/models.py` / `engine/graph.py` / `utils/llm.py`）
- 用户明确要求停下

***

## 八、最后

Sprint 25 累积了 \~3000 次 real LLM 调用、6 个 round 的实证教训。这份手册是把那些教训"硬编码"给后来者，让你不用从 0 开始踩坑。

**最重要的一条**：评测系统是诚实的工具。每一次 gate 失败都是它在告诉你"这条路有问题"。**不要试图绕过它**——绕过的代价是后续 Sprint 全部基于错误数据，发现时已经晚了所以一定不要做任何降级！！！ 失败了就是失败了！降级兜底没有意义。

继续。
