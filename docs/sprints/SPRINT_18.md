# Sprint 18 Plan：灰度上线与对比评估

**文档状态**：Completed
**版本目标**：Sprint 18 / Dual-loop rollout guardrails
**Sprint 周期**：2 周
**定位**：Product Planning v2 的第九个实现 Sprint
**作者**：Codex
**最后更新**：2026-04-22

---

## 1. Sprint 18 要解决什么问题

Sprint 17 让双循环链路从 ScenePlan、Actor Intent、Critic、GM、Memory、Inspector 一直贯通到 Narrator 渲染。但“能跑”还不等于“可以默认上线”。

Sprint 18 的目标是给双循环链路补齐灰度发布护栏：对比报告、CLI 报告、评估门禁说明和回滚 runbook。这样系统管理员可以判断当前会话是否具备替换旧链路的证据，并在异常时快速退回安全路径。

---

## 2. Sprint Goal

**提供 dual-loop rollout compare report，让旧链路与双循环链路的关键证据可观测、可脚本化、可回滚。**

Sprint 18 结束时，项目具备：

- `/api/simulate/{sim_id}/dual-loop/compare`
- `python -m worldbox_writer.evals.dual_loop_compare <sim_id>` CLI
- rollout readiness checks
- rollback flag/runbook 指向
- model-eval / integration guardrail 策略
- API / CLI / helper 回归测试

---

## 3. 方案骨架

### 3.1 承诺交付

1. dual-loop compare report helper
2. compare report API
3. compare report CLI
4. rollout readiness checks
5. rollback runbook
6. 发布前检查文档更新

### 3.2 非目标

- 不把双循环强制切为唯一默认引擎之外的无回退路径
- 不新增在线 A/B 实验平台
- 不让 model-eval 成为默认 CI gate
- 不新增前端面板，只预留 TypeScript contract 和 API client

---

## 4. 方案收敛记录

### Round 1：把 compare 信息塞进 diagnostics

问题：

- diagnostics 面向当前运行状态，compare report 面向发布判定和回滚证据
- 灰度报告需要 CLI 复用，不能只存在于 API 聚合逻辑中

结论：否决。

### Round 2：新增可复用 report helper，API 和 CLI 共用

采用方案：

- `build_dual_loop_compare_report()` 从 WorldState、rendered nodes 和 telemetry 生成报告
- API endpoint 和 CLI 共用同一 helper
- readiness checks 分 required / optional，避免缺少 PromptTrace 时误判为硬失败
- rollback 信息在报告中直接暴露 `FEATURE_DUAL_LOOP_ENABLED=0`

结论：采用。

---

## 5. Sprint Backlog

| ID | 条目 | 优先级 | 状态 |
| :--- | :--- | :--- | :--- |
| S18-01 | dual-loop compare helper | P0 | Done |
| S18-02 | compare report API | P0 | Done |
| S18-03 | compare report CLI | P0 | Done |
| S18-04 | rollout / rollback docs | P0 | Done |
| S18-05 | API / helper / CLI tests | P0 | Done |

---

## 6. 成功标准

- Compare report 能统计 legacy node/rendered counts
- Compare report 能统计 SceneScript、NarratorInput v2、IntentCritique、PromptTrace 和 reflection note 证据
- readiness 必须检查 feature flag、SceneScript lineage、NarratorInput v2 和 rollback path
- CLI 能把报告写入 `artifacts/dual-loop-compare/<sim_id>.json`
- runbook 明确 `FEATURE_DUAL_LOOP_ENABLED=0` 的回滚路径
- `make lint`、`make test`、`make typecheck` 通过；最终回归执行 `make integration`

---

## 7. 为什么这个范围满足设计预期

Sprint 18 选择“报告 + 文档 + CLI”而不是直接做更复杂的实验平台，是因为当前最需要的是上线前证据闭环。API 支撑前端或运维面板，CLI 支撑脚本化评估，runbook 支撑快速回退。

至此，Product Planning v2 的双循环主线已经具备：结构化契约、场控、隔离 Actor、Critic、GM、认知记忆、Inspector、SceneScript 渲染和灰度发布护栏。
