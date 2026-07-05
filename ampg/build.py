from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from .config import GatewayConfig, ProtocolConfig, SiteConfig
from .renderers import PrivacyRenderStats, render_gemtext, render_privacy_html


IGNORED_DIRS = {".git", ".hg", ".svn", ".vscode", "__pycache__"}
IGNORED_SUFFIXES = (".bak", ".tmp", ".swp")


@dataclass(frozen=True)
class BuildResult:
    site_id: str
    protocol: str
    renderer: str
    output_root: Path
    files_written: int
    files_skipped: int = 0
    privacy_stats: PrivacyRenderStats | None = None


def build_gateway(config: GatewayConfig) -> list[BuildResult]:
    results: list[BuildResult] = []
    for site in config.sites:
        _validate_source(site)
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            results.append(build_protocol(site, protocol))
    return results


def build_protocol(site: SiteConfig, protocol: ProtocolConfig) -> BuildResult:
    output_root = site.outputs.root / protocol.name
    _prepare_output_root(output_root)
    if protocol.renderer == "clearnet":
        return _copy_clearnet(site, protocol, output_root)
    if protocol.renderer == "privacy-html":
        return _render_privacy_html_tree(site, protocol, output_root)
    if protocol.renderer == "gemtext":
        return _render_gemtext_tree(site, protocol, output_root)
    raise ValueError(f"{site.id}/{protocol.name}: unsupported renderer {protocol.renderer!r}")


def _copy_clearnet(site: SiteConfig, protocol: ProtocolConfig, output_root: Path) -> BuildResult:
    files_written = 0
    for source_path in _iter_source_files(site.source.path):
        target_path = output_root / source_path.relative_to(site.source.path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        files_written += 1
    return BuildResult(
        site_id=site.id,
        protocol=protocol.name,
        renderer=protocol.renderer,
        output_root=output_root,
        files_written=files_written,
    )


def _render_privacy_html_tree(
    site: SiteConfig, protocol: ProtocolConfig, output_root: Path
) -> BuildResult:
    files_written = 0
    files_skipped = 0
    stats = PrivacyRenderStats()
    max_asset_bytes = int(protocol.options.get("max_asset_bytes", 1024 * 1024))
    script_policy = str(protocol.options.get("script_policy", "strip"))
    if script_policy != "strip":
        raise ValueError(
            f"{site.id}/{protocol.name}: privacy-html only supports script_policy='strip'"
        )
    for source_path in _iter_source_files(site.source.path):
        target_path = output_root / source_path.relative_to(site.source.path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.suffix.lower() in {".html", ".htm"}:
            html = source_path.read_text(encoding="utf-8", errors="replace")
            rendered, file_stats = render_privacy_html(html)
            target_path.write_text(rendered, encoding="utf-8")
            stats = stats.add(file_stats)
        elif source_path.suffix.lower() in {".js", ".map"}:
            files_skipped += 1
            continue
        elif source_path.stat().st_size > max_asset_bytes:
            files_skipped += 1
            continue
        else:
            shutil.copy2(source_path, target_path)
        files_written += 1
    return BuildResult(
        site_id=site.id,
        protocol=protocol.name,
        renderer=protocol.renderer,
        output_root=output_root,
        files_written=files_written,
        files_skipped=files_skipped,
        privacy_stats=stats,
    )


def _render_gemtext_tree(
    site: SiteConfig, protocol: ProtocolConfig, output_root: Path
) -> BuildResult:
    files_written = 0
    files_skipped = 0
    max_asset_bytes = int(protocol.options.get("max_asset_bytes", 1024 * 1024))
    for source_path in _iter_source_files(site.source.path):
        if source_path.suffix.lower() in {".html", ".htm"}:
            target_path = _target_with_suffix(site.source.path, output_root, source_path, ".gmi")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            html = source_path.read_text(encoding="utf-8", errors="replace")
            target_path.write_text(render_gemtext(html, rewrite_link=_rewrite_gemtext_link), encoding="utf-8")
        elif source_path.suffix.lower() in {".js", ".css", ".map"}:
            files_skipped += 1
            continue
        elif source_path.stat().st_size > max_asset_bytes:
            files_skipped += 1
            continue
        else:
            target_path = output_root / source_path.relative_to(site.source.path)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
        files_written += 1
    return BuildResult(
        site_id=site.id,
        protocol=protocol.name,
        renderer=protocol.renderer,
        output_root=output_root,
        files_written=files_written,
        files_skipped=files_skipped,
    )


def _iter_source_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRS for part in rel_parts):
            continue
        if any(part.startswith(".") and part != ".well-known" for part in rel_parts):
            continue
        if path.name.endswith(IGNORED_SUFFIXES) or ".bak." in path.name:
            continue
        yield path


def _validate_source(site: SiteConfig) -> None:
    if not site.source.path.exists():
        raise FileNotFoundError(f"{site.id}: source path does not exist: {site.source.path}")
    if not site.source.path.is_dir():
        raise NotADirectoryError(f"{site.id}: source path is not a directory: {site.source.path}")


def _prepare_output_root(output_root: Path) -> None:
    marker = output_root / ".ampg-output"
    if output_root.exists() and any(output_root.iterdir()) and not marker.exists():
        raise RuntimeError(
            f"refusing to clean non-empty unmarked output directory: {output_root}"
        )
    if marker.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    marker.write_text("generated by AMPG\n", encoding="utf-8")


def _target_with_suffix(source_root: Path, output_root: Path, source_path: Path, suffix: str) -> Path:
    rel_path = source_path.relative_to(source_root)
    return (output_root / rel_path).with_suffix(suffix)


def _rewrite_gemtext_link(href: str) -> str:
    if href.startswith("#"):
        return href
    if href.startswith(("http://", "https://", "gemini://", "mailto:")):
        return href
    path, sep, fragment = href.partition("#")
    if path.endswith(".html") or path.endswith(".htm"):
        path = path.rsplit(".", 1)[0] + ".gmi"
    return path + (sep + fragment if sep else "")
