# 文档导航

仓库文档入口索引。新成员先读根 [README.md](../README.md) 和 [AGENTS.md](../AGENTS.md)。

---

## 1. 初次进入项目

- [项目总览与快速开始](../README.md)
- [Agent 执行契约](../AGENTS.md)
- [贡献指南](../CONTRIBUTING.md)
- [安全策略](../SECURITY.md)
- [变更记录](../CHANGELOG.md)

## 2. 架构与设计

- [系统架构设计](architecture/DESIGN.md) — 三层架构、双循环数据流、技术栈、关键决策
- [双循环推演引擎设计](architecture/DUAL_LOOP_ENGINE_DESIGN.md) — ScenePlan → Actor → Critic → GM → Narrator 协议

## 3. 开发与交付

- [开发指南](development/DEVELOPMENT.md) — 环境、命令、CI 门禁、Secrets、分支提交规范
- [敏捷开发指南](development/AGILE_GUIDE.md) — 测试分层 L1/L2/L3、DoD、Sprint 规则
- [运行手册](development/RUNBOOK.md) — 常见故障排查、Feature Flag 止损
- [Dual-loop Rollout Runbook](development/DUAL_LOOP_ROLLOUT.md) — 双循环灰度与恢复流程
- [发布流程](development/RELEASE_PROCESS.md)
- [类型检查基线](development/TYPECHECK_BASELINE.md)

## 4. 产品与质量

- [产品策略](product/PRODUCT_STRATEGY.md) — 定位、竞品、差距分析、差异化策略、路线图
- [质量评估框架](product/QUALITY_FRAMEWORK.md) — 评测协议、LLM-as-judge、AI 味检测

## 5. 迭代编排

- [Orchestrator 总控手册](orchestrator/README.md) — 北极星、双轴评估、四档标准、迭代主流程
- [当前状态快照](orchestrator/state.json)

## 6. Sprint 记录

- [Sprint 文档清单与清理策略](sprints/README.md)
- [Sprint 24 计划](sprints/SPRINT_24.md)

## 7. 模板

- [Model Eval Workflow 模板](ci/model-eval.yml.template)
