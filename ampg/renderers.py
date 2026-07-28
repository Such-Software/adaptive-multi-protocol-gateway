from __future__ import annotations

from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import re
from typing import Callable


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


class GemtextRenderer(HTMLParser):
    def __init__(self, rewrite_link: Callable[[str], str] | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.rewrite_link = rewrite_link or (lambda href: href)
        self.lines: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.skip_stack: list[str] = []
        self.heading_level: int | None = None
        self.list_depth = 0
        self.anchor_stack: list[tuple[str, list[str]]] = []
        self.in_pre = False
        self.pre_parts: list[str] = []

    def render(self, html: str) -> str:
        self.feed(html)
        self.close()
        self._flush_block()
        return _squash_blank_lines(self.lines)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {name.lower(): value for name, value in attrs}
        if tag in ACTIVE_TAGS or tag in {"nav", "noscript", "svg"}:
            self.skip_stack.append(tag)
            return
        if self.skip_stack:
            return
        if tag in {"p", "div", "section", "article", "header", "footer"}:
            self._flush_block()
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_block()
            self.heading_level = min(int(tag[1]), 3)
        elif tag == "li":
            self._flush_block()
            self.list_depth += 1
        elif tag == "br":
            self._append_text(" ")
        elif tag == "a":
            href = attrs_dict.get("href")
            if href:
                self.anchor_stack.append((href, []))
        elif tag == "img":
            src = attrs_dict.get("src")
            alt = attrs_dict.get("alt") or "image"
            if src:
                self.links.append((self.rewrite_link(src), f"Image: {_normalize_text(alt)}"))
        elif tag == "pre":
            self._flush_block()
            self.in_pre = True
            self.pre_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_stack:
            if self.skip_stack[-1] == tag:
                self.skip_stack.pop()
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_block()
            self.heading_level = None
        elif tag in {"p", "div", "section", "article", "header", "footer"}:
            self._flush_block()
        elif tag == "li":
            self._flush_block(prefix="- ")
            self.list_depth = max(0, self.list_depth - 1)
        elif tag == "a" and self.anchor_stack:
            href, parts = self.anchor_stack.pop()
            label = _normalize_text("".join(parts)) or href
            self.links.append((self.rewrite_link(href), label))
        elif tag == "pre" and self.in_pre:
            self.lines.append("```")
            self.lines.extend("".join(self.pre_parts).strip("\n").splitlines())
            self.lines.append("```")
            self.lines.append("")
            self.in_pre = False
            self.pre_parts = []

    def handle_data(self, data: str) -> None:
        if self.skip_stack:
            return
        if self.in_pre:
            self.pre_parts.append(data)
            return
        self._append_text(data)

    def _append_text(self, data: str) -> None:
        if self.anchor_stack:
            self.anchor_stack[-1][1].append(data)
        self.text_parts.append(data)

    def _flush_block(self, prefix: str = "") -> None:
        text = _normalize_text("".join(self.text_parts))
        if text:
            if self.heading_level is not None:
                self.lines.append(f"{'#' * self.heading_level} {text}")
            else:
                self.lines.append(f"{prefix}{text}")
        for href, label in self.links:
            if href.startswith("#"):
                continue
            self.lines.append(f"=> {href} {label}")
        if text or self.links:
            self.lines.append("")
        self.text_parts = []
        self.links = []


def render_gemtext(html: str, rewrite_link: Callable[[str], str] | None = None) -> str:
    return GemtextRenderer(rewrite_link=rewrite_link).render(html)


MICRON_STRUCTURAL_PREFIXES = (">", "<", "#", "-")


def micron_escape(text: str) -> str:
    """Escape inline text so micron renders it literally.

    Micron's control character is the backtick, so an unescaped one in content
    would open a formatting or link run. Escapes with a preceding backslash.
    Line-leading structural characters are handled separately at line emission
    (see `_escape_line_start`), because whether a character is structural
    depends on it landing at column 0, not on which chunk it arrived in.
    """
    return text.replace("\\", "\\\\").replace("`", "\\`")


def _escape_line_start(line: str) -> str:
    """Neutralize a structural character at column 0 of an emitted line.

    `>` is a heading, `<` resets heading depth, `#` is a comment, and `-` is a
    divider. Without this, a vendor named ">Free Beer" silently becomes a
    section heading on the published page.
    """
    if line[:1] in MICRON_STRUCTURAL_PREFIXES:
        return "\\" + line
    return line


class MicronRenderer(HTMLParser):
    """Render HTML into micron, the markup Nomad Network nodes serve.

    Micron is NOT Gemtext. Headings are `>` / `>>` / `>>>` by depth, links are
    inline as ```[label`url]`` rather than standalone lines, emphasis is a
    toggle pair, and literal blocks are fenced with ```=``. Reference: the
    ``TOPIC_MARKUP`` section of NomadNet's in-app guide, which is the only
    specification that exists.

    Emitting Gemtext into a `.mu` file (which this function used to do) produces
    a page that a Nomad Network browser renders as raw punctuation.
    """

    def __init__(self, rewrite_link: Callable[[str], str] | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.rewrite_link = rewrite_link or (lambda href: href)
        self.lines: list[str] = []
        self.text_parts: list[str] = []
        self.skip_stack: list[str] = []
        self.heading_level: int | None = None
        self.anchor_stack: list[tuple[str, list[str]]] = []
        self.in_pre = False
        self.pre_parts: list[str] = []

    def render(self, html: str) -> str:
        self.feed(html)
        self.close()
        self._flush_block()
        return _squash_blank_lines(self.lines)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {name.lower(): value for name, value in attrs}
        if tag in ACTIVE_TAGS or tag in {"nav", "noscript", "svg"}:
            self.skip_stack.append(tag)
            return
        if self.skip_stack:
            return
        if tag in {"p", "div", "section", "article", "header", "footer"}:
            self._flush_block()
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_block()
            self.heading_level = min(int(tag[1]), 3)
        elif tag == "li":
            self._flush_block()
        elif tag == "br":
            self._append_text(" ")
        elif tag == "hr":
            self._flush_block()
            self.lines.append("-")
        elif tag in {"strong", "b"}:
            self.text_parts.append("`!")
        elif tag in {"em", "i"}:
            self.text_parts.append("`*")
        elif tag == "a":
            href = attrs_dict.get("href")
            if href:
                self.anchor_stack.append((href, []))
        elif tag == "img":
            src = attrs_dict.get("src")
            alt = attrs_dict.get("alt") or "image"
            if src:
                self._emit_link(self.rewrite_link(src), f"Image: {_normalize_text(alt)}")
        elif tag == "pre":
            self._flush_block()
            self.in_pre = True
            self.pre_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_stack:
            if self.skip_stack[-1] == tag:
                self.skip_stack.pop()
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_block()
            self.heading_level = None
        elif tag in {"p", "div", "section", "article", "header", "footer", "li"}:
            self._flush_block(prefix=" - " if tag == "li" else "")
        elif tag in {"strong", "b"}:
            self.text_parts.append("`!")
        elif tag in {"em", "i"}:
            self.text_parts.append("`*")
        elif tag == "a" and self.anchor_stack:
            href, parts = self.anchor_stack.pop()
            label = _normalize_text("".join(parts)) or href
            self._emit_link(self.rewrite_link(href), label)
        elif tag == "pre" and self.in_pre:
            # Literal block: content is emitted verbatim, so it must NOT be escaped.
            self.lines.append("`=")
            self.lines.extend("".join(self.pre_parts).strip("\n").splitlines())
            self.lines.append("`=")
            self.lines.append("")
            self.in_pre = False
            self.pre_parts = []

    def handle_data(self, data: str) -> None:
        if self.skip_stack:
            return
        if self.in_pre:
            self.pre_parts.append(data)
            return
        self._append_text(data)

    def _append_text(self, data: str) -> None:
        if self.anchor_stack:
            self.anchor_stack[-1][1].append(data)
            return
        self.text_parts.append(micron_escape(data))

    def _emit_link(self, href: str, label: str) -> None:
        # In-page anchors have no meaning on a Nomad node; drop the link, keep the text.
        if href.startswith("#"):
            self.text_parts.append(micron_escape(label))
            return
        self.text_parts.append(f"`[{micron_escape(label)}`{micron_escape(href)}]")

    def _flush_block(self, prefix: str = "") -> None:
        text = _normalize_text("".join(self.text_parts))
        if text:
            if self.heading_level is not None:
                self.lines.append(f"{'>' * self.heading_level}{text}")
            elif prefix:
                self.lines.append(f"{prefix}{text}")
            else:
                self.lines.append(_escape_line_start(text))
            self.lines.append("")
        self.text_parts = []


def render_micron(html: str, rewrite_link: Callable[[str], str] | None = None) -> str:
    return MicronRenderer(rewrite_link=rewrite_link).render(html)


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


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _squash_blank_lines(lines: list[str]) -> str:
    output: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        output.append(line.rstrip())
        previous_blank = blank
    while output and not output[-1]:
        output.pop()
    return "\n".join(output) + "\n"
