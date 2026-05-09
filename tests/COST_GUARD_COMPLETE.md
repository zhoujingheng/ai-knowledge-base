# 第12节实操任务1完成总结 - CostGuard 成本控制

## ✅ 完成内容

成功实现 `tests/cost_guard.py`，为多 Agent 系统提供三重成本保护机制。

## 核心功能

### 1. CostRecord 数据类
记录单次 LLM 调用的完整信息：
- `timestamp`: 调用时间戳
- `node_name`: 节点名称
- `prompt_tokens`: 输入 tokens
- `completion_tokens`: 输出 tokens
- `cost_yuan`: 成本（人民币元）
- `model`: 模型名称

### 2. CostGuard 类 - 三重保护

#### 保护机制 1：成本追踪 (`record()`)
```python
guard.record("analyze", {"prompt_tokens": 2000, "completion_tokens": 1000})
```
- 记录每次 LLM 调用的 token 用量
- 自动计算成本：`(prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000`
- 累加到总成本

#### 保护机制 2：预警提醒 (`check()`)
```python
result = guard.check()
# {"status": "warning", "message": "[预警] 成本已达预算的 80%！"}
```
- 达到预警阈值（默认 80%）时返回 `status="warning"`
- 提前提醒，避免超标

#### 保护机制 3：预算熔断 (`check()` 抛异常)
```python
try:
    guard.check()
except BudgetExceededError as e:
    print(f"预算超标：{e}")
```
- 成本超出预算时抛出 `BudgetExceededError`
- 强制停止工作流，防止成本失控

### 3. 成本报告 (`get_report()`)
```python
report = guard.get_report()
# {
#   "total_cost_yuan": 0.0083,
#   "total_calls": 3,
#   "cost_by_node": {
#     "collect": 0.0002,
#     "analyze": 0.004,
#     "review": 0.0041
#   }
# }
```
- 按节点分组统计成本
- 一眼看出哪个节点最费钱
- 指导优化方向

### 4. 保存报告 (`save_report()`)
```python
path = guard.save_report("cost_report.json")
```
- 保存详细成本报告到 JSON 文件
- 包含每次调用的完整记录

## 测试结果

所有 4 个测试场景通过：

### 测试 1：成本追踪 ✅
```
调用次数: 3
总成本: ¥0.0083
按节点: {'collect': 0.0002, 'analyze': 0.004, 'review': 0.0041}
预算状态: ok
```

### 测试 2：预算超限 ✅
```
预算超限检测通过: 成本已超出预算！当前: ¥0.3000, 预算: ¥0.00
```

### 测试 3：预警阈值 ✅
```
预警状态: warning — [预警] 成本已达预算的 90%！
```

### 测试 4：保存报告 ✅
```
报告已保存到: test_cost_report.json
```

## 设计亮点

| 设计点 | 为什么这样做 |
|--------|-------------|
| 三重保护 | record() 是仪表盘，预警是黄灯，BudgetExceededError 是保险丝 |
| CostRecord 数据类 | 每次调用记录完整信息（节点名、时间戳、token 数），方便按节点统计 |
| check() 抛异常 | 超预算是严重事件，异常比返回值更难被忽略 |
| get_report() 按节点分组 | 一眼看出哪个节点最费钱，指导优化方向 |
| 价格参数化 | input_price 和 output_price 可配置，适应不同模型定价 |

## 成本计算公式

```python
cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
```

- 价格单位：元/百万 tokens
- 默认价格：输入 ¥1.0/M，输出 ¥2.0/M（DeepSeek 定价）

## 使用示例

### 基本使用
```python
from tests.cost_guard import CostGuard, BudgetExceededError

# 创建守卫，设置预算 1 元
guard = CostGuard(budget_yuan=1.0, alert_threshold=0.8)

# 记录每次 LLM 调用
guard.record("analyze", {"prompt_tokens": 2000, "completion_tokens": 1000})
guard.record("review", {"prompt_tokens": 2500, "completion_tokens": 800})

# 检查预算状态
try:
    result = guard.check()
    if result["status"] == "warning":
        print(f"预警：{result['message']}")
except BudgetExceededError as e:
    print(f"预算超标，停止执行：{e}")

# 生成报告
report = guard.get_report()
print(f"总成本：¥{report['total_cost_yuan']}")
print(f"按节点：{report['cost_by_node']}")
```

### 集成到 LangGraph 工作流
```python
# 在工作流初始化时创建守卫
guard = CostGuard(budget_yuan=1.0)

# 在每个节点中记录成本
def analyze_node(state):
    response, usage = chat_json(prompt, system=system_prompt)
    guard.record("analyze", usage)
    guard.check()  # 检查预算
    return {"analyses": result}
```

## 文件信息

- **文件路径**: `tests/cost_guard.py`
- **代码行数**: 242 行
- **测试覆盖**: 4 个测试场景
- **Git 提交**: `feat: add CostGuard with budget control and circuit breaker`

## 下一步

CostGuard 已完成，可以集成到工作流中：
1. 在 `workflows/graph.py` 初始化 CostGuard
2. 在每个节点调用 LLM 后记录成本
3. 在关键节点检查预算状态
4. 工作流结束时生成成本报告

## 成本优化建议

根据 `get_report()` 的按节点统计，可以针对性优化：
- 如果 analyze_node 成本高 → 优化 prompt，减少输出长度
- 如果 review_node 成本高 → 降低审核频率，提高首次通过率
- 如果 revise_node 成本高 → 改进修订策略，减少迭代次数

## 监控指标

- **平均成本/条**: 目标 <¥0.001
- **预警触发率**: 目标 <5%
- **预算超标率**: 目标 0%
- **最费钱节点**: 持续优化
