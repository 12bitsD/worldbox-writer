# Secrets Policy

**文档状态**：Active (v0.6.0+)  
**最后更新**：2026-04-18

本文档定义仓库内与 CI 中的 secret 使用边界，目的是把“不要提交密钥”进一步收敛成可执行规则。

## 1. Secret 分类

当前仓库主要存在三类 secret：

- 本地开发 secret
  - 例如 `.env` 中的 `LLM_API_KEY`
- CI secret
  - 例如 GitHub Actions 中的 `LLM_API_KEY`
- 平台环境 secret
  - 未来 staging / production 使用的 provider key、database credential、service token

## 2. 当前登记项

| 名称 | 用途 | 存放位置 | 责任说明 |
|---|---|---|---|
| `LLM_API_KEY` | 真实模型访问 | 本地 `.env` / GitHub Actions Secret | 维护者负责配置与轮换 |
| `LLM_BASE_URL` | 自定义模型网关 | 本地 `.env` / GitHub Actions Secret | 按 provider 环境配置 |
| `LLM_MODEL` | 模型名 | 本地 `.env` / GitHub Actions Variable | 非敏感，但应与环境一致 |

## 3. 强制规则

- 真实 secret 不得提交到 Git 仓库
- `.env.example` 只能放占位符，不得放真实值
- 新增 secret 时，必须同步更新本文件或 `SECURITY.md`
- CI 中优先使用 GitHub Actions Secrets / Variables，而不是硬编码到 workflow

## 4. 轮换建议

- `LLM_API_KEY` 至少在以下场景轮换：
  - 人员权限变化
  - 可疑泄露
  - provider 主动要求
- 若发生泄露，处理顺序应为：
  1. 立即废弃旧密钥
  2. 替换 CI / 本地环境密钥
  3. 检查 Git 历史、Issue、PR、日志是否有外泄痕迹
  4. 记录事件并评估影响范围

## 5. 当前限制

- 还没有 staging / production 的 environment secret 分层
- 还没有自动化 secret inventory 校验
- 还没有统一的 secret owner / expiry metadata 系统
