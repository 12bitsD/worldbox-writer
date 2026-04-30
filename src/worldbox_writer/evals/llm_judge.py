"""LLM-as-judge evaluation for web-novel quality.

Sprint 25 R6 final state. Follows `docs/product/QUALITY_SPEC.md` (single
source of truth). Public API:

- `judge_committee(text)` — single-passage scoring across 13 dimensions
  (7 per-passage + 5 conditional + 3 toxic with forced_stupidity also
  carrying conditional applicability). Returns per-dim records, three-axis
  aggregate (emotion 0.4 / structure 0.3 / prose 0.3), toxic veto at score
  ≥ 8, and overall (vetoed → 0).

- `judge_multi_chapter(chapters)` — cross-passage scoring across 4
  cross-passage dimensions (foreshadowing / character_arc / stakes /
  setting). Requires ≥ 2 chapters; returns per-dim records and an overall
  mean of applicable scores.

- `parse_judge_response(raw)` — defensive JSON parser shared by both APIs;
  falls back to `{"error": "parse_failed", "raw": raw}` when nothing
  parseable is found.

Deprecated APIs removed in Sprint 25 R6 (judge_prose / judge_story /
judge_scene_script / batch_judge / aggregate_judge_results / build_*_
judge_prompt). The single-prompt-multi-dim approach was found in R1 to
smear scores across unrelated dimensions; the committee approach replaces
it everywhere.
"""

from __future__ import annotations

import json
import os
import time as _time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping

from worldbox_writer.evals.dimension_prompts import (
    ALL_DIMENSIONS,
    CROSS_PASSAGE_DIMENSIONS,
    DIMENSION_AXIS_MAP,
    TOXIC_VETO_IDS,
    DimensionPrompt,
    build_multi_chapter_user_message,
    build_user_message,
)
from worldbox_writer.utils.llm import chat_completion

DEFAULT_JUDGE_MODEL = "gpt-5.5"
JUDGE_MODEL_ENV = "WORLDBOX_JUDGE_MODEL"


def _resolve_judge_model(model: str | None) -> str:
    return model or os.environ.get(JUDGE_MODEL_ENV, DEFAULT_JUDGE_MODEL)


def _fenced_blocks(raw: str) -> list[str]:
    blocks: list[str] = []
    cursor = 0
    fence = "```"
    while True:
        start = raw.find(fence, cursor)
        if start == -1:
            break
        content_start = raw.find("\n", start + len(fence))
        if content_start == -1:
            break
        end = raw.find(fence, content_start + 1)
        if end == -1:
            break
        blocks.append(raw[content_start + 1 : end].strip())
        cursor = end + len(fence)
    return blocks


def _json_candidates(raw: str) -> list[str]:
    candidates = _fenced_blocks(raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1].strip())
    candidates.append(raw.strip())
    return candidates


def parse_judge_response(raw: str) -> dict[str, Any]:
    """Parse a judge response, returning an error dict when JSON is invalid."""
    for candidate in _json_candidates(raw):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {"error": "parse_failed", "raw": raw}


COMMITTEE_SCHEMA_VERSION = "committee-v0.2"
COMMITTEE_AXIS_WEIGHTS: dict[str, float] = {
    "emotion_axis": 0.4,
    "structure_axis": 0.3,
    "prose_axis": 0.3,
}
COMMITTEE_TOXIC_VETO_THRESHOLD = 8.0


_QUOTE_NORMALIZATION = str.maketrans(
    {
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "‘": "'",  # left single quote
        "’": "'",  # right single quote
    }
)


def _normalize_for_substring(s: str) -> str:
    """Normalize quote variants and whitespace for evidence substring checks.

    Judge models occasionally swap curly/straight quotes when echoing source
    text. We accept that as still being a valid quote, but reject anything
    not derivable from the original after this normalization.
    """
    return "".join(ch for ch in s.translate(_QUOTE_NORMALIZATION) if not ch.isspace())


def _evidence_in_text(text: str, quote: str) -> bool:
    """True iff `quote` is a substring of `text` after light normalization.

    Empty quote is treated as "not in text" — callers decide what an empty
    quote means based on dimension category and score threshold.
    """
    if not quote.strip():
        return False
    return _normalize_for_substring(quote) in _normalize_for_substring(text)


def _committee_call_one(
    dim: DimensionPrompt,
    text: str,
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    """Run one dimension prompt against text and return a normalized record."""
    started = _time.time()
    messages = [
        {"role": "system", "content": dim.system_prompt},
        {"role": "user", "content": build_user_message(text)},
    ]
    raw = ""
    error: str | None = None
    try:
        raw = chat_completion(
            messages,
            role="narrator",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    parsed = parse_judge_response(raw) if raw else {"error": error or "no_response"}

    parse_status = "ok"
    applicable: bool | None = None
    score: float | None = None
    if isinstance(parsed.get("error"), str) and "applicable" not in parsed:
        parse_status = "parse_failed"
    elif "applicable" not in parsed:
        parse_status = "missing_fields"
    else:
        applicable = bool(parsed.get("applicable"))

    raw_score = parsed.get("score")
    if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
        score = round(min(10.0, max(0.0, float(raw_score))), 2)

    evidence_quote = str(parsed.get("evidence_quote") or "")[:240]
    setup_quote = str(parsed.get("setup_quote") or "")[:240]

    # Schema coercions enforced post-parse:
    # 1. forced_stupidity v0.2 hard rule — applicable=true requires BOTH
    #    setup_quote AND a numeric score. R2 observed the judge returning
    #    applicable=true + score=null when it couldn't find a setup. Coerce
    #    those into applicable=false so downstream veto logic isn't fed a
    #    half-judgement.
    # 2. Evidence substring validation — when score ≥ 5, evidence_quote
    #    must be a real substring of the input. R3 found judges occasionally
    #    paraphrase or invent the quote. Fabricated quote → demote score to 4.
    coercions: list[str] = []
    if dim.dim_id == "forced_stupidity" and applicable is True:
        if score is None:
            applicable = False
            coercions.append("forced_stupidity_no_score")
        elif not setup_quote.strip():
            applicable = False
            score = None
            coercions.append("forced_stupidity_no_setup")

    evidence_invalid = False
    if evidence_quote.strip() and not _evidence_in_text(text, evidence_quote):
        evidence_invalid = True
        coercions.append("evidence_quote_not_in_source")
        if isinstance(score, (int, float)) and score >= 5:
            score = 4.0
            coercions.append("score_demoted_due_to_fabricated_evidence")

    setup_invalid = False
    if dim.dim_id == "forced_stupidity" and setup_quote.strip():
        if not _evidence_in_text(text, setup_quote):
            setup_invalid = True
            coercions.append("setup_quote_not_in_source")
            if applicable is True:
                applicable = False
                score = None
                coercions.append("forced_stupidity_demoted_due_to_fabricated_setup")

    elapsed_ms = int((_time.time() - started) * 1000)
    return {
        "dim_id": dim.dim_id,
        "category": dim.category,
        "applicable": applicable,
        "score": score,
        "evidence_quote": evidence_quote,
        "evidence_invalid": evidence_invalid,
        "setup_quote": setup_quote,
        "setup_invalid": setup_invalid,
        "rule_hit": str(parsed.get("rule_hit") or ""),
        "reasoning": str(parsed.get("reasoning") or "")[:120],
        "raw_excerpt": raw[:240],
        "parse_status": parse_status,
        "error": error,
        "elapsed_ms": elapsed_ms,
        "coercions": coercions,
    }


def _committee_axis_aggregate(
    per_dim: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Average applicable+scored dims into three axis means.

    Conditional dims that returned applicable=false are excluded — they don't
    drag the axis up or down.
    """
    buckets: dict[str, list[float]] = {axis: [] for axis in COMMITTEE_AXIS_WEIGHTS}
    n_applicable: dict[str, int] = {axis: 0 for axis in COMMITTEE_AXIS_WEIGHTS}
    n_total: dict[str, int] = {axis: 0 for axis in COMMITTEE_AXIS_WEIGHTS}

    for dim_id, axis in DIMENSION_AXIS_MAP.items():
        record = per_dim.get(dim_id)
        if record is None:
            continue
        n_total[axis] += 1
        if record.get("applicable") and isinstance(record.get("score"), (int, float)):
            buckets[axis].append(float(record["score"]))
            n_applicable[axis] += 1

    axis_scores = {
        axis: round(sum(scores) / len(scores), 2) if scores else None
        for axis, scores in buckets.items()
    }
    return {
        "axis_scores": axis_scores,
        "n_applicable_per_axis": n_applicable,
        "n_total_per_axis": n_total,
    }


def _committee_toxic_summary(
    per_dim: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Return per-toxic-dim summary and list of dims that triggered veto."""
    summary: dict[str, Any] = {}
    veto_reasons: list[str] = []
    for dim_id in sorted(TOXIC_VETO_IDS):
        record = per_dim.get(dim_id)
        if record is None:
            summary[dim_id] = {
                "applicable": None,
                "score": None,
                "hit": False,
                "evidence_quote": "",
                "rule_hit": "",
            }
            continue
        applicable = record.get("applicable")
        score = record.get("score")
        # For conditional toxic dims (e.g., forced_stupidity v0.2): only counts
        # as a hit if applicable=true AND score >= threshold.
        # For always-applicable toxic dims (preachiness, ai_prose_ticks):
        # applicable is always true, so just score-based.
        is_hit = (
            isinstance(score, (int, float))
            and applicable is not False
            and float(score) >= COMMITTEE_TOXIC_VETO_THRESHOLD
        )
        summary[dim_id] = {
            "applicable": applicable,
            "score": score,
            "hit": is_hit,
            "evidence_quote": record.get("evidence_quote", ""),
            "rule_hit": record.get("rule_hit", ""),
        }
        if is_hit:
            veto_reasons.append(dim_id)
    return summary, veto_reasons


def _committee_overall(
    axis_scores: Mapping[str, float | None],
    weights: Mapping[str, float],
) -> tuple[float, dict[str, float]]:
    """Compute weighted overall, normalizing weights over axes that have data."""
    valid = {
        axis: float(weights.get(axis, 0.0))
        for axis, score in axis_scores.items()
        if score is not None and weights.get(axis, 0.0) > 0
    }
    total_weight = sum(valid.values())
    if not valid or total_weight <= 0:
        return 0.0, {axis: 0.0 for axis in weights}
    normalized = {axis: w / total_weight for axis, w in valid.items()}
    overall = sum(float(axis_scores[axis]) * normalized[axis] for axis in normalized)
    full_weights = {axis: 0.0 for axis in weights}
    full_weights.update(normalized)
    return round(overall, 2), full_weights


def judge_committee(
    text: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 320,
    concurrency: int = 1,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Score a passage by running every kept dimension as an independent judge.

    Default concurrency=1 because R1 showed that high-concurrency real-LLM
    runs exhaust macOS ephemeral ports. Override only if running on Linux or
    with infrastructure that supports it.
    """
    started = _time.time()
    selected_model = _resolve_judge_model(model)
    effective_weights = dict(COMMITTEE_AXIS_WEIGHTS)
    if weights:
        for axis, value in weights.items():
            if axis in effective_weights and isinstance(value, (int, float)):
                effective_weights[axis] = max(0.0, float(value))

    workers = max(1, int(concurrency))
    if workers == 1:
        records = [
            _committee_call_one(
                dim,
                text,
                model=selected_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            for dim in ALL_DIMENSIONS
        ]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            records = list(
                executor.map(
                    lambda dim: _committee_call_one(
                        dim,
                        text,
                        model=selected_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ),
                    ALL_DIMENSIONS,
                )
            )

    per_dim = {record["dim_id"]: record for record in records}
    axis_aggregate = _committee_axis_aggregate(per_dim)
    toxic_summary, veto_reasons = _committee_toxic_summary(per_dim)
    weighted_pre_veto, normalized_weights = _committee_overall(
        axis_aggregate["axis_scores"],
        effective_weights,
    )
    vetoed = bool(veto_reasons)
    overall = 0.0 if vetoed else weighted_pre_veto

    errors = [
        {
            "dim_id": record["dim_id"],
            "parse_status": record["parse_status"],
            "error": record["error"],
        }
        for record in records
        if record["parse_status"] != "ok" or record["error"]
    ]

    elapsed = round(_time.time() - started, 2)
    return {
        "schema_version": COMMITTEE_SCHEMA_VERSION,
        "model": selected_model,
        "text_chars": len(text),
        "per_dimension": per_dim,
        "axis_scores": axis_aggregate["axis_scores"],
        "n_applicable_per_axis": axis_aggregate["n_applicable_per_axis"],
        "n_total_per_axis": axis_aggregate["n_total_per_axis"],
        "toxic": toxic_summary,
        "vetoed": vetoed,
        "veto_reasons": veto_reasons,
        "weighted_pre_veto": weighted_pre_veto,
        "weights": normalized_weights,
        "overall": overall,
        "errors": errors,
        "elapsed_seconds": elapsed,
    }


# ===========================================================================
# Sprint 25 R5 — judge_multi_chapter API (cross-passage dimensions)
# ===========================================================================
#
# Inputs ≥ 2 chapters; runs the 4 cross-passage prompts (foreshadowing /
# character arc / stakes / setting). Output schema parallels judge_committee:
# per_dimension records + an aggregate `overall` (mean of applicable scores).
#
# This is independent of the per-chapter committee — Sprint 26+ generation
# work uses both: judge_committee per chapter + judge_multi_chapter on the
# whole sequence. They answer different questions and should not be merged.

from worldbox_writer.evals.dimension_prompts import (
    CROSS_PASSAGE_DIMENSIONS,
    build_multi_chapter_user_message,
)

MULTI_CHAPTER_SCHEMA_VERSION = "multi-chapter-v0.1"


def _multichapter_call_one(
    dim,
    chapters: list[str],
    *,
    model: str | None,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    """Run one cross-passage prompt against the chapter sequence."""
    started = _time.time()
    messages = [
        {"role": "system", "content": dim.system_prompt},
        {"role": "user", "content": build_multi_chapter_user_message(chapters)},
    ]
    raw = ""
    error: str | None = None
    try:
        raw = chat_completion(
            messages,
            role="narrator",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    parsed = parse_judge_response(raw) if raw else {"error": error or "no_response"}

    parse_status = "ok"
    applicable: bool | None = None
    score: float | None = None
    if isinstance(parsed.get("error"), str) and "applicable" not in parsed:
        parse_status = "parse_failed"
    elif "applicable" not in parsed:
        parse_status = "missing_fields"
    else:
        applicable = bool(parsed.get("applicable"))

    raw_score = parsed.get("score")
    if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
        score = round(min(10.0, max(0.0, float(raw_score))), 2)

    # evidence_quotes is an array for cross-passage; coerce defensively
    evidence_quotes_raw = parsed.get("evidence_quotes") or []
    if isinstance(evidence_quotes_raw, str):
        evidence_quotes_raw = [evidence_quotes_raw]
    evidence_quotes = [str(q)[:240] for q in evidence_quotes_raw if isinstance(q, str)]

    # Validate each evidence quote is a substring of joined chapters
    joined_text = "\n".join(chapters)
    invalid_quotes = [
        q
        for q in evidence_quotes
        if q.strip() and not _evidence_in_text(joined_text, q)
    ]
    coercions: list[str] = []
    if invalid_quotes:
        coercions.append("evidence_quotes_not_in_source")
        if score is not None and score >= 5:
            score = 4.0
            coercions.append("score_demoted_due_to_fabricated_evidence")

    elapsed_ms = int((_time.time() - started) * 1000)
    return {
        "dim_id": dim.dim_id,
        "category": dim.category,
        "applicable": applicable,
        "score": score,
        "evidence_quotes": evidence_quotes,
        "invalid_evidence_quotes": invalid_quotes,
        "rule_hit": str(parsed.get("rule_hit") or ""),
        "reasoning": str(parsed.get("reasoning") or "")[:200],
        "raw_excerpt": raw[:240],
        "parse_status": parse_status,
        "error": error,
        "coercions": coercions,
        "elapsed_ms": elapsed_ms,
    }


def judge_multi_chapter(
    chapters: list[str],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 360,
    concurrency: int = 1,
) -> dict[str, Any]:
    """Score a chapter sequence on the 4 cross-passage dimensions.

    Returns a dict with `per_dimension` (4 records), an `overall` mean of
    applicable+scored dims, and bookkeeping (errors, elapsed). At least 2
    chapters required; if fewer, all dims return applicable=false.
    """
    started = _time.time()
    selected_model = _resolve_judge_model(model)

    if len(chapters) < 2:
        return {
            "schema_version": MULTI_CHAPTER_SCHEMA_VERSION,
            "model": selected_model,
            "chapter_count": len(chapters),
            "per_dimension": {
                dim.dim_id: {
                    "dim_id": dim.dim_id,
                    "category": "cross_passage",
                    "applicable": False,
                    "score": None,
                    "evidence_quotes": [],
                    "rule_hit": "",
                    "reasoning": "fewer than 2 chapters supplied",
                    "parse_status": "ok",
                    "error": None,
                    "coercions": [],
                    "elapsed_ms": 0,
                }
                for dim in CROSS_PASSAGE_DIMENSIONS
            },
            "overall": None,
            "n_applicable": 0,
            "errors": [],
            "elapsed_seconds": 0.0,
        }

    workers = max(1, int(concurrency))
    if workers == 1:
        records = [
            _multichapter_call_one(
                dim,
                chapters,
                model=selected_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            for dim in CROSS_PASSAGE_DIMENSIONS
        ]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            records = list(
                executor.map(
                    lambda dim: _multichapter_call_one(
                        dim,
                        chapters,
                        model=selected_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ),
                    CROSS_PASSAGE_DIMENSIONS,
                )
            )

    per_dim = {record["dim_id"]: record for record in records}
    applicable_scores = [
        float(r["score"])
        for r in records
        if r["applicable"] and isinstance(r["score"], (int, float))
    ]
    overall = (
        round(sum(applicable_scores) / len(applicable_scores), 2)
        if applicable_scores
        else None
    )

    errors = [
        {
            "dim_id": record["dim_id"],
            "parse_status": record["parse_status"],
            "error": record["error"],
        }
        for record in records
        if record["parse_status"] != "ok" or record["error"]
    ]

    elapsed = round(_time.time() - started, 2)
    return {
        "schema_version": MULTI_CHAPTER_SCHEMA_VERSION,
        "model": selected_model,
        "chapter_count": len(chapters),
        "per_dimension": per_dim,
        "overall": overall,
        "n_applicable": len(applicable_scores),
        "errors": errors,
        "elapsed_seconds": elapsed,
    }
