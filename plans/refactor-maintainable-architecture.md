# 可维护架构重构

## 背景

当前后端的主要问题不是缺少模式，而是职责混在同一层：`api/server.py` 同时承担 HTTP 路由、Session 编排、世界编辑、分支恢复和导出；`engine/graph.py` 同时承担 LangGraph 节点、Prompt 拼装、LLM 调用、质量检查和 metadata 写入。目标是做低风险的渐进分层，让 Controller 变薄、业务用例可测试、Agent/Engine 依赖接口而不是直接依赖全局函数，同时避免引入复杂 DI 容器或大规模重写。

## 方案

### 1. 明确分层边界 — `src/worldbox_writer/api/server.py` (modify)

保留 FastAPI app 创建和路由注册，但把 handler 改成薄 Controller：只做参数接收、异常转 HTTP、调用 service、返回 schema。按 MVC 实践映射为：Model 是 `core/models.py` 与持久化实体，View 是 `api/schemas.py` / serializer / 前端组件，Controller 是 `api/routes/*`，Application Service 负责用例编排。先不改公开 API shape，避免前端联动风险。

### 2. 拆出 API 用例服务 — `src/worldbox_writer/api/services/simulation_service.py` (add)

新增 `SimulationService` 管理启动、恢复、轮询 payload、干预、运行线程回调等用例，签名保持简单：
- `start(request: StartSimulationRequest) -> SimulationResponse`
- `get(sim_id: str, branch: str | None = None) -> dict[str, Any]`
- `intervene(sim_id: str, request: InterveneRequest) -> dict[str, Any]`

`SimulationSession` 可以先迁到 `api/session.py`，保留现有字段和队列语义；service 内部继续使用现有 `_sessions` 与 `_executor`，第一步不引入 repository interface，避免过度设计。风险是并发状态写入，迁移时每次只移动一个 endpoint 并保持现有 tests 通过。

### 3. 将世界编辑和分支能力从 server 分离 — `src/worldbox_writer/api/services/world_edit_service.py` (add)

把 `_apply_wiki_request`、角色编辑、关系编辑、世界规则编辑、约束新增、分支创建/切换/对比拆成两个 service：`WorldEditService` 和 `BranchService`。这些 service 接收 `SimulationSession` / `WorldState`，返回更新后的 payload 或 domain error，不直接依赖 FastAPI。这样 Controller 只负责把 domain error 转成 `HTTPException`。边界上不新建复杂 command bus，只用普通方法。

### 4. 收拢 Engine 节点业务 — `src/worldbox_writer/engine/services/narration_service.py` (add)

`engine/graph.py` 只保留 LangGraph wiring、state routing 和 telemetry 入口；把 narrator 相关逻辑迁到 `NarrationService.render_current_node(state: SimulationState) -> NarrationResult`。该 service 负责构建 `NarratorInput`、调用 narrator prompt、JSON retry、ai_prose_ticks 策略、写回 node metadata。后续 Actor event、GateKeeper self-heal、relationship update 可以按同样方式拆，但第一轮只拆 narrator，因为它现在最重且最容易测试。

### 5. 引入轻量 LLM 接口 — `src/worldbox_writer/llm/gateway.py` (add)

定义一个最小 Protocol，而不是引入 DI 框架：

```python
class CompletionGateway(Protocol):
    def complete(self, profile_id: str, messages: list[dict[str, str]], **kwargs: Any) -> str: ...
    def last_metadata(self) -> dict[str, Any] | None: ...
```

默认实现 `ProfiledCompletionGateway` 包装 `chat_completion_with_profile()` 和 `get_last_llm_call_metadata()`。Agent 构造函数从 `llm: Any = None` 逐步迁到 `gateway: CompletionGateway | None = None`，测试里可注入 fake gateway。第一轮先改 Narrator/Actor/Critic 三类高频路径，避免一次触动所有 Agent。

### 6. 常量和配置按领域收口 — `src/worldbox_writer/engine/constants.py` (add)

不要创建一个全局巨型 `constants.py`。按领域放置：
- `engine/constants.py`：`AI_PROSE_TICKS_BANNED_MARKERS`、`GATE_KEEPER_SELF_HEAL_ATTEMPTS`、relationship keyword sets。
- `api/constants.py`：session status、SSE event type、branch pacing allowlist。
- `config/settings.py`：运行时可变配置和 env default，继续保留。
- `config/agent_profiles.yaml` / `prompts/*.yaml`：采样参数和 prompt，不回收到 Python 常量。

规则是：业务固定词表放 constants，环境可变值放 settings，模型采样放 YAML profile，prompt 文本放 prompt YAML。这样能减少 magic string，又不会把所有东西集中成第二个事实源。

### 7. 前端按容器和视图拆小 — `frontend/src/hooks/useSimulation.ts` (modify)

前端不需要完整 MVC，但可以按同样原则降复杂度：`useSimulation.ts` 保留组合入口，拆出 `useSimulationTransport` 管 SSE/polling，`useSimulationActions` 管 start/intervene/export，`useBranchActions` 管 branch 操作。`App.tsx` 保持页面 composition，不直接承载业务规则。第一轮只拆 hook，不改组件 props shape。

## 关键文件

| File | Change | Notes |
|------|--------|-------|
| `src/worldbox_writer/api/server.py` | modify | 从胖 Controller 逐步改成路由注册和薄 handler |
| `src/worldbox_writer/api/routes/simulations.py` | add | 承载 simulation HTTP endpoints 的薄 Controller |
| `src/worldbox_writer/api/session.py` | add | 承载 `SimulationSession` 和 session 状态辅助 |
| `src/worldbox_writer/api/services/simulation_service.py` | add | 启动、恢复、查询、干预等 simulation 用例 |
| `src/worldbox_writer/api/services/world_edit_service.py` | add | wiki、角色、关系、世界规则、约束编辑 |
| `src/worldbox_writer/api/services/branch_service.py` | add | 分支创建、切换、恢复、对比 |
| `src/worldbox_writer/engine/graph.py` | modify | 保留 LangGraph wiring，移出 narrator 重逻辑 |
| `src/worldbox_writer/engine/services/narration_service.py` | add | narrator 输入构建、渲染、质量策略和 metadata 写回 |
| `src/worldbox_writer/engine/constants.py` | add | Engine 领域固定常量和词表 |
| `src/worldbox_writer/api/constants.py` | add | API session status、event type、pacing 常量 |
| `src/worldbox_writer/llm/gateway.py` | add | 轻量 LLM completion 接口和默认实现 |
| `frontend/src/hooks/useSimulation.ts` | modify | 拆成组合 hook，保留对外返回 shape |

## 验证

1. 每个迁移小步先跑对应 focused tests，例如 `pytest tests/test_api/test_edit_endpoints.py -q`、`pytest tests/test_engine/test_progressive_feedback.py -q`。
2. 每完成一个阶段跑默认门禁：`make lint`、`make test`。
3. LLM gateway 改动后跑 `pytest tests/test_agents/test_critic.py tests/test_agents/test_narrator_quality.py tests/test_utils/test_llm.py -q`。
4. Agent/Prompt/真实模型路径变更后尝试 `make integration`，若外部 provider 返回 402 或无 key，需要记录为环境失败而不是代码失败。
5. 前端 hook 拆分后跑 `cd frontend && pnpm vitest run src/hooks src/App.test.tsx && pnpm build`。
