# State.py 更新记录

## 更新内容

### 新增字段：`needs_human_review`

在 `workflows/state.py` 的 `KBState` TypedDict 中添加了 `needs_human_review` 字段。

```python
needs_human_review: bool
"""
是否需要人工审核
True: 审核循环超过最大次数仍未通过，已写入 pending_review/ 目录
False: 正常流程，无需人工介入
由 HumanFlag 节点设置为 True
"""
```

## 字段说明

- **类型**: `bool`
- **默认值**: `False`
- **设置时机**: 由 `human_flag_node` 在审核循环超过最大迭代次数时设置为 `True`
- **用途**: 标记工作流需要人工介入，问题数据已保存到 `knowledge/pending_review/` 目录

## 更新的文件列表

以下文件已更新，在初始化 `KBState` 时添加了 `needs_human_review: False`：

1. ✅ `workflows/state.py` - 类型定义
2. ✅ `workflows/graph.py` - 主工作流初始化
3. ✅ `run_workflow.py` - 启动脚本初始化
4. ✅ `test_reviewer.py` - 审核测试
5. ✅ `test_reviewer_fail.py` - 审核失败测试
6. ✅ `test_reviser.py` - 修订测试
7. ✅ `test_human_flag.py` - 人工介入测试

## KBState 完整字段列表

更新后的 `KBState` 包含 8 个字段：

1. `sources: list[dict]` - 采集到的原始数据源
2. `analyses: list[dict]` - LLM 分析后的结构化结果
3. `articles: list[dict]` - 格式化、去重后的知识条目
4. `review_feedback: str` - 审核反馈意见
5. `review_passed: bool` - 审核是否通过
6. `iteration: int` - 当前审核循环次数
7. **`needs_human_review: bool`** - 是否需要人工审核（新增）
8. `cost_tracker: dict` - Token 用量和成本追踪

## 使用示例

### 初始化状态

```python
from workflows.state import KBState

initial_state: KBState = {
    "sources": [],
    "analyses": [],
    "articles": [],
    "review_feedback": "",
    "review_passed": False,
    "iteration": 0,
    "needs_human_review": False,  # 新增字段
    "cost_tracker": {
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_cost_usd": 0.0,
        "by_node": {}
    }
}
```

### HumanFlag 节点设置

```python
def human_flag_node(state: KBState) -> dict:
    """审核循环超限时的兜底节点"""
    # ... 保存数据到 pending_review/ ...
    
    return {
        "needs_human_review": True,  # 标记需要人工介入
        "cost_tracker": tracker
    }
```

### 条件路由使用

```python
def should_continue(state: KBState) -> str:
    """决定工作流下一步"""
    if state["needs_human_review"]:
        return "human_flag"  # 进入人工介入流程
    elif state["review_passed"]:
        return "save"  # 审核通过，保存
    else:
        return "revise"  # 审核未通过，修订
```

## 验证测试

所有测试通过：

```bash
$ python test_human_flag.py
[HumanFlag] ⚠️ 达到 3 次审核仍未通过
[HumanFlag] 已保存到 knowledge/pending_review/pending-*.json
needs_human_review: True
[OK] 测试完成
```

## 向后兼容性

此更新是**向后兼容**的：
- 新增字段有明确的默认值（`False`）
- 不影响现有节点的功能
- 只有 `human_flag_node` 会设置此字段为 `True`

## 下一步

需要在 `workflows/graph.py` 中添加条件路由逻辑，根据 `needs_human_review` 字段决定是否进入人工介入流程。
