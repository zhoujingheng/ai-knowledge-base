# AI 知识库助手 - Agent 工作手册

## 1. 项目概述

本项目是一个 AI/LLM/Agent 领域技术动态采集与分析系统，自动从 GitHub Trending 和 Hacker News 抓取相关内容，通过 AI 分析后结构化存储，并支持多渠道分发（ Telegram /飞书）。

## 2. 技术栈

| 类别 | 技术选型 |
|------|----------|
| 运行时 | Python 3.12 |
| AI 底座 | OpenCode + 国产大模型（通义千问 / 豆包 / DeepSeek 等） |
| Agent 框架 | LangGraph |
| 端侧部署 | OpenClaw |
| 存储格式 | JSON |

## 3. 编码规范

### 3.1 风格指南

- 遵循 **PEP 8** 规范
- 变量 / 函数 / 模块命名使用 **snake_case**
- 类命名使用 **PascalCase**
- 常量命名使用 **SCREAMING_SNAKE_CASE**

### 3.2 文档字符串

采用 **Google 风格 docstring**：

```python
def fetch_trending_repos(limit: int = 50, language: str = "python") -> list[dict]:
    """获取 GitHub Trending 仓库列表。

    Args:
        limit: 返回的仓库数量上限，默认为 50。
        language: 编程语言过滤条件，默认为 "python"。

    Returns:
        包含仓库信息的字典列表，每项包含 name、url、description 等字段。

    Raises:
        requests.RequestException: 网络请求失败时抛出。
    """
    ...
```

### 3.3 日志与输出

- **禁止使用裸 `print()`**，统一使用 `logger.info()` / `logger.warning()` / `logger.error()`
- 日志配置统一使用 `logging` 模块，格式规范分级输出

### 3.4 其他要求

- 所有外部 API 调用必须配置超时（`timeout=30`）
- 敏感信息（API Key、Telegram Bot Token 等）通过环境变量读取，禁止硬编码

### 3.5 格式化要求

| 语言 | 工具 | 配置 |
|------|------|------|
| Python | black | 默认配置 |
| TypeScript | Prettier | `compilerOptions: { "strict": true }` |

### 3.6 禁止事项

- **禁止使用无解释的魔法字符串**：允许有常量定义或注释说明的字符串
- **禁止提交 TODO / FIXME / XXX / HACK 到 main**：使用 lint 工具检测

### 3.7 覆盖率要求

- 行覆盖率 ≥ 80%（排除 `tests/` 文件和简单数据模型）

### 3.8 CI 验证

| 语言 | Lint | Format | Test |
|------|------|--------|------|
| Python | ruff | ruff | pytest |
| TypeScript | ESLint | Prettier | vitest |

## 4. 项目结构

```
ai-knowledge-base/
├── .opencode/
│   ├── agents/              # Agent 定义文件
│   │   ├── collector.py     # 采集 Agent
│   │   ├── analyzer.py      # 分析 Agent
│   │   └── curator.py       # 整理 Agent
│   ├── skills/              # 复用技能模块
│   └── config.yaml          # 全局配置
├── knowledge/
│   ├── raw/                 # 原始采集数据（JSON）
│   └── articles/            # 整理后的结构化知识条目
├── src/
│   ├── fetcher/             # 数据抓取模块
│   ├── parser/              # 解析与处理模块
│   ├── distributor/         # 分发模块（Telegram / 飞书）
│   └── utils/               # 工具函数
├── tests/                   # 测试文件
├── requirements.txt
└── README.md
```

## 5. 知识条目 JSON 格式

存储于 `knowledge/articles/` 目录，文件命名格式：`{id}.json`

```json
{
  "id": "hn-20260428-001",
  "title": "GPT-4.1 发布：上下文窗口扩展至 200K",
  "source_url": "https://news.ycombinator.com/item?id=12345678",
  "source": "hackernews",
  "summary": "OpenAI 发布 GPT-4.1 模型，上下文窗口从 128K 扩展至 200K...",
  "tags": ["LLM", "OpenAI", "GPT-4"],
  "status": "published",
  "priority": "high",
  "created_at": "2026-04-28T10:00:00Z",
  "updated_at": "2026-04-28T10:00:00Z",
  "published_channels": ["telegram"],
  "metadata": {
    "author": "openai",
    "score": 489,
    "comments": 156
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 唯一标识，格式：`{source}-{date}-{序号}` |
| `title` | string | 是 | 标题，最多 200 字符 |
| `source_url` | string | 是 | 原始链接 |
| `source` | string | 是 | 来源：`github_trending` / `hackernews` |
| `summary` | string | 是 | AI 生成的摘要，50-500 字符 |
| `tags` | string[] | 是 | 标签，最多 5 个 |
| `status` | string | 是 | 状态：`draft` / `review` / `published` / `archived` |
| `priority` | string | 否 | 优先级：`high` / `medium` / `low` |
| `created_at` | string | 是 | ISO 8601 格式时间戳 |
| `updated_at` | string | 是 | ISO 8601 格式时间戳 |
| `published_channels` | string[] | 否 | 已发布的渠道 |
| `metadata` | object | 否 | 额外元数据 |

## 6. Agent 角色概览

| Agent | 角色名 | 核心职责 | 输入 | 输出 |
|-------|--------|----------|------|------|
| `collector` | 采集员 | 从 GitHub Trending 和 Hacker News 抓取原始数据 | 关键词列表、时间范围 | `knowledge/raw/` 下的 JSON 文件 |
| `analyzer` | 分析员 | 对原始内容进行摘要提取、标签生成、去重判断 | `knowledge/raw/` 的数据 | 更新 `knowledge/articles/` 中的 `summary`、`tags`、`priority` 字段 |
| `curator` | 整理员 | 质量审核、状态流转、多渠道分发 | `knowledge/articles/` 待发布条目 | 推送至 Telegram / 飞书，更新 `published_channels` |

## 7. 红线（绝对禁止的操作）

> 以下操作 **绝对禁止**，违者直接拒绝执行。

| # | 红线规则 | 说明 |
|---|----------|------|
| 1 | **禁止硬编码任何 API Key / Token** | 所有密钥必须通过环境变量或 `.env` 文件读取 |
| 2 | **禁止向任何第三方服务发送非约定的用户数据** | 仅发送用户主动请求的内容 |
| 3 | **禁止跳过日志记录直接使用 print()** | 统一使用 `logger` 模块 |
| 4 | **禁止在生产环境使用 `debug=True`** | 除本地开发调试外，任何环境不得开启调试模式 |
| 5 | **禁止在代码中写入 `TODO` / `FIXME` 而不记录 Issue** | 技术债务需通过 Issue 追踪 |
| 6 | **禁止直接请求用户隐私信息** | 遵循最小必要原则 |
| 7 | **禁止修改他人在 `knowledge/` 下的个人标注** | 尊重用户的数据主权 |
| 8 | **禁止在未配置熔断机制的情况下调用外部 API** | 必须设置超时和重试策略 |

---

*本手册由 AI 自动生成，如有疑问请联系项目维护者。*