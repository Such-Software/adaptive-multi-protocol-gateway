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
    "ipfs": "ipfs",
}

DEFAULT_POLICIES = {
    "clearnet": "adopt",
    "tor": "auto",
    "i2p": "auto",
    "gemini": "auto",
    "reticulum": "auto",
    "ipfs": "auto",
}


@dataclass(frozen=True)
class SourceConfig:
    kind: str
    path: Path
    canonical_url: str | None = None


@dataclass(frozen=True)
class OutputConfig:
    root: Path
    plan_root: Path


@dataclass(frozen=True)
class ProtocolConfig:
    name: str
    enabled: bool
    renderer: str
    daemon: str
    daemon_policy: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutePolicyConfig:
    match: str
    tier: str
    identity: str = "none"
    payments: str = "none"
    realtime: bool = False
    public_allowed: bool = True


@dataclass(frozen=True)
class InteractionConfig:
    default_tier: str = "static"
    deny_routes: tuple[str, ...] = ()
    routes: tuple[RoutePolicyConfig, ...] = ()


@dataclass(frozen=True)
class SiteConfig:
    id: str
    domain: str
    source: SourceConfig
    outputs: OutputConfig
    protocols: dict[str, ProtocolConfig]
    interactions: InteractionConfig


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
    interactions = raw_site.get("interactions") or {}

    site_id = _required_str(raw_site, "id")
    domain = _required_str(raw_site, "domain")
    source_kind = _required_str(source, "kind")
    if source_kind != "static-html":
        raise ValueError(f"{site_id}: unsupported source kind {source_kind!r}")

    source_path = _resolve_path(base_dir, _required_str(source, "path"))
    output_root = _resolve_path(base_dir, _required_str(outputs, "root"))
    plan_root = _resolve_path(base_dir, str(outputs.get("plan_root", "../dist/ampg-plan")))

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
        outputs=OutputConfig(root=output_root, plan_root=plan_root),
        protocols=parsed_protocols,
        interactions=_parse_interactions(interactions),
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


def _parse_interactions(raw_interactions: dict[str, Any]) -> InteractionConfig:
    raw_routes = raw_interactions.get("route", ())
    if isinstance(raw_routes, dict):
        raw_routes = (raw_routes,)
    if not isinstance(raw_routes, (list, tuple)):
        raise ValueError("site.interactions.route must be a table array")
    deny_routes = raw_interactions.get("deny_routes", ())
    if not isinstance(deny_routes, (list, tuple)):
        raise ValueError("site.interactions.deny_routes must be an array")
    return InteractionConfig(
        default_tier=str(raw_interactions.get("default_tier", "static")),
        deny_routes=tuple(str(route) for route in deny_routes),
        routes=tuple(_parse_route_policy(raw_route) for raw_route in raw_routes),
    )


def _parse_route_policy(raw_route: dict[str, Any]) -> RoutePolicyConfig:
    if not isinstance(raw_route, dict):
        raise ValueError("site.interactions.route entries must be tables")
    return RoutePolicyConfig(
        match=_required_str(raw_route, "match"),
        tier=str(raw_route.get("tier", "static")),
        identity=str(raw_route.get("identity", "none")),
        payments=str(raw_route.get("payments", "none")),
        realtime=bool(raw_route.get("realtime", False)),
        public_allowed=bool(raw_route.get("public_allowed", True)),
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
