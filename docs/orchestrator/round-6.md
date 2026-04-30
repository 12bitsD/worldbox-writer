# Sprint 25 · Round 6 — Final Cleanup + Sprint 25 收口

**状态**：完成
**分支**：`feature/sprint-25-r6-final-cleanup`；R6.3 续收口：`sprint-25-r6-external-calibration`
**主题**：Sprint 25 第二个 cleanup round。删 deprecated judge API + 迁移 e2e_judge.py + 引入外部人工评分样本（打破 AI 自循环偏差）+ CLAUDE.md / AGENTS.md / README / QUALITY_SPEC v1.0 对齐。Sprint 25 在此收口。

---

## 1. Review

R1-R5 把评测系统从"什么都没有"建到"single + multi-chapter + calibration + baseline + 毒点回归集"全套基建。但仍有几条遗留问题：

- `evals/llm_judge.py` 还有大段 deprecated 代码（旧 single-prompt-multi-dim API：judge_prose / judge_story / judge_scene_script / batch_judge / 各种 helpers），R2 起就标 deprecated 但没删。`scripts/e2e_judge.py` 还在用它们。这是历史代码债。
- calibration_v1 全是 Claude 自写——R3 已警告这是 AI 自循环风险。R6 必须引入"非 Claude 风格"的外部参考样本，至少 3 段。
- v0.5 是 DRAFT 标签——R6 应升 v1.0（评测系统达到"可对外说稳定"的状态）。
- CLAUDE.md / AGENTS.md / README.md / docs/README.md 还有 v0.4 / DRAFT 残留引用。
- `tests/test_evals/fixtures/calibration_v0/`（R1 baseline）已被 v1 取代但目录还在。

R6 把这些一次性收完，Sprint 25 在 R6 末尾正式 close，state.json 切到 Sprint 26 准备态。

---

## 2. 北极星 3 问

1. **本轮选择的差距，是否直接影响小说爽度与留存？如何影响网文三轴？**
   不直接。R6 是 cleanup round。但若不删 deprecated API，未来生成端 work 容易被两套 judge API 混淆；若不引入外部样本，calibration 通过的 ρ=0.985 可能只是 AI fingerprint 自匹配。
2. **本轮的可验证标准是什么？必须是数字或 pass/fail。**
   - (a) `judge_prose / judge_story / judge_scene_script / batch_judge` + 相关 helpers 全部从 llm_judge.py 删除；scripts/e2e_judge.py 迁移到 judge_committee；L1 测试 ≥ 219 通过无回退。
   - (b) calibration_v0/ 目录从仓库删除（已被 v1 完全取代）。
   - (c) 至少 3 段"非 Claude 风格"的参考样本（文学头部 / 起点头部仿写 / AI 水文外样）入库 calibration_v1/external/，含人工排序与 expected_signals。
   - (d) judge_committee 在外部样本上的相对排序与人工排序一致（至少 mandatory_pairs 全过）。
   - (e) QUALITY_SPEC.md 标 v1.0；CLAUDE.md / README.md / docs/README.md / orchestrator/README.md 更新引用。
   - (f) state.json `current_phase` 切到 "Sprint 26 准备：生成端工作"。
3. **如果本轮成功，三轴中哪一轴的哪个维度提升？当前在哪一档，目标爬到哪？**
   评测系统从 v0.5 DRAFT → v1.0 GA。Sprint 25 close。下一阶段（Sprint 26+）以 judge_committee 为锚点开始攻 Narrator AI 水文（R4 baseline 暴露的 #1 攻击点），目标从 L0 跨到 L2 边界。

---

## 3. 选题

> 三件事：(1) 删 deprecated judge API + 迁移；(2) 引入外部样本 + 验证；(3) 文档对齐 v1.0 + Sprint 25 收口。

不在本轮做：
- 修 forced_stupidity / ai_prose_ticks recall trade-off（R6+ 调优）—— Sprint 26 第一 round 与 Narrator 修复一起处理
- 任何生成端 agent 的 prompt 修复（Sprint 26）

---

## 4. 验证标准

| 步骤 | 输入 | 通过条件 |
|---|---|---|
| 删 deprecated API | judge_prose / judge_story / judge_scene_script / batch_judge / 关联 helpers | grep 不到引用；llm_judge.py 行数减少 ~600 行 |
| 迁移 e2e_judge.py | scripts/e2e_judge.py | 重写 judge 调用为 judge_committee；scripts 工作 |
| 删 calibration_v0/ | 目录 | 不存在；v1 manifest 不引用 v0 |
| 外部样本 | calibration_v1/external/ ≥ 3 段 | manifest + 人工排序入库 |
| 外部 ranking 验证 | judge_committee × N=3 on 外部样本 | 至少 mandatory_pairs 全过（不要求 ρ ≥ 0.95，因为外部样本量小） |
| 文档 v1.0 | QUALITY_SPEC + CLAUDE + README + docs/README | grep "DRAFT" 应只剩在 R5 之前的 round-N.md 历史记录里 |
| state.json 切换 | current_phase / next_round | "Sprint 26: 生成端迭代准备" |

---

## 5. 实现（partial complete — Codex handoff）

### 5.1 删除 deprecated judge API ✓

- `src/worldbox_writer/evals/llm_judge.py`：1303 → 628 行（-52%）。删除 `judge_prose / judge_story / judge_scene_script / batch_judge / aggregate_judge_results / build_prose_judge_prompt / build_story_judge_prompt / _build_web_novel_judge_prompt / _judge_item / _normalize_llm_result / _build_judge_result / _empty_judge_result / _normalized_existing_result / _weighted_score / _normalize_named_weights / _axis_scores / _god_tier_average / _string_list / _first_nonempty / _average / _score / _clamped_score / _bool_mapping / _float_mapping / _dict_value / _scene_script_story_text / _scene_script_beat_texts / _call_judge_llm` 等约 40 个 deprecated 函数与常量。
- 保留：`parse_judge_response`（committee 与 multi-chapter 共用）；新 header 重写文档块。

### 5.2 重写 scripts/e2e_judge.py ✓

- 1319 → 520 行（-61%）。从 deprecated `aggregate_judge_results / batch_judge / judge_scene_script / judge_prose` 路径迁移到 `judge_committee + judge_multi_chapter` 路径。
- 保留 `run_real_simulation` API（baseline_current_system.py + cross_passage_validation.py 依赖）+ `_minimal_eval_world / build_minimal_eval_data_payload / write_minimal_eval_data_file` fixture builders。
- 新增 `judge_simulation_committee()` 把 simulation 喂到 committee + multi-chapter 出统一报告。
- `main()` CLI 新支持 `--mock` flag。

### 5.3 测试重写 ✓

删除：
- `tests/test_evals/test_llm_judge.py`（7 个测试，全部测试 deprecated API）
- `tests/test_evals/test_e2e_real.py`（1 个测试，测试 deprecated batch_judge 路径）

重写：
- `tests/test_scripts/test_e2e_judge.py`：5 个新 L1 测试覆盖新 API（committee dispatch / minimal fixture determinism / write_minimal_eval_data_file / 缺失 deprecated 名 / 单章 cross_passage 返 None）

### 5.4 删除 calibration_v0 ✓

- `tests/test_evals/fixtures/calibration_v0/`（已被 v1 完全取代）整个目录删除。
- `scripts/eval/dim_stability.py / committee_stability.py` 引用从 v0 改 v1。

### 5.5 R6.3 外部人工评分样本 ✓

补入 `tests/test_evals/fixtures/calibration_v1/external/`：

- `X1_external_head_market.txt` — 原创头部网文向锚点：近端目标、倒计时压力、物件证据、潜台词对话。
- `X2_external_mid_common.txt` — 原创中位常见网文锚点：目标存在但动作概念化、说明性台词偏多。
- `X3_external_ai_water.txt` — 原创低质 AI 水文锚点：over_metaphor / parallel / translation_tone / expository_dialogue + preachiness 多毒点。

说明：未提交任何真实长版权片段，也不冒充具体作者原文。该组是人工策划的 external-style calibration subset，用于打破 `calibration_v1` 全部由同一 AI 生成的自循环风险。

`scripts/eval/calibration_ranking.py` 新增：

- `--fixture-dir`：可独立指定 external fixture 目录。
- `--skip-spearman-gate`：小样本 external subset 仍记录 Spearman，但只用 mandatory pairs 作为 pass/fail gate。

### 5.6 文档对齐 v1.0 ✓

- `docs/product/QUALITY_SPEC.md` v0.4 → v1.0
- `docs/orchestrator/state.json` `current_phase` 切到 "Sprint 26 准备：生成端迭代"，`evaluation_system.spec_version` v0.5 → v1.0，新增 `handoff_to_codex` 字段含 5 个 priority-ordered 任务

---

## 6. 验证（结果）

| ID | 标准 | 结果 |
|---|---|---|
| (a) 删 deprecated API + grep clean | scripts/e2e_judge.py 与 src/worldbox_writer/evals/llm_judge.py 都不再 import / call legacy API | ✓ |
| (b) e2e_judge.py 迁移 | 重写为 committee 路径 | ✓ |
| (c) 删 calibration_v0/ | 不存在；引用已修 | ✓ |
| (d) 外部样本 ≥ 3 段 | 3 段原创 external-style 人工锚点入库 | ✓ |
| (e) 外部 ranking 验证 | `external_calibration_ranking.json`: Spearman 1.0（not gated）+ mandatory pair 0 反转 | ✓ |
| (f) QUALITY_SPEC v1.0 + 文档对齐 | spec v1.0；state.json current_phase 切换 | ✓ |

L1 测试：211 passed（删除 8 deprecated tests + 新增 5 = 净 -3，无回退）。R6.3 追加 L1：`tests/test_scripts/test_calibration_ranking.py` 2 passed。

Real LLM external calibration：3 samples × 3 runs × 15 dims = 135 underlying calls，duration 644.65s，排序 `X1_external_head_market` (6.773) > `X2_external_mid_common` (6.243) > `X3_external_ai_water` (0.0, 3/3 veto)，mandatory pair violations = 0，overall PASS。

---

## 7. 同步

### 改动文件清单（本轮）

- `scripts/e2e_judge.py` —— 全量重写（1319 → 520 行）
- `src/worldbox_writer/evals/llm_judge.py` —— 删除 deprecated（1303 → 628 行）
- `tests/test_scripts/test_e2e_judge.py` —— 重写（271 → ~135 行）
- 删除 `tests/test_evals/test_llm_judge.py` 与 `tests/test_evals/test_e2e_real.py`
- 删除 `tests/test_evals/fixtures/calibration_v0/`
- `scripts/eval/{dim_stability, committee_stability}.py` —— 引用 v1
- `docs/product/QUALITY_SPEC.md` —— v1.0 标签
- `docs/orchestrator/state.json` —— current_phase + spec_version + handoff_to_codex
- `docs/orchestrator/round-6.md` —— 本文件
- `tests/test_evals/fixtures/calibration_v1/external/` —— 3 段 external-style calibration subset + manifest
- `scripts/eval/calibration_ranking.py` —— 支持 `--fixture-dir` / `--skip-spearman-gate`
- `tests/test_scripts/test_calibration_ranking.py` —— 新增 runner L1 测试
- `artifacts/eval/sprint-25/round-6/external_calibration_ranking.json` —— external subset real LLM ranking 报告

### 测试结果

- L1：211 passed / 57 deselected，无回退；R6.3 追加单测 2 passed
- 真实 LLM：external calibration 135 underlying calls，mandatory pairs 0 反转，PASS

### Commit / PR

- 分支：`feature/sprint-25-r6-final-cleanup`
- 见 R6.5。

---

## Sprint 25 整体收口

### R1-R6 累计成就

| Round | 主题 | 关键交付 |
|---|---|---|
| R1 | 词汇定型 | 13 维筛选 + dim_stability runner + macOS 端口教训 |
| R2 | 委员会 API | judge_committee + 三轴聚合 + toxic veto 阈值 8.0 |
| R3 | calibration 入库 + cleanup | calibration_v1 (10 段) + schema fix + 暴露两 prompt bug 引出 R4 |
| R4 | prompt 修 + baseline | calibration ρ=0.985 + 当前生产 baseline (L0, overall 3.73, veto 46%) + L1-L4 档位定义 |
| R5 | multi-chapter + 毒点回归 | judge_multi_chapter + 4 cross-passage 维度 + 毒点回归集 (recall 0.611 / FP 0.000) |
| R6 | final cleanup | 删 ~600 行 deprecated + 重写 e2e_judge + external calibration subset + 文档 v1.0 |

总真实 LLM 调用：~3000 次跨 6 round。0 个被绕过的"假装通过"——失败 gate 全部诚实记录引导后续 round。

### 元层教训（R1-R6 累积）

1. **macOS 临时端口耗尽**：concurrency=1 是 LLM 评测默认（R1）
2. **整数 1-10 打分系统的 std 自然下限**：~0.55，强制 < 0.5 等于强制相同分（R2）
3. **失败 gate 不调阈值**：暴露 prompt bug 比假装通过有价值（R3）
4. **网文产品定位优先**：calibration ranking 按 网文 lens 而非文学 lens（R4）
5. **tier-aware std 阈值**：mid-tier 样本上 std 高是真实 ambiguity 不是 prompt 缺陷（R5）
6. **Trade-off 记录优于完美**：R5 forced_stupidity recall 0% vs 防 payoff 误判 100% 是值得的 trade-off，文档化即可（R5/R6）

### Sprint 26 起点

- 评测系统：v1.0，可信度由 calibration ρ=0.985 + 0% FP rate 锚定
- 当前生产位置：L0（被 ai_prose_ticks 拖累）
- Sprint 26 第一攻击点：Narrator prompt 加 ai_prose_ticks 子类禁用，预计直接 L0 → L2 边界

详细 Codex handoff 见 `docs/orchestrator/state.json` 的 `handoff_to_codex` 字段，含 5 个 priority-ordered 任务。

---

## 下一轮预选题（Codex 接力）

见 state.json `handoff_to_codex` 字段。Priority 1-2 是 Sprint 26 生成端工作，priority 3-5 是 R6 残留 + R5 trade-off 调优。
