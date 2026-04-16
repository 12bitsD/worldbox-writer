"""
LLM 客户端工厂模块

支持通过环境变量切换不同的 LLM 后端：

配置方式（.env 或环境变量）：
  # MIMO（推荐）
  LLM_PROVIDER=mimo
  LLM_API_KEY=tp-xxxx
  LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1

  # Kimi
  LLM_PROVIDER=kimi
  LLM_API_KEY=sk-xxxx
  LLM_BASE_URL=https://api.moonshot.cn/v1

  # OpenAI
  LLM_PROVIDER=openai
  LLM_API_KEY=sk-xxxx

  # 本地 Ollama
  LLM_PROVIDER=ollama
  LLM_BASE_URL=http://localhost:11434/v1
  LLM_MODEL=qwen2.5:14b

模型选择策略：
  - MIMO: mimo-v2-pro（适合所有角色，需关闭 thinking 模式）
  - Kimi: kimi-k2-5（长上下文，适合叙述者和世界构建）
  - 沙盒/OpenAI: gpt-4.1-mini（快速，适合所有角色）
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from openai import OpenAI

# ---------------------------------------------------------------------------
# Provider 配置
# ---------------------------------------------------------------------------

MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
KIMI_BASE_URL = "https://api.moonshot.cn/v1"

# MIMO 模型映射
MIMO_MODEL_MAP = {
    "director": "mimo-v2-pro",
    "gate_keeper": "mimo-v2-pro",
    "node_detector": "mimo-v2-pro",
    "actor": "mimo-v2-pro",
    "narrator": "mimo-v2-pro",
    "world_builder": "mimo-v2-pro",
    "memory": "mimo-v2-pro",
}

# Kimi 模型映射（按角色分配不同上下文长度）
KIMI_MODEL_MAP = {
    "director": "kimi-k2-5",
    "gate_keeper": "kimi-k2-5",
    "node_detector": "kimi-k2-5",
    "actor": "kimi-k2-5",
    "narrator": "kimi-k2-5",
    "world_builder": "kimi-k2-5",
    "memory": "kimi-k2-5",
}

# 沙盒/OpenAI 兼容模型映射
OPENAI_MODEL_MAP = {
    "director": "gpt-4.1-mini",
    "gate_keeper": "gpt-4.1-mini",
    "node_detector": "gpt-4.1-mini",
    "actor": "gpt-4.1-mini",
    "narrator": "gpt-4.1-mini",
    "world_builder": "gpt-4.1-mini",
    "memory": "gpt-4.1-mini",
}

# Gemini 兼容映射
GEMINI_MODEL_MAP = {
    "director": "gemini-2.5-flash",
    "gate_keeper": "gemini-2.5-flash",
    "node_detector": "gemini-2.5-flash",
    "actor": "gemini-2.5-flash",
    "narrator": "gemini-2.5-flash",
    "world_builder": "gemini-2.5-flash",
    "memory": "gemini-2.5-flash",
}


# ---------------------------------------------------------------------------
# .env 文件加载（如果存在）
# ---------------------------------------------------------------------------


def _load_dotenv() -> None:
    """简单加载 .env 文件中的环境变量（不覆盖已有变量）"""
    import pathlib

    env_file = pathlib.Path(__file__).parent.parent.parent.parent / ".env"
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def _detect_provider() -> str:
    """自动检测当前使用的 LLM Provider"""
    explicit = os.environ.get("LLM_PROVIDER", "").lower()
    if explicit:
        return explicit

    base_url = os.environ.get("LLM_BASE_URL", "")
    if "xiaomimimo" in base_url or "mimo" in base_url:
        return "mimo"
    if "moonshot" in base_url:
        return "kimi"
    if "ollama" in base_url or "localhost:11434" in base_url:
        return "ollama"
    if "gemini" in base_url or "generativelanguage" in base_url:
        return "gemini"

    # 默认使用沙盒内置接口
    return "openai"


def get_llm_client() -> OpenAI:
    """获取 LLM 客户端"""
    provider = _detect_provider()
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL")

    if provider == "mimo":
        return OpenAI(
            api_key=api_key,
            base_url=base_url or MIMO_BASE_URL,
        )
    elif provider == "kimi":
        return OpenAI(
            api_key=api_key,
            base_url=KIMI_BASE_URL,
        )
    elif provider in ("ollama", "local"):
        return OpenAI(
            api_key=api_key or "ollama",
            base_url=base_url or "http://localhost:11434/v1",
        )
    else:
        # openai / sandbox default
        if base_url:
            return OpenAI(api_key=api_key, base_url=base_url)
        return OpenAI(api_key=api_key)


def get_model_name(role: str) -> str:
    """根据 provider 和角色获取对应的模型名称"""
    provider = _detect_provider()

    # 允许通过环境变量强制覆盖模型
    override = os.environ.get("LLM_MODEL")
    if override:
        return override

    if provider == "mimo":
        return MIMO_MODEL_MAP.get(role, "mimo-v2-pro")
    elif provider == "kimi":
        return KIMI_MODEL_MAP.get(role, "kimi-k2-5")
    elif provider == "gemini":
        return GEMINI_MODEL_MAP.get(role, "gemini-2.5-flash")
    else:
        return OPENAI_MODEL_MAP.get(role, "gpt-4.1-mini")


def _get_extra_body(provider: str) -> Optional[dict]:
    """获取特定 provider 需要的额外请求体参数"""
    if provider == "mimo":
        # MIMO 需要禁用 thinking 模式以获得正常响应
        return {"thinking": {"type": "disabled"}}
    return None


def chat_completion(
    messages: list,
    role: str = "director",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    stream: bool = False,
    on_token: Optional[Callable[[str], None]] = None,
    top_p: Optional[float] = None,
) -> str:
    """统一的 chat completion 接口

    Args:
        messages: OpenAI 格式的消息列表
        role: Agent 角色名，用于选择合适的模型
        temperature: 生成温度
        max_tokens: 最大输出 token 数
        stream: 是否使用流式输出（当 on_token 传入时自动启用）
        on_token: 流式回调，每个 content token 到达时调用
        top_p: nucleus sampling 参数

    Returns:
        模型输出的完整文本内容
    """
    client = get_llm_client()
    model = get_model_name(role)
    provider = _detect_provider()
    extra_body = _get_extra_body(provider)

    # 构建公共参数
    kwargs = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if extra_body:
        kwargs["extra_body"] = extra_body
    if top_p is not None:
        kwargs["top_p"] = top_p

    if on_token is not None:
        # 流式模式
        kwargs["stream"] = True
        response = client.chat.completions.create(**kwargs)
        collected = []
        for chunk in response:
            if not chunk.choices:
                # 最后一个 usage chunk，choices 为空
                continue
            delta = chunk.choices[0].delta
            # 跳过 reasoning_content（thinking 模式的中间推理）
            content = delta.content if delta and delta.content else None
            if content:
                collected.append(content)
                on_token(content)
        return "".join(collected)
    else:
        # 非流式模式（原有行为）
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content


def get_provider_info() -> dict:
    """返回当前 LLM 配置信息（用于调试和状态面板显示）"""
    provider = _detect_provider()
    return {
        "provider": provider,
        "model_sample": get_model_name("narrator"),
        "base_url": os.environ.get("LLM_BASE_URL", "default"),
    }
