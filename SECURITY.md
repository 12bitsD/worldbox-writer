# Security Policy

**文档状态**：Active (v0.6.0+)  
**最后更新**：2026-04-18

本文档说明 WorldBox Writer 的安全问题上报方式、敏感信息处理要求和基础安全边界。

## 1. 支持范围

当前默认支持维护的是：

- `main` 分支上的最新代码
- 当前发布版本对应的最近一个小版本线

历史 Sprint 文档和废弃实验代码不承诺提供安全修复。

## 2. 如何报告漏洞

如果问题涉及以下内容，请按安全漏洞处理，而不是公开提 Issue：

- API Key、Token、Secret 泄露
- 未授权访问
- 任意文件读写
- 远程命令执行
- Prompt 注入导致越权访问本地资源
- 依赖库高危漏洞且可被当前运行路径利用

建议的报告方式：

1. 优先使用 GitHub 私密安全报告或私密联系维护者
2. 不要在公开 Issue、PR、评论里贴出可利用细节
3. 在报告中提供复现步骤、影响范围、前提条件和建议修复方向

如果没有私密报告通道，至少应通过 GitHub 私信或其他维护者私下渠道先联系项目维护者。

## 3. Secret 管理要求

- 真实密钥只能放在本地 `.env` 或 CI Secret Store 中
- `.env`、数据库文件、日志文件不得提交到仓库
- 示例配置只能写入 `.env.example`
- 任何测试数据都不得包含真实生产凭据

## 4. 依赖与供应链要求

- Python 和前端依赖升级应优先通过独立 PR 完成
- 升级 PR 需要附带最少一次 `make lint` 和 `make test`
- 对高危漏洞依赖，优先修复，再评估功能迭代

## 5. LLM 与数据边界

当前项目依赖外部 LLM 提供商时，需要注意：

- 不要向外部模型发送不必要的敏感用户数据
- 在 Prompt 中避免包含本地密钥、路径、系统凭据
- 本地 Ollama 适合敏感内容验证；公网模型适合公开或低敏数据

## 6. 当前已落地的安全配套

仓库内已经加入以下基础安全护栏：

- `CodeQL` workflow
- dependency review workflow
- `gitleaks` secret scan workflow
- `Dependabot` version update 配置

这些能力主要覆盖基础 SAST/SCA 与 secret scan 的仓库侧落地。

## 7. 仍待平台侧完成的部分

当前仍依赖平台设置或后续工程化补充的内容：

- GitHub 原生 secret scanning / push protection
- Dependabot alerts / security updates 开关确认
- 发布前安全审计清单
- 运行时审计日志和告警链路
