---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# 技术摘要分析技能

## 使用场景

- 需要对已采集的原始技术内容进行深度分析
- 需要生成结构化的知识条目
- 需要发现技术趋势和新兴概念

## 执行步骤

### 第一步：读取最新采集文件

从 `knowledge/raw/` 目录读取最新采集的 JSON 文件。

```bash
# 查找最新文件
ls -t knowledge/raw/*.json | head -1
```

### 第二步：逐条深度分析

对每条内容进行以下维度的分析：

- **中文摘要**：不超过 50 字，精炼描述核心内容
- **技术亮点**：2-3 个，用事实说话（如性能提升 50%、首次支持 XXX 等）
- **评分**：1-10 分
- **标签建议**：3-5 个相关标签

### 第三步：趋势发现

分析所有条目，发现：

- **共同主题**：多个项目涉及的相似领域
- **新概念**：首次出现的值得关注的技术方向
- **关联性**：看似不相关但内在联系的项目

### 第四步：输出 JSON

将分析结果写入 `knowledge/articles/` 目录。

## 评分标准

| 分数段 | 含义 | 说明 |
|--------|------|------|
| 9-10 | 改变格局 | 突破性创新，可能重塑行业格局 |
| 7-8 | 直接有帮助 | 对当前工作有直接实用价值 |
| 5-6 | 值得了解 | 有一定价值，值得关注但非紧急 |
| 1-4 | 可略过 | 价值有限，非必要了解 |

### 评分理由要求

每项评分必须附带具体理由，说明：

- 为什么给出这个分数
- 与同类项目相比的优势/劣势
- 适用的场景和人群

## 注意事项

1. 评分必须客观，避免个人偏好影响
2. 摘要用词精准，避免模糊表述
3. 技术亮点必须有数据或事实支撑
4. 标签建议要有代表性，便于后续检索

## 约束规则

- 15 个项目中，9-10 分不超过 2 个
- 确保评分分布符合正态分布，高分项目需真正出色

## 输出格式

```json
{
  "source": "github_trending",
  "skill": "tech-summary",
  "collected_at": "2026-04-30T10:00:00Z",
  "items": [
    {
      "name": "vllm-project/vllm",
      "url": "https://github.com/vllm-project/vllm",
      "summary": "高性能 LLM 推理框架，吞吐量提升 2-3 倍",
      "highlights": [
        "首创 PagedAttention，显存效率提升 2 倍",
        "连续批处理支持，吞吐量提升 2-3 倍",
        "支持主流开源 LLM 模型"
      ],
      "score": 9,
      "score_reason": "突破性技术创新，直接解决 LLM 推理瓶颈，对生产环境有重大价值",
      "tags": ["LLM", "推理优化", "性能", "GPU"]
    }
  ],
  "trends": {
    "common_themes": ["LLM 推理优化", "Agent 框架"],
    "new_concepts": ["PagedAttention", "MoE"]
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| source | string | 数据来源 |
| skill | string | 技能名称，固定为 `tech-summary` |
| collected_at | string | 采集时间，ISO 8601 格式 |
| items | array | 分析结果列表 |
| name | string | 项目名称 |
| url | string | 项目地址 |
| summary | string | 中文摘要，不超过 50 字 |
| highlights | string[] | 技术亮点，2-3 个 |
| score | int | 评分，1-10 |
| score_reason | string | 评分理由 |
| tags | string[] | 标签建议，3-5 个 |
| trends | object | 趋势发现 |
| common_themes | string[] | 共同主题 |
| new_concepts | string[] | 新概念 |