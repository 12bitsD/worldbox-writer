# Relationship Schema v1

本文档定义 Sprint 6 开始使用的角色关系结构，用于统一：
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
- 更复杂的关系演化逻辑和交互展示留给 Sprint 7 继续补齐。
