"""
HumanFlag Agent — 人工介入节点（异常终点）

当审核循环超过最大迭代次数仍未通过时，将问题条目写入 pending_review/ 目录，
等待人工审核，避免污染主知识库。
"""

import json
import os
from datetime import datetime, timezone

from workflows.state import KBState


def human_flag_node(state: KBState) -> dict:
    """
    审核循环超过上限时的兜底节点

    将未通过审核的 analyses 写入 knowledge/pending_review/ 目录，
    标记为需要人工审核，不进入主知识库。

    Args:
        state: 工作流状态

    Returns:
        {"needs_human_review": True} 标记需要人工介入
    """
    analyses = state.get("analyses", [])
    iteration = state.get("iteration", 0)
    feedback = state.get("review_feedback", "")
    tracker = state.get("cost_tracker", {})

    print(f"[HumanFlag] ⚠️ 达到 {iteration} 次审核仍未通过")
    print(f"[HumanFlag] 问题条目数量: {len(analyses)}")

    # 打印反馈摘要
    if feedback:
        feedback_preview = feedback[:200].replace("\n", " ")
        print(f"[HumanFlag] 最后反馈: {feedback_preview}...")
    else:
        print(f"[HumanFlag] 最后反馈: (无)")

    # 确定 pending_review 目录路径
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pending_dir = os.path.join(base, "knowledge", "pending_review")
    os.makedirs(pending_dir, exist_ok=True)

    # 生成文件名（带时间戳）
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    filepath = os.path.join(pending_dir, f"pending-{today}.json")

    # 构建待审核数据
    pending_data = {
        "timestamp": today,
        "iterations_used": iteration,
        "last_feedback": feedback,
        "analyses_count": len(analyses),
        "analyses": analyses,
        "cost_summary": {
            "total_tokens": tracker.get("total_tokens", 0),
            "total_cost_usd": tracker.get("total_cost_usd", 0.0),
            "by_node": tracker.get("by_node", {})
        },
        "status": "pending_human_review",
        "notes": f"审核循环 {iteration} 次后仍未通过质量标准，需要人工判断是否为数据质量问题或标准过严。"
    }

    # 写入文件
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(pending_data, f, ensure_ascii=False, indent=2)

    print(f"[HumanFlag] 已保存到 {filepath}")
    print(f"[HumanFlag] 请人工审核后决定：")
    print(f"  1. 调整审核标准（降低阈值或修改评分维度）")
    print(f"  2. 改进数据源质量（更换采集源或过滤规则）")
    print(f"  3. 手动修改后移入主知识库")

    return {
        "needs_human_review": True,
        "cost_tracker": tracker
    }
