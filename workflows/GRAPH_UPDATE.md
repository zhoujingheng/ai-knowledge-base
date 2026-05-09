# 工作流图结构更新

## 更新内容

`workflows/graph.py` 已更新为支持完整的审核循环，包括修订和人工介入分支。

## 新的工作流结构

```
collect (采集)
    ↓
analyze (分析)
    ↓
organize (整理)
    ↓
review (审核)
    ↓
    ├─────────────┼─────────────┐
    ↓             ↓             ↓
(通过)        (未通过        (未通过
              iter<3)       iter>=3)
    ↓             ↓             ↓
organize      revise      human_flag
    ↓             ↓             ↓
  save        review          END
    ↓             ↑
  END             └─ (循环)
```

## 关键变更

### 1. 导入新节点

```python
from workflows.reviewer import review_node
from workflows.reviser import revise_node
from workflows.human_flag import human_flag_node
```

### 2. 注册新节点

```python
graph.add_node("review", review_node)      # 使用 reviewer.py 的生产版本
graph.add_node("revise", revise_node)      # 修订节点
graph.add_node("human_flag", human_flag_node)  # 人工介入节点
```

### 3. 三路条件路由

新的路由函数 `route_after_review()` 替代了原来的 `review_router()`：

```python
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
        return "organize"
    elif iteration < 3:
        return "revise"
    else:
        return "human_flag"
```

### 4. 条件边配置

```python
graph.add_conditional_edges(
    "review",
    route_after_review,
    {
        "organize": "organize",    # 审核通过 → 整理（然后保存）
        "revise": "revise",        # 审核未通过 + iter<3 → 修订
        "human_flag": "human_flag" # 审核未通过 + iter>=3 → 人工介入
    }
)
```

### 5. 修订循环边

```python
graph.add_edge("revise", "review")  # 修订后返回审核
```

### 6. 终止边

```python
graph.add_edge("save", END)
graph.add_edge("human_flag", END)
```

## 路由逻辑测试

所有路由测试通过：

| 场景 | review_passed | iteration | 路由结果 |
|------|---------------|-----------|----------|
| 审核通过 | True | 0 | organize |
| 首次未通过 | False | 0 | revise |
| 第二次未通过 | False | 1 | revise |
| 第三次未通过 | False | 2 | revise |
| 超过最大次数 | False | 3 | human_flag |

## 执行流程示例

### 场景 1：首次审核通过

```
collect → analyze → organize → review (通过) → organize → save → END
```

### 场景 2：第二次审核通过

```
collect → analyze → organize → review (未通过, iter=0)
    → revise → review (通过, iter=1)
    → organize → save → END
```

### 场景 3：三次审核均未通过

```
collect → analyze → organize → review (未通过, iter=0)
    → revise → review (未通过, iter=1)
    → revise → review (未通过, iter=2)
    → revise → review (未通过, iter=3)
    → human_flag → END
```

## 节点职责

| 节点 | 文件 | 职责 |
|------|------|------|
| collect | workflows/nodes.py | 采集 GitHub 数据 |
| analyze | workflows/nodes.py | LLM 分析生成摘要 |
| organize | workflows/nodes.py | 过滤、去重、格式化 |
| review | workflows/reviewer.py | 五维度质量审核 |
| revise | workflows/reviser.py | 根据反馈修订内容 |
| human_flag | workflows/human_flag.py | 保存到待审核目录 |
| save | workflows/nodes.py | 保存到主知识库 |

## 状态字段使用

| 字段 | 读取节点 | 写入节点 |
|------|----------|----------|
| sources | analyze | collect |
| analyses | organize, review, revise | analyze, revise |
| articles | save | organize |
| review_feedback | revise, human_flag | review |
| review_passed | route_after_review | review |
| iteration | route_after_review, review, revise, human_flag | review |
| needs_human_review | - | human_flag |
| cost_tracker | 所有节点 | 所有节点 |

## 日志输出增强

新增对 `needs_human_review` 字段的日志输出：

```python
if "needs_human_review" in state_update:
    needs_review = state_update['needs_human_review']
    if needs_review:
        print(f"[WARN] 需要人工审核: {needs_review}")
```

## 验证结果

- ✅ 所有导入成功
- ✅ 图构建成功
- ✅ 三路路由逻辑正确
- ✅ 审核通过路由到 organize
- ✅ 未通过且 iter<3 路由到 revise
- ✅ 未通过且 iter>=3 路由到 human_flag

## 下一步

可以运行完整的工作流测试：

```bash
python run_workflow.py
# 或
python -m workflows.graph
```
