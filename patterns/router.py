#!/usr/bin/env python3
"""
Router Module - Two-layer intent classification with handler dispatch.

Layer 1: Keyword fast matching (zero LLM cost).
Layer 2: LLM classification fallback (ambiguous queries).

Intents:
    github_search   - Search GitHub repositories via API.
    knowledge_query - Search local knowledge base articles.
    general_chat    - Direct LLM conversation.

Usage:
    from patterns.router import route

    print(route("搜 github transformer 项目"))
    print(route("知识库里有没有关于 agent 的文章"))
    print(route("什么是 RAG"))
"""

from __future__ import annotations

import json
import logging
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.model_client import chat_with_retry

logger = logging.getLogger(__name__)

# ============================================================
# LLM adapter wrappers (compatible with expected workflows.model_client interface)
# ============================================================


def chat(
    messages: list[dict[str, str]], **kwargs: Any
) -> tuple[str, Any]:
    """Call LLM and return (text, usage) tuple.

    Args:
        messages: List of message dicts with 'role' and 'content'.
        **kwargs: Passed to chat_with_retry (temperature, max_tokens, etc.).

    Returns:
        Tuple of (response_text, usage_object).
    """
    resp = chat_with_retry(messages, **kwargs)
    return resp.content, resp.usage


def chat_json(
    messages: list[dict[str, str]], **kwargs: Any
) -> dict[str, Any]:
    """Call LLM and return parsed JSON response.

    Args:
        messages: List of message dicts with 'role' and 'content'.
        **kwargs: Passed to chat_with_retry.

    Returns:
        Parsed JSON dictionary.

    Raises:
        ValueError: If response cannot be parsed as JSON.
    """
    kwargs.setdefault("temperature", 0.1)
    kwargs.setdefault("max_tokens", 500)
    text, _ = chat(messages, **kwargs)

    json_match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL
    )
    if json_match:
        return json.loads(json_match.group(1))

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))

    raise ValueError(
        f"Failed to parse JSON from LLM response: {text[:200]}"
    )


# ============================================================
# Layer 1: Keyword-based classification (zero-cost)
# ============================================================

KEYWORDS: dict[str, list[str]] = {
    "github_search": [
        "github", "仓库", "repo", "repository", "开源项目",
        "star", "stars", "github.com", "github 搜索",
        "搜 github", "搜一下 github", "在 github 上",
        "github 项目", "github 开源",
    ],
    "knowledge_query": [
        "知识库", "本地知识", "本地文章", "之前存的",
        "已保存", "存档", "之前收集", "之前抓取",
        "知识库中", "本地检索", "本地搜索",
    ],
}


def _classify_keywords(query: str) -> str | None:
    """Layer 1: keyword-based intent classification.

    Args:
        query: User query string.

    Returns:
        Intent name if a keyword matches, None otherwise.
    """
    query_lower = query.lower()
    for intent, keywords in KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                logger.info("Keyword matched: '%s' -> %s", kw, intent)
                return intent
    return None


# ============================================================
# Layer 2: LLM-based classification (fallback)
# ============================================================

CLASSIFY_PROMPT = (
    "Classify the user query into exactly one intent.\n"
    "\n"
    "Intents:\n"
    "- github_search: User wants to search GitHub for repositories or code.\n"
    "- knowledge_query: User wants to search a local knowledge base of saved articles.\n"
    "- general_chat: Conversation, factual questions, explanations, or anything else.\n"
    "\n"
    "User query: {query}\n"
    "\n"
    'Respond with JSON only: {{"intent": "<intent>", "confidence": 0.0}}'
)


def _classify_llm(query: str) -> str:
    """Layer 2: LLM-based intent classification.

    Args:
        query: User query string.

    Returns:
        Intent name (github_search, knowledge_query, or general_chat).
    """
    messages = [
        {"role": "user", "content": CLASSIFY_PROMPT.format(query=query)}
    ]
    result = chat_json(messages)
    intent = result.get("intent", "general_chat")
    confidence = result.get("confidence", 0)
    logger.info(
        "LLM classified: %s (confidence=%.2f)", intent, confidence
    )
    return intent


# ============================================================
# Two-layer router
# ============================================================


def _classify(query: str) -> str:
    """Two-layer intent classification.

    Layer 1: Fast keyword match (zero LLM cost).
    Layer 2: LLM classification fallback.

    Args:
        query: User query string.

    Returns:
        Intent name.
    """
    intent = _classify_keywords(query)
    if intent is not None:
        return intent
    return _classify_llm(query)


# ============================================================
# Handler: github_search
# ============================================================

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

_SEARCH_PREFIXES = [
    "github", "搜 github", "github search", "github 搜索",
    "在 github 上", "搜", "搜索",
]


def _handle_github_search(query: str) -> str:
    """Search GitHub repositories via the Search API.

    Args:
        query: User query string containing search terms.

    Returns:
        Formatted search results string.
    """
    search_terms = query
    for prefix in _SEARCH_PREFIXES:
        if search_terms.lower().startswith(prefix):
            search_terms = search_terms[len(prefix):].strip(" ,:，： ")
            break

    if not search_terms or len(search_terms) < 2:
        return "Please provide more specific GitHub search terms."

    encoded = urllib.parse.quote(search_terms)
    url = (
        f"{GITHUB_SEARCH_URL}"
        f"?q={encoded}&sort=stars&order=desc&per_page=5"
    )

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AiKnowledgeBase/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return f"GitHub API error: HTTP {e.code}"
    except urllib.error.URLError as e:
        return f"GitHub API unreachable: {e.reason}"

    items = data.get("items", [])
    if not items:
        return f'No GitHub repositories found for "{search_terms}".'

    total = data.get("total_count", 0)
    lines = [
        f'GitHub 搜索 "{search_terms}" (共 {total} 个结果):'
    ]
    for i, item in enumerate(items, 1):
        name = item["full_name"]
        stars = item.get("stargazers_count", 0)
        desc = (item.get("description") or "").strip()
        desc = desc[:80] + "..." if len(desc) > 80 else desc
        repo_url = item["html_url"]
        lines.append(f"  {i}. {name}  {stars} stars")
        if desc:
            lines.append(f"     {desc}")
        lines.append(f"     {repo_url}")

    return "\n".join(lines)


# ============================================================
# Handler: knowledge_query
# ============================================================

ARTICLE_DIR = Path("knowledge/articles")


def _load_articles() -> list[dict[str, Any]]:
    """Load all article JSON files from the knowledge base.

    Returns:
        List of article dictionaries.
    """
    articles: list[dict[str, Any]] = []
    if not ARTICLE_DIR.exists():
        return articles

    for filepath in sorted(ARTICLE_DIR.glob("*.json")):
        if filepath.name == "index.json":
            continue
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                articles.append(data)
            elif isinstance(data, list):
                articles.extend(data)
        except (json.JSONDecodeError, IOError):
            continue

    return articles


def _handle_knowledge_query(query: str) -> str:
    """Search local knowledge base articles by keyword relevance.

    Args:
        query: User query string.

    Returns:
        Formatted search results from local articles.
    """
    articles = _load_articles()
    if not articles:
        return "Knowledge base is empty. Run the collection pipeline first."

    query_lower = query.lower()
    query_terms = {t for t in query_lower.split() if len(t) >= 1}

    scored: list[tuple[int, dict[str, Any]]] = []
    for article in articles:
        title = (article.get("title", "") or "").lower()
        summary = (article.get("summary", "") or "").lower()
        tags_text = " ".join(article.get("tags", [])).lower()
        combined = f"{title} {summary} {tags_text}"

        score = 0
        for term in query_terms:
            if term in title:
                score += 5
            elif term in tags_text:
                score += 3
            elif term in summary:
                score += 2
            elif term in combined:
                score += 1

        if score > 0:
            scored.append((score, article))

    if not scored:
        for article in articles:
            title = (article.get("title", "") or "").lower()
            summary = (article.get("summary", "") or "").lower()
            combined = f"{title} {summary}"
            if any(
                ch in combined
                for ch in query_lower
                if ch.strip() and not ch.isascii()
            ):
                scored.append((1, article))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:5]

    if not top:
        return f'No articles found matching "{query}".'

    lines = [f'知识库检索 "{query}" ({len(top)} 条结果):']
    for i, (score, article) in enumerate(top, 1):
        title = article.get("title", "Untitled")
        summary = article.get("summary", "")
        summary = summary[:100] + "..." if len(summary) > 100 else summary
        source_url = article.get("source_url", "")
        tags = ", ".join(article.get("tags", []))

        lines.append(f"  {i}. {title}")
        if summary:
            lines.append(f"     {summary}")
        if tags:
            lines.append(f"     标签: {tags}")
        if source_url:
            lines.append(f"     {source_url}")

    return "\n".join(lines)


# ============================================================
# Handler: general_chat
# ============================================================

SYSTEM_GENERAL = (
    "You are a helpful AI assistant. "
    "Answer concisely and accurately. "
    "Keep responses under 500 characters unless asked for detail."
)


def _handle_general_chat(query: str) -> str:
    """Handle general conversation via LLM.

    Args:
        query: User query string.

    Returns:
        LLM response text.
    """
    messages = [
        {"role": "system", "content": SYSTEM_GENERAL},
        {"role": "user", "content": query},
    ]
    text, usage = chat(messages, temperature=0.7, max_tokens=500)
    logger.info(
        "General chat: %d prompt + %d completion = %d tokens",
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.total_tokens,
    )
    return text


# ============================================================
# Handler registry
# ============================================================

_HANDLERS: dict[str, Any] = {
    "github_search": _handle_github_search,
    "knowledge_query": _handle_knowledge_query,
    "general_chat": _handle_general_chat,
}


# ============================================================
# Public entry point
# ============================================================


def route(query: str) -> str:
    """Route a user query to the appropriate handler.

    Two-layer intent classification:
        1. Keyword fast match (no LLM cost).
        2. LLM classification fallback for ambiguous queries.

    Args:
        query: User query string.

    Returns:
        Handler response string.
    """
    if not query or not query.strip():
        return "Please enter a query."

    intent = _classify(query.strip())
    handler = _HANDLERS.get(intent, _handle_general_chat)
    return handler(query.strip())


# ============================================================
# Test entry point
# ============================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    test_cases = [
        ("L1-GitHub", "搜 github transformer 项目"),
        ("L1-Knowledge", "知识库里有没有关于 agent 的文章"),
        ("L1-Chat", "你好，今天天气怎么样"),
        ("L2-GitHub-KW", "帮我找一下大模型相关的开源项目"),
        ("L2-Knowledge", "之前是不是存过关于 RAG 的内容"),
        ("L2-Chat", "什么是 Transformer 架构"),
        ("L1-Chinese-Space", "在 github 上搜索 大模型 工具"),
    ]

    passed = 0
    for label, q in test_cases:
        print(f"\n{'=' * 60}")
        print(f"[{label}] Query: {q}")
        print(f"{'=' * 60}")
        try:
            result = route(q)
            print(result)
            passed += 1
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\n{'=' * 60}")
    print(f"Test complete: {passed}/{len(test_cases)} passed")
    print(f"{'=' * 60}")

    if "--interactive" in sys.argv:
        print("\nInteractive mode. Type 'quit' to exit.\n")
        while True:
            try:
                user_input = input("> ").strip()
                if user_input.lower() in ("quit", "exit", "q"):
                    break
                if not user_input:
                    continue
                print(route(user_input))
                print()
            except (KeyboardInterrupt, EOFError):
                print()
                break
