# Sprint 25: 评测体系重建（Eval-as-Goal-Language）

**Sprint Goal**：把分散在 `WEB_NOVEL_CRITERIA.md` / `QUALITY_FRAMEWORK.md` / `orchestrator/README.md` 的"质量定义 + 测量协议 + 档位"收敛为**一份单一真相源** `docs/product/QUALITY_SPEC.md`，建立可校准、有证据、能稳定复现的 judge 委员会，并用新评测重测当前系统取得**可信基线**与**重新定义的 L1–L4 档位**。

在 Sprint 25 退出之前**不动任何生成端代码**。先有可信的尺，再去量身高。

---

## 立项动机

Sprint 24 留下来的状态：
- 旧 baseline 7.5 是用旧评测得到的分数。旧评测有两个结构性问题：
  1. **单 prompt 评 13 维**：注意力被稀释，分数互相污染（高文笔倾向把所有维度都打 7-8）。
  2. **本地启发式分数与 LLM judge 混淆**：刚在 pre-flight cleanup 里删除（commit `chore(eval): pre-flight cleanup`），但旧分数从未在干净的协议下重测过。
- 旧四档表（L1-L4，每轴 ≥ 6/7/8/9）是用旧评测分数定的绝对阈值。评测换了，绝对阈值不再有锚点。
- 三份文档（criteria / framework / orchestrator）三套词汇，迭代时翻译损失让方向跑偏。

**结论**：先重建评测、再重测、再重定档位、再迭代生成端。

---

## 验收标准（Sprint Exit Criteria）

1. `docs/product/QUALITY_SPEC.md` 是评测系统的 **single source of truth**：
   - Dimensions（保留维度 + 测量定义）
   - Measurement protocol（judge 委员会调用方式）
   - Tiers（基于新评测词汇的 L1–L4 定义）
   - Calibration anchors（人工标注样本指针）
   旧的 `WEB_NOVEL_CRITERIA.md` / `QUALITY_FRAMEWORK.md` 要么删除，要么变为指向新 spec 的索引页。
2. 新 judge 委员会跑通：
   - 同一文本连续 5 次 judge，每个保留维度的 axis_score **std < 0.5**。
   - 非满分维度的 `evidence_quotes` 非空率 **≥ 80%**。
3. 毒点注入测试集：
   - 4 类毒点 × 2 段命中样本 + 4 段干净样本，召回 **≥ 95%**，误报率 **≤ 10%**。
4. 校准基线：
   - 5–10 段人工评分参考样本入库。
   - judge 委员会给出的相对排序与人工排序 **100% 一致**。
5. 重测当前系统：
   - 跑 ≥ 3 个真实 simulation × 4 章，新评测下的基线写入 `state.json`。
   - 基于这份基线重写 `QUALITY_SPEC.md` 的档位章节。
6. CI 与文档对齐：
   - `make integration` / `make model-eval` 流程引用新 spec。
   - `CLAUDE.md` / `AGENTS.md` 同步新词汇。

---

## Rounds

| Round | 主题 | 验收（real LLM 验证） |
|---|---|---|
| **R1** | 词汇定型：调研头部网文 + 反思现有 13 维，提出新 dimension 草案并跑稳定性实证 | 每个保留维度同输入 5 次 std < 1.0；输出 v0.1 dimension 列表与剔除依据 |
| **R2** | 委员会落地 + evidence schema | 委员会跑同输入 5 次 axis_score std < 0.5；非满分维度 evidence_quotes 非空率 ≥ 80% |
| **R3** | **清理 + 人工校准 anchor**（cleanup round） | 三份旧文档收敛为一份；5–10 段校准样本人工评分入库；judge 相对排序 100% 与人工一致 |
| **R4** | 重测当前系统 + 重定 L1–L4 档位 | 3-5 simulation × 4 章新基线；档位章节用基线 + calibration 重写 |
| **R5** | 毒点注入回归 + 跨章节 judge | 注入召回 ≥ 95%；4 章 multi-chapter judge 跑通 |
| **R6** | **清理 + Sprint 25 收口**（cleanup round） | 死代码清理；CLAUDE.md/AGENTS.md 同步；state.json 用新词汇重写 |

每轮在 `docs/orchestrator/round-N.md` 写完整的 7 步流程记录（北极星 3 问 → 选题 → 验证标准 → 实现 → 验证 → 同步）。

---

## 工程约束

- **每轮 1 个 feature branch**：`feature/sprint-25-rN-<topic>`，自审 PR / 合并入 main。
- **测试分层**：判官的 JSON 解析 / 聚合 / schema 兜底走 L1 mock；判官**质量行为**全部走 real LLM (`@pytest.mark.eval`)。
- **artifacts 落地**：每轮 eval 产物落 `artifacts/eval/sprint-25/round-N/`，纳入 git。
- **失败必须显性**：判官失败返 0.0 + error（已在 pre-flight 落实），不再用 5.0 兜底；round 报告里同时记录失败案例与原因。
- **不动生成端**：本 Sprint 期间禁止修改 `src/worldbox_writer/agents/*` 的生产逻辑（`narrator_iterative.py` 的非生产原型除外）。

---

## 与北极星的连接

> 北极星：让 Agent 写出 L2 级长篇网文。

Sprint 25 不直接提升任何生成质量。它是把所有后续 Sprint 的"是否走对方向"这件事变成可证伪的工程问题。Sprint 25 之后，每一个生成端 Sprint 都要在 round-N.md 写出"在 QUALITY_SPEC 的 X 维度上从 A → B"，否则不开。
