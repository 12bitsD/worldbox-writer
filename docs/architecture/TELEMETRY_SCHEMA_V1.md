# Telemetry Schema v1

本文档定义 Sprint 6 引入、并在 Sprint 7 扩展为可关联调用链的业务可读 Telemetry 结构。

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
  "ts": "2026-04-17T01:23:45+00:00",
  "trace_id": "trace_abcd1234",
  "request_id": "llm_1234abcd",
  "parent_event_id": "evt-parent",
  "span_kind": "llm",
  "provider": "mimo",
  "model": "mimo-v2-pro",
  "duration_ms": 842,
  "branch_id": "branch_ab12cd34",
  "forked_from_node_id": "node_1234",
  "source_branch_id": "main",
  "source_sim_id": "abcd1234"
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
- `trace_id`
  - 一次推演链路内共享的追踪 ID，用于前端按会话串联事件。
- `request_id`
  - 单次 LLM 调用或单次子过程的唯一请求 ID。
- `parent_event_id`
  - 父事件 ID，用于表达同一条链上的前后关联。
- `span_kind`
  - 事件类别，当前允许值：
  - `event`
  - `llm`
  - `user`
  - `system`
- `provider`
  - LLM Provider 标识，如 `mimo`、`openai`、`ollama`、`injected`。
- `model`
  - 本次调用实际使用的模型名。
- `duration_ms`
  - 调用或处理阶段耗时，单位毫秒。
- `branch_id`
  - 当前事件所属世界线。主线固定为 `main`。
- `forked_from_node_id`
  - 若当前世界线来自历史分叉，记录分叉来源节点 ID。
- `source_branch_id`
  - 该世界线直接来源的父分支 ID。
- `source_sim_id`
  - 该世界线所属的原始会话 ID。Sprint 8 当前仍为单 session 内多分支，因此通常与 `sim_id` 相同。

## Sprint 6 基线

Sprint 6 只做“业务可读事件”，不做：
- prompt 全量记录
- chain-of-thought 暴露
- 分布式 trace
- span 级链路分析

## Sprint 7 扩展

Sprint 7 在不引入完整 tracing 系统的前提下，补了最小可用的关联字段：

- 统一为每次 LLM 调用记录 `provider`、`model`、`request_id`。
- 为一次推演会话补 `trace_id`，使 REST / SSE / 历史恢复三条链路字段一致。
- 通过 `parent_event_id` 和 `span_kind` 区分用户事件、系统事件和 LLM 事件。

## Sprint 8 扩展

Sprint 8 在原有调用链字段上继续补充分支上下文：

- 为所有事件补 `branch_id`，保证前端不需要再从 raw payload 猜当前世界线。
- 为 branch create / switch / continue 补 `forked_from_node_id`、`source_branch_id`、`source_sim_id`。
- 约定分支切换后的 REST、SSE 和历史恢复返回同一套 branch context，不允许恢复时丢字段。

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
- `branch_created`
- `branch_switched`
- `branch_progressed`
- `pacing_updated`

## 设计原则

- v1 优先稳定可读和可持久化。
- v1 优先服务 UI 展示和会话回放。
- 关联字段以“够用”为准，不引入完整分布式 tracing 基建。
