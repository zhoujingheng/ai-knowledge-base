#!/usr/bin/env python3
"""
知识库自动化工作流启动脚本

使用方法：
    python run_workflow.py
"""

if __name__ == "__main__":
    from workflows.graph import build_graph
    from workflows.state import KBState
    import sys
    import io
    import os
    from pathlib import Path

    # 设置 UTF-8 输出（解决 Windows 控制台编码问题）
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

    print("=" * 60)
    print("启动知识库自动化工作流")
    print("=" * 60)

    # 构建工作流
    app = build_graph()

    # 初始化状态
    initial_state: KBState = {
        "sources": [],
        "analyses": [],
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

    # 流式执行工作流
    print("\n开始执行工作流...\n")

    try:
        for step_output in app.stream(initial_state):
            # step_output 格式: {node_name: state_update}
            for node_name, state_update in step_output.items():
                print(f"\n{'=' * 60}")
                print(f"节点: {node_name}")
                print(f"{'=' * 60}")

                # 打印关键输出
                if "sources" in state_update:
                    print(f"[OK] 采集数据: {len(state_update['sources'])} 条")

                if "analyses" in state_update:
                    print(f"[OK] 分析结果: {len(state_update['analyses'])} 条")
                    if state_update['analyses']:
                        sample = state_update['analyses'][0]
                        print(f"  示例 - 分类: {sample.get('category', 'N/A')}")
                        print(f"  示例 - 评分: {sample.get('quality_score', 0):.2f}")

                if "articles" in state_update:
                    print(f"[OK] 知识条目: {len(state_update['articles'])} 条")
                    if state_update['articles']:
                        sample = state_update['articles'][0]
                        print(f"  示例 - 标题: {sample.get('title', 'N/A')}")

                if "review_passed" in state_update:
                    passed = state_update['review_passed']
                    iteration = state_update.get('iteration', 0)
                    print(f"[OK] 审核结果: {'通过' if passed else '未通过'}")
                    print(f"  当前迭代: {iteration}")
                    if not passed and state_update.get('review_feedback'):
                        print(f"  反馈摘要: {state_update['review_feedback'][:100]}...")

                if "needs_human_review" in state_update:
                    needs_review = state_update['needs_human_review']
                    if needs_review:
                        print(f"[WARN] 需要人工审核: {needs_review}")

                if "cost_tracker" in state_update:
                    tracker = state_update['cost_tracker']
                    if tracker.get('total_tokens', 0) > 0:
                        print(f"[OK] Token 用量: {tracker['total_tokens']} (${tracker['total_cost_usd']:.4f})")

        print("\n" + "=" * 60)
        print("工作流执行完成！")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\n工作流被用户中断")
    except Exception as e:
        print(f"\n\n工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
