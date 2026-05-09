#!/usr/bin/env python3
"""
测试 human_flag.py 的 human_flag_node 函数

模拟审核循环超限场景
"""

import sys
import io
import os
from pathlib import Path

# 设置 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from workflows.human_flag import human_flag_node
from workflows.state import KBState


def test_human_flag_node():
    """测试 human_flag_node 函数"""

    print("=" * 60)
    print("测试 HumanFlag 人工介入节点")
    print("=" * 60)

    # 模拟超过最大迭代次数的场景
    problem_analyses = [
        {
            "source_url": "https://github.com/example/problematic-repo",
            "original_title": "example/problematic-repo",
            "category": "未分类",
            "tags": ["工具"],
            "summary": "一个工具。",
            "key_points": ["功能"],
            "quality_score": 0.3
        },
        {
            "source_url": "https://github.com/example/low-quality",
            "original_title": "example/low-quality",
            "category": "其他",
            "tags": [],
            "summary": "项目描述不清晰。",
            "key_points": [],
            "quality_score": 0.2
        }
    ]

    # 模拟最后一次审核反馈
    last_feedback = """## 审核结果（第 3 次）

### 评分详情
- 摘要质量 (25%): 2/10
- 技术深度 (25%): 1/10
- 相关性 (20%): 3/10
- 原创性 (15%): 1/10
- 格式规范 (15%): 2/10

**加权总分**: 1.85/10 ✗ 未通过

### 审核意见
经过 3 次修订，内容质量仍未达标。主要问题：

1. **数据源质量问题**：原始仓库描述过于简单，缺少足够信息进行分析
2. **技术相关性不足**：项目与 AI/ML 领域关联度低
3. **信息完整性差**：缺少关键技术细节和应用场景

建议：
- 考虑更换数据源或添加过滤规则
- 调整采集标准，提高 stars 阈值
- 人工审核是否应纳入知识库
"""

    # 构建测试状态
    test_state: KBState = {
        "sources": [],
        "analyses": problem_analyses,
        "articles": [],
        "review_feedback": last_feedback,
        "review_passed": False,
        "iteration": 3,  # 已经 3 次迭代
        "needs_human_review": False,
        "cost_tracker": {
            "total_tokens": 5420,
            "prompt_tokens": 3200,
            "completion_tokens": 2220,
            "total_cost_usd": 0.0010,
            "by_node": {
                "analyze_node": {"tokens": 1500, "cost": 0.0003},
                "review_node": {"tokens": 2400, "cost": 0.0005},
                "revise_node": {"tokens": 1520, "cost": 0.0003}
            }
        }
    }

    print(f"\n场景：审核循环 {test_state['iteration']} 次后仍未通过")
    print(f"问题条目数量：{len(problem_analyses)}")
    print(f"累计 Token 用量：{test_state['cost_tracker']['total_tokens']}")
    print(f"累计成本：${test_state['cost_tracker']['total_cost_usd']:.4f}")

    print("\n" + "=" * 60)
    print("执行 HumanFlag 节点...")
    print("=" * 60 + "\n")

    # 调用 human_flag_node
    result = human_flag_node(test_state)

    # 打印结果
    print("\n" + "=" * 60)
    print("执行结果")
    print("=" * 60)
    print(f"needs_human_review: {result.get('needs_human_review', False)}")

    # 检查文件是否创建
    pending_dir = Path("knowledge/pending_review")
    if pending_dir.exists():
        files = list(pending_dir.glob("pending-*.json"))
        if files:
            latest_file = max(files, key=lambda p: p.stat().st_mtime)
            print(f"\n生成的文件: {latest_file}")

            # 读取并显示文件内容摘要
            import json
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            print(f"\n文件内容摘要:")
            print(f"  时间戳: {data['timestamp']}")
            print(f"  迭代次数: {data['iterations_used']}")
            print(f"  条目数量: {data['analyses_count']}")
            print(f"  状态: {data['status']}")
            print(f"  Token 用量: {data['cost_summary']['total_tokens']}")
            print(f"  总成本: ${data['cost_summary']['total_cost_usd']:.4f}")
            print(f"\n  备注: {data['notes']}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_human_flag_node()
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
