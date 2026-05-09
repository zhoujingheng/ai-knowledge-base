"""
LangGraph 工作流共享状态定义

遵循"报告式通信"原则：状态字段存储结构化摘要，而非原始数据。
每个节点读取上游结果，处理后更新状态，供下游节点使用。
"""

from typing import TypedDict


class KBState(TypedDict):
    """知识库自动化工作流的共享状态"""

    # 数据采集阶段
    sources: list[dict]
    """
    采集到的原始数据源列表
    格式: [{"url": str, "title": str, "content": str, "timestamp": str}, ...]
    存储从 RSS/API 获取的未处理内容
    """

    # LLM 分析阶段
    analyses: list[dict]
    """
    LLM 分析后的结构化结果列表
    格式: [{"source_url": str, "category": str, "tags": list[str],
            "summary": str, "key_points": list[str]}, ...]
    存储提取的关键信息和分类标签
    """

    # 格式化与去重阶段
    articles: list[dict]
    """
    格式化、去重后的知识条目列表
    格式: [{"title": str, "content": str, "metadata": dict,
            "hash": str, "is_duplicate": bool}, ...]
    存储最终可发布的知识条目
    """

    # Supervisor 审核阶段
    review_feedback: str
    """
    审核反馈意见（Markdown 格式）
    包含质量评估、改进建议、具体问题说明
    当 review_passed=False 时，此字段指导重新处理
    """

    review_passed: bool
    """
    审核是否通过
    True: 内容质量达标，可进入发布流程
    False: 需要根据 review_feedback 重新处理
    """

    iteration: int
    """
    当前审核循环次数（从 0 开始）
    最多允许 3 次迭代（初次 + 2 次重试）
    超过限制后强制通过或人工介入
    """

    needs_human_review: bool
    """
    是否需要人工审核
    True: 审核循环超过最大次数仍未通过，已写入 pending_review/ 目录
    False: 正常流程，无需人工介入
    由 HumanFlag 节点设置为 True
    """

    # 成本追踪
    cost_tracker: dict
    """
    Token 用量和成本追踪
    格式: {
        "total_tokens": int,
        "prompt_tokens": int,
        "completion_tokens": int,
        "total_cost_usd": float,
        "by_node": {
            "node_name": {"tokens": int, "cost": float},
            ...
        }
    }
    用于监控和优化 LLM 调用成本
    """
