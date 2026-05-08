#!/usr/bin/env python3
"""
Knowledge entry JSON validator.

Validates JSON files against the knowledge base schema.
Supports single file or glob patterns (*.json).

Usage:
    python hooks/validate_json.py <json_file> [json_file2 ...]
    python hooks/validate_json.py "knowledge/articles/*.json"
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "title": str,
    "source_url": str,
    "summary": str,
    "tags": list,
    "status": str,
}

ID_PATTERN = re.compile(r"^[a-z]+-\d{8}-\d{3}$")

VALID_STATUSES = {"draft", "review", "published", "archived"}

VALID_AUDIENCES = {"beginner", "intermediate", "advanced"}

URL_PATTERN = re.compile(r"^https?://.+")


class ValidationError:
    """Represents a single validation error."""

    def __init__(self, file_path: Path, field: str, message: str) -> None:
        self.file_path = file_path
        self.field = field
        self.message = message

    def __str__(self) -> str:
        return f"{self.file_path}: [{self.field}] {self.message}"


class Validator:
    """Validates knowledge entry JSON files."""

    def __init__(self) -> None:
        self.errors: list[ValidationError] = []

    def validate_file(self, file_path: Path) -> bool:
        """Validate a single JSON file. Returns True if valid."""
        self.errors.clear()

        data = self._parse_json(file_path)
        if data is None:
            return False

        if isinstance(data, list):
            for item in data:
                self._validate_item(item, file_path)
        else:
            self._validate_item(data, file_path)

        return len(self.errors) == 0

    def _parse_json(self, file_path: Path) -> dict[str, Any] | list[Any] | None:
        """Parse JSON file and return data or None on error."""
        try:
            content = file_path.read_text(encoding="utf-8")
            return json.loads(content)
        except json.JSONDecodeError as e:
            self.errors.append(
                ValidationError(file_path, "json", f"Invalid JSON: {e.msg} at line {e.lineno}")
            )
            return None
        except UnicodeDecodeError as e:
            self.errors.append(
                ValidationError(file_path, "json", f"Encoding error: {e.reason}")
            )
            return None

    def _validate_item(
        self, item: dict[str, Any], file_path: Path
    ) -> None:
        """Validate a single knowledge entry item."""
        self._validate_required_fields(item, file_path)
        self._validate_id(item.get("id"), file_path)
        self._validate_status(item.get("status"), file_path)
        self._validate_url(item.get("source_url"), file_path)
        self._validate_summary(item.get("summary"), file_path)
        self._validate_tags(item.get("tags"), file_path)
        self._validate_score(item.get("score"), file_path)
        self._validate_audience(item.get("audience"), file_path)

    def _validate_required_fields(
        self, item: dict[str, Any], file_path: Path
    ) -> None:
        """Check all required fields exist and have correct types."""
        for field, expected_type in REQUIRED_FIELDS.items():
            if field not in item:
                self.errors.append(
                    ValidationError(file_path, field, "Missing required field")
                )
            elif not isinstance(item[field], expected_type):
                actual = type(item[field]).__name__
                expected = expected_type.__name__
                self.errors.append(
                    ValidationError(
                        file_path, field, f"Expected {expected}, got {actual}"
                    )
                )

    def _validate_id(self, item_id: str | None, file_path: Path) -> None:
        """Validate ID format: {source}-{YYYYMMDD}-{NNN}."""
        if item_id is None:
            return

        if not ID_PATTERN.match(item_id):
            self.errors.append(
                ValidationError(
                    file_path,
                    "id",
                    f'Invalid format "{item_id}", expected {{source}}-{{YYYYMMDD}}-{{NNN}}',
                )
            )

    def _validate_status(self, status: str | None, file_path: Path) -> None:
        """Validate status is one of the allowed values."""
        if status is None:
            return

        if status not in VALID_STATUSES:
            valid = ", ".join(sorted(VALID_STATUSES))
            self.errors.append(
                ValidationError(
                    file_path,
                    "status",
                    f'Invalid value "{status}", expected one of: {valid}',
                )
            )

    def _validate_url(self, url: str | None, file_path: Path) -> None:
        """Validate URL format (http:// or https://)."""
        if url is None:
            return

        if not URL_PATTERN.match(url):
            self.errors.append(
                ValidationError(
                    file_path,
                    "source_url",
                    f'Invalid URL format "{url}"',
                )
            )

    def _validate_summary(self, summary: str | None, file_path: Path) -> None:
        """Validate summary is at least 20 characters."""
        if summary is None:
            return

        if len(summary) < 20:
            self.errors.append(
                ValidationError(
                    file_path,
                    "summary",
                    f'Summary too short ({len(summary)} chars), minimum 20',
                )
            )

    def _validate_tags(self, tags: list[Any] | None, file_path: Path) -> None:
        """Validate tags is a non-empty list."""
        if tags is None:
            return

        if not isinstance(tags, list):
            return

        if len(tags) < 1:
            self.errors.append(
                ValidationError(
                    file_path,
                    "tags",
                    "At least 1 tag required",
                )
            )

    def _validate_score(self, score: Any | None, file_path: Path) -> None:
        """Validate score (if present) is between 1 and 10."""
        if score is None:
            return

        if isinstance(score, (int, float)):
            if score < 1 or score > 10:
                self.errors.append(
                    ValidationError(
                        file_path,
                        "score",
                        f"Score {score} out of range [1-10]",
                    )
                )

    def _validate_audience(
        self, audience: str | None, file_path: Path
    ) -> None:
        """Validate audience (if present) is one of the allowed values."""
        if audience is None:
            return

        if audience not in VALID_AUDIENCES:
            valid = ", ".join(sorted(VALID_AUDIENCES))
            self.errors.append(
                ValidationError(
                    file_path,
                    "audience",
                    f'Invalid value "{audience}", expected one of: {valid}',
                )
            )


def expand_paths(paths: list[str]) -> list[Path]:
    """Expand glob patterns and return unique Path objects."""
    result: set[Path] = set()

    for p in paths:
        path = Path(p)
        if "*" in p or "?" in p:
            result.update(Path.cwd().glob(p))
        else:
            result.add(path)

    return sorted(result)


def print_error_summary(
    errors: list[ValidationError],
    total_files: int,
    passed_files: int,
) -> None:
    """Print error summary and statistics."""
    print("\n" + "=" * 60)
    print("VALIDATION FAILED")
    print("=" * 60)

    for err in errors:
        print(f"  [X] {err}")

    print()
    print("-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"  Total files checked: {total_files}")
    print(f"  Passed: {passed_files}")
    print(f"  Failed: {total_files - passed_files}")
    print(f"  Total errors: {len(errors)}")
    print("=" * 60)


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

    validator = Validator()
    all_errors: list[ValidationError] = []
    passed = 0

    for path in paths:
        if validator.validate_file(path):
            print(f"  [OK] {path}")
            passed += 1
        else:
            all_errors.extend(validator.errors)
            print(f"  [FAIL] {path}")

    print()
    print(f"Checked {len(paths)} file(s), {passed} passed, {len(paths) - passed} failed")

    if all_errors:
        print_error_summary(all_errors, len(paths), passed)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))