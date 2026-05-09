#!/usr/bin/env python3
"""
测试 reviewer.py 的 review_node 函数

模拟一个包含 analyses 的状态，调用 review_node 进行审核
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


def test_review_node():
    """测试 review_node 函数"""

    print("=" * 60)
    print("测试 Reviewer 审核节点")
    print("=" * 60)

    # 模拟 analyses 数据
    mock_analyses = [
        {
            "source_url": "https://github.com/example/ai-project-1",
            "original_title": "example/ai-project-1",
            "category": "深度学习框架",
            "tags": ["PyTorch", "深度学习", "神经网络"],
            "summary": "一个基于 PyTorch 的深度学习框架，提供高效的模型训练和推理能力。",
            "key_points": [
                "支持分布式训练",
                "内置常用模型架构",
                "提供可视化工具"
            ],
            "quality_score": 0.85
        },
        {
            "source_url": "https://github.com/example/nlp-toolkit",
            "original_title": "example/nlp-toolkit",
            "category": "NLP工具",
            "tags": ["NLP", "文本处理", "Transformers"],
            "summary": "自然语言处理工具包，集成了多种预训练模型和文本处理功能。",
            "key_points": [
                "支持多语言",
                "预训练模型库",
                "简单易用的 API"
            ],
            "quality_score": 0.78
        },
        {
            "source_url": "https://github.com/example/cv-models",
            "original_title": "example/cv-models",
            "category": "计算机视觉",
            "tags": ["计算机视觉", "目标检测", "图像分类"],
            "summary": "计算机视觉模型集合，包含目标检测、图像分类等常用模型。",
            "key_points": [
                "YOLO 系列模型",
                "ResNet 变体",
                "实时推理优化"
            ],
            "quality_score": 0.92
        }
    ]

    # 构建测试状态
    test_state: KBState = {
        "sources": [],
        "analyses": mock_analyses,
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

    print(f"\n测试数据：{len(mock_analyses)} 条 analyses")
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
        if "by_node" in tracker and "review_node" in tracker["by_node"]:
            node_stats = tracker["by_node"]["review_node"]
            print(f"  review_node: {node_stats['tokens']} tokens (${node_stats['cost']:.4f})")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_review_node()
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
