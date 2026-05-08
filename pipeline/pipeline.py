#!/usr/bin/env python3
"""
Knowledge Base Automation Pipeline

A four-step pipeline for collecting, analyzing, organizing, and saving
AI-related content from GitHub and RSS sources.

Usage:
    python pipeline/pipeline.py --sources github,rss --limit 20
    python pipeline/pipeline.py --sources github --limit 5
    python pipeline/pipeline.py --sources rss --limit 10
    python pipeline/pipeline.py --sources github --limit 5 --dry-run
    python pipeline/pipeline.py --verbose
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from model_client import chat_with_retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class GitHubCollector:
    """Collects AI-related content from GitHub Search API."""

    def __init__(self, limit: int = 10):
        """Initialize GitHub collector.

        Args:
            limit: Maximum number of repositories to collect.
        """
        self.limit = limit
        self.base_url = "https://api.github.com"
        self.client = httpx.Client(timeout=30.0)

    def collect(self) -> list[dict[str, Any]]:
        """Collect repositories from GitHub.

        Returns:
            List of repository data dictionaries.
        """
        logger.info(f"Collecting up to {self.limit} repositories from GitHub...")

        # Search for AI/ML related repositories
        query = "ai OR llm OR agent OR machine-learning language:python stars:>100"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(self.limit, 100),
        }

        headers = {}
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        try:
            response = self.client.get(
                f"{self.base_url}/search/repositories",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("items", [])
            logger.info(f"Found {len(items)} repositories")

            results = []
            for item in items[:self.limit]:
                results.append({
                    "source": "github",
                    "title": item["full_name"],
                    "url": item["html_url"],
                    "description": item.get("description", ""),
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language", ""),
                    "topics": item.get("topics", []),
                    "collected_at": datetime.utcnow().isoformat() + "Z",
                })

            return results

        except httpx.HTTPError as e:
            logger.error(f"GitHub API error: {e}")
            return []

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "client"):
            self.client.close()


class RSSCollector:
    """Collects content from RSS feeds."""

    def __init__(self, config_path: str = "pipeline/rss_sources.yaml", limit: int = 10):
        """Initialize RSS collector.

        Args:
            config_path: Path to RSS sources configuration file.
            limit: Maximum number of items to collect per feed.
        """
        self.config_path = Path(config_path)
        self.limit = limit
        self.client = httpx.Client(timeout=30.0)

    def collect(self) -> list[dict[str, Any]]:
        """Collect items from RSS feeds.

        Returns:
            List of RSS item data dictionaries.
        """
        if not self.config_path.exists():
            logger.warning(f"RSS config not found: {self.config_path}")
            return []

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        sources = config.get("sources", [])
        enabled_sources = [s for s in sources if s.get("enabled", False)]

        logger.info(f"Collecting from {len(enabled_sources)} RSS feeds...")

        results = []
        for source in enabled_sources:
            name = source["name"]
            url = source["url"]

            try:
                logger.info(f"Fetching {name}: {url}")
                response = self.client.get(url)
                response.raise_for_status()

                items = self._parse_rss(response.text, source)
                results.extend(items[:self.limit])
                logger.info(f"Collected {len(items[:self.limit])} items from {name}")

            except httpx.HTTPError as e:
                logger.error(f"Failed to fetch {name}: {e}")
                continue

        return results

    def _parse_rss(self, xml_content: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse RSS XML content using simple regex.

        Args:
            xml_content: RSS XML content.
            source: Source configuration.

        Returns:
            List of parsed items.
        """
        items = []

        # Simple regex-based parsing (not a full XML parser)
        item_pattern = r"<item>(.*?)</item>"
        title_pattern = r"<title>(.*?)</title>"
        link_pattern = r"<link>(.*?)</link>"
        description_pattern = r"<description>(.*?)</description>"

        item_matches = re.findall(item_pattern, xml_content, re.DOTALL)

        for item_xml in item_matches:
            title_match = re.search(title_pattern, item_xml, re.DOTALL)
            link_match = re.search(link_pattern, item_xml, re.DOTALL)
            desc_match = re.search(description_pattern, item_xml, re.DOTALL)

            if title_match and link_match:
                title = self._clean_html(title_match.group(1))
                link = link_match.group(1).strip()
                description = self._clean_html(desc_match.group(1)) if desc_match else ""

                items.append({
                    "source": "rss",
                    "source_name": source["name"],
                    "category": source.get("category", "unknown"),
                    "title": title,
                    "url": link,
                    "description": description,
                    "collected_at": datetime.utcnow().isoformat() + "Z",
                })

        return items

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities.

        Args:
            text: HTML text.

        Returns:
            Cleaned text.
        """
        # Remove CDATA
        text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode common HTML entities
        text = text.replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&amp;", "&").replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        return text.strip()

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "client"):
            self.client.close()


class ContentAnalyzer:
    """Analyzes content using LLM."""

    def analyze(self, item: dict[str, Any]) -> dict[str, Any]:
        """Analyze a single content item.

        Args:
            item: Raw content item.

        Returns:
            Analyzed item with summary, score, and tags.
        """
        title = item.get("title", "")
        description = item.get("description", "")

        prompt = f"""Analyze this AI/ML content and provide:
1. A concise summary (20-100 words)
2. A technical depth score (1-10, where 10 is most advanced)
3. Up to 3 relevant tags from: agent, llm, framework, tool, research, deployment, fine-tuning, rag, prompt-engineering

Title: {title}
Description: {description}

Respond in JSON format:
{{
  "summary": "...",
  "score": 7,
  "tags": ["tag1", "tag2"]
}}"""

        try:
            logger.info(f"Analyzing: {title[:50]}...")
            messages = [{"role": "user", "content": prompt}]
            response = chat_with_retry(messages, temperature=0.3, max_tokens=500)

            # Parse JSON from response
            content = response.content.strip()
            # Extract JSON if wrapped in markdown code blocks
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                content = json_match.group(1)

            analysis = json.loads(content)

            item["summary"] = analysis.get("summary", "")
            item["score"] = analysis.get("score", 5)
            item["tags"] = analysis.get("tags", [])

            logger.info(f"Analysis complete: score={item['score']}, tags={item['tags']}")

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            item["summary"] = description[:200] if description else title
            item["score"] = 5
            item["tags"] = []

        return item


class ContentOrganizer:
    """Organizes and validates content."""

    def __init__(self, articles_dir: str = "knowledge/articles"):
        """Initialize organizer.

        Args:
            articles_dir: Directory containing existing articles.
        """
        self.articles_dir = Path(articles_dir)
        self.existing_urls = self._load_existing_urls()

    def _load_existing_urls(self) -> set[str]:
        """Load URLs from existing articles.

        Returns:
            Set of existing URLs.
        """
        urls = set()
        if not self.articles_dir.exists():
            return urls

        for json_file in self.articles_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if "source_url" in item:
                                urls.add(item["source_url"])
                    elif "source_url" in data:
                        urls.add(data["source_url"])
            except (json.JSONDecodeError, IOError):
                continue

        logger.info(f"Loaded {len(urls)} existing URLs")
        return urls

    def organize(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Organize and deduplicate items.

        Args:
            items: List of analyzed items.

        Returns:
            List of organized and validated items.
        """
        logger.info(f"Organizing {len(items)} items...")

        organized = []
        for item in items:
            # Deduplicate by URL
            url = item.get("url", "")
            if url in self.existing_urls:
                logger.info(f"Skipping duplicate: {url}")
                continue

            # Generate ID
            source = item.get("source", "unknown")
            date_str = datetime.utcnow().strftime("%Y%m%d")
            url_hash = hashlib.md5(url.encode()).hexdigest()[:3]
            item_id = f"{source}-{date_str}-{url_hash}"

            # Standardize format
            organized_item = {
                "id": item_id,
                "title": item.get("title", ""),
                "source_url": url,
                "source": source,
                "summary": item.get("summary", ""),
                "tags": item.get("tags", []),
                "status": "draft",
                "score": item.get("score"),
                "created_at": item.get("collected_at", datetime.utcnow().isoformat() + "Z"),
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }

            # Validate
            if self._validate(organized_item):
                organized.append(organized_item)
                self.existing_urls.add(url)

        logger.info(f"Organized {len(organized)} unique items")
        return organized

    def _validate(self, item: dict[str, Any]) -> bool:
        """Validate item format.

        Args:
            item: Item to validate.

        Returns:
            True if valid, False otherwise.
        """
        required_fields = ["id", "title", "source_url", "summary", "tags", "status"]

        for field in required_fields:
            if field not in item or not item[field]:
                logger.warning(f"Invalid item: missing {field}")
                return False

        if len(item["summary"]) < 20:
            logger.warning(f"Invalid item: summary too short")
            return False

        if not item["tags"] or len(item["tags"]) == 0:
            logger.warning(f"Invalid item: no tags")
            return False

        return True


class Pipeline:
    """Main pipeline orchestrator."""

    def __init__(
        self,
        sources: list[str],
        limit: int = 10,
        dry_run: bool = False,
        raw_dir: str = "knowledge/raw",
        articles_dir: str = "knowledge/articles",
    ):
        """Initialize pipeline.

        Args:
            sources: List of sources to collect from (github, rss).
            limit: Maximum items to collect per source.
            dry_run: If True, don't save files.
            raw_dir: Directory for raw collected data.
            articles_dir: Directory for final articles.
        """
        self.sources = sources
        self.limit = limit
        self.dry_run = dry_run
        self.raw_dir = Path(raw_dir)
        self.articles_dir = Path(articles_dir)

        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.articles_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict[str, Any]:
        """Run the complete pipeline.

        Returns:
            Pipeline execution statistics.
        """
        logger.info("=" * 60)
        logger.info("Starting Knowledge Base Pipeline")
        logger.info("=" * 60)

        stats = {
            "collected": 0,
            "analyzed": 0,
            "organized": 0,
            "saved": 0,
        }

        # Step 1: Collect
        raw_items = []
        if "github" in self.sources:
            collector = GitHubCollector(limit=self.limit)
            raw_items.extend(collector.collect())

        if "rss" in self.sources:
            collector = RSSCollector(limit=self.limit)
            raw_items.extend(collector.collect())

        stats["collected"] = len(raw_items)
        logger.info(f"Step 1: Collected {stats['collected']} items")

        if not raw_items:
            logger.warning("No items collected, exiting")
            return stats

        # Save raw data
        if not self.dry_run:
            raw_file = self.raw_dir / f"raw_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            with open(raw_file, "w", encoding="utf-8") as f:
                json.dump(raw_items, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved raw data to {raw_file}")

        # Step 2: Analyze
        analyzer = ContentAnalyzer()
        analyzed_items = []
        for item in raw_items:
            analyzed = analyzer.analyze(item)
            analyzed_items.append(analyzed)

        stats["analyzed"] = len(analyzed_items)
        logger.info(f"Step 2: Analyzed {stats['analyzed']} items")

        # Step 3: Organize
        organizer = ContentOrganizer(articles_dir=str(self.articles_dir))
        organized_items = organizer.organize(analyzed_items)

        stats["organized"] = len(organized_items)
        logger.info(f"Step 3: Organized {stats['organized']} items")

        # Step 4: Save
        if not self.dry_run:
            for item in organized_items:
                item_id = item["id"]
                file_path = self.articles_dir / f"{item_id}.json"

                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(item, f, indent=2, ensure_ascii=False)

                logger.info(f"Saved: {file_path}")
                stats["saved"] += 1

        logger.info(f"Step 4: Saved {stats['saved']} articles")

        logger.info("=" * 60)
        logger.info("Pipeline Complete")
        logger.info(f"Collected: {stats['collected']}")
        logger.info(f"Analyzed: {stats['analyzed']}")
        logger.info(f"Organized: {stats['organized']}")
        logger.info(f"Saved: {stats['saved']}")
        logger.info("=" * 60)

        return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Knowledge Base Automation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline/pipeline.py --sources github,rss --limit 20
  python pipeline/pipeline.py --sources github --limit 5
  python pipeline/pipeline.py --sources rss --limit 10
  python pipeline/pipeline.py --sources github --limit 5 --dry-run
  python pipeline/pipeline.py --verbose
        """,
    )

    parser.add_argument(
        "--sources",
        type=str,
        default="github,rss",
        help="Comma-separated list of sources (github, rss). Default: github,rss",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum items to collect per source. Default: 10",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without saving files",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    sources = [s.strip() for s in args.sources.split(",")]

    # Validate sources
    valid_sources = {"github", "rss"}
    invalid = set(sources) - valid_sources
    if invalid:
        logger.error(f"Invalid sources: {invalid}. Valid sources: {valid_sources}")
        sys.exit(1)

    try:
        pipeline = Pipeline(
            sources=sources,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        stats = pipeline.run()

        if stats["saved"] == 0 and not args.dry_run:
            logger.warning("No articles saved")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\nPipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
