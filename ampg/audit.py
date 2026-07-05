from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re

from .build import _iter_source_files
from .config import GatewayConfig, SiteConfig


@dataclass(frozen=True)
class AuditIssue:
    site_id: str
    path: Path
    severity: str
    code: str
    message: str


def audit_gateway(config: GatewayConfig) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for site in config.sites:
        issues.extend(audit_site(site))
    return issues


def audit_site(site: SiteConfig) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for path in _iter_source_files(site.source.path):
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        rel_path = path.relative_to(site.source.path)
        page_issues = SemanticHtmlAuditor(site.id, rel_path).audit(html)
        issues.extend(page_issues)
    return issues


class SemanticHtmlAuditor(HTMLParser):
    def __init__(self, site_id: str, path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.site_id = site_id
        self.path = path
        self.issues: list[AuditIssue] = []
        self.last_heading_level = 0
        self.h1_count = 0
        self.anchor_stack: list[tuple[str, list[str], bool]] = []
        self.skip_stack: list[str] = []

    def audit(self, html: str) -> list[AuditIssue]:
        self.feed(html)
        self.close()
        if self.h1_count == 0:
            self._warn("missing_h1", "page has no h1 heading")
        elif self.h1_count > 1:
            self._warn("multiple_h1", f"page has {self.h1_count} h1 headings")
        return self.issues

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {name.lower(): value for name, value in attrs}
        if tag in {"script", "style"}:
            self.skip_stack.append(tag)
            return
        if self.skip_stack:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._handle_heading(int(tag[1]))
        elif tag == "img":
            alt = attrs_dict.get("alt")
            if alt is None or not _normalize_text(alt):
                self._warn("missing_alt", "image is missing meaningful alt text")
            if self.anchor_stack:
                href, text, _ = self.anchor_stack.pop()
                self.anchor_stack.append((href, text, True))
        elif tag == "a":
            href = attrs_dict.get("href")
            if href:
                self.anchor_stack.append((href, [], False))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_stack:
            if self.skip_stack[-1] == tag:
                self.skip_stack.pop()
            return
        if tag == "a" and self.anchor_stack:
            href, text_parts, has_image = self.anchor_stack.pop()
            text = _normalize_text("".join(text_parts))
            if not text and not has_image and not href.startswith("#"):
                self._warn("empty_link_text", f"link to {href!r} has no text")

    def handle_data(self, data: str) -> None:
        if self.skip_stack:
            return
        if self.anchor_stack:
            href, text_parts, has_image = self.anchor_stack.pop()
            text_parts.append(data)
            self.anchor_stack.append((href, text_parts, has_image))

    def _handle_heading(self, level: int) -> None:
        if level == 1:
            self.h1_count += 1
        if self.last_heading_level and level > self.last_heading_level + 1:
            self._warn(
                "heading_level_skip",
                f"heading jumps from h{self.last_heading_level} to h{level}",
            )
        self.last_heading_level = level

    def _warn(self, code: str, message: str) -> None:
        self.issues.append(
            AuditIssue(
                site_id=self.site_id,
                path=self.path,
                severity="warn",
                code=code,
                message=message,
            )
        )


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
