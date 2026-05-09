"""
LangGraph 工作流组装

工作流结构：
collect → analyze → organize → review
                                  ↓
                    ┌─────────────┼─────────────┐
                    ↓             ↓             ↓
              (通过)          (未通过        (未通过
                              iter<3)       iter>=3)
                    ↓             ↓             ↓
                  save        revise      human_flag
                    ↓             ↓             ↓
                  END         review          END
                                ↑
                                └─ (循环)
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
    save_node
)
from workflows.reviewer import review_node
from workflows.reviser import revise_node
from workflows.human_flag import human_flag_node


def route_after_review(state: KBState) -> str:
    """
    审核后的 3 路条件路由

    返回:
        - "organize": 审核通过，进入整理和保存流程
        - "revise": 审核未通过且 iteration < 3，进入修订流程
        - "human_flag": 审核未通过且 iteration >= 3，进入人工介入流程
    """
    passed = state["review_passed"]
    iteration = state["iteration"]

    if passed:
        # 审核通过，进入整理节点（然后保存）
        return "organize"
    elif iteration < 3:
        # 审核未通过，但未达最大迭代次数，进入修订
        return "revise"
    else:
        # 审核未通过，且已达最大迭代次数，进入人工介入
        return "human_flag"


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
    graph.add_node("revise", revise_node)
    graph.add_node("human_flag", human_flag_node)
    graph.add_node("save", save_node)

    # 设置入口点
    graph.set_entry_point("collect")

    # 添加线性边
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "organize")
    graph.add_edge("organize", "review")

    # 添加条件边：review 之后根据审核结果和迭代次数分支
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {
            "organize": "organize",    # 审核通过 → 整理（然后保存）
            "revise": "revise",        # 审核未通过 + iter<3 → 修订
            "human_flag": "human_flag" # 审核未通过 + iter>=3 → 人工介入
        }
    )

    # 添加修订循环边：revise → review
    graph.add_edge("revise", "review")

    # 添加终止边
    graph.add_edge("save", END)
    graph.add_edge("human_flag", END)

    # 编译图
    app = graph.compile()

    return app


if __name__ == "__main__":
    from workflows.model_client import get_cost_guard, BudgetExceededError

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

    except BudgetExceededError as e:
        print(f"\n[FATAL] 预算熔断触发：{e}")
    except KeyboardInterrupt:
        print("\n\n工作流被用户中断")
    except Exception as e:
        print(f"\n\n工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # ★ 接入点 ③ · 收尾打报告 · 落盘到 knowledge/cost-report.json
        guard = get_cost_guard()
        report = guard.get_report()
        print(f"\n[CostGuard] 总调用 {report['total_calls']} 次 · 总成本 ¥{report['total_cost_yuan']}")
        print(f"[CostGuard] 按节点：{report['cost_by_node']}")

        # 保存报告
        report_path = guard.save_report("knowledge/cost-report.json")
        print(f"[CostGuard] 成本报告已保存到 {report_path}")
