from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib

from .route_manifest import load_route_manifest

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
    source: str = "config"


@dataclass(frozen=True)
class InteractionConfig:
    default_tier: str = "static"
    deny_routes: tuple[str, ...] = ()
    routes: tuple[RoutePolicyConfig, ...] = ()
    route_manifest: Path | None = None


@dataclass(frozen=True)
class SiteConfig:
    id: str
    domain: str
    source: SourceConfig
    outputs: OutputConfig
    protocols: dict[str, ProtocolConfig]
    interactions: InteractionConfig


@dataclass(frozen=True)
class ProfileConfig:
    name: str
    protocols: tuple[str, ...] = ()
    platform: str | None = None
    write_artifacts: bool = False
    description: str = ""


@dataclass(frozen=True)
class GatewayConfig:
    config_path: Path
    sites: list[SiteConfig]
    profiles: dict[str, ProfileConfig] = field(default_factory=dict)


def load_config(path: Path) -> GatewayConfig:
    config_path = path.resolve()
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    sites = [_parse_site(raw_site, config_path.parent) for raw_site in data.get("site", [])]
    if not sites:
        raise ValueError("config must declare at least one [[site]]")
    profiles = _parse_profiles(data.get("profiles", {}))
    return GatewayConfig(config_path=config_path, sites=sites, profiles=profiles)


def _parse_profiles(raw_profiles: Any) -> dict[str, ProfileConfig]:
    if raw_profiles is None:
        return {}
    if not isinstance(raw_profiles, dict):
        raise ValueError("profiles must be a table")
    profiles: dict[str, ProfileConfig] = {}
    for name, raw_profile in raw_profiles.items():
        if not isinstance(raw_profile, dict):
            raise ValueError(f"profile {name!r} must be a table")
        platform = raw_profile.get("platform")
        if platform is not None and not isinstance(platform, str):
            raise ValueError(f"profile {name!r}.platform must be a string")
        description = raw_profile.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"profile {name!r}.description must be a string")
        profiles[str(name)] = ProfileConfig(
            name=str(name),
            protocols=_string_array(
                raw_profile.get("protocols", ()),
                f"profile {name!r}.protocols",
            ),
            platform=platform,
            write_artifacts=bool(raw_profile.get("write_artifacts", False)),
            description=description,
        )
    return profiles


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
        interactions=_parse_interactions(interactions, base_dir, site_id),
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


def _parse_interactions(
    raw_interactions: dict[str, Any],
    base_dir: Path,
    site_id: str,
) -> InteractionConfig:
    if not isinstance(raw_interactions, dict):
        raise ValueError("site.interactions must be a table")

    route_manifest = _route_manifest_path(raw_interactions, base_dir)
    manifest_data = load_route_manifest(route_manifest, site_id=site_id) if route_manifest else {}

    default_tier = str(
        raw_interactions.get("default_tier", manifest_data.get("default_tier", "static"))
    )
    deny_routes = _string_array(manifest_data.get("deny_routes", ()), "route manifest deny_routes")
    deny_routes += _string_array(raw_interactions.get("deny_routes", ()), "site.interactions.deny_routes")
    routes = tuple(
        _parse_route_policy(raw_route, default_tier, source="route-manifest")
        for raw_route in _route_array(manifest_data.get("routes", ()), "route manifest routes")
    )
    routes += tuple(
        _parse_route_policy(raw_route, default_tier, source="config")
        for raw_route in _route_array(raw_interactions.get("route", ()), "site.interactions.route")
    )
    return InteractionConfig(
        default_tier=default_tier,
        deny_routes=tuple(deny_routes),
        routes=routes,
        route_manifest=route_manifest,
    )


def _parse_route_policy(
    raw_route: dict[str, Any],
    default_tier: str,
    *,
    source: str,
) -> RoutePolicyConfig:
    if not isinstance(raw_route, dict):
        raise ValueError("route policy entries must be objects")
    return RoutePolicyConfig(
        match=_required_str(raw_route, "match"),
        tier=str(raw_route.get("tier", default_tier)),
        identity=str(raw_route.get("identity", "none")),
        payments=str(raw_route.get("payments", "none")),
        realtime=bool(raw_route.get("realtime", False)),
        public_allowed=bool(raw_route.get("public_allowed", True)),
        source=source,
    )


def _route_manifest_path(raw_interactions: dict[str, Any], base_dir: Path) -> Path | None:
    raw_path = raw_interactions.get("route_manifest")
    if raw_path is None:
        return None
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("site.interactions.route_manifest must be a path string")
    return _resolve_path(base_dir, raw_path)


def _route_array(raw_routes: Any, context: str) -> tuple[Any, ...]:
    if isinstance(raw_routes, dict):
        return (raw_routes,)
    if raw_routes is None:
        return ()
    if not isinstance(raw_routes, (list, tuple)):
        raise ValueError(f"{context} must be an array")
    return tuple(raw_routes)


def _string_array(raw_values: Any, context: str) -> tuple[str, ...]:
    if raw_values is None:
        return ()
    if not isinstance(raw_values, (list, tuple)):
        raise ValueError(f"{context} must be an array")
    return tuple(str(value) for value in raw_values)


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
