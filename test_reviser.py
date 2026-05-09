#!/usr/bin/env python3
"""
测试 reviser.py 的 revise_node 函数

模拟审核反馈，测试内容修订功能
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

from workflows.reviser import revise_node
from workflows.state import KBState


def test_revise_node():
    """测试 revise_node 函数"""

    print("=" * 60)
    print("测试 Reviser 修订节点")
    print("=" * 60)

    # 模拟需要改进的 analyses 数据
    original_analyses = [
        {
            "source_url": "https://github.com/example/ai-tool",
            "original_title": "example/ai-tool",
            "category": "其他",
            "tags": ["工具"],
            "summary": "一个 AI 工具。",
            "key_points": ["功能"],
            "quality_score": 0.4
        },
        {
            "source_url": "https://github.com/example/ml-lib",
            "original_title": "example/ml-lib",
            "category": "机器学习",
            "tags": ["ML"],
            "summary": "机器学习库。",
            "key_points": ["模型训练"],
            "quality_score": 0.5
        }
    ]

    # 模拟审核反馈
    review_feedback = """## 审核结果（第 1 次）

### 评分详情
- 摘要质量 (25%): 3/10
- 技术深度 (25%): 2/10
- 相关性 (20%): 5/10
- 原创性 (15%): 2/10
- 格式规范 (15%): 3/10

**加权总分**: 3.05/10 ✗ 未通过

### 审核意见
分析结果质量较低，需要改进：

1. **摘要质量**：摘要过于简短（如"一个 AI 工具"、"机器学习库"），缺少核心功能和技术特点描述
2. **技术深度**：标签过于笼统（如"工具"、"ML"），分类不够具体，缺少技术栈信息
3. **相关性**：内容与 AI/ML 相关，但描述不够专业
4. **原创性**：要点过于简单（如"功能"、"模型训练"），未体现项目独特价值
5. **格式规范**：标签格式不统一，要点数量不足

**改进建议**：
- 扩充摘要至 50-100 字，增加技术细节和应用场景
- 补充具体技术栈标签（如 PyTorch、TensorFlow、Scikit-learn 等）
- 细化分类（如"深度学习框架"、"NLP工具"、"计算机视觉"等）
- 增加 3-5 个具体要点，突出项目特色和创新点
"""

    # 构建测试状态
    test_state: KBState = {
        "sources": [],
        "analyses": original_analyses,
        "articles": [],
        "review_feedback": review_feedback,
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

    print(f"\n原始数据：{len(original_analyses)} 条 analyses")
    print("\n原始 analyses 示例：")
    for i, analysis in enumerate(original_analyses, 1):
        print(f"\n{i}. {analysis['original_title']}")
        print(f"   分类: {analysis['category']}")
        print(f"   标签: {analysis['tags']}")
        print(f"   摘要: {analysis['summary']}")
        print(f"   要点: {analysis['key_points']}")
        print(f"   评分: {analysis['quality_score']}")

    print("\n" + "=" * 60)
    print("开始修订...")
    print("=" * 60 + "\n")

    # 调用 revise_node
    result = revise_node(test_state)

    # 打印结果
    if not result:
        print("\n修订被跳过（返回空字典）")
    else:
        improved_analyses = result.get("analyses", [])

        print("\n" + "=" * 60)
        print("修订结果")
        print("=" * 60)
        print(f"\n改进后数量: {len(improved_analyses)} 条")

        print("\n改进后 analyses 示例：")
        for i, analysis in enumerate(improved_analyses, 1):
            print(f"\n{i}. {analysis['original_title']}")
            print(f"   分类: {analysis['category']}")
            print(f"   标签: {analysis['tags']}")
            print(f"   摘要: {analysis['summary']}")
            print(f"   要点: {analysis['key_points']}")
            print(f"   评分: {analysis['quality_score']}")

        # 打印 token 用量
        tracker = result['cost_tracker']
        if tracker.get('total_tokens', 0) > 0:
            print(f"\nToken 用量: {tracker['total_tokens']} (${tracker['total_cost_usd']:.4f})")
            if "by_node" in tracker and "revise_node" in tracker["by_node"]:
                node_stats = tracker["by_node"]["revise_node"]
                print(f"  revise_node: {node_stats['tokens']} tokens (${node_stats['cost']:.4f})")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_revise_node()
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
