# Dual-loop Rollout Runbook

**文档状态**：Active
**最后更新**：2026-04-22

本文档说明双循环推演链路的灰度、评估和回滚流程。

## 1. Feature Flag

双循环链路由环境变量控制：

```bash
FEATURE_DUAL_LOOP_ENABLED=1
```

紧急回滚时关闭：

```bash
export FEATURE_DUAL_LOOP_ENABLED=0
make dev-api
```

关闭后的预期行为：

- 主图退回 legacy Actor candidate event 路径
- Inspector / compare API 仍可读取已有会话证据
- 已持久化的 `SceneScript`、`NarratorInput` 和 rendered text 不会被删除

## 2. Compare Report

API：

```bash
curl http://localhost:8000/api/simulate/<sim_id>/dual-loop/compare
```

CLI：

```bash
python -m worldbox_writer.evals.dual_loop_compare <sim_id>
```

强制 readiness 失败时返回非零退出码：

```bash
python -m worldbox_writer.evals.dual_loop_compare <sim_id> --require-ready
```

报告默认写入：

```text
artifacts/dual-loop-compare/<sim_id>.json
```

## 3. Readiness 判定

Required checks：

- `dual_loop_feature_flag`：`FEATURE_DUAL_LOOP_ENABLED` 必须开启
- `scene_script_lineage`：当前主线节点必须有 `SceneScript` metadata
- `narrator_input_v2`：SceneScript 节点必须由 `NarratorInput` v2 渲染
- `rollback_path`：报告必须带出回滚 flag 和 runbook

Optional checks：

- `critic_verdict_trace`：没有 verdict 只给 warning，不阻断旧会话排查
- `prompt_trace_visibility`：没有 PromptTrace 只给 warning，不阻断旧会话排查

## 4. 发布前验证

常规 PR gate：

```bash
make lint
make test
```

涉及 payload/type contract：

```bash
make typecheck
```

涉及 agent、prompt、真实模型行为：

```bash
make integration
```

模型质量评估：

```bash
make model-eval
```

`make model-eval` 当前是发布护栏和人工评估入口，不是默认 CI blocking gate。

## 5. 回滚步骤

1. 设置 `FEATURE_DUAL_LOOP_ENABLED=0`
2. 重启 API 服务
3. 访问 `GET /api/health` 确认服务恢复
4. 新建一次普通推演，确认 legacy 路径能生成节点和正文
5. 对事故会话执行 compare report，保存 `artifacts/dual-loop-compare/<sim_id>.json`
6. 创建修复 issue，附上 compare report、integration/model-eval 结果和 provider 信息

## 6. 恢复步骤

确认修复通过后：

```bash
export FEATURE_DUAL_LOOP_ENABLED=1
make dev-api
```

恢复后重新执行：

```bash
make lint
make test
make integration
```

然后对至少一个新会话生成 compare report，确认 readiness 为 `ready`。
