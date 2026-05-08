#!/usr/bin/env python3
"""
Knowledge entry quality checker.

Evaluates JSON files across 5 quality dimensions and produces scores.
Supports single file or glob patterns (*.json).

Usage:
    python hooks/check_quality.py <json_file> [json_file2 ...]
    python hooks/check_quality.py "knowledge/articles/*.json"
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DimensionScore:
    name: str
    score: float
    max_score: float
    details: str = ""


@dataclass
class QualityReport:
    file_path: Path
    dimensions: list[DimensionScore] = field(default_factory=list)
    total_score: float = 0.0
    grade: str = "C"

    @property
    def passed(self) -> bool:
        return self.grade != "C"


TECH_KEYWORDS = {
    "python", "javascript", "java", "c++", "golang", "rust", "typescript",
    "api", "sdk", "cli", "框架", "库", "算法", "数据结构", "并发", "异步",
    "缓存", "数据库", "索引", "事务", "分布式", "微服务", "容器", "docker",
    "k8s", "kubernetes", "编排", "监控", "日志", "devops", "ci", "cd",
    "机器学习", "深度学习", "神经网络", "模型", "训练", "推理", "特征",
    "nlp", "cv", "transformer", "bert", "gpt", "llm", "大模型", "prompt",
    "推理", "token", "embedding", "向量", "检索", "rag", "检索增强",
    "grpc", "http", "websocket", "tcp", "udp", "协议", "加密", "tls",
    "ssl", "认证", "授权", "oauth", "jwt", "session", "cookie",
    "前端", "后端", "全栈", "移动端", "ios", "android", "react", "vue",
    "angular", "node", "django", "flask", "spring", "springboot",
    "redis", "mongodb", "mysql", "postgresql", "elasticsearch", "kafka",
    "rabbitmq", "zookeeper", "etcd", "hadoop", "spark", "flink",
    "aws", "azure", "gcp", "阿里云", "腾讯云", "华为云",
    "性能", "优化", "瓶颈", "压测", "负载", "高可用", "容灾", "备份",
    "架构", "设计模式", "单例", "工厂", "观察者", "策略", "模板方法",
}

STANDARD_TAGS = {
    "tutorial", "article", "paper", "news", "tool", "dataset", "course",
    "blog", "documentation", "reference", "video", "podcast", "book",
    "discussion", "opinion", "review", "comparison", "cheatsheet",
    "入门", "进阶", "实战", "理论", "案例", "工具", "资源", "新闻",
    "教程", "文档", "论文", "博客", "视频", "书籍",
}

EMPTY_WORDS_CN = {
    "赋能", "抓手", "闭环", "打通", "全链路", "底层逻辑", "颗粒度",
    "对齐", "拉通", "沉淀", "强大的", "革命性的", "痛点", "难点",
    "亮点", "价值", "落地", "赋能", "精细化", "差异化", "多元化",
    "体系化", "可视化", "可量化", "可执行", "可落地", "闭环",
}

EMPTY_WORDS_EN = {
    "groundbreaking", "revolutionary", "game-changing", "cutting-edge",
    "state-of-the-art", "best-in-class", "world-class", "industry-leading",
    "next-generation", "innovative", "disruptive", "transformative",
    "cutting-edge", "first-of-its-kind", "unprecedented", "breakthrough",
}


class QualityChecker:
    """Check quality of knowledge entry JSON files."""

    def __init__(self) -> None:
        self.reports: list[QualityReport] = []

    def check_file(self, file_path: Path) -> QualityReport:
        """Check a single JSON file and return quality report."""
        report = QualityReport(file_path=file_path)

        try:
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            report.dimensions.append(DimensionScore("JSON", 0, 100, f"Parse error: {e}"))
            report.grade = "C"
            return report

        if isinstance(data, list):
            items = data
        else:
            items = [data]

        if not items:
            report.dimensions.append(DimensionScore("Content", 0, 100, "Empty file"))
            report.grade = "C"
            return report

        item = items[0]

        summary_dim = self._check_summary_quality(item.get("summary", ""))
        depth_dim = self._check_technical_depth(item.get("score"))
        format_dim = self._check_format_completeness(item, file_path)
        tags_dim = self._check_tag_precision(item.get("tags", []))
        empty_dim = self._check_empty_words(item)

        report.dimensions.extend([summary_dim, depth_dim, format_dim, tags_dim, empty_dim])
        report.total_score = sum(d.score for d in report.dimensions)
        report.grade = self._calculate_grade(report.total_score)

        return report

    def _check_summary_quality(self, summary: str) -> DimensionScore:
        length = len(summary)
        score = 0.0
        details = []

        if length >= 50:
            score = 25.0
            details.append(f"excellent ({length} chars)")
        elif length >= 20:
            score = 15.0
            details.append(f"basic ({length} chars)")
        else:
            details.append(f"too short ({length} chars, need >=20)")
            return DimensionScore("Summary", score, 25, "; ".join(details))

        has_tech = False
        summary_lower = summary.lower()
        for kw in TECH_KEYWORDS:
            if kw in summary_lower or kw in summary:
                has_tech = True
                break

        if has_tech:
            score = min(score + 5, 25.0)
            details.append("tech keywords +5")

        return DimensionScore("Summary", score, 25, "; ".join(details))

    def _check_technical_depth(self, score: Any | None) -> DimensionScore:
        if score is None:
            return DimensionScore("Tech Depth", 0, 25, "missing score field")

        try:
            s = float(score)
        except (TypeError, ValueError):
            return DimensionScore("Tech Depth", 0, 25, f"score type error: {type(score).__name__}")

        if s < 1 or s > 10:
            return DimensionScore("Tech Depth", 0, 25, f"score out of range: {s}")

        mapped = (s / 10) * 25
        return DimensionScore("Tech Depth", mapped, 25, f"score={s:.1f} -> {mapped:.1f}")

    def _check_format_completeness(self, item: dict[str, Any], file_path: Path) -> DimensionScore:
        score = 0.0
        details = []

        id_val = item.get("id")
        if id_val and isinstance(id_val, str) and re.match(r"^[a-z]+-\d{8}-\d{3}$", id_val):
            score += 4
            details.append("id[+]")
        else:
            details.append("id[-]")

        title = item.get("title")
        if title and isinstance(title, str) and len(title) > 0:
            score += 4
            details.append("title[+]")
        else:
            details.append("title[-]")

        url = item.get("source_url")
        if url and isinstance(url, str) and re.match(r"^https?://", url):
            score += 4
            details.append("url[+]")
        else:
            details.append("url[-]")

        status = item.get("status")
        if status in {"draft", "review", "published", "archived"}:
            score += 4
            details.append("status[+]")
        else:
            details.append("status[-]")

        has_timestamp = False
        for key in item:
            if key.lower() in {"created_at", "updated_at", "date", "timestamp"}:
                val = item[key]
                if isinstance(val, str) and len(val) >= 8:
                    has_timestamp = True
                    break

        if has_timestamp:
            score += 4
            details.append("timestamp[+]")
        else:
            details.append("timestamp[-]")

        return DimensionScore("Format", score, 20, "; ".join(details))

    def _check_tag_precision(self, tags: Any) -> DimensionScore:
        if not isinstance(tags, list):
            return DimensionScore("Tags", 0, 15, "tags not array")

        count = len(tags)
        if count == 0:
            return DimensionScore("Tags", 0, 15, "no tags")

        if count > 3:
            score = 10.0
            detail = f"too many ({count} tags, suggest 1-3)"
        elif count == 0:
            score = 0.0
            detail = "no tags"
        elif count <= 3:
            score = 15.0
            detail = f"ideal ({count} tags)"

        valid_count = 0
        tag_details = []
        for tag in tags:
            if not isinstance(tag, str):
                continue
            tag_lower = tag.lower()
            if tag_lower in STANDARD_TAGS:
                valid_count += 1
                tag_details.append(f"{tag}[+]")
            else:
                tag_details.append(f"{tag}[?]")

        if count >= 1 and count <= 3:
            detail = f"{count} tags"
            if valid_count > 0:
                detail += f", {valid_count} standard"
                score = 15.0
            else:
                detail += ", no standard tags"

        return DimensionScore("Tags", score, 15, detail)

    def _check_empty_words(self, item: dict[str, Any]) -> DimensionScore:
        fields = [
            str(item.get("title", "")),
            str(item.get("summary", "")),
        ]
        for tag in item.get("tags", []):
            if isinstance(tag, str):
                fields.append(tag)

        text = " ".join(fields)
        found: list[str] = []

        for word in EMPTY_WORDS_CN:
            if word in text:
                found.append(word)

        text_lower = text.lower()
        for word in EMPTY_WORDS_EN:
            if word in text_lower:
                found.append(word)

        if not found:
            return DimensionScore("Buzzwords", 15.0, 15, "no buzzwords")

        score = max(0, 15.0 - len(found) * 5)
        # Only show count to avoid encoding issues
        return DimensionScore("Buzzwords", score, 15, f"found {len(found)} buzzwords")

    def _calculate_grade(self, total: float) -> str:
        if total >= 80:
            return "A"
        elif total >= 60:
            return "B"
        else:
            return "C"


def expand_paths(paths: list[str]) -> list[Path]:
    """Expand glob patterns and return unique Path objects."""
    result: set[Path] = set()

    for p in paths:
        path = Path(p)
        if "*" in p or "?" in p:
            result.update(Path.cwd().glob(p))
        else:
            if path.exists():
                result.add(path)

    return sorted(result)


def print_progress_bar(current: int, total: int, width: int = 40) -> str:
    """Print a simple ASCII progress bar."""
    if total == 0:
        return "[ " + " " * width + " ] 0%"
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    percent = int(100 * current / total)
    return f"[{bar}] {percent}%"


def print_report(report: QualityReport) -> None:
    """Print quality report for a single file."""
    print(f"\n{'-' * 50}")
    print(f"File: {report.file_path.name}")
    print(f"{'-' * 50}")

    for dim in report.dimensions:
        pct = dim.score / dim.max_score * 100 if dim.max_score > 0 else 0
        bar_len = int(pct / 5)
        bar = "#" * bar_len + "-" * (20 - bar_len)
        print(f"  {dim.name:12} [{bar}] {dim.score:5.1f}/{dim.max_score:.0f}  {dim.details}")

    print(f"{'-' * 50}")
    total_bar_len = int(report.total_score / 5)
    total_bar = "#" * total_bar_len + "-" * (20 - total_bar_len)
    grade_symbol = {"A": "[+]", "B": "[!]", "C": "[x]"}
    print(f"  {'Total':12} [{total_bar}] {report.total_score:5.1f}/100  {grade_symbol[report.grade]} Grade {report.grade}")


def main(argv: list[str]) -> int:
    """Main entry point."""
    if len(argv) < 2:
        print(f"Usage: {argv[0]} <json_file> [json_file2 ...]")
        print(f"       {argv[0]} knowledge/articles/*.json")
        return 1

    paths = expand_paths(argv[1:])
    if not paths:
        print(f"No files found matching: {argv[1:]}")
        return 1

    checker = QualityChecker()
    reports: list[QualityReport] = []

    print(f"\n[*] Checking {len(paths)} file(s)...\n")

    for i, path in enumerate(paths):
        report = checker.check_file(path)
        reports.append(report)
        print_progress_bar(i + 1, len(paths))
        print_report(report)

    print(f"\n{'=' * 50}")
    print("SUMMARY")
    print(f"{'=' * 50}")

    grade_counts = {"A": 0, "B": 0, "C": 0}
    total_score = 0.0

    for report in reports:
        grade_counts[report.grade] += 1
        total_score += report.total_score

    avg_score = total_score / len(reports) if reports else 0

    print(f"  Files checked: {len(reports)}")
    print(f"  Grade A: {grade_counts['A']} | Grade B: {grade_counts['B']} | Grade C: {grade_counts['C']}")
    print(f"  Average score: {avg_score:.1f}")
    print(f"{'=' * 50}")

    if grade_counts["C"] > 0:
        print(f"\n[!] Found {grade_counts['C']} file(s) with grade C")
        return 1

    print("\n[+] All files passed quality check")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))