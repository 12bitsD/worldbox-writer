# 中国网文（商业化）AI 评测标准——索引页

**文档状态**：DEPRECATED · 内容已迁移
**迁移时间**：Sprint 25 R3 cleanup（2026-04-30）

---

本文件原本承载评测维度定义、毒点红线、四档量表等内容。

Sprint 25 R3 将这些内容与 `QUALITY_FRAMEWORK.md`、`docs/orchestrator/README.md` 的四档表合并为单一真相源 [`QUALITY_SPEC.md`](./QUALITY_SPEC.md)。

请直接阅读：

| 原内容 | 新位置 |
|---|---|
| 三轴维度定义（情绪爽点 / 网文结构 / 商业文笔） | [QUALITY_SPEC.md §1](./QUALITY_SPEC.md#1-dimensions评测维度) |
| 神作进阶轴（4 维） | [QUALITY_SPEC.md §1.3 cross-passage](./QUALITY_SPEC.md#13-cross-passage-dimensionsmulti-chapter-judge-才用r5-引入) |
| 毒点红线（一票否决） | [QUALITY_SPEC.md §1.4 toxic flags](./QUALITY_SPEC.md#14-toxic-flags独立专家二值) |
| 1-10 分量化打分量表 | 各 dimension prompt（`src/worldbox_writer/evals/dimension_prompts.py`） |
| 权重与档位 | [QUALITY_SPEC.md §2 测量协议](./QUALITY_SPEC.md#2-measurement-protocol测量协议) + §3 档位（R4 填充） |

变更原因：维度定义、测量协议、档位三件事过去散在三处，迭代时词汇翻译损失让方向跑偏。`QUALITY_SPEC.md` 是 single source of truth。
