# Graph.py 更新完成总结

## ✅ 更新内容

成功修改 `workflows/graph.py` 以支持完整的审核循环，包括修订和人工介入分支。

## 关键变更

### 1. 导入新节点

```python
from workflows.reviewer import review_node      # 生产版审核节点
from workflows.reviser import revise_node       # 修订节点
from workflows.human_flag import human_flag_node # 人工介入节点
```

### 2. 注册节点

新增 3 个节点：
- `"review"` - 使用 `workflows.reviewer.review_node`（五维度评分）
- `"revise"` - 使用 `workflows.reviser.revise_node`（根据反馈修订）
- `"human_flag"` - 使用 `workflows.human_flag.human_flag_node`（人工介入）

### 3. 三路条件路由

新的路由函数 `route_after_review()` 实现三路分支：

```python
def route_after_review(state: KBState) -> str:
    passed = state["review_passed"]
    iteration = state["iteration"]

    if passed:
        return "organize"      # 审核通过 → 整理和保存
    elif iteration < 3:
        return "revise"        # 未通过 + iter<3 → 修订
    else:
        return "human_flag"    # 未通过 + iter>=3 → 人工介入
```

### 4. 条件边配置

```python
graph.add_conditional_edges(
    "review",
    route_after_review,
    {
        "organize": "organize",
        "revise": "revise",
        "human_flag": "human_flag"
    }
)
```

### 5. 修订循环边

```python
graph.add_edge("revise", "review")  # 形成 revise → review 循环
```

### 6. 终止边

```python
graph.add_edge("save", END)
graph.add_edge("human_flag", END)
```

## 工作流结构

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

## 路由测试结果

所有 5 个测试场景通过：

| 场景 | review_passed | iteration | 路由结果 | 状态 |
|------|---------------|-----------|----------|------|
| 审核通过 | True | 0 | organize | ✅ |
| 首次未通过 | False | 0 | revise | ✅ |
| 第二次未通过 | False | 1 | revise | ✅ |
| 第三次未通过 | False | 2 | revise | ✅ |
| 超过最大次数 | False | 3 | human_flag | ✅ |

## 执行流程示例

### 场景 A：首次审核通过

```
collect → analyze → organize → review (通过)
    → organize → save → END
```

**Token 消耗**: ~4000 tokens (~$0.0008)

### 场景 B：第二次审核通过

```
collect → analyze → organize → review (未通过, iter=0)
    → revise → review (通过, iter=1)
    → organize → save → END
```

**Token 消耗**: ~8000 tokens (~$0.0016)

### 场景 C：三次审核均未通过

```
collect → analyze → organize → review (未通过, iter=0)
    → revise → review (未通过, iter=1)
    → revise → review (未通过, iter=2)
    → revise → review (未通过, iter=3)
    → human_flag → END
```

**Token 消耗**: ~12000 tokens (~$0.0024)
**结果**: 数据保存到 `knowledge/pending_review/`

## 日志输出增强

新增对 `needs_human_review` 字段的监控：

```python
if "needs_human_review" in state_update:
    needs_review = state_update['needs_human_review']
    if needs_review:
        print(f"[WARN] 需要人工审核: {needs_review}")
```

## 同步更新的文件

- ✅ `workflows/graph.py` - 主工作流图
- ✅ `run_workflow.py` - 启动脚本

## 验证结果

```bash
$ python -c "from workflows.graph import build_graph; build_graph()"
[OK] Graph built successfully

$ python -c "from workflows.graph import route_after_review; ..."
[OK] All routing tests passed (5/5)
```

## 使用方法

### 运行完整工作流

```bash
python run_workflow.py
# 或
python -m workflows.graph
```

### 测试路由逻辑

```bash
python -c "from workflows.graph import route_after_review; ..."
```

## 下一步

工作流已完全集成，可以进行端到端测试：

1. 运行完整工作流，观察审核循环
2. 测试低质量数据触发人工介入
3. 验证 `pending_review/` 目录的文件生成
4. 监控 Token 消耗和成本

## 技术细节

### 节点执行顺序

1. **collect_node**: 采集 GitHub 数据
2. **analyze_node**: LLM 分析生成摘要
3. **organize_node**: 过滤、去重、格式化
4. **review_node**: 五维度质量评分
5. **route_after_review**: 决定下一步
   - 通过 → organize → save → END
   - 未通过 (iter<3) → revise → review (循环)
   - 未通过 (iter>=3) → human_flag → END

### 状态传递

每个节点返回部分状态更新，LangGraph 自动合并到全局状态：

```python
# review_node 返回
{
    "review_passed": True/False,
    "review_feedback": "...",
    "iteration": iteration + 1,
    "cost_tracker": {...}
}

# revise_node 返回
{
    "analyses": improved_analyses,  # 覆盖原 analyses
    "cost_tracker": {...}
}

# human_flag_node 返回
{
    "needs_human_review": True,
    "cost_tracker": {...}
}
```

## 成本优化建议

1. **提高首次通过率**: 优化 analyze_node 的 prompt
2. **降低审核标准**: 调整 reviewer.py 的阈值（7.0 → 6.5）
3. **减少修订次数**: 改进 revise_node 的修订策略
4. **数据源过滤**: 在 collect_node 提高质量门槛

## 监控指标

- 首次通过率: 目标 >70%
- 平均迭代次数: 目标 <1.5
- 人工介入率: 目标 <10%
- 平均成本/条: 目标 <$0.001
