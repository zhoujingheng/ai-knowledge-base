"""
LangGraph 工作流组装

工作流结构：
collect → analyze → organize → review
                      ↑           ↓
                      └─ (False) ─┘
                                  ↓ (True)
                                save → END
"""

import sys
import io
import os
from pathlib import Path

# 设置 UTF-8 输出（解决 Windows 控制台编码问题）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 加载 .env 文件
def load_env():
    """加载 .env 文件中的环境变量"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

load_env()

from langgraph.graph import StateGraph, END

from workflows.state import KBState
from workflows.nodes import (
    collect_node,
    analyze_node,
    organize_node,
    review_node,
    save_node
)


def review_router(state: KBState) -> str:
    """
    审核路由函数：根据 review_passed 决定下一步

    返回:
        - "save": 审核通过，进入保存流程
        - "organize": 审核未通过，返回整理节点修正
    """
    if state["review_passed"]:
        return "save"
    else:
        return "organize"


def build_graph():
    """
    构建并编译 LangGraph 工作流

    返回: 编译后的 CompiledGraph 实例
    """
    # 创建状态图
    graph = StateGraph(KBState)

    # 添加节点
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", review_node)
    graph.add_node("save", save_node)

    # 设置入口点
    graph.set_entry_point("collect")

    # 添加线性边
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "organize")
    graph.add_edge("organize", "review")

    # 添加条件边：review 之后根据审核结果分支
    graph.add_conditional_edges(
        "review",
        review_router,
        {
            "save": "save",        # 审核通过 → 保存
            "organize": "organize"  # 审核未通过 → 返回整理
        }
    )

    # 添加终止边
    graph.add_edge("save", END)

    # 编译图
    app = graph.compile()

    return app


if __name__ == "__main__":
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
