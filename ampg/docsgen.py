from __future__ import annotations

from pathlib import Path

from .metadata import CONFIG_FIELDS, DAEMON_ADAPTERS, RENDER_PROFILES


GENERATED_DIR = Path("docs/generated")


def generate_docs(root: Path, *, check: bool = False) -> list[Path]:
    docs = {
        GENERATED_DIR / "config-schema.md": _config_schema_doc(),
        GENERATED_DIR / "daemon-adapters.md": _daemon_adapters_doc(),
        GENERATED_DIR / "render-profiles.md": _render_profiles_doc(),
    }
    changed: list[Path] = []
    for rel_path, content in docs.items():
        path = root / rel_path
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        changed.append(rel_path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    if check and changed:
        names = ", ".join(str(path) for path in changed)
        raise RuntimeError(f"generated docs are stale: {names}")
    return changed


def _header(title: str) -> str:
    return (
        f"# {title}\n\n"
        "> Status: generated | Updated by `python3 -m ampg docs generate` | Applies to: AMPG\n\n"
        "This file is generated from code. Do not edit it by hand.\n\n"
    )


def _config_schema_doc() -> str:
    rows = [
        "| Section | Field | Type | Required | Default | Description |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for field in CONFIG_FIELDS:
        rows.append(
            "| "
            f"{field.section} | "
            f"`{field.field}` | "
            f"{field.kind} | "
            f"{'yes' if field.required else 'no'} | "
            f"{field.default or '-'} | "
            f"{field.description} |"
        )
    return _header("Generated Config Schema") + "\n".join(rows) + "\n"


def _daemon_adapters_doc() -> str:
    sections = [_header("Generated Daemon Adapters")]
    for adapter in DAEMON_ADAPTERS:
        sections.append(f"## {adapter.daemon}\n")
        sections.append(f"- Protocols: {', '.join(adapter.protocols)}")
        sections.append(f"- Default policy: `{adapter.default_policy}`")
        sections.append(f"- Generated artifacts: {', '.join(adapter.generated_artifacts)}")
        sections.append("")
        sections.append("Notes:")
        for note in adapter.notes:
            sections.append(f"- {note}")
        sections.append("")
    return "\n".join(sections)


def _render_profiles_doc() -> str:
    sections = [_header("Generated Render Profiles")]
    for profile in RENDER_PROFILES:
        sections.append(f"## {profile.name}\n")
        sections.append(profile.summary)
        sections.append("")
        sections.append(f"- Output: {profile.output}")
        sections.append("")
        sections.append("Defaults:")
        for default in profile.defaults:
            sections.append(f"- {default}")
        sections.append("")
    return "\n".join(sections)
