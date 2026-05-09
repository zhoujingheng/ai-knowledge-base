#!/usr/bin/env python3
"""
完整审核循环测试

测试工作流的三种路由场景：
1. 审核通过 → organize → save
2. 审核未通过 (iter<3) → revise → review
3. 审核未通过 (iter>=3) → human_flag
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

from workflows.graph import route_after_review
from workflows.state import KBState


def test_routing_logic():
    """测试三路路由逻辑"""

    print("=" * 60)
    print("测试审核循环路由逻辑")
    print("=" * 60)
    print()

    # 测试场景 1：审核通过
    print("场景 1：审核通过")
    print("-" * 60)
    state1: KBState = {
        "sources": [],
        "analyses": [{"summary": "test"}],
        "articles": [],
        "review_feedback": "",
        "review_passed": True,
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
    route1 = route_after_review(state1)
    print(f"输入: review_passed=True, iteration=0")
    print(f"输出: {route1}")
    print(f"预期: organize")
    print(f"结果: {'[OK]' if route1 == 'organize' else '[FAIL]'}")
    print()

    # 测试场景 2：首次审核未通过
    print("场景 2：首次审核未通过 (iteration=0)")
    print("-" * 60)
    state2: KBState = {
        "sources": [],
        "analyses": [{"summary": "test"}],
        "articles": [],
        "review_feedback": "需要改进",
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
    route2 = route_after_review(state2)
    print(f"输入: review_passed=False, iteration=0")
    print(f"输出: {route2}")
    print(f"预期: revise")
    print(f"结果: {'[OK]' if route2 == 'revise' else '[FAIL]'}")
    print()

    # 测试场景 3：第二次审核未通过
    print("场景 3：第二次审核未通过 (iteration=1)")
    print("-" * 60)
    state3: KBState = {
        "sources": [],
        "analyses": [{"summary": "test"}],
        "articles": [],
        "review_feedback": "仍需改进",
        "review_passed": False,
        "iteration": 1,
        "needs_human_review": False,
        "cost_tracker": {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost_usd": 0.0,
            "by_node": {}
        }
    }
    route3 = route_after_review(state3)
    print(f"输入: review_passed=False, iteration=1")
    print(f"输出: {route3}")
    print(f"预期: revise")
    print(f"结果: {'[OK]' if route3 == 'revise' else '[FAIL]'}")
    print()

    # 测试场景 4：第三次审核未通过
    print("场景 4：第三次审核未通过 (iteration=2)")
    print("-" * 60)
    state4: KBState = {
        "sources": [],
        "analyses": [{"summary": "test"}],
        "articles": [],
        "review_feedback": "仍需改进",
        "review_passed": False,
        "iteration": 2,
        "needs_human_review": False,
        "cost_tracker": {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost_usd": 0.0,
            "by_node": {}
        }
    }
    route4 = route_after_review(state4)
    print(f"输入: review_passed=False, iteration=2")
    print(f"输出: {route4}")
    print(f"预期: revise")
    print(f"结果: {'[OK]' if route4 == 'revise' else '[FAIL]'}")
    print()

    # 测试场景 5：超过最大迭代次数
    print("场景 5：超过最大迭代次数 (iteration=3)")
    print("-" * 60)
    state5: KBState = {
        "sources": [],
        "analyses": [{"summary": "test"}],
        "articles": [],
        "review_feedback": "质量仍不达标",
        "review_passed": False,
        "iteration": 3,
        "needs_human_review": False,
        "cost_tracker": {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost_usd": 0.0,
            "by_node": {}
        }
    }
    route5 = route_after_review(state5)
    print(f"输入: review_passed=False, iteration=3")
    print(f"输出: {route5}")
    print(f"预期: human_flag")
    print(f"结果: {'[OK]' if route5 == 'human_flag' else '[FAIL]'}")
    print()

    # 汇总结果
    print("=" * 60)
    print("测试汇总")
    print("=" * 60)
    results = [
        route1 == "organize",
        route2 == "revise",
        route3 == "revise",
        route4 == "revise",
        route5 == "human_flag"
    ]
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")
    if passed == total:
        print("状态: [OK] 所有测试通过")
    else:
        print("状态: [FAIL] 部分测试失败")


if __name__ == "__main__":
    try:
        test_routing_logic()
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
