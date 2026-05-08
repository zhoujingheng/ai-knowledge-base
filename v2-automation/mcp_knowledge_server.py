#!/usr/bin/env python3
"""
MCP Knowledge Server

Provides search and retrieval capabilities for the local knowledge base
via the Model Context Protocol (MCP).

Usage:
    python mcp_knowledge_server.py

Protocol: JSON-RPC 2.0 over stdio
"""

import json
import os
import sys
from pathlib import Path
from typing import Any


class KnowledgeBase:
    """Manages the local knowledge base."""

    def __init__(self, articles_dir: str = "knowledge/articles"):
        self.articles_dir = Path(articles_dir)
        self.articles: list[dict[str, Any]] = []
        self._load_articles()

    def _load_articles(self) -> None:
        """Load all JSON articles from the knowledge directory."""
        self.articles = []
        if not self.articles_dir.exists():
            return

        for json_file in self.articles_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.articles.extend(data)
                    else:
                        self.articles.append(data)
            except (json.JSONDecodeError, IOError):
                continue

    def search_articles(self, keyword: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search articles by keyword in title and summary."""
        keyword_lower = keyword.lower()
        results = []

        for article in self.articles:
            title = article.get("title", "").lower()
            summary = article.get("summary", "").lower()

            if keyword_lower in title or keyword_lower in summary:
                results.append({
                    "id": article.get("id"),
                    "title": article.get("title"),
                    "summary": article.get("summary"),
                    "source": article.get("source"),
                    "tags": article.get("tags", []),
                    "score": article.get("score"),
                })

        return results[:limit]

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get full article content by ID."""
        for article in self.articles:
            if article.get("id") == article_id:
                return article
        return None

    def get_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        total = len(self.articles)
        sources: dict[str, int] = {}
        tags: dict[str, int] = {}

        for article in self.articles:
            # Count sources
            source = article.get("source", "unknown")
            sources[source] = sources.get(source, 0) + 1

            # Count tags
            for tag in article.get("tags", []):
                tags[tag] = tags.get(tag, 0) + 1

        # Get top 10 tags
        top_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_articles": total,
            "sources": sources,
            "top_tags": [{"tag": tag, "count": count} for tag, count in top_tags],
        }


class MCPServer:
    """MCP Server implementation using JSON-RPC 2.0 over stdio."""

    def __init__(self):
        self.kb = KnowledgeBase()
        self.server_info = {
            "name": "knowledge-server",
            "version": "1.0.0",
        }

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a JSON-RPC 2.0 request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "tools/list":
                result = self._handle_tools_list()
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            else:
                return self._error_response(request_id, -32601, f"Method not found: {method}")

            return self._success_response(request_id, result)

        except Exception as e:
            return self._error_response(request_id, -32603, str(e))

    def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": self.server_info,
            "capabilities": {
                "tools": {}
            }
        }

    def _handle_tools_list(self) -> dict[str, Any]:
        """Handle tools/list request."""
        return {
            "tools": [
                {
                    "name": "search_articles",
                    "description": "Search articles by keyword in title and summary",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "Search keyword"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results",
                                "default": 5
                            }
                        },
                        "required": ["keyword"]
                    }
                },
                {
                    "name": "get_article",
                    "description": "Get full article content by ID",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "article_id": {
                                "type": "string",
                                "description": "Article ID"
                            }
                        },
                        "required": ["article_id"]
                    }
                },
                {
                    "name": "knowledge_stats",
                    "description": "Get knowledge base statistics (total articles, sources, top tags)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                }
            ]
        }

    def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "search_articles":
            keyword = arguments.get("keyword")
            limit = arguments.get("limit", 5)
            results = self.kb.search_articles(keyword, limit)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(results, ensure_ascii=False, indent=2)
                    }
                ]
            }

        elif tool_name == "get_article":
            article_id = arguments.get("article_id")
            article = self.kb.get_article(article_id)
            if article:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(article, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Article not found: {article_id}"
                        }
                    ],
                    "isError": True
                }

        elif tool_name == "knowledge_stats":
            stats = self.kb.get_stats()
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(stats, ensure_ascii=False, indent=2)
                    }
                ]
            }

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _success_response(self, request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        """Create a successful JSON-RPC response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }

    def _error_response(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        """Create an error JSON-RPC response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }

    def _read_message(self) -> dict[str, Any] | None:
        """Read a single JSON-RPC message from stdin using Content-Length framing.

        Uses os.read() for unbuffered I/O to avoid Windows pipe blocking issues.

        Returns:
            Parsed message dict, or None if input stream ends.
        """
        fd = sys.stdin.fileno()
        header_bytes = b""
        separator = b"\r\n\r\n"

        while separator not in header_bytes:
            ch = os.read(fd, 1)
            if not ch:
                return None
            header_bytes += ch

        header_str = header_bytes.decode("utf-8")
        content_length = None

        for line in header_str.split("\r\n"):
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("content-length:"):
                try:
                    content_length = int(line.split(":", 1)[1].strip())
                except ValueError:
                    raise ValueError(f"Invalid Content-Length header: {line}")

        if content_length is None:
            return None

        body = os.read(fd, content_length)
        return json.loads(body.decode("utf-8"))

    def _send_message(self, message: dict[str, Any]) -> None:
        """Send a JSON-RPC message to stdout with Content-Length framing.

        Args:
            message: The JSON-RPC message to send.
        """
        body = json.dumps(message, ensure_ascii=False)
        content = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n{body}"
        sys.stdout.write(content)
        sys.stdout.flush()

    def run(self) -> None:
        """Run the MCP server on stdio with Content-Length framing."""
        while True:
            try:
                request = self._read_message()
                if request is None:
                    break

                response = self.handle_request(request)

                # Notifications (no id) do not receive a response
                if "id" not in request:
                    continue

                self._send_message(response)

            except (json.JSONDecodeError, ValueError) as e:
                error_response = self._error_response(
                    None, -32700, f"Parse error: {e}"
                )
                self._send_message(error_response)
            except Exception as e:
                error_response = self._error_response(
                    None, -32603, f"Internal error: {e}"
                )
                self._send_message(error_response)


def main() -> None:
    """Main entry point."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
