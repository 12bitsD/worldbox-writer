# Telemetry Schema v1

本文档定义 Sprint 6 引入的业务可读 Telemetry 结构。

目标：
- 为前端日志面板提供稳定输入。
- 为历史会话回放提供稳定结构。
- 避免在 Sprint 6 直接引入复杂 tracing 系统。

## 结构定义

```json
{
  "event_id": "evt-uuid",
  "sim_id": "abcd1234",
  "tick": 2,
  "agent": "gate_keeper",
  "stage": "rejected",
  "level": "warning",
  "message": "候选事件被边界层拒绝",
  "payload": {
    "reason": "违反主角第一幕不能死亡的约束",
    "hint": "调整事件强度，避免直接死亡"
  },
  "ts": "2026-04-17T01:23:45+00:00"
}
```

## 字段说明

- `event_id`
  - 事件唯一 ID。
- `sim_id`
  - 所属推演会话 ID。
- `tick`
  - 该事件对应的故事推演步数。
- `agent`
  - 事件来源模块，如 `director`、`actor`、`gate_keeper`、`node_detector`、`narrator`、`simulation`、`user`。
- `stage`
  - 当前阶段标识，如 `world_initialized`、`proposal_generated`、`rejected`。
- `level`
  - 严重级别：
  - `info`
  - `warning`
  - `error`
- `message`
  - 面向用户的简短说明。
- `payload`
  - 结构化补充信息。
- `ts`
  - 事件生成时间戳。

## Sprint 6 范围

Sprint 6 只做“业务可读事件”，不做：
- prompt 全量记录
- chain-of-thought 暴露
- 分布式 trace
- span 级链路分析

## 推荐事件类型

- `world_initialized`
- `world_enriched`
- `proposal_generated`
- `passed`
- `rejected`
- `node_committed`
- `intervention_requested`
- `intervention_submitted`
- `started`
- `completed`
- `failed`

## 设计原则

- v1 优先稳定可读和可持久化。
- v1 优先服务 UI 展示和会话回放。
- 更复杂的 trace 规范留到 Sprint 7 的 Telemetry SDK v1。
