# 质量评估框架——索引页

**文档状态**：DEPRECATED · 内容已迁移
**迁移时间**：Sprint 25 R3 cleanup（2026-04-30）

---

本文件原本承载评测协议、LLM-as-judge prompt 模板、毒点检测标准、迭代停机规则等内容。

Sprint 25 R3 将这些内容与 `WEB_NOVEL_CRITERIA.md`、`docs/orchestrator/README.md` 的四档表合并为单一真相源 [`QUALITY_SPEC.md`](./QUALITY_SPEC.md)。

请直接阅读：

| 原内容 | 新位置 |
|---|---|
| 评测协议（样本量 / 盲评 / 对标盲测） | [QUALITY_SPEC.md §2 测量协议](./QUALITY_SPEC.md#2-measurement-protocol测量协议) |
| 工程闭环（"judge LLM 是质量分数唯一来源"） | [QUALITY_SPEC.md §2.7 evidence schema](./QUALITY_SPEC.md#27-evidence-schema-强制约束) + §2.8 |
| LLM-as-judge prompt 模板（旧单 prompt 13 维） | 已拆为 per-dimension prompts，见 `src/worldbox_writer/evals/dimension_prompts.py` |
| 毒点检测与拦截标准 | [QUALITY_SPEC.md §1.4 toxic flags](./QUALITY_SPEC.md#14-toxic-flags独立专家二值) + §2.6 toxic veto 规则 |
| 迭代停机规则 | [`docs/orchestrator/README.md`](../orchestrator/README.md)（停机规则的归属） |

变更原因：维度定义、测量协议、档位三件事过去散在三处，迭代时词汇翻译损失让方向跑偏。`QUALITY_SPEC.md` 是 single source of truth。
