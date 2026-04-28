"""
LLM client factory and routing helpers.

Sprint 9 extends the original single-provider setup into a configurable
role/group-based router with optional evaluation-gated fallback and lightweight
token/cost diagnostics.
"""

from __future__ import annotations

import json
import math
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Optional, cast
from uuid import uuid4

import httpx
from openai import OpenAI

MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
KIMI_BASE_URL = "https://api.kimi.com/coding/"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_LLM_PROVIDER = "kimi"

LOGIC_ROLES = {"director", "gate_keeper", "node_detector", "actor", "memory"}
CREATIVE_ROLES = {"narrator", "world_builder"}

MIMO_MODEL_MAP = {
    "director": "mimo-v2-pro",
    "gate_keeper": "mimo-v2-pro",
    "node_detector": "mimo-v2-pro",
    "actor": "mimo-v2-pro",
    "narrator": "mimo-v2-pro",
    "world_builder": "mimo-v2-pro",
    "memory": "mimo-v2-pro",
}

KIMI_MODEL_MAP = {
    "director": "kimi-k2.5",
    "gate_keeper": "kimi-k2.5",
    "node_detector": "kimi-k2.5",
    "actor": "kimi-k2.5",
    "narrator": "kimi-k2.5",
    "world_builder": "kimi-k2.5",
    "memory": "kimi-k2.5",
}

GEMINI_MODEL_MAP = {
    "director": "gemini-2.5-flash",
    "gate_keeper": "gemini-2.5-flash",
    "node_detector": "gemini-2.5-flash",
    "actor": "gemini-2.5-flash",
    "narrator": "gemini-2.5-flash",
    "world_builder": "gemini-2.5-flash",
    "memory": "gemini-2.5-flash",
}

DEFAULT_PRICE_OVERRIDES: dict[str, dict[str, float]] = {}


class EmptyLLMResponseError(RuntimeError):
    """Raised when a provider returns a syntactically successful empty response."""


def _load_dotenv() -> None:
    import pathlib

    env_file = pathlib.Path(__file__).parent.parent.parent.parent / ".env"
    if not env_file.exists():
        return

    with open(env_file) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class ResolvedLLMRoute:
    role: str
    route_group: str
    provider: str
    model: str
    api_key: str
    base_url: Optional[str]
    fallback_applied: bool = False
    fallback_reason: Optional[str] = None
    benchmark_score: Optional[float] = None
    benchmark_threshold: Optional[float] = None


_LAST_LLM_CALL_METADATA: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "_LAST_LLM_CALL_METADATA", default=None
)


def _set_last_llm_call_metadata(metadata: dict[str, Any]) -> None:
    _LAST_LLM_CALL_METADATA.set(metadata)


def get_last_llm_call_metadata() -> Optional[dict[str, Any]]:
    metadata = _LAST_LLM_CALL_METADATA.get()
    return dict(metadata) if metadata else None


def _role_key(role: str) -> str:
    return role.strip().upper().replace("-", "_")


def _route_group_for_role(role: str) -> str:
    if role in CREATIVE_ROLES:
        return "creative"
    if role in LOGIC_ROLES:
        return "logic"
    return "default"


def _first_non_empty(*keys: str) -> Optional[str]:
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return None


def _detect_provider_from_values(
    explicit: Optional[str], base_url: Optional[str]
) -> str:
    if explicit:
        return _normalize_provider(explicit)

    normalized_url = (base_url or "").lower()
    if "xiaomimimo" in normalized_url or "mimo" in normalized_url:
        return "mimo"
    if "moonshot" in normalized_url or "api.kimi.com" in normalized_url:
        return "kimi"
    if "ollama" in normalized_url or "localhost:11434" in normalized_url:
        return "ollama"
    if "gemini" in normalized_url or "generativelanguage" in normalized_url:
        return "gemini"
    return DEFAULT_LLM_PROVIDER


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower().replace("_", "-")
    if normalized in {"kimi", "kimi-coding", "moonshot", "moonshot-kimi"}:
        return "kimi"
    if normalized in {
        "mimo",
        "xiaomi-mimo",
        "xiaomimimo",
        "token-plan",
        "token-plan-cn",
    }:
        return "mimo"
    if normalized in {"ollama", "local", "local-ollama"}:
        return "ollama"
    return normalized


def _default_base_url(provider: str) -> Optional[str]:
    if provider == "mimo":
        return MIMO_BASE_URL
    if provider == "kimi":
        return KIMI_BASE_URL
    if provider in {"ollama", "local"}:
        return OLLAMA_BASE_URL
    return None


def _default_model_name(provider: str, role: str) -> str:
    if provider == "mimo":
        return MIMO_MODEL_MAP.get(role, "mimo-v2-pro")
    if provider == "kimi":
        return KIMI_MODEL_MAP.get(role, "kimi-k2.5")
    if provider == "gemini":
        return GEMINI_MODEL_MAP.get(role, "gemini-2.5-flash")
    return KIMI_MODEL_MAP.get(role, "kimi-k2.5")


def _provider_has_builtin_model_default(provider: str) -> bool:
    return provider in {"mimo", "kimi", "gemini"}


def _fallback_provider_if_model_missing(
    provider: str, explicit_model: Optional[str]
) -> str:
    if explicit_model or _provider_has_builtin_model_default(provider):
        return provider
    return DEFAULT_LLM_PROVIDER


def _load_eval_report() -> dict[str, Any]:
    report_path = os.environ.get("LLM_EVAL_REPORT_PATH")
    if not report_path:
        return {}

    try:
        with open(report_path, encoding="utf-8") as handle:
            return cast(dict[str, Any], json.load(handle))
    except Exception:
        return {}


def _resolve_benchmark_gate(
    route_group: str,
) -> tuple[Optional[float], Optional[float]]:
    report = _load_eval_report()
    routes = cast(dict[str, Any], report.get("routes") or {})
    route = cast(dict[str, Any], routes.get(route_group) or {})
    score = route.get("score")
    threshold = route.get("threshold")
    if isinstance(score, (int, float)) and isinstance(threshold, (int, float)):
        return float(score), float(threshold)
    return None, None


def _should_fallback(
    *,
    role: str,
    route_group: str,
    provider: str,
    model: str,
) -> tuple[bool, Optional[str], Optional[float], Optional[float]]:
    if route_group == "default":
        return False, None, None, None

    benchmark_score, benchmark_threshold = _resolve_benchmark_gate(route_group)
    if benchmark_score is None or benchmark_threshold is None:
        return False, None, benchmark_score, benchmark_threshold

    if benchmark_score >= benchmark_threshold:
        return False, None, benchmark_score, benchmark_threshold

    global_provider = _fallback_provider_if_model_missing(
        _detect_default_provider(),
        os.environ.get("LLM_MODEL"),
    )
    global_model = _resolve_model_for_role(
        role=role,
        provider=global_provider,
        explicit_model=os.environ.get("LLM_MODEL"),
    )
    if provider == global_provider and model == global_model:
        return False, None, benchmark_score, benchmark_threshold

    reason = (
        f"{route_group} score {benchmark_score:.2f} below threshold "
        f"{benchmark_threshold:.2f}"
    )
    return True, reason, benchmark_score, benchmark_threshold


def _resolve_model_for_role(
    *,
    role: str,
    provider: str,
    explicit_model: Optional[str],
) -> str:
    if explicit_model:
        return explicit_model
    return _default_model_name(provider, role)


def _resolve_api_key(role_key: str, route_group: str) -> str:
    return (
        _first_non_empty(
            f"LLM_API_KEY_{role_key}",
            f"LLM_API_KEY_{route_group.upper()}",
            "LLM_API_KEY",
            "OPENAI_API_KEY",
        )
        or ""
    )


def _resolve_base_url(
    role_key: str,
    route_group: str,
    provider_hint: Optional[str],
) -> Optional[str]:
    override = _first_non_empty(
        f"LLM_BASE_URL_{role_key}",
        f"LLM_BASE_URL_{route_group.upper()}",
        "LLM_BASE_URL",
    )
    provider = _detect_provider_from_values(provider_hint, override)
    return override or _default_base_url(provider)


def resolve_llm_route(role: str) -> ResolvedLLMRoute:
    role = role.strip().lower()
    role_key = _role_key(role)
    route_group = _route_group_for_role(role)

    role_provider = os.environ.get(f"LLM_PROVIDER_{role_key}")
    group_provider = os.environ.get(f"LLM_PROVIDER_{route_group.upper()}")
    global_provider = os.environ.get("LLM_PROVIDER")

    provider = _detect_provider_from_values(
        role_provider or group_provider or global_provider,
        _resolve_base_url(role_key, route_group, role_provider or group_provider),
    )

    explicit_model = _first_non_empty(
        f"LLM_MODEL_{role_key}",
        f"LLM_MODEL_{route_group.upper()}",
        "LLM_MODEL",
    )
    original_provider = provider
    provider = _fallback_provider_if_model_missing(provider, explicit_model)
    provider_defaulted_to_kimi = provider != original_provider
    model = _resolve_model_for_role(
        role=role,
        provider=provider,
        explicit_model=explicit_model,
    )
    api_key = _resolve_api_key(role_key, route_group)
    base_url = (
        _default_base_url(provider)
        if provider_defaulted_to_kimi
        else _resolve_base_url(role_key, route_group, provider)
    )

    fallback, reason, benchmark_score, benchmark_threshold = _should_fallback(
        role=role,
        route_group=route_group,
        provider=provider,
        model=model,
    )
    if fallback:
        global_explicit_model = os.environ.get("LLM_MODEL")
        fallback_provider = _detect_provider()
        provider = _fallback_provider_if_model_missing(
            fallback_provider,
            global_explicit_model,
        )
        model = _resolve_model_for_role(
            role=role,
            provider=provider,
            explicit_model=global_explicit_model,
        )
        api_key = _first_non_empty("LLM_API_KEY", "OPENAI_API_KEY") or api_key
        base_url = (
            _default_base_url(provider)
            if provider != fallback_provider
            else os.environ.get("LLM_BASE_URL") or _default_base_url(provider)
        )

    return ResolvedLLMRoute(
        role=role,
        route_group=route_group,
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        fallback_applied=fallback,
        fallback_reason=reason,
        benchmark_score=benchmark_score,
        benchmark_threshold=benchmark_threshold,
    )


def _detect_default_provider() -> str:
    return _detect_provider_from_values(
        os.environ.get("LLM_PROVIDER"),
        os.environ.get("LLM_BASE_URL"),
    )


def _detect_provider() -> str:
    return _detect_default_provider()


@lru_cache(maxsize=16)
def _build_client(provider: str, base_url: Optional[str], api_key: str) -> OpenAI:
    if provider == "mimo":
        return OpenAI(api_key=api_key, base_url=base_url or MIMO_BASE_URL)
    if provider == "kimi":
        return OpenAI(api_key=api_key, base_url=base_url or KIMI_BASE_URL)
    if provider in {"ollama", "local"}:
        return OpenAI(api_key=api_key or "ollama", base_url=base_url or OLLAMA_BASE_URL)
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def get_llm_client(route: Optional[ResolvedLLMRoute] = None) -> OpenAI:
    resolved = route or resolve_llm_route("director")
    return _build_client(resolved.provider, resolved.base_url, resolved.api_key)


def get_model_name(role: str) -> str:
    return resolve_llm_route(role).model


def _get_extra_body(provider: str) -> Optional[dict[str, Any]]:
    if provider == "mimo":
        return {"thinking": {"type": "disabled"}}
    return None


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _messages_text(messages: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
    return "\n".join(chunks)


def _uses_anthropic_messages(route: ResolvedLLMRoute) -> bool:
    base_url = (route.base_url or "").lower()
    return route.provider == "kimi" and "api.kimi.com/coding" in base_url


def _anthropic_messages_endpoint(base_url: Optional[str]) -> str:
    root = (base_url or KIMI_BASE_URL).rstrip("/")
    if root.endswith("/v1/messages"):
        return root
    if root.endswith("/v1"):
        return f"{root}/messages"
    return f"{root}/v1/messages"


def _message_content_to_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return ""


def _convert_messages_to_anthropic(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, str]]]:
    system_parts: list[str] = []
    converted: list[dict[str, str]] = []

    for message in messages:
        role = str(message.get("role", "user")).lower()
        text = _message_content_to_text(message).strip()
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        if converted and converted[-1]["role"] == role:
            converted[-1]["content"] += f"\n\n{text}"
        else:
            converted.append({"role": role, "content": text})

    if not converted:
        converted.append({"role": "user", "content": "继续"})
    if converted[0]["role"] == "assistant":
        converted.insert(0, {"role": "user", "content": "继续"})

    return "\n\n".join(system_parts), converted


def _extract_anthropic_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            chunks.append(part["text"])
    return "".join(chunks)


def _chat_completion_anthropic_messages(
    messages: list[dict[str, Any]],
    *,
    route: ResolvedLLMRoute,
    temperature: float,
    max_tokens: int,
    stream: bool,
    on_token: Optional[Callable[[str], None]],
    top_p: Optional[float],
) -> str:
    system_prompt, anthropic_messages = _convert_messages_to_anthropic(messages)
    payload: dict[str, Any] = {
        "model": route.model,
        "messages": anthropic_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system_prompt:
        payload["system"] = system_prompt
    if top_p is not None:
        payload["top_p"] = top_p

    headers = {
        "x-api-key": route.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "user-agent": "worldbox-writer/0.5.0",
    }
    endpoint = _anthropic_messages_endpoint(route.base_url)

    if on_token is not None or stream:
        payload["stream"] = True
        collected: list[str] = []
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST", endpoint, headers=headers, json=payload
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line.removeprefix("data:").strip()
                    if not raw or raw == "[DONE]":
                        continue
                    event = json.loads(raw)
                    if event.get("type") != "content_block_delta":
                        continue
                    delta = event.get("delta") or {}
                    token = delta.get("text")
                    if isinstance(token, str) and token:
                        collected.append(token)
                        if on_token is not None:
                            on_token(token)
        return "".join(collected)

    with httpx.Client(timeout=120.0) as client:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        return _extract_anthropic_text(response.json())


def _load_price_overrides() -> dict[str, dict[str, float]]:
    raw = os.environ.get("LLM_PRICE_OVERRIDES_JSON")
    if not raw:
        return DEFAULT_PRICE_OVERRIDES
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return cast(dict[str, dict[str, float]], parsed)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Failed to parse price overrides")
    return DEFAULT_PRICE_OVERRIDES


def _estimate_cost_usd(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Optional[float]:
    pricing = _load_price_overrides().get(model)
    if not pricing:
        return None

    input_per_1m = pricing.get("input_per_1m")
    output_per_1m = pricing.get("output_per_1m")
    if input_per_1m is None or output_per_1m is None:
        return None

    return round(
        (prompt_tokens / 1_000_000) * input_per_1m
        + (completion_tokens / 1_000_000) * output_per_1m,
        8,
    )


def chat_completion(
    messages: list,
    role: str = "director",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    stream: bool = False,
    on_token: Optional[Callable[[str], None]] = None,
    top_p: Optional[float] = None,
) -> str:
    resolved_route = resolve_llm_route(role)
    client = get_llm_client(resolved_route)
    extra_body = _get_extra_body(resolved_route.provider)
    request_id = f"llm_{uuid4().hex[:12]}"
    started_at = time.perf_counter()
    prompt_tokens = _estimate_tokens(
        _messages_text(cast(list[dict[str, Any]], messages))
    )

    kwargs: dict[str, Any] = {
        "model": resolved_route.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body
    if top_p is not None:
        kwargs["top_p"] = top_p

    try:
        if _uses_anthropic_messages(resolved_route):
            text = _chat_completion_anthropic_messages(
                cast(list[dict[str, Any]], messages),
                route=resolved_route,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                on_token=on_token,
                top_p=top_p,
            )
        elif on_token is not None or stream:
            kwargs["stream"] = True
            response = client.chat.completions.create(**cast(Any, kwargs))
            collected: list[str] = []
            for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = delta.content if delta and delta.content else None
                if content:
                    collected.append(content)
                    if on_token is not None:
                        on_token(content)
            text = "".join(collected)
        else:
            response = client.chat.completions.create(**cast(Any, kwargs))
            text = response.choices[0].message.content or ""

        if not text.strip():
            raise EmptyLLMResponseError("LLM provider returned an empty completion")

        completion_tokens = _estimate_tokens(text)
        _set_last_llm_call_metadata(
            {
                "request_id": request_id,
                "provider": resolved_route.provider,
                "model": resolved_route.model,
                "role": role,
                "route_group": resolved_route.route_group,
                "fallback_applied": resolved_route.fallback_applied,
                "fallback_reason": resolved_route.fallback_reason,
                "benchmark_score": resolved_route.benchmark_score,
                "benchmark_threshold": resolved_route.benchmark_threshold,
                "stream": on_token is not None or stream,
                "estimated_prompt_tokens": prompt_tokens,
                "estimated_completion_tokens": completion_tokens,
                "estimated_cost_usd": _estimate_cost_usd(
                    model=resolved_route.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                ),
                "duration_ms": int((time.perf_counter() - started_at) * 1000),
                "status": "completed",
            }
        )
        return text
    except Exception:
        _set_last_llm_call_metadata(
            {
                "request_id": request_id,
                "provider": resolved_route.provider,
                "model": resolved_route.model,
                "role": role,
                "route_group": resolved_route.route_group,
                "fallback_applied": resolved_route.fallback_applied,
                "fallback_reason": resolved_route.fallback_reason,
                "benchmark_score": resolved_route.benchmark_score,
                "benchmark_threshold": resolved_route.benchmark_threshold,
                "stream": on_token is not None or stream,
                "estimated_prompt_tokens": prompt_tokens,
                "estimated_completion_tokens": 0,
                "estimated_cost_usd": _estimate_cost_usd(
                    model=resolved_route.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=0,
                ),
                "duration_ms": int((time.perf_counter() - started_at) * 1000),
                "status": "failed",
            }
        )
        raise


def get_provider_info() -> dict[str, Any]:
    logic_route = resolve_llm_route("actor")
    creative_route = resolve_llm_route("narrator")
    provider = (
        logic_route.provider
        if logic_route.provider == creative_route.provider
        else "mixed"
    )
    return {
        "provider": provider,
        "model_sample": creative_route.model,
        "base_url": creative_route.base_url
        or os.environ.get("LLM_BASE_URL", "default"),
        "routing": {
            "logic": {
                "provider": logic_route.provider,
                "model": logic_route.model,
                "fallback_applied": logic_route.fallback_applied,
                "benchmark_score": logic_route.benchmark_score,
                "benchmark_threshold": logic_route.benchmark_threshold,
            },
            "creative": {
                "provider": creative_route.provider,
                "model": creative_route.model,
                "fallback_applied": creative_route.fallback_applied,
                "benchmark_score": creative_route.benchmark_score,
                "benchmark_threshold": creative_route.benchmark_threshold,
            },
        },
    }
