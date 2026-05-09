# Pending Review 目录

此目录存放审核循环超过最大迭代次数（3次）仍未通过质量标准的内容，等待人工审核。

## 文件格式

每个文件命名为 `pending-{timestamp}.json`，包含以下字段：

```json
{
  "timestamp": "2026-05-09-035526",
  "iterations_used": 3,
  "last_feedback": "最后一次审核的详细反馈...",
  "analyses_count": 2,
  "analyses": [...],
  "cost_summary": {
    "total_tokens": 5420,
    "total_cost_usd": 0.0010,
    "by_node": {...}
  },
  "status": "pending_human_review",
  "notes": "说明信息"
}
```

## 为什么需要人工介入？

当内容经过 3 次审核循环（初次 + 2 次修订）仍未通过时，说明问题可能不在"质量"而在"数据"：

1. **数据源质量问题**：原始数据本身信息不足，无法通过 LLM 改进达标
2. **审核标准过严**：评分阈值或维度设置不合理，需要调整
3. **技术相关性不足**：采集到的内容与 AI/ML 领域关联度低

## 人工审核流程

### 1. 查看问题内容

```bash
# 查看最新的待审核文件
ls -lt knowledge/pending_review/ | head -5

# 读取文件内容
cat knowledge/pending_review/pending-{timestamp}.json
```

### 2. 分析问题原因

检查 `last_feedback` 字段，了解审核未通过的具体原因：
- 摘要质量低 → 原始描述不清晰
- 技术深度不足 → 缺少技术栈信息
- 相关性低 → 与 AI/ML 领域关联度低
- 原创性差 → 内容过于泛化
- 格式不规范 → 标签或结构问题

### 3. 决策处理方式

#### 选项 A：调整审核标准

如果认为标准过严，修改 `workflows/reviewer.py`：

```python
# 降低通过阈值
passed = weighted_score >= 6.5  # 原为 7.0

# 或调整权重
weights = {
    "summary_quality": 0.30,      # 提高摘要权重
    "technical_depth": 0.20,      # 降低技术深度权重
    "relevance": 0.20,
    "originality": 0.15,
    "formatting": 0.15
}
```

#### 选项 B：改进数据源

修改 `workflows/nodes.py` 的 `collect_node`：

```python
# 提高 stars 阈值
query = "AI OR machine-learning language:Python stars:>500"  # 原为 >100

# 添加过滤规则
if item.get("description") and len(item["description"]) > 50:
    sources.append(...)
```

#### 选项 C：手动修改后移入主库

1. 手动编辑 `analyses` 字段，改进内容质量
2. 将改进后的条目移入 `knowledge/articles/`
3. 更新 `knowledge/index.json`

```bash
# 示例：手动处理后移入主库
python scripts/import_pending.py pending-2026-05-09-035526.json
```

### 4. 删除已处理文件

```bash
rm knowledge/pending_review/pending-{timestamp}.json
```

## 监控建议

定期检查此目录：

```bash
# 统计待审核文件数量
ls knowledge/pending_review/ | wc -l

# 查看最近一周的待审核文件
find knowledge/pending_review/ -name "*.json" -mtime -7
```

如果待审核文件持续增多，说明需要调整审核标准或数据源质量。

## 成本追踪

每个文件的 `cost_summary` 记录了该批次的 Token 消耗：

- `total_tokens`: 总 Token 数
- `total_cost_usd`: 总成本（美元）
- `by_node`: 各节点的详细用量

用于评估审核循环的成本效益。
