#!/usr/bin/env python3
"""
完整测试：对比修订前后的 analyses 质量提升
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


def compare_analyses(original, improved):
    """对比原始和改进后的 analyses"""

    print("\n" + "=" * 80)
    print("修订前后对比")
    print("=" * 80)

    for i, (orig, impr) in enumerate(zip(original, improved), 1):
        print(f"\n【条目 {i}】{orig['original_title']}")
        print("-" * 80)

        print(f"\n分类:")
        print(f"  修订前: {orig['category']}")
        print(f"  修订后: {impr['category']}")

        print(f"\n标签:")
        print(f"  修订前: {orig['tags']} ({len(orig['tags'])} 个)")
        print(f"  修订后: {impr['tags']} ({len(impr['tags'])} 个)")

        print(f"\n摘要:")
        print(f"  修订前 ({len(orig['summary'])} 字符): {orig['summary']}")
        print(f"  修订后 ({len(impr['summary'])} 字符): {impr['summary']}")

        print(f"\n要点:")
        print(f"  修订前 ({len(orig['key_points'])} 个):")
        for point in orig['key_points']:
            print(f"    - {point}")
        print(f"  修订后 ({len(impr['key_points'])} 个):")
        for point in impr['key_points']:
            print(f"    - {point}")

        print(f"\n质量评分:")
        print(f"  修订前: {orig['quality_score']:.2f}")
        print(f"  修订后: {impr['quality_score']:.2f}")
        print(f"  提升: +{(impr['quality_score'] - orig['quality_score']):.2f}")


def main():
    print("=" * 80)
    print("Reviser 修订效果完整测试")
    print("=" * 80)

    # 原始低质量数据
    original_analyses = [
        {
            "source_url": "https://github.com/example/ai-tool",
            "original_title": "example/ai-tool",
            "category": "其他",
            "tags": ["工具"],
            "summary": "一个 AI 工具。",
            "key_points": ["功能"],
            "quality_score": 0.4
        }
    ]

    # 审核反馈
    review_feedback = """## 审核反馈

### 主要问题：
1. 摘要过于简短，缺少技术细节
2. 标签不够具体，需要补充技术栈
3. 分类过于笼统
4. 要点数量不足，内容空洞

### 改进建议：
- 扩充摘要至 50-100 字，说明核心功能和技术特点
- 添加具体技术栈标签（如 PyTorch、TensorFlow 等）
- 细化分类（如"深度学习框架"、"NLP工具"等）
- 增加 3-5 个具体要点，突出项目价值
"""

    # 构建状态
    state = {
        "analyses": original_analyses,
        "review_feedback": review_feedback,
        "iteration": 1,
        "cost_tracker": {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost_usd": 0.0,
            "by_node": {}
        }
    }

    # 执行修订
    result = revise_node(state)

    if not result:
        print("\n修订失败或被跳过")
        return

    improved_analyses = result.get("analyses", [])

    # 对比结果
    compare_analyses(original_analyses, improved_analyses)

    # 统计改进
    print("\n" + "=" * 80)
    print("改进统计")
    print("=" * 80)

    orig = original_analyses[0]
    impr = improved_analyses[0]

    print(f"\n摘要长度: {len(orig['summary'])} → {len(impr['summary'])} 字符 (+{len(impr['summary']) - len(orig['summary'])})")
    print(f"标签数量: {len(orig['tags'])} → {len(impr['tags'])} 个 (+{len(impr['tags']) - len(orig['tags'])})")
    print(f"要点数量: {len(orig['key_points'])} → {len(impr['key_points'])} 个 (+{len(impr['key_points']) - len(orig['key_points'])})")
    print(f"质量评分: {orig['quality_score']:.2f} → {impr['quality_score']:.2f} (+{impr['quality_score'] - orig['quality_score']:.2f})")

    # Token 用量
    tracker = result['cost_tracker']
    if tracker.get('total_tokens', 0) > 0:
        print(f"\nToken 用量: {tracker['total_tokens']} (${tracker['total_cost_usd']:.4f})")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
