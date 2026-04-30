#!/usr/bin/env python3
"""
Unified LLM Client Module

Provides a unified interface for calling different LLM providers
(DeepSeek, Qwen, OpenAI) with retry logic, usage tracking, and cost estimation.

Usage:
    from pipeline.model_client import quick_chat, get_client

    # Quick one-liner
    response = quick_chat("Explain quantum computing in one sentence")
    print(response.content)

    # Advanced usage with client
    client = get_client()
    response = client.chat([
        {"role": "user", "content": "Hello!"}
    ])
    print(f"Cost: ${response.usage.estimated_cost:.6f}")
"""

import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class Usage:
    """Token usage and cost information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float


@dataclass
class LLMResponse:
    """Unified LLM response."""

    content: str
    usage: Usage
    model: str
    provider: str


# Pricing per 1M tokens (USD)
PRICING = {
    "deepseek": {
        "deepseek-chat": {"prompt": 0.14, "completion": 0.28},
    },
    "qwen": {
        "qwen-plus": {"prompt": 0.50, "completion": 0.50},
        "qwen-turbo": {"prompt": 0.30, "completion": 0.30},
    },
    "openai": {
        "gpt-4o": {"prompt": 2.50, "completion": 10.00},
        "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
        "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
    },
}


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model name (uses default if None).
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            LLMResponse with content and usage information.

        Raises:
            httpx.HTTPError: If the API request fails.
        """
        pass

    @abstractmethod
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Estimate cost in USD for given token usage.

        Args:
            prompt_tokens: Number of prompt tokens.
            completion_tokens: Number of completion tokens.
            model: Model name.

        Returns:
            Estimated cost in USD.
        """
        pass


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible API provider (DeepSeek, Qwen, OpenAI)."""

    def __init__(
        self,
        provider_name: str,
        api_key: str,
        base_url: str,
        default_model: str,
        timeout: float = 60.0,
    ):
        """Initialize the provider.

        Args:
            provider_name: Provider name (deepseek, qwen, openai).
            api_key: API key for authentication.
            base_url: Base URL for the API.
            default_model: Default model to use.
            timeout: Request timeout in seconds.
        """
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        """Send a chat completion request."""
        model = model or self.default_model

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        logger.info(f"Calling {self.provider_name} API: model={model}, messages={len(messages)}")

        response = self.client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage_data = data.get("usage", {})

        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)
        total_tokens = usage_data.get("total_tokens", prompt_tokens + completion_tokens)

        estimated_cost = self.estimate_cost(prompt_tokens, completion_tokens, model)

        usage = Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
        )

        return LLMResponse(
            content=content,
            usage=usage,
            model=model,
            provider=self.provider_name,
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Estimate cost in USD for given token usage."""
        pricing = PRICING.get(self.provider_name, {}).get(model)

        if not pricing:
            logger.warning(f"No pricing data for {self.provider_name}/{model}, returning 0")
            return 0.0

        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]

        return prompt_cost + completion_cost

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "client"):
            self.client.close()


def get_client() -> LLMProvider:
    """Get LLM client based on environment variables.

    Environment variables:
        LLM_PROVIDER: Provider name (deepseek, qwen, openai). Default: deepseek
        DEEPSEEK_API_KEY: DeepSeek API key
        QWEN_API_KEY: Qwen API key
        OPENAI_API_KEY: OpenAI API key

    Returns:
        Configured LLMProvider instance.

    Raises:
        ValueError: If provider is unknown or API key is missing.
    """
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()

    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is required")
        return OpenAICompatibleProvider(
            provider_name="deepseek",
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            default_model="deepseek-chat",
        )

    elif provider == "qwen":
        api_key = os.getenv("QWEN_API_KEY")
        if not api_key:
            raise ValueError("QWEN_API_KEY environment variable is required")
        return OpenAICompatibleProvider(
            provider_name="qwen",
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            default_model="qwen-plus",
        )

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        return OpenAICompatibleProvider(
            provider_name="openai",
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
        )

    else:
        raise ValueError(f"Unknown provider: {provider}. Supported: deepseek, qwen, openai")


def chat_with_retry(
    messages: list[dict[str, str]],
    max_retries: int = 3,
    **kwargs: Any,
) -> LLMResponse:
    """Call LLM with exponential backoff retry.

    Args:
        messages: List of message dicts.
        max_retries: Maximum number of retry attempts.
        **kwargs: Additional arguments passed to client.chat().

    Returns:
        LLMResponse from successful call.

    Raises:
        httpx.HTTPError: If all retries fail.
    """
    client = get_client()

    for attempt in range(max_retries):
        try:
            return client.chat(messages, **kwargs)
        except httpx.HTTPError as e:
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} attempts failed")
                raise

            wait_time = 2 ** attempt
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)

    raise RuntimeError("Unreachable code")


def quick_chat(
    prompt: str,
    system_prompt: str | None = None,
    **kwargs: Any,
) -> LLMResponse:
    """Quick one-liner to chat with LLM.

    Args:
        prompt: User prompt.
        system_prompt: Optional system prompt.
        **kwargs: Additional arguments passed to chat_with_retry().

    Returns:
        LLMResponse with content and usage.
    """
    messages = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.append({"role": "user", "content": prompt})

    return chat_with_retry(messages, **kwargs)


def estimate_tokens(text: str) -> int:
    """Rough estimation of token count (1 token ≈ 4 characters for English).

    Args:
        text: Input text.

    Returns:
        Estimated token count.
    """
    return len(text) // 4


if __name__ == "__main__":
    # Test code
    logger.info("Testing LLM client...")

    try:
        # Test 1: Quick chat
        logger.info("\n=== Test 1: Quick Chat ===")
        response = quick_chat(
            "Explain what is an AI agent in one sentence.",
            temperature=0.7,
            max_tokens=100,
        )
        logger.info(f"Response: {response.content}")
        logger.info(f"Model: {response.provider}/{response.model}")
        logger.info(f"Tokens: {response.usage.total_tokens}")
        logger.info(f"Cost: ${response.usage.estimated_cost:.6f}")

        # Test 2: Multi-turn conversation
        logger.info("\n=== Test 2: Multi-turn Conversation ===")
        messages = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "2+2 equals 4."},
            {"role": "user", "content": "What about 3+3?"},
        ]
        response = chat_with_retry(messages, temperature=0.5)
        logger.info(f"Response: {response.content}")
        logger.info(f"Cost: ${response.usage.estimated_cost:.6f}")

        # Test 3: Token estimation
        logger.info("\n=== Test 3: Token Estimation ===")
        text = "This is a sample text for token estimation."
        estimated = estimate_tokens(text)
        logger.info(f"Text: {text}")
        logger.info(f"Estimated tokens: {estimated}")

        logger.info("\n✓ All tests passed!")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
