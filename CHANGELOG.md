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

### Changed
- GitHub Actions 改为直接调用仓库脚本
- 默认 CI 门禁收敛为后端质量门禁和前端质量门禁
- README 文档导航改为更清晰的分层入口

### Fixed
- 修复前端 Sprint 6 fixture 的类型漂移问题
- 修复仓库内现存的 `black` 格式化欠账

## [0.5.0] - 2026-04-17

### Added
- 实时事件流
- 本地 SQLite 持久化
- 等待态编辑能力
- Sprint 6 的关系图谱和 Telemetry 面板
