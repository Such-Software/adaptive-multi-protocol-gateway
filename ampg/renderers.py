from __future__ import annotations

from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser


VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

ACTIVE_TAGS = {"script", "style"}


@dataclass(frozen=True)
class PrivacyRenderStats:
    removed_active_tags: int = 0
    removed_event_handlers: int = 0
    removed_inline_styles: int = 0
    removed_remote_assets: int = 0

    def add(self, other: "PrivacyRenderStats") -> "PrivacyRenderStats":
        return PrivacyRenderStats(
            removed_active_tags=self.removed_active_tags + other.removed_active_tags,
            removed_event_handlers=self.removed_event_handlers + other.removed_event_handlers,
            removed_inline_styles=self.removed_inline_styles + other.removed_inline_styles,
            removed_remote_assets=self.removed_remote_assets + other.removed_remote_assets,
        )


class PrivacyHtmlRenderer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.skip_stack: list[str] = []
        self.stats = PrivacyRenderStats()

    def render(self, html: str) -> tuple[str, PrivacyRenderStats]:
        self.feed(html)
        self.close()
        return "".join(self.parts), self.stats

    def handle_decl(self, decl: str) -> None:
        if not self.skip_stack:
            self.parts.append(f"<!{decl}>")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ACTIVE_TAGS:
            self.skip_stack.append(tag)
            self.stats = PrivacyRenderStats(
                removed_active_tags=self.stats.removed_active_tags + 1,
                removed_event_handlers=self.stats.removed_event_handlers,
                removed_inline_styles=self.stats.removed_inline_styles,
                removed_remote_assets=self.stats.removed_remote_assets,
            )
            return
        if self.skip_stack:
            return
        clean_attrs = self._clean_attrs(tag, attrs)
        self.parts.append(f"<{tag}{_format_attrs(clean_attrs)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ACTIVE_TAGS:
            self.stats = PrivacyRenderStats(
                removed_active_tags=self.stats.removed_active_tags + 1,
                removed_event_handlers=self.stats.removed_event_handlers,
                removed_inline_styles=self.stats.removed_inline_styles,
                removed_remote_assets=self.stats.removed_remote_assets,
            )
            return
        if self.skip_stack:
            return
        clean_attrs = self._clean_attrs(tag, attrs)
        self.parts.append(f"<{tag}{_format_attrs(clean_attrs)}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_stack:
            if self.skip_stack[-1] == tag:
                self.skip_stack.pop()
            return
        if tag not in VOID_ELEMENTS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.skip_stack:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self.skip_stack:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.skip_stack:
            self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        return

    def _clean_attrs(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> list[tuple[str, str | None]]:
        clean: list[tuple[str, str | None]] = []
        for name, value in attrs:
            attr = name.lower()
            if attr.startswith("on"):
                self.stats = PrivacyRenderStats(
                    removed_active_tags=self.stats.removed_active_tags,
                    removed_event_handlers=self.stats.removed_event_handlers + 1,
                    removed_inline_styles=self.stats.removed_inline_styles,
                    removed_remote_assets=self.stats.removed_remote_assets,
                )
                continue
            if attr == "style":
                self.stats = PrivacyRenderStats(
                    removed_active_tags=self.stats.removed_active_tags,
                    removed_event_handlers=self.stats.removed_event_handlers,
                    removed_inline_styles=self.stats.removed_inline_styles + 1,
                    removed_remote_assets=self.stats.removed_remote_assets,
                )
                continue
            if attr in {"src", "poster"} and value and _is_remote_url(value):
                self.stats = PrivacyRenderStats(
                    removed_active_tags=self.stats.removed_active_tags,
                    removed_event_handlers=self.stats.removed_event_handlers,
                    removed_inline_styles=self.stats.removed_inline_styles,
                    removed_remote_assets=self.stats.removed_remote_assets + 1,
                )
                continue
            if tag == "link" and attr == "href" and value and _is_remote_url(value):
                self.stats = PrivacyRenderStats(
                    removed_active_tags=self.stats.removed_active_tags,
                    removed_event_handlers=self.stats.removed_event_handlers,
                    removed_inline_styles=self.stats.removed_inline_styles,
                    removed_remote_assets=self.stats.removed_remote_assets + 1,
                )
                continue
            clean.append((name, value))
        return clean


def render_privacy_html(html: str) -> tuple[str, PrivacyRenderStats]:
    return PrivacyHtmlRenderer().render(html)


def _format_attrs(attrs: list[tuple[str, str | None]]) -> str:
    if not attrs:
        return ""
    rendered = []
    for name, value in attrs:
        if value is None:
            rendered.append(escape(name, quote=True))
        else:
            rendered.append(f'{escape(name, quote=True)}="{escape(value, quote=True)}"')
    return " " + " ".join(rendered)


def _is_remote_url(value: str) -> bool:
    lower = value.lower()
    return lower.startswith("http://") or lower.startswith("https://") or lower.startswith("//")
