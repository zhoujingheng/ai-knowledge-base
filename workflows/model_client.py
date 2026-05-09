"""
LLM 客户端包装器

为 workflows 提供简化的 LLM 调用接口，包装 pipeline.model_client
集成 CostGuard 自动记账和熔断
"""

import json
import os
from typing import Any

from pipeline.model_client import quick_chat
from tests.cost_guard import CostGuard, BudgetExceededError


# 全局 CostGuard 实例（懒加载）
_cost_guard: CostGuard | None = None


def get_cost_guard() -> CostGuard:
    """全局 CostGuard 实例（懒加载 · 一次运行共享一个）"""
    global _cost_guard
    if _cost_guard is None:
        _cost_guard = CostGuard(
            budget_yuan=float(os.getenv("BUDGET_YUAN", "1.0")),
            alert_threshold=float(os.getenv("BUDGET_ALERT", "0.8")),
        )
    return _cost_guard


def chat(prompt: str, system: str | None = None, temperature: float = 0.7, node_name: str = "unknown") -> tuple[str, dict]:
    """
    调用 LLM 并返回文本响应和用量统计
    自动记账和预算检查

    Args:
        prompt: 用户提示词
        system: 系统提示词（可选）
        temperature: 采样温度，0.0-2.0（默认 0.7）
        node_name: 节点名称（用于成本追踪）

    Returns:
        (response_text, usage_dict) 元组
        usage_dict 格式: {
            "prompt_tokens": int,
            "completion_tokens": int,
            "total_tokens": int,
            "cost_usd": float
        }

    Raises:
        BudgetExceededError: 当成本超出预算时
    """
    response = quick_chat(prompt, system_prompt=system, temperature=temperature, max_tokens=2000)

    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
        "cost_usd": response.usage.estimated_cost
    }

    # ★ 接入点 ① · 每次 LLM 调用自动 record
    guard = get_cost_guard()
    guard.record(node_name, usage, model=response.model)

    # ★ 接入点 ② · check() · 超预算自动抛 BudgetExceededError
    guard.check()

    return response.content, usage


def chat_json(prompt: str, system: str | None = None, temperature: float = 0.7, node_name: str = "unknown") -> tuple[dict, dict]:
    """
    调用 LLM 并解析 JSON 响应
    自动记账和预算检查

    Args:
        prompt: 用户提示词（应要求 LLM 输出 JSON）
        system: 系统提示词（可选）
        temperature: 采样温度，0.0-2.0（默认 0.7）
        node_name: 节点名称（用于成本追踪）

    Returns:
        (parsed_json, usage_dict) 元组

    Raises:
        json.JSONDecodeError: 如果响应不是有效的 JSON
        BudgetExceededError: 当成本超出预算时
    """
    text, usage = chat(prompt, system=system, temperature=temperature, node_name=node_name)

    # 尝试提取 JSON（处理 markdown 代码块包裹的情况）
    text = text.strip()

    # 移除可能的 markdown 代码块标记
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    # 解析 JSON
    parsed = json.loads(text)

    return parsed, usage


def accumulate_usage(tracker: dict, usage: dict, node_name: str | None = None) -> dict:
    """
    累加 token 用量统计到追踪器

    Args:
        tracker: 现有的追踪器字典
        usage: 本次调用的用量统计
        node_name: 节点名称（用于分节点统计）

    Returns:
        更新后的追踪器字典
    """
    # 累加总量
    tracker["prompt_tokens"] += usage["prompt_tokens"]
    tracker["completion_tokens"] += usage["completion_tokens"]
    tracker["total_tokens"] += usage["total_tokens"]
    tracker["total_cost_usd"] += usage["cost_usd"]

    # 分节点统计
    if node_name:
        if "by_node" not in tracker:
            tracker["by_node"] = {}

        if node_name not in tracker["by_node"]:
            tracker["by_node"][node_name] = {
                "tokens": 0,
                "cost": 0.0
            }

        tracker["by_node"][node_name]["tokens"] += usage["total_tokens"]
        tracker["by_node"][node_name]["cost"] += usage["cost_usd"]

    return tracker
