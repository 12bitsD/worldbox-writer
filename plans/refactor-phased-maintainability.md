# 分阶段可维护性重构

## 背景

重新看过 `api/server.py`、`api/state.py`、`engine/graph.py`、`utils/llm.py`、`frontend/src/hooks/useSimulation.ts` 和相关测试后，当前维护成本主要来自三处混层：API handler 直接管理 session/DB/线程/分支，LangGraph node 直接拼 prompt 和调用 LLM，Agent/Engine 直接依赖全局 LLM 函数。计划目标是分阶段降低耦合，不改变公开 API，不一次性重写 graph，不引入复杂 DI 或 repository 框架。

## 方案

### 1. 先收口 API 状态和常量 — `src/worldbox_writer/api/state.py` (modify)

`api/state.py` 已有 `_executor`、`_sessions`、`_VALID_PACING_VALUES`、`_WORKSPACE_MUTABLE_STATUSES`，但 `api/server.py` 又定义了一份。第一步把 `server.py` 改成从 `api.state` 导入这些对象，并保留 `server._sessions`、`server._executor` 等旧名字作为兼容别名，因为 `tests/test_api/test_edit_endpoints.py` 和 `perf/load_gate.py` 直接 import 私有对象。常量只放领域内：API 状态常量留在 `api/state.py`，Engine 词表后续放 `engine/constants.py`，不要做全局巨型 constants。

### 2. 迁出 Session 模型和持久化辅助 — `src/worldbox_writer/api/session.py` (add)

把 `SimulationSession` 从 `api/server.py` 移到 `api/session.py`，并将 `_queue_event`、`_upsert_rendered_node`、`_merge_rendered_nodes_from_world`、`_sync_rendered_nodes_from_world` 迁到同一模块或 `api/session_store.py`。`server.py` 继续 re-export `SimulationSession`，先不改测试 import。这里不引入 repository interface，只保留现有内存 dict + SQLite 函数，因为当前只有一个存储实现。

### 3. 抽应用服务，不急着拆所有路由 — `src/worldbox_writer/api/services/simulation_service.py` (add)

新增 `SimulationService` 承接 start/get/intervene/list/recover/persist/run 这些用例：

```python
class SimulationService:
    def start(self, request: StartSimulationRequest, loop: asyncio.AbstractEventLoop) -> SimulationResponse: ...
    def get(self, sim_id: str, branch: str | None = None) -> dict[str, Any]: ...
    def submit_intervention(self, sim_id: str, instruction: str) -> dict[str, str]: ...
```

`_run_simulation_sync` 可以先作为 service 方法迁移，但 `server.py` 保留同名包装函数调用 service，避免现有测试直接断。风险是后台线程和 intervention event 的状态竞争；迁移时保持原来的 queue/event 字段不变，只改变所在模块。

### 4. 分支和工作台编辑分开抽 — `src/worldbox_writer/api/services/branch_service.py` (add)

把 `create_branch`、`switch_branch`、`compare_branches`、`update_branch_pacing` 的业务逻辑迁到 `BranchService`；把角色、关系、世界设定、constraint、wiki、rendered text 迁到 `WorkspaceService`。Service 返回普通 dict 或 domain exception，FastAPI handler 只负责转 `HTTPException`。第一轮只移动函数，不改 endpoint path 和 response shape；`api/routes/simulations.py` 可先只承载 start/get/stream，后续再按 `branches.py`、`workspace.py` 拆。

### 5. 让 `engine/graph.py` 回到 orchestration — `src/worldbox_writer/engine/services/narration_service.py` (add)

先只抽最重的 narrator node，不碰整条 LangGraph。新增 `NarrationService.render_current_node(state: SimulationState) -> dict[str, Any]`，内部处理 `NarratorInput` 构建、prompt message 构建、JSON retry、ai_prose_ticks 检查、metadata 写回和角色记忆更新。为避免循环 import，把 `SimulationState` TypedDict 移到 `engine/state.py`，`graph.py` 和 service 都从那里导入。`graph.narrator_node()` 变成一行 delegate 加 telemetry 边界保留。

### 6. 引入轻量 LLM Gateway，只先服务新代码 — `src/worldbox_writer/llm/gateway.py` (add)

不要立刻改完所有 Agent。先定义最小接口：

```python
class CompletionGateway(Protocol):
    def complete(self, profile_id: str, messages: list[dict[str, str]], **kwargs: Any) -> str: ...
    def last_metadata(self) -> dict[str, Any] | None: ...
```

默认实现包装 `chat_completion_with_profile()` 和 `get_last_llm_call_metadata()`。`NarrationService` 先使用 gateway；Actor/Critic/Director 等 Agent 仍可保留当前 `_invoke`，等 service 层稳定后再迁。这样不会一次性冲击所有 monkeypatch 测试。

### 7. 前端最后拆 hook，不改变组件契约 — `frontend/src/hooks/useSimulation.ts` (modify)

后端 API shape 稳定后再拆前端。保留 `useSimulation()` 的返回字段不变，新增 `useSimulationTransport` 管 SSE/polling，`useSimulationActions` 管 start/open/intervene/export，`useBranchActions` 管 branch 操作。`App.tsx` 不需要改业务逻辑，只继续消费同一个 hook 返回值。这样能减少 hook 体积，但不会让所有组件一起改 props。

## 关键文件

| File | Change | Notes |
|------|--------|-------|
| `src/worldbox_writer/api/state.py` | modify | 成为 API 内存状态和 API 常量的单一来源 |
| `src/worldbox_writer/api/session.py` | add | 承载 `SimulationSession` 和 session 队列/节点合并辅助 |
| `src/worldbox_writer/api/services/simulation_service.py` | add | 启动、查询、干预、恢复、后台运行用例 |
| `src/worldbox_writer/api/services/branch_service.py` | add | 分支创建、切换、对比、节奏更新 |
| `src/worldbox_writer/api/services/workspace_service.py` | add | 角色、关系、世界、约束、Wiki、正文编辑 |
| `src/worldbox_writer/api/routes/simulations.py` | add | 薄 Controller，先承载 start/get/stream/list |
| `src/worldbox_writer/api/server.py` | modify | 保留 app 创建、router 注册和旧私有符号兼容别名 |
| `src/worldbox_writer/engine/state.py` | add | 提供 `SimulationState`，避免 graph/service 循环 import |
| `src/worldbox_writer/engine/services/narration_service.py` | add | 从 `narrator_node` 抽出的渲染和质量策略 |
| `src/worldbox_writer/llm/gateway.py` | add | 新 service 使用的轻量 LLM 接口 |

## 验证

1. 每一步迁移后跑 focused tests：`pytest tests/test_api/test_edit_endpoints.py -q`、`pytest tests/test_engine/test_progressive_feedback.py -q`。
2. Session 兼容别名迁移后确认 `tests/test_api/test_edit_endpoints.py` 仍可 import `SimulationSession`、`_sessions`、`_run_simulation_sync`、`_restore_world_at_node`。
3. NarrationService 抽出后跑 `pytest tests/test_agents/test_narrator_quality.py tests/test_engine/test_progressive_feedback.py -q`。
4. LLM gateway 引入后跑 `pytest tests/test_utils/test_llm.py tests/test_agents/test_critic.py -q`，并保留旧 monkeypatch 路径直到 Agent 分批迁移完成。
5. 每个阶段完成后跑默认门禁：`make lint`、`make test`；真实 LLM 相关改动再尝试 `make integration`，外部 402/无 key 只记录为环境阻塞。
