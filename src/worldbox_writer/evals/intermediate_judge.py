"""LLM-as-judge scoring for intermediate agent outputs.

This module covers the P0 intermediate nodes from
docs/product/QUALITY_SPEC.md §5 (Intermediate Node Evaluation):

- actor_intent: isolated actor ActionIntent output
- critic_review: CriticAgent IntentCritique output

Quality scoring is always delegated to a judge LLM. Local code only validates
format, parses judge JSON, aggregates scores, and verifies evidence quotes.
"""

from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass
from typing import Any, Mapping, TypedDict

from worldbox_writer.evals.llm_judge import (
    DEFAULT_JUDGE_MODEL,
    _evidence_in_text,
    _resolve_judge_model,
    parse_judge_response,
)
from worldbox_writer.utils.llm import chat_completion

INTERMEDIATE_SCHEMA_VERSION = "intermediate-judge-v0.1"


class DimensionScore(TypedDict):
    name: str
    applicable: bool | None
    score: float | None
    evidence_quote: str
    reasoning: str
    parse_status: str
    error: str | None
    coercions: list[str]
    elapsed_ms: int


class NodeJudgement(TypedDict):
    schema_version: str
    node_name: str
    sample_id: str
    status: str
    dimensions: list[DimensionScore]
    overall: float | None
    evidence_chain: list[str]
    judge_model: str
    runtime_model: str
    errors: list[dict[str, Any]]
    elapsed_ms: int


@dataclass(frozen=True)
class IntermediateDimension:
    name: str
    chinese_name: str
    system_prompt: str


_OUTPUT_SCHEMA = """输出严格 JSON，不要 markdown，不要解释。schema：
{
  "applicable": true | false,
  "score": <0-10 数值；当 applicable=false 时为 null>,
  "evidence_quote": "<不超过 80 字的原始 input/output 片段，必须真实出现；找不到则空字符串>",
  "reasoning": "≤80 字"
}"""


def _dimension(
    name: str, chinese_name: str, question: str, anchors: str
) -> IntermediateDimension:
    return IntermediateDimension(
        name=name,
        chinese_name=chinese_name,
        system_prompt=(
            f"你是 WorldBox Writer 中间节点评测系统的「{chinese_name}」维度专家。\n"
            "你只评这一个维度，不评其他维度。必须同时阅读 input_context 与 output。\n\n"
            f"核心问题：\n{question}\n\n"
            f"评分锚点：\n{anchors}\n\n"
            f"{_OUTPUT_SCHEMA}\n\n"
            "硬规则：\n"
            "- 禁止用关键词命中或长度等启发式替代质量判断。\n"
            "- evidence_quote 必须是 input_context 或 output 中真实出现的原文子串。\n"
            "- 如果信息不足以判断，返回 applicable=false 且 score=null。\n"
        ),
    )


ACTOR_INTENT_DIMENSIONS: tuple[IntermediateDimension, ...] = (
    _dimension(
        "character_fidelity",
        "角色一致性",
        "行为是否符合该角色的 persona、目标、历史行为和当前处境，是否避免 OOC。",
        "10=高度贴合角色；6=基本合理但略通用；3=明显违背角色；0=完全不可置信。",
    ),
    _dimension(
        "motivation_visibility",
        "动机可见性",
        "intent 是否让读者看出角色为什么此刻这样做，而不仅是做了什么。",
        "10=动作自然显出欲望/恐惧/处境；5=动机存在但直白或模糊；0=完全无动机。",
    ),
    _dimension(
        "action_specificity",
        "行动具体性",
        "行动是否有目标、对象、手段和时空锚点，是否避免概括性动作。",
        "10=具体到动作/对象/位置；5=部分具体；0=空泛如处理危机/推进主线。",
    ),
    _dimension(
        "confidence_calibration",
        "置信度校准",
        "confidence 是否与行动可执行度、信息充分度和风险程度匹配。",
        "10=自评与可执行度高度匹配；5=略虚高/虚低；0=明显乱填或极端失真。",
    ),
    _dimension(
        "memory_consistency",
        "记忆一致性",
        "intent 是否与角色工作记忆、情景记忆、反思记忆或已知历史冲突。",
        "10=完全一致并善用记忆；5=未明显冲突但利用不足；0=直接违背记忆。",
    ),
)


CRITIC_REVIEW_DIMENSIONS: tuple[IntermediateDimension, ...] = (
    _dimension(
        "policy_recall",
        "政策召回",
        "当 intent 明显违反世界规则、知识边界、角色一致性或安全边界时，Critic 是否识别并阻断/警告。",
        "10=准确抓住违规；6=识别方向对但理由弱；3=遗漏主要违规；0=明显漏杀。",
    ),
    _dimension(
        "policy_precision",
        "政策精确性",
        "当 intent 看似敏感但实际合规时，Critic 是否避免误杀。",
        "10=准确放行；6=给 warning 但未误杀；3=误判较重；0=明显误杀。",
    ),
    _dimension(
        "reason_grounding",
        "理由扎根性",
        "reason 是否引用具体政策条款、世界规则、场景约束或上下文证据，而不是空泛拒绝。",
        "10=理由具体且可追溯；5=有依据但笼统；0=空话或与上下文无关。",
    ),
    _dimension(
        "severity_calibration",
        "严重度校准",
        "severity 是否与违规程度匹配。当前 Critic schema 为 info/warning/blocking。",
        "10=严重度精准；5=轻微偏高/偏低；0=blocking/info 完全反置。",
    ),
    _dimension(
        "revision_hint_actionability",
        "修正建议可执行性",
        "revision_hint 是否能被 Actor 直接采纳，产出合规且保留戏剧目标的版本。",
        "10=具体可执行；5=方向可用但偏泛；0=空泛、不可执行或误导。",
    ),
)


DIMENSIONS_BY_NODE: dict[str, tuple[IntermediateDimension, ...]] = {
    "actor_intent": ACTOR_INTENT_DIMENSIONS,
    "actor": ACTOR_INTENT_DIMENSIONS,
    "critic_review": CRITIC_REVIEW_DIMENSIONS,
    "critic": CRITIC_REVIEW_DIMENSIONS,
}

CANONICAL_NODE_NAMES = {
    "actor": "actor_intent",
    "actor_intent": "actor_intent",
    "critic": "critic_review",
    "critic_review": "critic_review",
}


def canonical_node_name(node_name: str) -> str:
    normalized = node_name.strip().lower().replace("-", "_")
    return CANONICAL_NODE_NAMES.get(normalized, normalized)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {
            key: _jsonable(val)
            for key, val in vars(value).items()
            if not key.startswith("_")
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _source_text(input_context: Any, output: Any) -> str:
    return json.dumps(
        {"input_context": _jsonable(input_context), "output": _jsonable(output)},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _format_errors(node_name: str, output: Any) -> list[str]:
    canonical = canonical_node_name(node_name)
    if not isinstance(output, Mapping):
        return ["output is not a structured mapping"]

    if canonical == "actor_intent":
        required = {"actor_name", "summary", "rationale", "confidence"}
    elif canonical == "critic_review":
        required = {"accepted", "reason_code", "severity", "reason", "revision_hint"}
    else:
        required = set()

    missing = sorted(key for key in required if key not in output)
    return [f"missing required field: {key}" for key in missing]


def _empty_result(
    *,
    node_name: str,
    sample_id: str,
    status: str,
    judge_model: str,
    runtime_model: str,
    errors: list[dict[str, Any]],
    elapsed_ms: int = 0,
) -> NodeJudgement:
    return {
        "schema_version": INTERMEDIATE_SCHEMA_VERSION,
        "node_name": node_name,
        "sample_id": sample_id,
        "status": status,
        "dimensions": [],
        "overall": None,
        "evidence_chain": [],
        "judge_model": judge_model,
        "runtime_model": runtime_model,
        "errors": errors,
        "elapsed_ms": elapsed_ms,
    }


def _judge_one_dimension(
    dim: IntermediateDimension,
    *,
    source_text: str,
    judge_model: str,
    temperature: float,
    max_tokens: int,
) -> DimensionScore:
    started = _time.time()
    raw = ""
    error: str | None = None
    retry_after_parse_error = False
    parsed: dict[str, Any] = {}
    for attempt in range(2):
        user_content = (
            "请评测以下中间节点样本。input_context 是被裁判节点看到的上下文，"
            "output 是该节点产物：\n\n"
            f"{source_text}"
        )
        if attempt > 0:
            user_content = (
                "上一次响应无法解析为指定 JSON。请重新评测同一个样本，只输出"
                "一个合法 JSON 对象，不要 markdown，不要额外解释。\n\n"
                f"{source_text}"
            )
        try:
            raw = chat_completion(
                [
                    {"role": "system", "content": dim.system_prompt},
                    {"role": "user", "content": user_content},
                ],
                role="narrator",
                model=judge_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            error = None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raw = ""

        parsed = parse_judge_response(raw) if raw else {"error": error or "no_response"}
        if "applicable" in parsed:
            break
        retry_after_parse_error = True

    parse_status = "ok"
    applicable: bool | None
    if isinstance(parsed.get("error"), str) and "applicable" not in parsed:
        parse_status = "parse_failed"
        applicable = None
    elif "applicable" not in parsed:
        parse_status = "missing_fields"
        applicable = None
    else:
        applicable = bool(parsed.get("applicable"))

    score: float | None = None
    raw_score = parsed.get("score")
    if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
        score = round(min(10.0, max(0.0, float(raw_score))), 2)

    evidence_quote = str(parsed.get("evidence_quote") or "")[:240]
    reasoning = str(parsed.get("reasoning") or parsed.get("reason") or "")[:240]
    coercions: list[str] = []
    if retry_after_parse_error and parse_status == "ok":
        coercions.append("judge_retry_after_parse_error")
    if evidence_quote.strip() and not _evidence_in_text(source_text, evidence_quote):
        coercions.append("evidence_quote_not_in_source")
        if score is not None and score >= 5:
            score = 4.0
            coercions.append("score_demoted_due_to_fabricated_evidence")

    elapsed_ms = int((_time.time() - started) * 1000)
    return {
        "name": dim.name,
        "applicable": applicable,
        "score": score,
        "evidence_quote": evidence_quote,
        "reasoning": reasoning,
        "parse_status": parse_status,
        "error": error,
        "coercions": coercions,
        "elapsed_ms": elapsed_ms,
    }


def judge_node_output(
    node_name: str,
    input_context: dict[str, Any],
    output: Any,
    *,
    sample_id: str = "",
    judge_model: str | None = None,
    runtime_model: str = "",
    temperature: float = 0.2,
    max_tokens: int = 320,
) -> NodeJudgement:
    """Score one intermediate node output with node-specific judge dimensions."""
    started = _time.time()
    canonical = canonical_node_name(node_name)
    selected_model = _resolve_judge_model(judge_model)
    sample_id = sample_id or "sample-unknown"

    dimensions = DIMENSIONS_BY_NODE.get(canonical)
    if dimensions is None:
        return _empty_result(
            node_name=canonical,
            sample_id=sample_id,
            status="unsupported_node",
            judge_model=selected_model,
            runtime_model=runtime_model,
            errors=[{"error": f"unsupported node: {node_name}"}],
        )

    format_errors = _format_errors(canonical, _jsonable(output))
    if format_errors:
        elapsed_ms = int((_time.time() - started) * 1000)
        return _empty_result(
            node_name=canonical,
            sample_id=sample_id,
            status="format_invalid",
            judge_model=selected_model,
            runtime_model=runtime_model,
            errors=[{"error": error} for error in format_errors],
            elapsed_ms=elapsed_ms,
        )

    text = _source_text(input_context, output)
    records = [
        _judge_one_dimension(
            dim,
            source_text=text,
            judge_model=selected_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        for dim in dimensions
    ]
    scores: list[float] = []
    for record in records:
        score = record["score"]
        if record["applicable"] is not False and score is not None:
            scores.append(float(score))
    overall = round(sum(scores) / len(scores), 2) if scores else None
    errors = [
        {
            "dimension": record["name"],
            "parse_status": record["parse_status"],
            "error": record["error"],
        }
        for record in records
        if record["parse_status"] != "ok" or record["error"]
    ]
    elapsed_ms = int((_time.time() - started) * 1000)
    return {
        "schema_version": INTERMEDIATE_SCHEMA_VERSION,
        "node_name": canonical,
        "sample_id": sample_id,
        "status": "ok" if not errors else "partial_error",
        "dimensions": records,
        "overall": overall,
        "evidence_chain": [
            record["evidence_quote"]
            for record in records
            if record["evidence_quote"].strip()
        ],
        "judge_model": selected_model or DEFAULT_JUDGE_MODEL,
        "runtime_model": runtime_model,
        "errors": errors,
        "elapsed_ms": elapsed_ms,
    }
