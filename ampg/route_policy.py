from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase

from .config import GatewayConfig, ProtocolConfig, RoutePolicyConfig, SiteConfig


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
class RouteExposure:
    site_id: str
    protocol: str
    route_index: int
    match: str
    source: str
    tier: str
    identity: str
    payments: str
    realtime: bool
    public_allowed: bool
    max_tier: str
    status: str
    reason: str


@dataclass(frozen=True)
class RouteIssue:
    site_id: str
    route_index: int
    match: str
    source: str
    tier: str
    code: str
    message: str


def route_exposures(config: GatewayConfig) -> list[RouteExposure]:
    exposures: list[RouteExposure] = []
    for site in config.sites:
        enabled_protocols = [protocol for protocol in site.protocols.values() if protocol.enabled]
        for route_index, route_policy in enumerate(site.interactions.routes):
            for protocol in enabled_protocols:
                status, reason = route_decision(site, protocol, route_policy)
                exposures.append(
                    RouteExposure(
                        site_id=site.id,
                        protocol=protocol.name,
                        route_index=route_index,
                        match=route_policy.match,
                        source=route_policy.source,
                        tier=route_policy.tier,
                        identity=route_policy.identity,
                        payments=route_policy.payments,
                        realtime=route_policy.realtime,
                        public_allowed=route_policy.public_allowed,
                        max_tier=protocol_max_tier(protocol),
                        status=status,
                        reason=reason,
                    )
                )
    return exposures


def route_issues(config: GatewayConfig) -> list[RouteIssue]:
    issues: list[RouteIssue] = []
    exposures = route_exposures(config)
    by_site_route_index = {
        (exposure.site_id, exposure.route_index): []
        for exposure in exposures
    }
    for exposure in exposures:
        by_site_route_index[(exposure.site_id, exposure.route_index)].append(exposure)

    for site in config.sites:
        for route_index, route_policy in enumerate(site.interactions.routes):
            if not route_has_public_intent(site, route_policy):
                continue
            decisions = by_site_route_index.get((site.id, route_index), [])
            if any(decision.status == "exposed" for decision in decisions):
                continue
            issues.append(
                RouteIssue(
                    site_id=site.id,
                    route_index=route_index,
                    match=route_policy.match,
                    source=route_policy.source,
                    tier=route_policy.tier,
                    code="no-compatible-protocol",
                    message="public route is not exposed by any enabled protocol",
                )
            )
    return issues


def route_exposed(site: SiteConfig, protocol: ProtocolConfig, route_policy: RoutePolicyConfig) -> bool:
    status, _reason = route_decision(site, protocol, route_policy)
    return status == "exposed"


def route_decision(
    site: SiteConfig,
    protocol: ProtocolConfig,
    route_policy: RoutePolicyConfig,
) -> tuple[str, str]:
    if route_policy.tier == "internal":
        return "skipped", "tier is internal"
    if not route_policy.public_allowed:
        return "skipped", "public_allowed=false"

    deny_route = denied_by(site, route_policy)
    if deny_route:
        return "skipped", f"matched deny_route {deny_route}"

    max_tier = protocol_max_tier(protocol)
    if tier_rank(route_policy.tier) > tier_rank(max_tier):
        return "skipped", f"tier {route_policy.tier} exceeds protocol max_tier {max_tier}"

    return "exposed", "public route within protocol max_tier"


def route_has_public_intent(site: SiteConfig, route_policy: RoutePolicyConfig) -> bool:
    return (
        route_policy.tier != "internal"
        and route_policy.public_allowed
        and denied_by(site, route_policy) is None
    )


def denied_by(site: SiteConfig, route_policy: RoutePolicyConfig) -> str | None:
    route_variants = _pattern_variants(route_policy.match)
    for deny_route in site.interactions.deny_routes:
        deny_pattern = _normalize_pattern(deny_route)
        if any(fnmatchcase(route_variant, deny_pattern) for route_variant in route_variants):
            return deny_route
    return None


def protocol_max_tier(protocol: ProtocolConfig) -> str:
    return str(protocol.options.get("max_tier", DEFAULT_MAX_TIERS.get(protocol.name, "static")))


def tier_rank(tier: str) -> int:
    try:
        return TIER_ORDER[tier]
    except KeyError as exc:
        raise ValueError(f"unsupported interaction tier {tier!r}") from exc


def fixture_path(match: str) -> str:
    value = _normalize_pattern(match).replace("*", "")
    if not value or value == "/":
        return "/"
    return value if value.endswith("/") else value + "/"


def _pattern_variants(pattern: str) -> tuple[str, ...]:
    normalized = _normalize_pattern(pattern)
    fixture = fixture_path(pattern)
    trimmed = fixture.rstrip("/") or "/"
    return tuple(dict.fromkeys((normalized, fixture, trimmed)))


def _normalize_pattern(pattern: str) -> str:
    value = pattern.strip()
    if not value.startswith("/"):
        value = "/" + value
    return value
