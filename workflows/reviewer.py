"""
Reviewer 审核节点

对 LLM 分析结果（analyses）进行质量审核，五维度评分
"""

from workflows.state import KBState
from workflows.model_client import chat_json, accumulate_usage


def review_node(state: KBState) -> dict:
    """
    Reviewer 审核节点：对 analyses 进行五维度质量评分

    评分维度（1-10分）：
    - summary_quality (摘要质量): 25%
    - technical_depth (技术深度): 25%
    - relevance (相关性): 20%
    - originality (原创性): 15%
    - formatting (格式规范): 15%

    通过标准：加权总分 >= 7.0

    返回: {"review_passed": bool, "review_feedback": str, "iteration": int, "cost_tracker": dict}
    """
    iteration = state.get("iteration", 0)
    tracker = state["cost_tracker"]
    analyses = state.get("analyses", [])

    print(f"[review_node] 开始审核（第 {iteration} 次迭代）...")
    print(f"[review_node] 当前 iteration = {iteration}")
    print(f"[review_node] 待审核 analyses 数量: {len(analyses)}")

    # 强制通过条件：已达最大迭代次数
    if iteration >= 2:
        print("[review_node] 已达最大迭代次数（3次），强制通过")
        return {
            "review_passed": True,
            "review_feedback": "已达最大迭代次数（3次），强制通过审核",
            "iteration": iteration + 1,
            "cost_tracker": tracker
        }

    # 边界情况：没有 analyses
    if not analyses:
        print("[review_node] 警告：没有 analyses 数据，默认通过")
        return {
            "review_passed": True,
            "review_feedback": "没有待审核的分析结果",
            "iteration": iteration + 1,
            "cost_tracker": tracker
        }

    # 构建审核 prompt
    system_prompt = """你是知识库内容质量审核专家。

任务：评估 LLM 分析结果的质量，输出 JSON 格式评分。

输出格式：
{
  "scores": {
    "summary_quality": 8,
    "technical_depth": 7,
    "relevance": 9,
    "originality": 6,
    "formatting": 8
  },
  "feedback": "具体改进建议（Markdown 格式）"
}

评分维度（1-10分）：
1. summary_quality（摘要质量）：摘要是否清晰、准确、简洁，能否快速传达核心信息
2. technical_depth（技术深度）：是否包含足够的技术细节，标签和分类是否专业
3. relevance（相关性）：内容是否与 AI/机器学习领域高度相关
4. originality（原创性）：是否提供了独特的见解或价值，而非泛泛而谈
5. formatting（格式规范）：结构是否规范，标签格式是否统一

评分标准：
- 9-10分：优秀，无明显问题
- 7-8分：良好，有小幅改进空间
- 5-6分：及格，需要明显改进
- 1-4分：不合格，存在严重问题

注意：只输出 JSON，不要添加其他文字。"""

    # 准备审核内容（只审核前 5 条）
    sample_analyses = analyses[:5]
    content_summary = []

    for i, analysis in enumerate(sample_analyses, 1):
        content_summary.append(f"""
### 分析结果 {i}
- 来源：{analysis.get('source_url', 'N/A')}
- 标题：{analysis.get('original_title', 'N/A')}
- 分类：{analysis.get('category', 'N/A')}
- 标签：{', '.join(analysis.get('tags', []))}
- 摘要：{analysis.get('summary', 'N/A')}
- 要点：{'; '.join(analysis.get('key_points', []))}
- 质量评分：{analysis.get('quality_score', 0):.2f}
""")

    prompt = f"""共 {len(analyses)} 条分析结果，以下是前 {len(sample_analyses)} 条样本：
{''.join(content_summary)}

请对这批分析结果进行质量评估，输出 JSON 格式评分。"""

    # 调用 LLM 进行审核
    try:
        result, usage = chat_json(prompt, system=system_prompt, temperature=0.1)
        tracker = accumulate_usage(tracker, usage, node_name="review_node")

        # 提取评分
        scores = result.get("scores", {})
        feedback = result.get("feedback", "")

        # 验证评分完整性
        required_dimensions = [
            "summary_quality",
            "technical_depth",
            "relevance",
            "originality",
            "formatting"
        ]

        missing_dimensions = [d for d in required_dimensions if d not in scores]
        if missing_dimensions:
            print(f"[review_node] 警告：缺少评分维度 {missing_dimensions}，使用默认值 5")
            for dim in missing_dimensions:
                scores[dim] = 5

        # 权重配置
        weights = {
            "summary_quality": 0.25,
            "technical_depth": 0.25,
            "relevance": 0.20,
            "originality": 0.15,
            "formatting": 0.15
        }

        # 手动计算加权总分（不信任模型算术）
        weighted_score = 0.0
        for dimension, weight in weights.items():
            score = scores.get(dimension, 5)  # 默认 5 分
            # 确保分数在 1-10 范围内
            score = max(1, min(10, score))
            weighted_score += score * weight

        # 判断是否通过
        passed = weighted_score >= 7.0

        # 构建详细反馈
        detailed_feedback = f"""## 审核结果（第 {iteration + 1} 次）

### 评分详情
- 摘要质量 (25%): {scores.get('summary_quality', 5)}/10
- 技术深度 (25%): {scores.get('technical_depth', 5)}/10
- 相关性 (20%): {scores.get('relevance', 5)}/10
- 原创性 (15%): {scores.get('originality', 5)}/10
- 格式规范 (15%): {scores.get('formatting', 5)}/10

**加权总分**: {weighted_score:.2f}/10 {'✓ 通过' if passed else '✗ 未通过'}

### 审核意见
{feedback}
"""

        print(f"[review_node] 审核完成 - 加权总分: {weighted_score:.2f}, 通过: {passed}")
        print(f"[review_node] 各维度评分: {scores}")

        return {
            "review_passed": passed,
            "review_feedback": detailed_feedback,
            "iteration": iteration + 1,
            "cost_tracker": tracker
        }

    except Exception as e:
        # LLM 调用失败时自动通过（不阻塞流程）
        print(f"[review_node] 审核失败: {e}，自动通过以避免阻塞流程")

        fallback_feedback = f"""## 审核异常（第 {iteration + 1} 次）

审核过程中发生异常：{str(e)}

为避免阻塞流程，自动通过审核。建议人工复查分析结果质量。
"""

        return {
            "review_passed": True,
            "review_feedback": fallback_feedback,
            "iteration": iteration + 1,
            "cost_tracker": tracker
        }
