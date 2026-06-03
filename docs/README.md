# 文档导航

仓库文档入口索引。新成员先读根 [README.md](../README.md) 和 [AGENTS.md](../AGENTS.md)。

> 2026-05-11 文档整理：开发流程类（AGILE_GUIDE / RUNBOOK / RELEASE_PROCESS / TYPECHECK_BASELINE / DUAL_LOOP_ROLLOUT）已合并到 `development/DEVELOPMENT.md`；架构类（DUAL_LOOP_ENGINE_DESIGN）已合并到 `architecture/DESIGN.md`；中间节点评测（INTERMEDIATE_EVAL_SPEC）已合并到 `product/QUALITY_SPEC.md §5`；Orchestrator 目录已归档到 `sprints/orchestrator/`。

---

## 1. 初次进入项目

- [项目总览与快速开始](../README.md)
- [Agent 执行契约](../AGENTS.md)
- [贡献指南](../CONTRIBUTING.md)
- [安全策略](../SECURITY.md)
- [变更记录](../CHANGELOG.md)

## 2. 架构与设计

- [系统架构设计](architecture/DESIGN.md) — 第一性原理、三层架构、双循环（Director → Actor → Critic → GM → GateKeeper → Narrator）数据流、技术栈、关键决策、可观测性

## 3. 开发与交付

- [开发指南](development/DEVELOPMENT.md) — 环境 / 命令 / 日常流程 / CI 门禁与分层测试 / DoD / Sprint 规则 / 分支提交 / Secrets / 运行手册 / Feature Flag 止损 / 发布流程 / 双循环灰度 / 类型检查基线 / 推荐仓库设置（统一入口）

## 4. 产品与质量

- [产品策略](product/PRODUCT_STRATEGY.md) — 定位、竞品、差距分析、差异化策略、路线图
- [质量评测系统 SPEC](product/QUALITY_SPEC.md) — single source of truth：维度定义 + 测量协议 + 档位 + calibration + 中间节点 LLM2LLM 评测（§5）

## 5. Sprint 与迭代编排

- [Sprint 文档清单](sprints/README.md)
- **[v0.1.0-beta 上线计划（Sprint 26 → 30）](sprints/LAUNCH_PLAN.md)** — 5 类标签（EVAL/CRAFT/PLAT/STAB/RLS）+ 上线门 + Trade-off
- [Sprint 25 计划](sprints/SPRINT_25.md)
- [Orchestrator 总控手册（已归档）](sprints/orchestrator/README.md) — 北极星、双轴评估、四档标准、迭代主流程
- [Orchestrator 当前状态快照](sprints/orchestrator/state.json)

## 6. 模板

- [Model Eval Workflow 模板](ci/model-eval.yml.template)
