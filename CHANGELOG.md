# Changelog

本文件记录面向版本发布的用户可见变更。

格式参考 Keep a Changelog，版本遵循语义化版本思路，但当前项目仍以迭代发布为主。

## [Unreleased]

### Added
- 统一的本地开发入口：`Makefile`
- 平台无关的 CI 脚本：`scripts/ci/*`
- 开发与治理文档：`CONTRIBUTING.md`、`SECURITY.md`、`DEV_WORKFLOW.md`
- 运行手册、发布流程和类型检查基线文档
- `CODEOWNERS` 代码归属定义
- Sprint 7 的关系图谱交互能力：节点聚焦、边详情、历史恢复后的稳定渲染
- Sprint 7 的 Telemetry 关联字段：`trace_id`、`request_id`、`parent_event_id`、`span_kind`、`provider`、`model`、`duration_ms`
- `useSimulation` 状态合并工具与对应前端回归测试

### Changed
- GitHub Actions 改为直接调用仓库脚本
- 默认 CI 门禁收敛为后端质量门禁和前端质量门禁
- README 文档导航改为更清晰的分层入口
- 实时 SSE、历史载荷和刷新恢复现在使用同一套稳定 ID 合并规则
- Telemetry 面板从简单倒序列表升级为可过滤、可分组、可关联阅读的日志视图
- GateKeeper 在拒绝候选事件后会基于 `revision_hint` 做有限次自愈重试

### Fixed
- 修复前端 Sprint 6 fixture 的类型漂移问题
- 修复仓库内现存的 `black` 格式化欠账
- 修复同一会话在实时运行、页面刷新和历史打开路径下的节点/遥测漂移
- 修复前后端 Telemetry schema 在 REST/SSE/持久化之间的不一致

## [0.5.0] - 2026-04-17

### Added
- 实时事件流
- 本地 SQLite 持久化
- 等待态编辑能力
- Sprint 6 的关系图谱和 Telemetry 面板
