#!/usr/bin/env python3
"""Small documentation hygiene check for AMPG."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def iter_markdown() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if ".git" not in path.parts
        and "docs/generated" not in str(path)
        and "private" not in path.parts
        and "dist" not in path.parts
    )


def has_status_header(text: str) -> bool:
    return any(line.startswith("> Status:") for line in text.splitlines()[:6])


def local_link_target(source: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if not target or target.startswith("#"):
        return None
    if "://" in target or target.startswith(("mailto:", "tel:")):
        return None
    target = target.split("#", 1)[0]
    if not target:
        return None
    return (source.parent / unquote(target)).resolve()


def main() -> int:
    errors: list[str] = []
    files = iter_markdown()
    checked_links = 0

    for path in files:
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        if not has_status_header(text):
            errors.append(f"{rel}: missing > Status: header in first 6 lines")

        for match in LINK_RE.finditer(text):
            target = local_link_target(path, match.group(1))
            if target is None:
                continue
            checked_links += 1
            if not target.exists():
                errors.append(f"{rel}: broken link -> {match.group(1)}")

    if errors:
        for error in errors:
            print(f"DOCS_CHECK status=error message={error}")
        print(f"DOCS_CHECK status=fail files={len(files)} links={checked_links}")
        return 1

    print(f"DOCS_CHECK status=ok files={len(files)} links={checked_links}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
