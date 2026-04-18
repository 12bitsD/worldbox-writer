# 发布流程

**文档状态**：Active (v0.6.0+)  
**最后更新**：2026-04-18

本文档说明 WorldBox Writer 的版本发布最小流程。

## 1. 发布目标

当前发布流程的目标不是自动化部署，而是确保每次版本发布都有：

- 明确的版本号
- 明确的变更记录
- 明确的验证结果
- 明确的回滚依据

## 2. 发布前检查

发布前至少完成以下动作：

1. `make lint`
2. `make test`
3. 如改动涉及类型结构，执行 `make typecheck`
4. 如改动涉及真实模型行为，执行 `make integration`
5. 更新 `CHANGELOG.md`
6. 更新 README 或相关设计文档

## 3. 版本号更新位置

当前仓库至少涉及以下版本号：

- `pyproject.toml`
- `frontend/package.json`

如果两端同时对外发布，应保持版本号一致。

## 4. 发布步骤

推荐流程：

1. 从 `main` 切发布分支或直接在发布 PR 中完成版本修改
2. 更新版本号
3. 更新 `CHANGELOG.md`
4. 合并到 `main`
5. 在 GitHub 打 tag，例如 `v0.6.0`
6. 创建 GitHub Release，并粘贴 changelog 摘要

当前仓库已经提供最小自动化：

- `.github/workflows/release.yml`

推荐做法：

- 合并发布 PR 后，推送 tag，例如 `git tag v0.6.0 && git push origin v0.6.0`
- 由 GitHub Actions 自动创建 Release

## 5. 发布说明模板

建议至少包含：

- 新增能力
- 修复项
- 是否有 breaking changes
- 升级注意事项
- 已知限制

## 6. 回滚原则

若发布后出现严重问题：

- 先确认问题是否来自前端静态资源、后端接口还是模型配置
- 使用上一个稳定 tag 作为回滚基线
- 回滚后补一条修复 PR，而不是直接在生产问题上继续叠改
