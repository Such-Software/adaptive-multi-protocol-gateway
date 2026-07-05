from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib


DEFAULT_DAEMONS = {
    "clearnet": "nginx",
    "tor": "tor",
    "i2p": "i2pd",
    "gemini": "agate",
    "reticulum": "rnsd",
}

DEFAULT_POLICIES = {
    "clearnet": "adopt",
    "tor": "auto",
    "i2p": "auto",
    "gemini": "auto",
    "reticulum": "auto",
}


@dataclass(frozen=True)
class SourceConfig:
    kind: str
    path: Path
    canonical_url: str | None = None


@dataclass(frozen=True)
class OutputConfig:
    root: Path


@dataclass(frozen=True)
class ProtocolConfig:
    name: str
    enabled: bool
    renderer: str
    daemon: str
    daemon_policy: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SiteConfig:
    id: str
    domain: str
    source: SourceConfig
    outputs: OutputConfig
    protocols: dict[str, ProtocolConfig]


@dataclass(frozen=True)
class GatewayConfig:
    config_path: Path
    sites: list[SiteConfig]


def load_config(path: Path) -> GatewayConfig:
    config_path = path.resolve()
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    sites = [_parse_site(raw_site, config_path.parent) for raw_site in data.get("site", [])]
    if not sites:
        raise ValueError("config must declare at least one [[site]]")
    return GatewayConfig(config_path=config_path, sites=sites)


def _parse_site(raw_site: dict[str, Any], base_dir: Path) -> SiteConfig:
    source = raw_site.get("source") or {}
    outputs = raw_site.get("outputs") or {}
    protocols = raw_site.get("protocols") or {}

    site_id = _required_str(raw_site, "id")
    domain = _required_str(raw_site, "domain")
    source_kind = _required_str(source, "kind")
    if source_kind != "static-html":
        raise ValueError(f"{site_id}: unsupported source kind {source_kind!r}")

    source_path = _resolve_path(base_dir, _required_str(source, "path"))
    output_root = _resolve_path(base_dir, _required_str(outputs, "root"))

    parsed_protocols = {
        name: _parse_protocol(name, raw_protocol)
        for name, raw_protocol in protocols.items()
        if isinstance(raw_protocol, dict)
    }

    return SiteConfig(
        id=site_id,
        domain=domain,
        source=SourceConfig(
            kind=source_kind,
            path=source_path,
            canonical_url=source.get("canonical_url"),
        ),
        outputs=OutputConfig(root=output_root),
        protocols=parsed_protocols,
    )


def _parse_protocol(name: str, raw_protocol: dict[str, Any]) -> ProtocolConfig:
    enabled = bool(raw_protocol.get("enabled", False))
    renderer = str(raw_protocol.get("renderer", name))
    daemon = str(raw_protocol.get("daemon", DEFAULT_DAEMONS.get(name, name)))
    policy = str(raw_protocol.get("daemon_policy", DEFAULT_POLICIES.get(name, "auto")))
    options = dict(raw_protocol)
    for key in ("enabled", "renderer", "daemon", "daemon_policy"):
        options.pop(key, None)
    return ProtocolConfig(
        name=name,
        enabled=enabled,
        renderer=renderer,
        daemon=daemon,
        daemon_policy=policy,
        options=options,
    )


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing required string field {key!r}")
    return value
