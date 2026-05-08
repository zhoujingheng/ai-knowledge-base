---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# GitHub Trending 采集技能

## 使用场景

- 需要追踪 GitHub 热门开源项目
- 需要为知识库收集 AI/LLM/Agent 领域的前沿项目
- 需要了解技术社区最新动向

## 执行步骤

### 第一步：搜索热门仓库

使用 GitHub API 或 WebFetch 工具获取 GitHub Trending 页面数据。

```bash
# 通过 API 获取 trending 仓库（推荐）
curl "https://api.github.com/search/repositories?q=created:>2024-01-01&sort=stars&order=desc&per_page=50"
```

### 第二步：提取信息

解析返回数据，提取以下字段：

- 仓库名称（full_name）
- 仓库地址（html_url）
- 描述（description）
- 星标数（stargazers_count）
- 编程语言（language）
- 主题标签（topics）
- 创建时间（created_at）

### 第三步：过滤

- **纳入条件**：AI、LLM、Agent、Machine Learning、Deep Learning 相关项目
- **排除条件**：包含 `awesome-` 前缀的列表项目

### 第四步：去重

基于 `full_name` 进行去重，保留星标数最高的版本。

### 第五步：撰写中文摘要

采用固定公式：

> 项目名 + 做什么 + 为什么值得关注

示例：

> vLLM 是一个高性能的 LLM 推理服务框架，支持 PagedAttention 和连续批处理，值得关注是因为它能显著提升 LLM 推理吞吐量和降低延迟。

摘要长度控制在 50-150 字。

### 第六步：排序取 Top 15

按星标数降序排列，选取前 15 个项目。

### 第七步：输出 JSON

将结果写入 `knowledge/raw/github-trending-YYYY-MM-DD.json` 文件。

## 注意事项

1. GitHub API 有速率限制（未认证 60次/小时），建议使用认证 Token
2. 避免采集过大的仓库（如 tensorflow、kubernetes 等巨型项目）
3. 优先选择近期创建或活跃更新的项目
4. 确保每个项目的摘要具有独特性和信息价值

## 输出格式

```json
{
  "source": "github_trending",
  "skill": "github-trending",
  "collected_at": "2026-04-30T10:00:00Z",
  "items": [
    {
      "name": "vllm-project/vllm",
      "url": "https://github.com/vllm-project/vllm",
      "summary": "vLLM 是一个高性能的 LLM 推理服务框架，支持 PagedAttention 和连续批处理，值得关注是因为它能显著提升 LLM 推理吞吐量和降低延迟。",
      "stars": 12500,
      "language": "Python",
      "topics": ["llm", "inference", "pagedattention"]
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| source | string | 数据来源，固定为 `github_trending` |
| skill | string | 技能名称，固定为 `github-trending` |
| collected_at | string | 采集时间，ISO 8601 格式 |
| items | array | 仓库列表 |
| name | string | 仓库全名（owner/repo） |
| url | string | 仓库地址 |
| summary | string | 中文摘要 |
| stars | int | 星标数 |
| language | string | 主要编程语言 |
| topics | string[] | 主题标签 |