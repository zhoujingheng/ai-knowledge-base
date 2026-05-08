#!/usr/bin/env python3
"""
Unified LLM Client Module

Provides a unified interface for calling different LLM providers
(DeepSeek, Qwen, OpenAI) with retry logic, usage tracking, and cost estimation.

Usage:
    from pipeline.model_client import quick_chat, get_client, cost_tracker

    # Quick one-liner
    response = quick_chat("Explain quantum computing in one sentence")
    print(response.content)

    # Advanced usage with client
    client = get_client()
    response = client.chat([
        {"role": "user", "content": "Hello!"}
    ])
    print(f"Cost: ${response.usage.estimated_cost:.6f}")

    # Print cost summary
    cost_tracker.report()
"""

import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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

# Pricing per 1M tokens (CNY)
CNY_PRICING: dict[str, dict[str, float]] = {
    "deepseek": {"prompt": 1, "completion": 2},
    "qwen": {"prompt": 4, "completion": 12},
    "openai": {"prompt": 150, "completion": 600},
}


@dataclass
class ProviderStats:
    """Accumulated statistics for a single LLM provider.

    Attributes:
        calls: Total number of API calls.
        prompt_tokens: Total prompt tokens consumed.
        completion_tokens: Total completion tokens consumed.
        total_tokens: Total tokens consumed.
    """

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CostTracker:
    """Tracks LLM API call token consumption and costs (CNY).

    Thread-safe for use with concurrent API calls.

    Usage:
        tracker = CostTracker()
        tracker.record(usage, "deepseek")
        print(f"Cost: ¥{tracker.estimated_cost():.4f}")
        tracker.report()
    """

    def __init__(self) -> None:
        """Initialize the cost tracker."""
        self._lock = threading.Lock()
        self._stats: dict[str, ProviderStats] = {}

    def record(self, usage: Usage, provider: str) -> None:
        """Record a single API call.

        Args:
            usage: Usage information from the API response.
            provider: Provider name (deepseek, qwen, openai).
        """
        with self._lock:
            if provider not in self._stats:
                self._stats[provider] = ProviderStats()
            stats = self._stats[provider]
            stats.calls += 1
            stats.prompt_tokens += usage.prompt_tokens
            stats.completion_tokens += usage.completion_tokens
            stats.total_tokens += usage.total_tokens

    def estimated_cost(self, provider: str | None = None) -> float:
        """Estimate total cost in CNY (元).

        Args:
            provider: Provider name. If None, returns total across all providers.

        Returns:
            Estimated cost in CNY.
        """
        with self._lock:
            if provider is not None:
                stats = self._stats.get(provider)
                if not stats or provider not in CNY_PRICING:
                    return 0.0
                pricing = CNY_PRICING[provider]
                prompt_cost = (stats.prompt_tokens / 1_000_000) * pricing["prompt"]
                completion_cost = (stats.completion_tokens / 1_000_000) * pricing["completion"]
                return prompt_cost + completion_cost

            total = 0.0
            for prov, stats in self._stats.items():
                if prov not in CNY_PRICING:
                    continue
                pricing = CNY_PRICING[prov]
                prompt_cost = (stats.prompt_tokens / 1_000_000) * pricing["prompt"]
                completion_cost = (stats.completion_tokens / 1_000_000) * pricing["completion"]
                total += prompt_cost + completion_cost
            return total

    def report(self, provider: str | None = None) -> None:
        """Print a formatted cost report via logger.

        Args:
            provider: Provider name. If None, prints summary for all providers.
        """
        with self._lock:
            providers = [provider] if provider else list(self._stats.keys())

            if not providers:
                logger.info("[CostTracker] No API calls recorded.")
                return

            logger.info("=" * 60)
            logger.info("LLM Cost Report (CNY)")
            logger.info("=" * 60)
            logger.info(
                f"{'Provider':12} {'Calls':>6} {'Prompt':>10} {'Completion':>12} "
                f"{'Total':>10} {'Cost(¥)':>10}"
            )
            logger.info("-" * 60)

            grand_calls = 0
            grand_tokens = 0
            grand_cost = 0.0

            for prov in providers:
                stats = self._stats.get(prov)
                if not stats:
                    continue

                cost = 0.0
                if prov in CNY_PRICING:
                    pricing = CNY_PRICING[prov]
                    prompt_cost = (stats.prompt_tokens / 1_000_000) * pricing["prompt"]
                    completion_cost = (stats.completion_tokens / 1_000_000) * pricing["completion"]
                    cost = prompt_cost + completion_cost

                logger.info(
                    f"{prov:12} {stats.calls:>6} {stats.prompt_tokens:>10,} "
                    f"{stats.completion_tokens:>12,} {stats.total_tokens:>10,} "
                    f"¥{cost:>9.4f}"
                )

                grand_calls += stats.calls
                grand_tokens += stats.total_tokens
                grand_cost += cost

            if not provider:
                logger.info("-" * 60)
                logger.info(
                    f"{'TOTAL':12} {grand_calls:>6} {'':>10} {'':>12} "
                    f"{grand_tokens:>10,} ¥{grand_cost:>9.4f}"
                )
                logger.info("=" * 60)


# Global cost tracker instance
cost_tracker = CostTracker()


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

        cost_tracker.record(usage, self.provider_name)

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
