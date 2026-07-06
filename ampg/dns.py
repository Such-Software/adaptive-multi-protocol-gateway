from __future__ import annotations

from dataclasses import dataclass
import socket

from .config import GatewayConfig


DNS_MODES = ("static", "dynamic")


@dataclass(frozen=True)
class DNSRecordPlan:
    site_id: str
    domain: str
    name: str
    type: str
    value: str
    status: str
    message: str


@dataclass(frozen=True)
class ConnectivityHint:
    method: str
    status: str
    command: str
    message: str


@dataclass(frozen=True)
class DNSPlan:
    status: str
    records: tuple[DNSRecordPlan, ...]
    hints: tuple[ConnectivityHint, ...]
    message: str


@dataclass(frozen=True)
class DNSCheckResult:
    site_id: str
    domain: str
    family: str
    expected: str
    resolved: tuple[str, ...]
    status: str
    message: str


def dns_plan(
    config: GatewayConfig,
    *,
    mode: str = "static",
    ipv4: str | None = None,
    ipv6: str | None = None,
    dynamic_hostname: str | None = None,
    behind_router: bool = False,
) -> DNSPlan:
    if mode not in DNS_MODES:
        raise ValueError(f"unsupported DNS mode {mode!r}")
    domains = _clearnet_sites(config)
    if not domains:
        return DNSPlan(
            status="skipped",
            records=(),
            hints=(),
            message="clearnet is not selected",
        )

    records: list[DNSRecordPlan] = []
    for site_id, domain in domains:
        if mode == "static":
            records.extend(_static_records(site_id, domain, ipv4=ipv4, ipv6=ipv6))
        else:
            records.extend(_dynamic_records(site_id, domain, dynamic_hostname=dynamic_hostname))
    hints = _connectivity_hints(behind_router=behind_router)
    status = _plan_status([record.status for record in records] + [hint.status for hint in hints])
    return DNSPlan(
        status=status,
        records=tuple(records),
        hints=tuple(hints),
        message=_plan_message(status),
    )


def dns_check(
    config: GatewayConfig,
    *,
    ipv4: str | None = None,
    ipv6: str | None = None,
    resolver=None,
) -> list[DNSCheckResult]:
    resolver = resolver or _resolve_domain
    results: list[DNSCheckResult] = []
    for site_id, domain in _clearnet_sites(config):
        resolved = resolver(domain)
        if ipv4:
            ipv4_values = tuple(value for value in resolved if _looks_ipv4(value))
            results.append(_check_result(site_id, domain, "A", ipv4, ipv4_values))
        if ipv6:
            ipv6_values = tuple(value for value in resolved if _looks_ipv6(value))
            results.append(_check_result(site_id, domain, "AAAA", ipv6, ipv6_values))
        if not ipv4 and not ipv6:
            results.append(
                DNSCheckResult(
                    site_id=site_id,
                    domain=domain,
                    family="any",
                    expected="-",
                    resolved=tuple(sorted(resolved)),
                    status="resolved" if resolved else "missing",
                    message="domain resolves" if resolved else "domain did not resolve",
                )
            )
    return results


def _static_records(
    site_id: str,
    domain: str,
    *,
    ipv4: str | None,
    ipv6: str | None,
) -> list[DNSRecordPlan]:
    records: list[DNSRecordPlan] = []
    if ipv4:
        records.append(
            DNSRecordPlan(
                site_id,
                domain,
                "@",
                "A",
                ipv4,
                "todo",
                "create or update apex IPv4 record",
            )
        )
    if ipv6:
        records.append(
            DNSRecordPlan(
                site_id,
                domain,
                "@",
                "AAAA",
                ipv6,
                "todo",
                "create or update apex IPv6 record",
            )
        )
    if not ipv4 and not ipv6:
        records.append(
            DNSRecordPlan(
                site_id,
                domain,
                "@",
                "A/AAAA",
                "<server-public-ip>",
                "review",
                "choose a stable public IPv4 or IPv6 address for this server",
            )
        )
    records.append(
        DNSRecordPlan(
            site_id,
            domain,
            "www",
            "CNAME",
            domain,
            "todo",
            "point www at the apex domain",
        )
    )
    return records


def _dynamic_records(
    site_id: str,
    domain: str,
    *,
    dynamic_hostname: str | None,
) -> list[DNSRecordPlan]:
    if not dynamic_hostname:
        return [
            DNSRecordPlan(
                site_id,
                domain,
                "@",
                "dynamic",
                "<dynamic-hostname>",
                "review",
                "choose a dynamic DNS hostname or provider API update target",
            )
        ]
    return [
        DNSRecordPlan(
            site_id,
            domain,
            "www",
            "CNAME",
            dynamic_hostname,
            "todo",
            "point www at the dynamic DNS hostname",
        ),
        DNSRecordPlan(
            site_id,
            domain,
            "@",
            "ALIAS/ANAME",
            dynamic_hostname,
            "review",
            "apex dynamic DNS is provider-specific; use ALIAS/ANAME or API-updated A/AAAA",
        ),
    ]


def _connectivity_hints(*, behind_router: bool) -> tuple[ConnectivityHint, ...]:
    if not behind_router:
        return (
            ConnectivityHint(
                "public-ingress",
                "review",
                "allow inbound TCP 80 and 443 to this host",
                "clearnet needs HTTP/HTTPS traffic to reach the server",
            ),
        )
    return (
        ConnectivityHint(
            "port-forward",
            "review",
            "forward router TCP 80 and 443 to this host",
            "best simple option when you control the router",
        ),
        ConnectivityHint(
            "ipv6",
            "review",
            "allow inbound TCP 80 and 443 to this host IPv6 address",
            "public IPv6 can avoid IPv4 NAT when the ISP provides it",
        ),
        ConnectivityHint(
            "pcp-natpmp-upnp",
            "review",
            "request router port mappings only after explicit approval",
            "automatic router mapping can help but must be opt-in",
        ),
        ConnectivityHint(
            "reverse-tunnel",
            "review",
            "route 80/443 through a VPS or managed tunnel to this host",
            "useful when port forwarding is impossible or CGNAT is present",
        ),
        ConnectivityHint(
            "dns-01-acme",
            "review",
            "use DNS-01 certificate validation when inbound port 80 is unavailable",
            "lets HTTPS certificates work even before direct inbound HTTP is reachable",
        ),
    )


def _check_result(
    site_id: str,
    domain: str,
    family: str,
    expected: str,
    resolved: tuple[str, ...],
) -> DNSCheckResult:
    if expected in resolved:
        return DNSCheckResult(
            site_id,
            domain,
            family,
            expected,
            tuple(sorted(resolved)),
            "matched",
            "DNS record matches expected value",
        )
    if resolved:
        return DNSCheckResult(
            site_id,
            domain,
            family,
            expected,
            tuple(sorted(resolved)),
            "mismatch",
            "domain resolves, but not to the expected value",
        )
    return DNSCheckResult(
        site_id,
        domain,
        family,
        expected,
        (),
        "missing",
        "domain did not resolve for this record family",
    )


def _clearnet_sites(config: GatewayConfig) -> list[tuple[str, str]]:
    return [
        (site.id, site.domain)
        for site in config.sites
        if "clearnet" in site.protocols and site.protocols["clearnet"].enabled
    ]


def _resolve_domain(domain: str) -> set[str]:
    try:
        results = socket.getaddrinfo(domain, None)
    except OSError:
        return set()
    return {item[4][0] for item in results}


def _looks_ipv4(value: str) -> bool:
    return "." in value


def _looks_ipv6(value: str) -> bool:
    return ":" in value


def _plan_status(statuses: list[str]) -> str:
    if "blocked" in statuses:
        return "blocked"
    if "todo" in statuses:
        return "todo"
    if "review" in statuses:
        return "review"
    return "ready"


def _plan_message(status: str) -> str:
    if status == "blocked":
        return "DNS setup has blockers"
    if status == "todo":
        return "DNS records or connectivity steps are ready to configure"
    if status == "review":
        return "DNS setup needs operator choices"
    if status == "skipped":
        return "clearnet DNS is not needed"
    return "DNS setup is ready"
