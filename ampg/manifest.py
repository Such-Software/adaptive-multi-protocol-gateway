from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .config import GatewayConfig, ProtocolConfig, RoutePolicyConfig, SiteConfig


SCHEMA = "ampg.fixture-manifest.v1"
TIER_ORDER = {
    "static": 0,
    "interactive-lite": 1,
    "identity": 2,
    "transactional": 3,
    "realtime": 4,
    "internal": 5,
}
DEFAULT_MAX_TIERS = {
    "clearnet": "realtime",
    "tor": "transactional",
    "i2p": "transactional",
    "gemini": "interactive-lite",
    "ipfs": "static",
    "reticulum": "interactive-lite",
}


@dataclass(frozen=True)
class ManifestWriteResult:
    site_id: str
    path: Path
    fixture_count: int


def fixture_manifest(site: SiteConfig) -> dict[str, Any]:
    fixtures = []
    for protocol in site.protocols.values():
        if not protocol.enabled:
            continue
        fixtures.append(_fixture_entry(site, protocol, None))
        fixtures.extend(
            _fixture_entry(site, protocol, route_policy)
            for route_policy in site.interactions.routes
            if _route_is_public(route_policy) and _route_supported(protocol, route_policy)
        )
    return {
        "schema": SCHEMA,
        "site": {
            "id": site.id,
            "domain": site.domain,
            "canonical_url": site.source.canonical_url or "",
        },
        "fixtures": fixtures,
    }


def write_fixture_manifests(config: GatewayConfig) -> list[ManifestWriteResult]:
    results: list[ManifestWriteResult] = []
    for site in config.sites:
        manifest = fixture_manifest(site)
        path = manifest_path(site)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        results.append(
            ManifestWriteResult(
                site_id=site.id,
                path=path,
                fixture_count=len(manifest["fixtures"]),
            )
        )
    return results


def manifest_path(site: SiteConfig) -> Path:
    return site.outputs.root / "ampg-fixture-manifest.json"


def _fixture_entry(
    site: SiteConfig,
    protocol: ProtocolConfig,
    route_policy: RoutePolicyConfig | None,
) -> dict[str, Any]:
    url, address_status = _fixture_url(site, protocol)
    transport = _transport_for(protocol.name)
    entry = {
        "protocol": protocol.name,
        "renderer": protocol.renderer,
        "url": _url_for_route(url, route_policy),
        "address_status": address_status,
        "output_path": _output_path_for_route(protocol.name, route_policy),
        "checks": {
            "transport": transport,
            "profile": transport,
        },
        "interaction": _interaction_policy(protocol, route_policy),
    }
    if route_policy:
        entry["route"] = {
            "match": route_policy.match,
            "fixture_path": _fixture_path(route_policy.match),
        }
    return entry


def _transport_for(protocol_name: str) -> str:
    if protocol_name in {"clearnet", "tor", "i2p", "gemini", "reticulum", "ipfs"}:
        return protocol_name
    return protocol_name


def _route_is_public(route_policy: RoutePolicyConfig) -> bool:
    return route_policy.public_allowed and route_policy.tier != "internal"


def _route_supported(protocol: ProtocolConfig, route_policy: RoutePolicyConfig) -> bool:
    max_tier = str(protocol.options.get("max_tier", DEFAULT_MAX_TIERS.get(protocol.name, "static")))
    return _tier_rank(route_policy.tier) <= _tier_rank(max_tier)


def _tier_rank(tier: str) -> int:
    try:
        return TIER_ORDER[tier]
    except KeyError as exc:
        raise ValueError(f"unsupported interaction tier {tier!r}") from exc


def _interaction_policy(
    protocol: ProtocolConfig,
    route_policy: RoutePolicyConfig | None,
) -> dict[str, Any]:
    if route_policy:
        return {
            "tier": route_policy.tier,
            "identity": route_policy.identity,
            "payments": route_policy.payments,
            "realtime": route_policy.realtime,
            "public_allowed": route_policy.public_allowed,
        }
    return {
        "tier": str(protocol.options.get("tier", protocol.options.get("max_tier", "static"))),
        "identity": str(protocol.options.get("identity", "none")),
        "payments": str(protocol.options.get("payments", "none")),
        "realtime": bool(protocol.options.get("realtime", False)),
        "public_allowed": bool(protocol.options.get("public_allowed", True)),
    }


def _url_for_route(base_url: str, route_policy: RoutePolicyConfig | None) -> str:
    if not route_policy:
        return base_url
    fixture_path = _fixture_path(route_policy.match)
    if base_url.startswith(("rns://", "lxmf://", "nomad://", "ipfs://", "ipns://")):
        return base_url
    return base_url.rstrip("/") + fixture_path


def _output_path_for_route(protocol_name: str, route_policy: RoutePolicyConfig | None) -> str:
    if not route_policy:
        return protocol_name
    return protocol_name + _fixture_path(route_policy.match)


def _fixture_path(match: str) -> str:
    value = match.strip()
    if not value.startswith("/"):
        value = "/" + value
    value = value.replace("*", "")
    if not value or value == "/":
        return "/"
    return value if value.endswith("/") else value + "/"


def _fixture_url(site: SiteConfig, protocol: ProtocolConfig) -> tuple[str, str]:
    configured_url = protocol.options.get("fixture_url") or protocol.options.get("browser_url")
    if configured_url:
        return _with_trailing_slash(str(configured_url)), "configured"

    if protocol.name == "clearnet":
        if site.source.canonical_url:
            return _with_trailing_slash(site.source.canonical_url), "configured"
        return f"https://{site.domain}/", "derived"

    if protocol.name == "tor":
        onion_url = protocol.options.get("onion_url")
        if onion_url:
            return _with_trailing_slash(str(onion_url)), "configured"
        onion_location = str(protocol.options.get("onion_location", "auto"))
        if onion_location and onion_location != "auto":
            return _with_scheme(onion_location, "http"), "configured"
        return f"http://{site.id}.onion/", "placeholder"

    if protocol.name == "i2p":
        i2p_url = protocol.options.get("i2p_url") or protocol.options.get("i2p_hostname")
        if i2p_url:
            return _with_scheme(str(i2p_url), "http"), "configured"
        return f"http://{site.id}.i2p/", "placeholder"

    if protocol.name == "gemini":
        gemini_url = protocol.options.get("gemini_url")
        if gemini_url:
            return _with_scheme(str(gemini_url), "gemini"), "configured"
        return f"gemini://{site.domain}/", "derived"

    if protocol.name == "reticulum":
        rns_url = protocol.options.get("rns_url")
        if rns_url:
            return _with_scheme(str(rns_url), "rns"), "configured"
        return f"rns://{site.id}", "placeholder"

    if protocol.name == "ipfs":
        ipfs_url = protocol.options.get("ipfs_url")
        if ipfs_url:
            return _with_scheme(str(ipfs_url), "ipfs"), "configured"
        cid = protocol.options.get("cid")
        if cid:
            return f"ipfs://{cid}", "configured"
        return f"/ipfs/{site.id}", "placeholder"

    return f"https://{site.domain}/", "derived"


def _with_scheme(value: str, scheme: str) -> str:
    if "://" in value:
        return _with_trailing_slash(value)
    return _with_trailing_slash(f"{scheme}://{value}")


def _with_trailing_slash(value: str) -> str:
    if value.startswith(("rns://", "lxmf://", "nomad://", "ipfs://", "ipns://")):
        return value
    if value.endswith("/"):
        return value
    return value + "/"
