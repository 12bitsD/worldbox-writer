# 类型检查基线

**文档状态**：Active (v0.6.0+)  
**最后更新**：2026-04-18

本文档记录当前 `make typecheck` 的已知基线，用于防止新增改动继续扩大类型债务。

## 1. 当前状态

执行命令：

```bash
make typecheck
```

当前结果：

- `mypy 1.20.1`
- `27` 个错误
- 分布在 `9` 个文件

## 2. 文件分布

| 文件 | 错误数 | 主要问题 |
|---|---:|---|
| `src/worldbox_writer/core/models.py` | 1 | 结构化返回值不匹配 |
| `src/worldbox_writer/utils/llm.py` | 3 | OpenAI SDK 调用签名与返回值类型 |
| `src/worldbox_writer/agents/world_builder.py` | 3 | `Any` 返回值泄漏 |
| `src/worldbox_writer/agents/node_detector.py` | 3 | `Any` 返回值泄漏 |
| `src/worldbox_writer/agents/narrator.py` | 3 | `Any` 返回值泄漏 |
| `src/worldbox_writer/agents/gate_keeper.py` | 3 | `Any` 返回值泄漏 |
| `src/worldbox_writer/agents/director.py` | 5 | `Optional` 边界与 `Any` 返回值 |
| `src/worldbox_writer/agents/actor.py` | 4 | `Any` 返回值与 `UUID`/`str` 不匹配 |
| `src/worldbox_writer/engine/graph.py` | 2 | `TypedDict` 缺字段与返回值类型 |

## 3. 当前治理规则

在类型债务清零前，执行以下规则：

1. 不要求默认 PR 门禁必须让 `make typecheck` 全绿
2. 新增改动不得引入新的 mypy 错误
3. 修改已在基线中的文件时，应优先顺手减少错误，而不是增加
4. 新模块、新文件原则上应做到 mypy 无错误

## 4. 建议清理顺序

推荐从最小风险开始：

1. `core/models.py`
2. `utils/llm.py`
3. `agents/director.py`
4. `agents/actor.py`
5. `engine/graph.py`
6. 其余 `agents/*`

## 5. 退出条件

满足以下条件后，可将 `make typecheck` 恢复为默认 CI 阻塞项：

- 基线错误数降为 `0`
- 新增类型检查 workflow 在 `main` 上连续稳定通过
- PR 模板和开发流程文档同步更新
