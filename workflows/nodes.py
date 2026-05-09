"""
LangGraph 工作流节点函数

每个节点是纯函数：接收 KBState，返回部分状态更新的 dict
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from workflows.state import KBState
from workflows.model_client import chat, chat_json, accumulate_usage
from tests.security import sanitize_input, filter_output


def collect_node(state: KBState) -> dict:
    """
    数据采集节点：调用 GitHub Search API 获取 AI 相关仓库

    返回: {"sources": list[dict], "cost_tracker": dict}
    """
    print("[collect_node] 开始采集 GitHub AI 仓库数据...")

    # GitHub Search API 查询参数
    query = "AI OR machine-learning OR deep-learning language:Python stars:>100"
    url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page=10"

    # 发起 HTTP 请求
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "KB-Automation-Workflow")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            items = data.get("items", [])
    except Exception as e:
        print(f"[collect_node] API 请求失败: {e}")
        items = []

    # 转换为标准化格式
    sources = []
    for item in items:
        sources.append({
            "url": item["html_url"],
            "title": item["full_name"],
            "content": item.get("description", ""),
            "stars": item["stargazers_count"],
            "language": item.get("language", ""),
            "timestamp": datetime.now().isoformat()
        })

    # ★ 接入点 ④ · 出 collect 之前对每条 source 的文本字段做清洗
    cleaned_sources = []
    total_warnings = 0
    for s in sources:
        for field in ("title", "content"):
            if field in s and isinstance(s[field], str):
                cleaned, warnings = sanitize_input(s[field])
                s[field] = cleaned
                total_warnings += len(warnings)
                if warnings:
                    print(f"[Security] {s.get('url', '?')} {field} 检出注入模式：{warnings}")
        cleaned_sources.append(s)

    if total_warnings > 0:
        print(f"[Security] collect 阶段共拦截 {total_warnings} 处可疑输入")

    print(f"[collect_node] 采集完成，共 {len(cleaned_sources)} 条数据")

    return {
        "sources": cleaned_sources,
        "cost_tracker": state.get("cost_tracker", {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost_usd": 0.0,
            "by_node": {}
        })
    }


def analyze_node(state: KBState) -> dict:
    """
    LLM 分析节点：对每条数据生成中文摘要、标签、评分

    返回: {"analyses": list[dict], "cost_tracker": dict}
    """
    print("[analyze_node] 开始 LLM 分析...")

    sources = state["sources"]
    tracker = state["cost_tracker"]
    analyses = []

    system_prompt = """你是知识库内容分析专家。
任务：分析 GitHub 仓库信息，生成结构化输出。
输出 JSON 格式：
{
  "category": "分类（如：深度学习框架/NLP工具/计算机视觉/强化学习）",
  "tags": ["标签1", "标签2", "标签3"],
  "summary": "中文摘要（50字内）",
  "key_points": ["要点1", "要点2"],
  "quality_score": 0.85
}
评分标准：stars > 1000 且有清晰描述 = 0.8+，否则 0.5-0.7"""

    for source in sources:
        prompt = f"""仓库信息：
- 名称：{source['title']}
- 描述：{source['content']}
- Stars：{source['stars']}
- 语言：{source['language']}
- URL：{source['url']}

请分析并输出 JSON。"""

        try:
            result, usage = chat_json(prompt, system=system_prompt, node_name="analyze")
            tracker = accumulate_usage(tracker, usage, node_name="analyze_node")

            analyses.append({
                "source_url": source["url"],
                "category": result.get("category", "未分类"),
                "tags": result.get("tags", []),
                "summary": result.get("summary", ""),
                "key_points": result.get("key_points", []),
                "quality_score": result.get("quality_score", 0.5),
                "original_title": source["title"]
            })
        except Exception as e:
            print(f"[analyze_node] 分析失败 {source['url']}: {e}")
            # 降级处理
            analyses.append({
                "source_url": source["url"],
                "category": "未分类",
                "tags": [],
                "summary": source["content"][:50],
                "key_points": [],
                "quality_score": 0.3,
                "original_title": source["title"]
            })

    print(f"[analyze_node] 分析完成，共 {len(analyses)} 条结果")

    return {
        "analyses": analyses,
        "cost_tracker": tracker
    }


def organize_node(state: KBState) -> dict:
    """
    格式化与去重节点：过滤低分条目、去重、根据审核反馈修正

    返回: {"articles": list[dict], "cost_tracker": dict}
    """
    print("[organize_node] 开始格式化与去重...")

    analyses = state["analyses"]
    tracker = state["cost_tracker"]
    iteration = state.get("iteration", 0)
    feedback = state.get("review_feedback", "")

    # 1. 过滤低分条目
    filtered = [a for a in analyses if a["quality_score"] >= 0.6]
    print(f"[organize_node] 过滤后保留 {len(filtered)}/{len(analyses)} 条")

    # 2. 按 URL 去重
    seen_urls = set()
    deduplicated = []
    for item in filtered:
        url = item["source_url"]
        if url not in seen_urls:
            seen_urls.add(url)
            deduplicated.append(item)

    print(f"[organize_node] 去重后保留 {len(deduplicated)} 条")

    # 3. 如果有审核反馈，用 LLM 修正
    articles = []
    if iteration > 0 and feedback:
        print(f"[organize_node] 第 {iteration} 次迭代，根据反馈修正内容...")

        system_prompt = f"""你是内容修正专家。
审核反馈：
{feedback}

任务：根据反馈改进内容，输出 JSON：
{{
  "title": "改进后的标题",
  "summary": "改进后的摘要",
  "tags": ["改进后的标签"],
  "category": "改进后的分类"
}}"""

        for item in deduplicated:
            prompt = f"""原内容：
- 标题：{item['original_title']}
- 摘要：{item['summary']}
- 标签：{item['tags']}
- 分类：{item['category']}

请改进并输出 JSON。"""

            try:
                result, usage = chat_json(prompt, system=system_prompt, node_name="organize")
                tracker = accumulate_usage(tracker, usage, node_name="organize_node")

                articles.append({
                    "title": result.get("title", item["original_title"]),
                    "content": result.get("summary", item["summary"]),
                    "metadata": {
                        "category": result.get("category", item["category"]),
                        "tags": result.get("tags", item["tags"]),
                        "source_url": item["source_url"],
                        "quality_score": item["quality_score"]
                    },
                    "hash": hash(item["source_url"]),
                    "is_duplicate": False
                })
            except Exception as e:
                print(f"[organize_node] 修正失败: {e}")
                # 使用原内容
                articles.append({
                    "title": item["original_title"],
                    "content": item["summary"],
                    "metadata": {
                        "category": item["category"],
                        "tags": item["tags"],
                        "source_url": item["source_url"],
                        "quality_score": item["quality_score"]
                    },
                    "hash": hash(item["source_url"]),
                    "is_duplicate": False
                })
    else:
        # 首次处理，直接格式化
        for item in deduplicated:
            articles.append({
                "title": item["original_title"],
                "content": item["summary"],
                "metadata": {
                    "category": item["category"],
                    "tags": item["tags"],
                    "source_url": item["source_url"],
                    "quality_score": item["quality_score"]
                },
                "hash": hash(item["source_url"]),
                "is_duplicate": False
            })

    print(f"[organize_node] 格式化完成，共 {len(articles)} 条知识条目")

    # ★ 接入点 ⑤ · 写盘前对每条 article 做 PII 掩码
    masked_articles = []
    total_pii = 0
    for art in articles:
        for field in ("title", "content"):
            if field in art and isinstance(art[field], str):
                filtered, detections = filter_output(art[field], mask=True)
                art[field] = filtered
                total_pii += len(detections)
                if detections:
                    print(f"[Security] {art.get('hash', '?')} {field} 掩码 PII：{detections}")
        masked_articles.append(art)

    if total_pii > 0:
        print(f"[Security] organize 阶段共掩码 {total_pii} 处 PII")

    return {
        "articles": masked_articles,
        "cost_tracker": tracker
    }


def review_node(state: KBState) -> dict:
    """
    Supervisor 审核节点：四维度评分，iteration >= 2 强制通过

    返回: {"review_passed": bool, "review_feedback": str, "iteration": int, "cost_tracker": dict}
    """
    iteration = state.get("iteration", 0)
    tracker = state["cost_tracker"]

    print(f"[review_node] 开始审核（第 {iteration} 次迭代）...")
    print(f"[review_node] 当前 iteration = {iteration}")

    # ========== 测试代码：模拟审核循环 ==========
    # 前 2 次强制不通过，第 3 次通过

    if iteration == 0:
        # 第 1 次审核：不通过
        passed = False
        feedback = """## 第 1 次审核反馈

### 问题：
1. 摘要过于简短，缺少技术细节
2. 标签不够精准，建议添加更具体的技术栈标签
3. 分类需要更细化

### 改进建议：
- 扩充摘要内容，增加核心功能描述
- 补充技术栈相关标签（如：PyTorch、TensorFlow 等）
- 将"AI工具"细化为更具体的子分类
"""
        print(f"[review_node] 第 1 次审核 - 通过: {passed}")

    elif iteration == 1:
        # 第 2 次审核：不通过
        passed = False
        feedback = """## 第 2 次审核反馈

### 问题：
1. 标签仍然不够具体，需要更精准的领域标签
2. 部分摘要的语言风格不一致
3. 分类层级需要进一步优化

### 改进建议：
- 统一摘要的语言风格和长度
- 添加更多领域特定标签（如：NLP、CV、RL 等）
- 确保分类的一致性和准确性
"""
        print(f"[review_node] 第 2 次审核 - 通过: {passed}")

    else:
        # 第 3 次审核（iteration >= 2）：通过
        passed = True
        feedback = """## 第 3 次审核反馈

### 评估结果：
✓ 摘要质量：良好，内容充实且清晰
✓ 标签准确性：标签精准，覆盖全面
✓ 分类合理性：分类准确，层级清晰
✓ 一致性：风格统一，格式规范

### 总评：
已达最大迭代次数（3次），内容质量符合要求，审核通过。
"""
        print(f"[review_node] 第 3 次审核（已达最大迭代次数）- 通过: {passed}")

    print(f"[review_node] review_passed = {passed}")

    return {
        "review_passed": passed,
        "review_feedback": feedback,
        "iteration": iteration + 1,
        "cost_tracker": tracker
    }

    # ========== 原始 LLM 审核代码（已注释） ==========
    # articles = state["articles"]
    #
    # # 构建审核 prompt
    # system_prompt = """你是知识库质量审核专家。
    # 任务：评估知识条目质量，输出 JSON：
    # {
    #   "passed": true/false,
    #   "overall_score": 0.85,
    #   "feedback": "具体改进建议（Markdown 格式）",
    #   "scores": {
    #     "summary_quality": 0.9,
    #     "tag_accuracy": 0.8,
    #     "category_appropriateness": 0.85,
    #     "consistency": 0.85
    #   }
    # }
    #
    # 评分维度：
    # 1. summary_quality: 摘要是否清晰、准确、简洁
    # 2. tag_accuracy: 标签是否精准、相关
    # 3. category_appropriateness: 分类是否合理
    # 4. consistency: 多条目间风格是否一致
    #
    # 通过标准：overall_score >= 0.75"""
    #
    # # 准备审核内容摘要
    # content_summary = []
    # for i, article in enumerate(articles[:5], 1):  # 只审核前 5 条
    #     content_summary.append(f"""
    # ### 条目 {i}
    # - 标题：{article['title']}
    # - 摘要：{article['content']}
    # - 分类：{article['metadata']['category']}
    # - 标签：{', '.join(article['metadata']['tags'])}
    # """)
    #
    # prompt = f"""共 {len(articles)} 条知识条目，以下是前 5 条样本：
    # {''.join(content_summary)}
    #
    # 请评估质量并输出 JSON。"""
    #
    # try:
    #     result, usage = chat_json(prompt, system=system_prompt)
    #     tracker = accumulate_usage(tracker, usage, node_name="review_node")
    #
    #     passed = result.get("passed", False)
    #     feedback = result.get("feedback", "")
    #     overall_score = result.get("overall_score", 0.0)
    #
    #     print(f"[review_node] 审核完成 - 通过: {passed}, 评分: {overall_score:.2f}")
    #
    #     return {
    #         "review_passed": passed,
    #         "review_feedback": feedback,
    #         "iteration": iteration + 1,
    #         "cost_tracker": tracker
    #     }
    # except Exception as e:
    #     print(f"[review_node] 审核失败: {e}，默认通过")
    #     return {
    #         "review_passed": True,
    #         "review_feedback": f"审核异常（{e}），默认通过",
    #         "iteration": iteration + 1,
    #         "cost_tracker": tracker
    #     }


def save_node(state: KBState) -> dict:
    """
    保存节点：将 articles 写入 knowledge/articles/ 并更新索引

    返回: {"cost_tracker": dict}
    """
    print("[save_node] 开始保存知识条目...")

    articles = state["articles"]
    tracker = state["cost_tracker"]

    # 确保目录存在
    articles_dir = Path("knowledge/articles")
    articles_dir.mkdir(parents=True, exist_ok=True)

    # 保存每条知识条目
    saved_files = []
    for article in articles:
        # 生成文件名（使用 hash 避免重复）
        filename = f"{article['hash']}.json"
        filepath = articles_dir / filename

        # 添加时间戳
        article["saved_at"] = datetime.now().isoformat()

        # 写入文件
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(article, f, ensure_ascii=False, indent=2)

        saved_files.append(str(filepath))

    print(f"[save_node] 已保存 {len(saved_files)} 个文件")

    # 更新索引文件
    index_path = Path("knowledge/index.json")

    # 读取现有索引
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)
    else:
        index_data = {
            "total_articles": 0,
            "last_updated": "",
            "articles": []
        }

    # 添加新条目到索引
    existing_hashes = {a["hash"] for a in index_data["articles"]}
    for article in articles:
        if article["hash"] not in existing_hashes:
            index_data["articles"].append({
                "hash": article["hash"],
                "title": article["title"],
                "category": article["metadata"]["category"],
                "tags": article["metadata"]["tags"],
                "source_url": article["metadata"]["source_url"],
                "saved_at": article["saved_at"]
            })

    # 更新索引元数据
    index_data["total_articles"] = len(index_data["articles"])
    index_data["last_updated"] = datetime.now().isoformat()

    # 写入索引文件
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"[save_node] 索引已更新，总计 {index_data['total_articles']} 条")

    # 打印成本统计
    print(f"\n[save_node] Token 用量统计：")
    print(f"  总 Tokens: {tracker['total_tokens']}")
    print(f"  总成本: ${tracker['total_cost_usd']:.4f}")
    if "by_node" in tracker:
        print(f"  各节点用量:")
        for node, stats in tracker["by_node"].items():
            print(f"    - {node}: {stats['tokens']} tokens (${stats['cost']:.4f})")

    return {
        "cost_tracker": tracker
    }
