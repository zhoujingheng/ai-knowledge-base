"""
Reviser 修订节点

根据审核反馈改进 analyses 内容
"""

from workflows.state import KBState
from workflows.model_client import chat_json, accumulate_usage


def revise_node(state: KBState) -> dict:
    """
    Reviser 修订节点：根据审核反馈改进 analyses

    读取 state["analyses"] 和 state["review_feedback"]，
    将反馈注入 prompt，调用 LLM 返回改进后的 analyses

    Args:
        state: 工作流状态

    Returns:
        {"analyses": improved_analyses, "cost_tracker": tracker}
        如果 analyses 或 feedback 为空，返回 {}（跳过修订）
    """
    analyses = state.get("analyses", [])
    feedback = state.get("review_feedback", "")
    tracker = state["cost_tracker"]
    iteration = state.get("iteration", 0)

    print(f"[revise_node] 开始修订（第 {iteration} 次迭代）...")
    print(f"[revise_node] 待修订 analyses 数量: {len(analyses)}")

    # 边界情况：没有 analyses 或 feedback，跳过修订
    if not analyses:
        print("[revise_node] 警告：没有 analyses 数据，跳过修订")
        return {}

    if not feedback or not feedback.strip():
        print("[revise_node] 警告：没有审核反馈，跳过修订")
        return {}

    # 构建修订 prompt
    system_prompt = """你是知识库内容修订专家。

任务：根据审核反馈改进分析结果，输出改进后的 JSON 列表。

输出格式：
{
  "analyses": [
    {
      "source_url": "原始URL",
      "original_title": "原始标题",
      "category": "改进后的分类",
      "tags": ["改进后的标签1", "标签2", "标签3"],
      "summary": "改进后的摘要（50-100字）",
      "key_points": ["改进后的要点1", "要点2", "要点3"],
      "quality_score": 0.85
    }
  ]
}

修订原则：
1. **摘要质量**：扩充摘要内容，增加技术细节和核心功能描述，确保清晰、准确、简洁
2. **技术深度**：补充具体技术栈标签（如 PyTorch、TensorFlow、BERT 等），细化分类
3. **相关性**：确保内容与 AI/机器学习领域高度相关，突出技术价值
4. **原创性**：挖掘项目的独特价值和创新点，避免泛泛而谈
5. **格式规范**：统一标签格式（首字母大写），确保结构一致

注意：
- 保持 source_url 和 original_title 不变
- quality_score 根据改进程度调整（0.6-1.0）
- 只输出 JSON，不要添加其他文字"""

    # 准备修订内容
    analyses_summary = []
    for i, analysis in enumerate(analyses, 1):
        analyses_summary.append({
            "index": i,
            "source_url": analysis.get("source_url", ""),
            "original_title": analysis.get("original_title", ""),
            "category": analysis.get("category", ""),
            "tags": analysis.get("tags", []),
            "summary": analysis.get("summary", ""),
            "key_points": analysis.get("key_points", []),
            "quality_score": analysis.get("quality_score", 0.5)
        })

    prompt = f"""## 审核反馈
{feedback}

## 待修订的分析结果
共 {len(analyses)} 条，详情如下：

```json
{analyses_summary}
```

请根据审核反馈改进这些分析结果，输出改进后的 JSON。"""

    # 调用 LLM 进行修订
    try:
        print(f"[revise_node] 调用 LLM 修订 {len(analyses)} 条 analyses...")

        result, usage = chat_json(prompt, system=system_prompt, temperature=0.4, node_name="revise")
        tracker = accumulate_usage(tracker, usage, node_name="revise_node")

        # 提取改进后的 analyses
        improved_analyses = result.get("analyses", [])

        if not improved_analyses:
            print("[revise_node] 警告：LLM 返回空列表，使用原始 analyses")
            return {}

        # 验证数据完整性
        valid_analyses = []
        for analysis in improved_analyses:
            # 确保必需字段存在
            if not analysis.get("source_url") or not analysis.get("summary"):
                print(f"[revise_node] 警告：跳过不完整的分析结果 {analysis.get('source_url', 'N/A')}")
                continue

            # 确保字段类型正确
            if not isinstance(analysis.get("tags", []), list):
                analysis["tags"] = []
            if not isinstance(analysis.get("key_points", []), list):
                analysis["key_points"] = []

            # 确保 quality_score 在合理范围内
            score = analysis.get("quality_score", 0.7)
            analysis["quality_score"] = max(0.0, min(1.0, score))

            valid_analyses.append(analysis)

        if not valid_analyses:
            print("[revise_node] 错误：所有改进结果都不完整，使用原始 analyses")
            return {}

        print(f"[revise_node] 修订完成，改进了 {len(valid_analyses)} 条 analyses")

        # 打印改进示例
        if valid_analyses:
            sample = valid_analyses[0]
            print(f"[revise_node] 示例 - 标题: {sample.get('original_title', 'N/A')}")
            print(f"[revise_node] 示例 - 分类: {sample.get('category', 'N/A')}")
            print(f"[revise_node] 示例 - 标签数: {len(sample.get('tags', []))}")
            print(f"[revise_node] 示例 - 摘要长度: {len(sample.get('summary', ''))} 字符")

        return {
            "analyses": valid_analyses,
            "cost_tracker": tracker
        }

    except Exception as e:
        # LLM 调用失败时返回空（保持原 analyses 不变）
        print(f"[revise_node] 修订失败: {e}，保持原 analyses 不变")
        import traceback
        traceback.print_exc()
        return {}
