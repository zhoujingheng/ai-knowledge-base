#!/usr/bin/env python3
"""
Supervisor Module - Quality-controlled task analysis with retry loop.

Worker Agent generates an analysis report in JSON.
Supervisor Agent reviews quality on accuracy, depth, and format.
Failed reviews trigger retries with feedback (up to max_retries rounds).

Usage:
    from patterns.supervisor import supervisor

    result = supervisor("Analyze the pros and cons of RAG vs fine-tuning")
    print(result["output"]["summary"])
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.model_client import chat_with_retry

logger = logging.getLogger(__name__)

# ============================================================
# LLM adapter (compatible with expected workflows.model_client interface)
# ============================================================


def chat(
    messages: list[dict[str, str]], **kwargs: Any
) -> tuple[str, Any]:
    """Call LLM and return (text, usage) tuple.

    Args:
        messages: List of message dicts with 'role' and 'content'.
        **kwargs: Passed to chat_with_retry.

    Returns:
        Tuple of (response_text, usage_object).
    """
    resp = chat_with_retry(messages, **kwargs)
    return resp.content, resp.usage


# ============================================================
# JSON extraction helper
# ============================================================


def _extract_json(text: str) -> dict[str, Any]:
    """Extract and parse JSON from LLM response text.

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed JSON dictionary.

    Raises:
        ValueError: If no valid JSON found.
    """
    json_match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL
    )
    if json_match:
        return json.loads(json_match.group(1))

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))

    raise ValueError(f"No JSON found in response: {text[:200]}")


# ============================================================
# Worker Agent
# ============================================================

WORKER_SYSTEM = (
    "You are an expert AI analysis agent. "
    "Analyze the given task and produce a structured JSON report. "
    "Be thorough, accurate, and well-organized. "
    "Respond with valid JSON only."
)


def _worker(task: str, feedback: str | None = None) -> dict[str, Any]:
    """Worker Agent: analyze a task and return a JSON report.

    Args:
        task: The analysis task description.
        feedback: Optional feedback from the supervisor for improvement.

    Returns:
        JSON analysis report dict with keys: title, summary, key_points,
        analysis, conclusion.
    """
    user_content = f"Task: {task}\n\n"
    if feedback:
        user_content += (
            f"Previous attempt was rejected. Feedback: {feedback}\n\n"
            f"Please address the feedback and produce an improved report."
        )
    user_content += (
        "Output format (JSON only):\n"
        "{\n"
        '  "title": "brief descriptive title",\n'
        '  "summary": "concise 50-200 word summary",\n'
        '  "key_points": ["point 1", "point 2", "point 3"],\n'
        '  "analysis": "detailed analysis section",\n'
        '  "conclusion": "final takeaway"\n'
        "}"
    )

    messages = [
        {"role": "system", "content": WORKER_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    text, usage = chat(messages, temperature=0.3, max_tokens=1200)
    logger.info(
        "Worker: %d prompt + %d completion = %d tokens",
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
    )

    try:
        return _extract_json(text)
    except (ValueError, json.JSONDecodeError) as e:
        logger.error("Worker JSON parse failed: %s", e)
        return {
            "title": task[:80],
            "summary": text[:200],
            "key_points": [],
            "analysis": text,
            "conclusion": "",
        }


# ============================================================
# Supervisor Agent
# ============================================================

SUPERVISOR_SYSTEM = (
    "You are a strict quality control supervisor. "
    "Review analysis reports against their original task. "
    "Evaluate on three dimensions (1-10 each): "
    "accuracy (factual correctness), "
    "depth (thoroughness and insight), "
    "format (structure and clarity). "
    "Respond with valid JSON only."
)


def _supervisor_review(worker_output: dict[str, Any], task: str) -> dict[str, Any]:
    """Supervisor Agent: review worker output quality.

    Args:
        worker_output: The worker agent's JSON analysis report.
        task: The original task description.

    Returns:
        Review dict with keys: accuracy, depth, format, score, passed, feedback.
    """
    report_text = json.dumps(worker_output, ensure_ascii=False, indent=2)

    user_content = (
        f"Original Task: {task}\n\n"
        f"Analysis Report to Review:\n{report_text}\n\n"
        "Evaluate accuracy (1-10), depth (1-10), and format (1-10). "
        "Score is the average of the three dimensions, rounded to integer. "
        "Passed is true if score >= 7.\n\n"
        "Output JSON only:\n"
        "{\n"
        '  "accuracy": <1-10>,\n'
        '  "depth": <1-10>,\n'
        '  "format": <1-10>,\n'
        '  "score": <average rounded to int>,\n'
        '  "passed": <true/false>,\n'
        '  "feedback": "<specific improvement suggestions, or empty if passed>"\n'
        "}"
    )

    messages = [
        {"role": "system", "content": SUPERVISOR_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    text, usage = chat(messages, temperature=0.2, max_tokens=500)
    logger.info(
        "Supervisor: %d prompt + %d completion = %d tokens",
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
    )

    try:
        review = _extract_json(text)
        review.setdefault("accuracy", 5)
        review.setdefault("depth", 5)
        review.setdefault("format", 5)
        review.setdefault("score", 5)
        review.setdefault("passed", False)
        review.setdefault("feedback", "")
        return review
    except (ValueError, json.JSONDecodeError) as e:
        logger.error("Supervisor JSON parse failed: %s", e)
        return {
            "accuracy": 5,
            "depth": 5,
            "format": 5,
            "score": 5,
            "passed": False,
            "feedback": f"Failed to parse review: {e}",
        }


# ============================================================
# Main supervisor loop
# ============================================================


def supervisor(task: str, max_retries: int = 3) -> dict[str, Any]:
    """Run the supervisor quality-control loop.

    Worker generates an analysis report. Supervisor reviews it.
    If score < 7, the worker retries with feedback, up to max_retries
    rounds. If all rounds fail, returns best effort with a warning.

    Args:
        task: The analysis task description.
        max_retries: Maximum retry rounds (default 3).

    Returns:
        Dict with keys:
            output: Final worker JSON report.
            attempts: Number of attempts taken (1 to max_retries + 1).
            final_score: Last supervisor score.
            scores: List of scores from each review round.
            feedback_history: List of supervisor feedback strings.
            warning: Warning message if max retries exceeded, else None.
    """
    logger.info("Supervisor loop started. Task: %s", task[:60])
    feedback: str | None = None
    scores: list[int] = []
    feedback_history: list[str] = []

    for attempt in range(1, max_retries + 2):
        logger.info("--- Attempt %d ---", attempt)

        worker_output = _worker(task, feedback)
        review = _supervisor_review(worker_output, task)

        accuracy = review.get("accuracy", 0)
        depth = review.get("depth", 0)
        fmt_score = review.get("format", 0)
        total = review.get("score", 0)
        passed = review.get("passed", False)

        logger.info(
            "Review: accuracy=%d depth=%d format=%d score=%d passed=%s",
            accuracy, depth, fmt_score, total, passed,
        )
        scores.append(total)

        if passed and total >= 7:
            logger.info(
                "PASSED on attempt %d with score %d", attempt, total
            )
            return {
                "output": worker_output,
                "attempts": attempt,
                "final_score": total,
                "scores": scores,
                "feedback_history": feedback_history,
            }

        fb = review.get("feedback", "").strip()
        if not fb:
            fb = (
                f"Improve on: "
                f"{'accuracy' if accuracy < 7 else ''}"
                f"{', ' if accuracy < 7 and depth < 7 else ''}"
                f"{'depth' if depth < 7 else ''}"
                f"{', ' if (accuracy < 7 or depth < 7) and fmt_score < 7 else ''}"
                f"{'format' if fmt_score < 7 else ''}"
                f". Score was {total}/10, need >=7."
            )
        feedback_history.append(fb)
        feedback = fb

        if attempt > max_retries:
            logger.warning(
                "Exceeded %d retry rounds, returning best effort", max_retries
            )

    # Should not reach here, but safety net
    final_output = _worker(task, feedback)
    return {
        "output": final_output,
        "attempts": max_retries + 1,
        "final_score": scores[-1] if scores else 0,
        "scores": scores,
        "feedback_history": feedback_history,
        "warning": (
            f"Exceeded maximum retries ({max_retries}). "
            "Returning best effort result."
        ),
    }


# ============================================================
# Test entry point
# ============================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    tasks = [
        "Explain the differences between RAG and fine-tuning for LLMs. "
        "Include pros, cons, and when to use each approach.",

        "Analyze the role of prompt engineering in modern AI applications. "
        "Cover few-shot, chain-of-thought, and system prompts.",
    ]

    for i, task in enumerate(tasks):
        print(f"\n{'=' * 60}")
        print(f"Task {i + 1}: {task[:60]}...")
        print(f"{'=' * 60}")

        result = supervisor(task, max_retries=3)

        output = result["output"]
        print(f"\n  Title:      {output.get('title', 'N/A')}")
        print(f"  Attempts:   {result['attempts']}")
        print(f"  Scores:     {result['scores']}")
        print(f"  Final:      {result['final_score']}/10")
        if result.get("warning"):
            print(f"  WARNING:    {result['warning']}")

        summary = output.get("summary", "")
        summary = summary[:150] + "..." if len(summary) > 150 else summary
        print(f"  Summary:    {summary}")

        feedbacks = result.get("feedback_history", [])
        if feedbacks:
            for idx, fb in enumerate(feedbacks):
                fb_short = fb[:100] + "..." if len(fb) > 100 else fb
                print(f"  Feedback #{idx + 1}: {fb_short}")

    print(f"\n{'=' * 60}")
    print("All test tasks completed.")
    print(f"{'=' * 60}")
