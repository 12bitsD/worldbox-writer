"""
LLM 客户端工厂模块

支持通过环境变量切换不同的 LLM 后端：

配置方式（.env 或环境变量）：
  # Kimi（推荐）
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
  - Kimi: kimi-k2-5（长上下文，适合叙述者和世界构建）
  - 沙盒/OpenAI: gpt-4.1-mini（快速，适合所有角色）
"""

from __future__ import annotations

import os
from typing import Optional

from openai import OpenAI

# ---------------------------------------------------------------------------
# Provider 配置
# ---------------------------------------------------------------------------

KIMI_BASE_URL = "https://api.moonshot.cn/v1"

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
# Client factory
# ---------------------------------------------------------------------------


def _detect_provider() -> str:
    """自动检测当前使用的 LLM Provider"""
    explicit = os.environ.get("LLM_PROVIDER", "").lower()
    if explicit:
        return explicit

    base_url = os.environ.get("LLM_BASE_URL", "")
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

    if provider == "kimi":
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

    if provider == "kimi":
        return KIMI_MODEL_MAP.get(role, "kimi-k2-5")
    elif provider == "gemini":
        return GEMINI_MODEL_MAP.get(role, "gemini-2.5-flash")
    else:
        return OPENAI_MODEL_MAP.get(role, "gpt-4.1-mini")


def chat_completion(
    messages: list,
    role: str = "director",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    stream: bool = False,
) -> str:
    """统一的 chat completion 接口

    Args:
        messages: OpenAI 格式的消息列表
        role: Agent 角色名，用于选择合适的模型
        temperature: 生成温度
        max_tokens: 最大输出 token 数
        stream: 是否使用流式输出（目前不支持，保留接口）

    Returns:
        模型输出的文本内容
    """
    client = get_llm_client()
    model = get_model_name(role)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def get_provider_info() -> dict:
    """返回当前 LLM 配置信息（用于调试和状态面板显示）"""
    provider = _detect_provider()
    return {
        "provider": provider,
        "model_sample": get_model_name("narrator"),
        "base_url": os.environ.get("LLM_BASE_URL", "default"),
    }
