"""CostGuard — 多 Agent 预算守卫

三重保护：成本追踪 (record) + 预警提醒 + 预算熔断 (BudgetExceededError)
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CostRecord:
    """单次 LLM 调用的成本记录"""
    timestamp: float
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: float
    model: str = ""


class BudgetExceededError(Exception):
    """预算超标异常 — 触发熔断"""
    pass


class CostGuard:
    """成本守卫：追踪、预警、熔断

    使用方式:
        guard = CostGuard(budget_yuan=1.0)
        guard.record("analyze", usage)   # 记录每次调用
        guard.check()                     # 检查是否超标
    """

    def __init__(
        self,
        budget_yuan: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
    ) -> None:
        """
        初始化成本守卫

        Args:
            budget_yuan: 预算上限（人民币元）
            alert_threshold: 预警阈值（0-1），达到预算的此比例时触发预警
            input_price_per_million: 输入 token 价格（元/百万 tokens）
            output_price_per_million: 输出 token 价格（元/百万 tokens）
        """
        self.budget_yuan = budget_yuan
        self.alert_threshold = alert_threshold
        self.input_price = input_price_per_million
        self.output_price = output_price_per_million

        self.records: list[CostRecord] = []
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_cost_yuan: float = 0.0
        self._alert_fired: bool = False

    def record(self, node_name: str, usage: dict, model: str = "") -> CostRecord:
        """
        记录一次 LLM 调用的 token 用量

        Args:
            node_name: 节点名称（如 "analyze", "review"）
            usage: token 用量字典，格式 {"prompt_tokens": int, "completion_tokens": int}
            model: 模型名称（可选）

        Returns:
            CostRecord: 本次调用的成本记录
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost = (prompt_tokens * self.input_price
                + completion_tokens * self.output_price) / 1_000_000

        rec = CostRecord(
            timestamp=time.time(),
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost,
            model=model,
        )
        self.records.append(rec)
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_cost_yuan += cost
        return rec

    def check(self) -> dict[str, Any]:
        """
        检查预算状态，超标时抛出 BudgetExceededError

        Returns:
            dict: 预算状态信息
                - status: "ok" | "warning" | "exceeded"
                - total_cost: 当前总成本（元）
                - budget: 预算上限（元）
                - usage_ratio: 使用比例（0-1）
                - message: 状态消息

        Raises:
            BudgetExceededError: 当成本超出预算时
        """
        ratio = self.total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 0

        # 超标检测 - 抛出异常强制停止
        if self.total_cost_yuan >= self.budget_yuan:
            raise BudgetExceededError(
                f"成本已超出预算！当前: ¥{self.total_cost_yuan:.4f}, "
                f"预算: ¥{self.budget_yuan:.2f}"
            )

        # 预警检测
        if ratio >= self.alert_threshold and not self._alert_fired:
            self._alert_fired = True
            status = "warning"
            message = f"[预警] 成本已达预算的 {ratio:.0%}！"
        else:
            status = "ok"
            message = f"成本正常: ¥{self.total_cost_yuan:.4f} / ¥{self.budget_yuan:.2f}"

        return {
            "status": status,
            "total_cost": round(self.total_cost_yuan, 6),
            "budget": self.budget_yuan,
            "usage_ratio": round(ratio, 4),
            "message": message
        }

    def get_report(self) -> dict:
        """
        生成成本报告（按节点分组统计）

        Returns:
            dict: 成本报告
                - total_cost_yuan: 总成本（元）
                - total_prompt_tokens: 总输入 tokens
                - total_completion_tokens: 总输出 tokens
                - total_calls: 总调用次数
                - budget_yuan: 预算上限
                - cost_by_node: 按节点分组的成本统计
        """
        by_node: dict[str, float] = {}
        for r in self.records:
            by_node[r.node_name] = by_node.get(r.node_name, 0) + r.cost_yuan

        return {
            "total_cost_yuan": round(self.total_cost_yuan, 6),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_calls": len(self.records),
            "budget_yuan": self.budget_yuan,
            "cost_by_node": {k: round(v, 6) for k, v in by_node.items()},
        }

    def save_report(self, path: str | None = None) -> str:
        """
        保存成本报告到 JSON 文件

        Args:
            path: 保存路径（可选），默认为 "cost_report_{timestamp}.json"

        Returns:
            str: 保存的文件路径
        """
        if path is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = f"cost_report_{timestamp}.json"

        report = self.get_report()

        # 添加详细记录
        report["records"] = [
            {
                "timestamp": r.timestamp,
                "node_name": r.node_name,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cost_yuan": round(r.cost_yuan, 6),
                "model": r.model
            }
            for r in self.records
        ]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return path


# --- 测试入口 ---
if __name__ == "__main__":
    import sys
    import io

    # 设置 UTF-8 输出（解决 Windows 控制台编码问题）
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    print("=== 测试 1：成本追踪 ===")
    guard = CostGuard(budget_yuan=1.0)
    guard.record("collect", {"prompt_tokens": 100, "completion_tokens": 50})
    guard.record("analyze", {"prompt_tokens": 2000, "completion_tokens": 1000})
    guard.record("review", {"prompt_tokens": 2500, "completion_tokens": 800})
    report = guard.get_report()
    print(f"  调用次数: {report['total_calls']}")
    print(f"  总成本: ¥{report['total_cost_yuan']}")
    print(f"  按节点: {report['cost_by_node']}")
    result = guard.check()
    print(f"  预算状态: {result['status']}\n")

    print("=== 测试 2：预算超限 ===")
    guard2 = CostGuard(budget_yuan=0.001)
    guard2.record("analyze", {"prompt_tokens": 100000, "completion_tokens": 100000})
    try:
        guard2.check()
        assert False, "应该抛出 BudgetExceededError！"
    except BudgetExceededError as e:
        print(f"  预算超限检测通过: {e}\n")

    print("=== 测试 3：预警阈值 ===")
    guard3 = CostGuard(budget_yuan=0.01, alert_threshold=0.5)
    guard3.record("analyze", {"prompt_tokens": 5000, "completion_tokens": 2000})
    result3 = guard3.check()
    print(f"  预警状态: {result3['status']} — {result3['message']}\n")

    print("=== 测试 4：保存报告 ===")
    guard4 = CostGuard(budget_yuan=1.0)
    guard4.record("collect", {"prompt_tokens": 100, "completion_tokens": 50})
    guard4.record("analyze", {"prompt_tokens": 2000, "completion_tokens": 1000})
    report_path = guard4.save_report("test_cost_report.json")
    print(f"  报告已保存到: {report_path}\n")

    print("所有测试通过！")
