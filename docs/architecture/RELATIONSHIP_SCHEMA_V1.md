# Relationship Schema v1

本文档定义 Sprint 6 引入、并在 Sprint 7 继续沿用的角色关系结构，用于统一：
- 后端 `WorldState` / `Character` 模型
- `GET /api/simulate/{id}` 响应
- SSE 后续关系图谱消费格式
- 前端 TypeScript 类型

## 结构定义

`Character.relationships` 使用如下结构：

```json
{
  "target-character-id": {
    "target_id": "target-character-id",
    "affinity": 42,
    "label": "ally",
    "note": "一起击退了追兵",
    "updated_at_tick": 3
  }
}
```

## 字段说明

- `target_id`
  - 目标角色 ID。
- `affinity`
  - 数值强度字段，供图谱排序和边样式映射使用。
- `label`
  - 关系标签，当前允许值：
  - `ally`
  - `neutral`
  - `rival`
  - `fear`
  - `trust`
  - `unknown`
- `note`
  - 面向用户的简短解释，不用于复杂推理。
- `updated_at_tick`
  - 最近一次更新该关系的推演 tick。

## 兼容策略

历史世界状态中可能仍然存在旧格式：

```json
{
  "target-character-id": "rival"
}
```

后端在加载旧数据时必须自动兼容并升级为 v1 结构：
- 若旧值是已知标签，则映射到 `label`。
- 若旧值不是已知标签，则写入 `note`，并使用 `label = "unknown"`。

## 设计原则

- v1 优先保证可解释、可持久化、可前端消费。
- v1 不追求复杂社交模拟。

## Sprint 7 落地结果

Sprint 7 没有改动这份结构的核心字段，而是基于同一份 schema 补齐了前端交互能力：

- 关系图谱支持节点选中与一跳聚焦。
- 边详情直接消费 `label`、`affinity`、`note`、`updated_at_tick`。
- 历史会话恢复时继续使用同一份结构化关系数据，不再依赖前端临时推断。
