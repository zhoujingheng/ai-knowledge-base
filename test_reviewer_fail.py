#!/usr/bin/env python3
"""
测试 reviewer.py 的审核循环（模拟低质量数据）
"""

import sys
import io
import os
from pathlib import Path

# 设置 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 加载 .env 文件
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

from workflows.reviewer import review_node
from workflows.state import KBState


def test_low_quality_analyses():
    """测试低质量 analyses（应该审核不通过）"""

    print("=" * 60)
    print("测试低质量 Analyses 审核")
    print("=" * 60)

    # 模拟低质量 analyses 数据
    low_quality_analyses = [
        {
            "source_url": "https://github.com/example/test",
            "original_title": "test",
            "category": "其他",
            "tags": ["工具"],
            "summary": "一个工具。",
            "key_points": ["功能"],
            "quality_score": 0.3
        },
        {
            "source_url": "https://github.com/example/demo",
            "original_title": "demo",
            "category": "未分类",
            "tags": [],
            "summary": "示例项目",
            "key_points": [],
            "quality_score": 0.2
        }
    ]

    # 构建测试状态
    test_state: KBState = {
        "sources": [],
        "analyses": low_quality_analyses,
        "articles": [],
        "review_feedback": "",
        "review_passed": False,
        "iteration": 0,
        "needs_human_review": False,
        "cost_tracker": {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost_usd": 0.0,
            "by_node": {}
        }
    }

    print(f"\n测试数据：{len(low_quality_analyses)} 条低质量 analyses")
    print("\n开始审核...\n")

    # 调用 review_node
    result = review_node(test_state)

    # 打印结果
    print("\n" + "=" * 60)
    print("审核结果")
    print("=" * 60)
    print(f"review_passed: {result['review_passed']}")
    print(f"iteration: {result['iteration']}")
    print(f"\nreview_feedback:\n{result['review_feedback']}")

    # 打印 token 用量
    tracker = result['cost_tracker']
    if tracker.get('total_tokens', 0) > 0:
        print(f"\nToken 用量: {tracker['total_tokens']} (${tracker['total_cost_usd']:.4f})")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_low_quality_analyses()
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
