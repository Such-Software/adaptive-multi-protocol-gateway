from __future__ import annotations

from dataclasses import dataclass
import datetime as _datetime
import os
from pathlib import Path
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .config import GatewayConfig, SiteConfig
from .addresses import effective_address_records


DNS_MODES = ("static", "dynamic")
DNS_PROVIDERS = ("namecheap",)
DNS_MAIL_POLICIES = ("preserve", "disabled")
DEFAULT_TTL = 1800
NAMECHEAP_SUPPORTED_RECORD_TYPES = {
    "A",
    "AAAA",
    "ALIAS",
    "CAA",
    "CNAME",
    "MX",
    "MXE",
    "NS",
    "TXT",
    "URL",
    "URL301",
    "FRAME",
}


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
class FreeDomainHint:
    provider: str
    suffixes: tuple[str, ...]
    fit: str
    records: str
    workflow: str
    status: str
    url: str
    message: str


@dataclass(frozen=True)
class DNSPlan:
    status: str
    records: tuple[DNSRecordPlan, ...]
    hints: tuple[ConnectivityHint, ...]
    free_domains: tuple[FreeDomainHint, ...]
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


@dataclass(frozen=True)
class ProviderDNSRecord:
    name: str
    type: str
    value: str
    ttl: int = DEFAULT_TTL
    mx_pref: int | None = None


@dataclass(frozen=True)
class DNSProviderRecordPlan:
    site_id: str
    domain: str
    name: str
    type: str
    value: str
    ttl: int
    status: str
    message: str


@dataclass(frozen=True)
class DNSZoneSnapshot:
    provider: str
    domain: str
    raw: str
    records: tuple[ProviderDNSRecord, ...]
    status: str
    message: str


@dataclass(frozen=True)
class DNSBackupResult:
    provider: str
    domain: str
    status: str
    path: Path | None
    records: int
    message: str


@dataclass(frozen=True)
class DNSApplyChange:
    domain: str
    name: str
    type: str
    action: str
    current: str
    desired: str
    status: str
    message: str


@dataclass(frozen=True)
class DNSApplyResult:
    provider: str
    domain: str
    mode: str
    status: str
    backup_path: Path | None
    changes: tuple[DNSApplyChange, ...]
    message: str


def dns_plan(
    config: GatewayConfig,
    *,
    mode: str = "static",
    ipv4: str | None = None,
    ipv6: str | None = None,
    dynamic_hostname: str | None = None,
    behind_router: bool = False,
    free_domain_hints: bool = False,
) -> DNSPlan:
    if mode not in DNS_MODES:
        raise ValueError(f"unsupported DNS mode {mode!r}")
    domains = _clearnet_sites(config)
    if not domains:
        return DNSPlan(
            status="skipped",
            records=(),
            hints=(),
            free_domains=(),
            message="clearnet is not selected",
        )

    records: list[DNSRecordPlan] = []
    for site_id, domain in domains:
        if mode == "static":
            records.extend(_static_records(site_id, domain, ipv4=ipv4, ipv6=ipv6))
        else:
            records.extend(_dynamic_records(site_id, domain, dynamic_hostname=dynamic_hostname))
    hints = _connectivity_hints(behind_router=behind_router)
    free_domains = FREE_DOMAIN_HINTS if free_domain_hints else ()
    status = _plan_status([record.status for record in records] + [hint.status for hint in hints])
    return DNSPlan(
        status=status,
        records=tuple(records),
        hints=tuple(hints),
        free_domains=free_domains,
        message=_plan_message(status),
    )


FREE_DOMAIN_HINTS: tuple[FreeDomainHint, ...] = (
    FreeDomainHint(
        provider="is-a.dev",
        suffixes=("is-a.dev",),
        fit="developer personal sites and projects",
        records="DNS records through reviewed repository changes",
        workflow="fork repository, add domain config, open pull request",
        status="community-reviewed",
        url="https://github.com/is-a-dev/register",
        message="good beginner option when a developer-branded subdomain is acceptable",
    ),
    FreeDomainHint(
        provider="JS.ORG",
        suffixes=("js.org",),
        fit="JavaScript ecosystem projects",
        records="CNAME",
        workflow="configure hosting custom domain, then open pull request",
        status="strict-scope",
        url="https://github.com/js-org/js.org",
        message="only use for sites directly related to the JavaScript community",
    ),
    FreeDomainHint(
        provider="Open Domains",
        suffixes=("is-cool.dev", "is-local.org", "is-not-a.dev", "localplayer.dev"),
        fit="students and open-source projects",
        records="A, AAAA, CNAME, NS, TXT, and related DNS records",
        workflow="register through the current Open Domains web app",
        status="verify-current-domains",
        url="https://opendomains.andrewstech.me/",
        message="GitHub registry moved to a web app; verify the current domain list before use",
    ),
    FreeDomainHint(
        provider="Community GitHub registries",
        suffixes=(
            "is-an.app",
            "cluster.ws",
            "wip.la",
            "thedev.id",
            "io.day",
            "jsid.dev",
            "is-a.co",
            "is-a-good.dev",
            "is-really.cool",
            "js.cool",
        ),
        fit="personal sites, hobby apps, and open-source projects",
        records="varies by registry",
        workflow="review registry terms, then open the requested issue or pull request",
        status="verify-before-use",
        url="https://github.com/tarampampam/domains",
        message="treat as optional naming ideas; availability and rules can change",
    ),
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


def provider_dns_record_plan(
    config: GatewayConfig,
    *,
    ipv4: str | None = None,
    ipv6: str | None = None,
    mail_policy: str = "preserve",
    discovery: bool = True,
) -> tuple[DNSProviderRecordPlan, ...]:
    if mail_policy not in DNS_MAIL_POLICIES:
        raise ValueError(f"unsupported DNS mail policy {mail_policy!r}")
    records: list[DNSProviderRecordPlan] = []
    for site, record in _desired_dns_records(
        config,
        ipv4=ipv4,
        ipv6=ipv6,
        mail_policy=mail_policy,
        discovery=discovery,
    ):
        records.append(
            DNSProviderRecordPlan(
                site.id,
                site.domain,
                record.name,
                record.type,
                record.value,
                record.ttl,
                "todo",
                _provider_record_message(record),
            )
        )
    if not records:
        return (
            DNSProviderRecordPlan(
                "-",
                "-",
                "-",
                "-",
                "-",
                DEFAULT_TTL,
                "skipped",
                "no enabled DNS-backed protocols need provider records",
            ),
        )
    return tuple(records)


def dns_backup(
    config: GatewayConfig,
    *,
    provider: str,
    credentials: Path,
    backup_dir: Path | None = None,
    client_ip: str | None = None,
) -> list[DNSBackupResult]:
    dns_provider = _dns_provider(provider, credentials=credentials, client_ip=client_ip)
    target_backup_dir = backup_dir or _default_backup_dir(config)
    return [_backup_domain(dns_provider, domain, target_backup_dir) for domain in _dns_domains(config)]


def dns_apply(
    config: GatewayConfig,
    *,
    provider: str,
    credentials: Path,
    ipv4: str | None = None,
    ipv6: str | None = None,
    mail_policy: str = "preserve",
    discovery: bool = True,
    backup_dir: Path | None = None,
    dry_run: bool = True,
    client_ip: str | None = None,
) -> list[DNSApplyResult]:
    if mail_policy not in DNS_MAIL_POLICIES:
        raise ValueError(f"unsupported DNS mail policy {mail_policy!r}")
    if not ipv4 and not ipv6:
        raise ValueError("dns apply requires --ipv4, --ipv6, or both")

    dns_provider = _dns_provider(provider, credentials=credentials, client_ip=client_ip)
    target_backup_dir = backup_dir or _default_backup_dir(config)
    desired_by_domain: dict[str, list[ProviderDNSRecord]] = {}
    for site, record in _desired_dns_records(
        config,
        ipv4=ipv4,
        ipv6=ipv6,
        mail_policy=mail_policy,
        discovery=discovery,
    ):
        desired_by_domain.setdefault(site.domain, []).append(record)

    results: list[DNSApplyResult] = []
    for domain in _dns_domains(config):
        snapshot = dns_provider.get_hosts(domain)
        if snapshot.status != "ok":
            results.append(
                DNSApplyResult(
                    provider=dns_provider.name,
                    domain=domain,
                    mode="dry-run" if dry_run else "live",
                    status="blocked",
                    backup_path=None,
                    changes=(),
                    message=f"provider fetch failed: {snapshot.message}",
                )
            )
            continue

        backup_path: Path | None = None
        raw_desired = tuple(desired_by_domain.get(domain, ()))
        desired = tuple(_records_supported_by_provider(dns_provider.name, raw_desired))
        changes = _unsupported_record_changes(domain, dns_provider.name, raw_desired)
        changes += _record_changes(domain, snapshot.records, desired, mail_policy=mail_policy)
        next_records = merge_dns_records(snapshot.records, desired, mail_policy=mail_policy)
        status = _apply_status(changes)
        message = "dry-run; provider was not changed"
        write_changes = [change for change in changes if change.status != "skipped"]
        if not dry_run and write_changes:
            backup_path = _write_dns_backup(dns_provider.name, domain, snapshot.raw, target_backup_dir)
            dns_provider.set_hosts(domain, next_records, mail_policy=mail_policy)
            message = "provider zone updated after backup"
            status = "applied"
        elif not dry_run:
            message = "no supported provider changes to apply"
        results.append(
            DNSApplyResult(
                provider=dns_provider.name,
                domain=domain,
                mode="dry-run" if dry_run else "live",
                status=status,
                backup_path=backup_path,
                changes=changes,
                message=message,
            )
        )
    return results


def merge_dns_records(
    existing: tuple[ProviderDNSRecord, ...] | list[ProviderDNSRecord],
    desired: tuple[ProviderDNSRecord, ...] | list[ProviderDNSRecord],
    *,
    mail_policy: str = "preserve",
) -> tuple[ProviderDNSRecord, ...]:
    desired_records = tuple(_normalize_provider_record(record) for record in desired)
    managed_keys = _managed_record_keys(desired_records)
    retained = [
        _normalize_provider_record(record)
        for record in existing
        if not _is_managed_record(record, managed_keys, mail_policy=mail_policy)
    ]
    return tuple(sorted(retained + list(desired_records), key=_record_sort_key))


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


def _desired_dns_records(
    config: GatewayConfig,
    *,
    ipv4: str | None,
    ipv6: str | None,
    mail_policy: str,
    discovery: bool,
) -> list[tuple[SiteConfig, ProviderDNSRecord]]:
    addresses = {
        (record.site_id, record.protocol): record
        for record in effective_address_records(config)
        if record.address_status in {"configured", "captured"}
    }
    desired: list[tuple[SiteConfig, ProviderDNSRecord]] = []
    for site in config.sites:
        enabled = {name for name, protocol in site.protocols.items() if protocol.enabled}
        if not enabled.intersection({"clearnet", "gemini", "reticulum"}):
            continue
        target_names = ["@"]
        if "clearnet" in enabled:
            target_names.append("www")
        if "gemini" in enabled:
            target_names.append("gemini")
        if "reticulum" in enabled:
            target_names.append("reticulum")

        for name in target_names:
            if ipv4:
                desired.append((site, ProviderDNSRecord(name, "A", ipv4)))
            if ipv6:
                desired.append((site, ProviderDNSRecord(name, "AAAA", ipv6)))

        if "clearnet" in enabled:
            desired.append((site, ProviderDNSRecord("@", "CAA", '0 issue "letsencrypt.org"')))

        if mail_policy == "disabled":
            desired.append((site, ProviderDNSRecord("@", "TXT", "v=spf1 -all")))
            desired.append(
                (
                    site,
                    ProviderDNSRecord(
                        "_dmarc",
                        "TXT",
                        "v=DMARC1; p=reject; adkim=s; aspf=s",
                    ),
                )
            )

        if "gemini" in enabled:
            port = int(site.protocols["gemini"].options.get("port", 1965))
            desired.append(
                (
                    site,
                    ProviderDNSRecord(
                        "_gemini._tcp",
                        "SRV",
                        f"0 0 {port} gemini.{site.domain}.",
                    ),
                )
            )

        if "reticulum" in enabled:
            port = int(site.protocols["reticulum"].options.get("port", 4242))
            desired.append(
                (
                    site,
                    ProviderDNSRecord(
                        "_reticulum._tcp",
                        "SRV",
                        f"0 0 {port} reticulum.{site.domain}.",
                    ),
                )
            )
            reticulum_address = addresses.get((site.id, "reticulum"))
            reticulum_hint = f"transport=reticulum.{site.domain}:{port}"
            if reticulum_address:
                host = _url_host(reticulum_address.url)
                if host:
                    reticulum_hint = f"rns={host}; {reticulum_hint}"
            desired.append((site, ProviderDNSRecord("_reticulum", "TXT", reticulum_hint)))

        if discovery:
            tor_address = addresses.get((site.id, "tor"))
            tor_host = _url_host(tor_address.url) if tor_address else ""
            if tor_host:
                desired.append((site, ProviderDNSRecord("_tor", "TXT", f"onion={tor_host}")))
            i2p_address = addresses.get((site.id, "i2p"))
            i2p_host = _url_host(i2p_address.url) if i2p_address else ""
            if i2p_host:
                desired.append((site, ProviderDNSRecord("_i2p", "TXT", f"b32={i2p_host}")))
    return desired


def _provider_record_message(record: ProviderDNSRecord) -> str:
    if record.type == "SRV":
        return "service discovery record; provider support varies"
    if record.name in {"_tor", "_i2p", "_reticulum"}:
        return "AMPG transport discovery hint for compatible browsers"
    if record.type == "CAA":
        return "allow Let's Encrypt certificate issuance"
    if record.type == "TXT" and record.value.startswith("v=spf1"):
        return "mark this non-mail domain as not sending mail"
    if record.name == "_dmarc":
        return "reject spoofed mail for this non-mail domain"
    return "create or update AMPG-managed provider record"


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


def _dns_domains(config: GatewayConfig) -> tuple[str, ...]:
    domains = []
    for site in config.sites:
        if site.domain not in domains and any(protocol.enabled for protocol in site.protocols.values()):
            domains.append(site.domain)
    return tuple(domains)


def _default_backup_dir(config: GatewayConfig) -> Path:
    if config.paths:
        return config.paths.state_dir / "dns-backups"
    return config.config_path.parent / ".ampg/state/dns-backups"


def _backup_domain(provider, domain: str, backup_dir: Path) -> DNSBackupResult:
    snapshot = provider.get_hosts(domain)
    path = _write_dns_backup(provider.name, domain, snapshot.raw, backup_dir)
    return DNSBackupResult(
        provider=provider.name,
        domain=domain,
        status=snapshot.status,
        path=path,
        records=len(snapshot.records),
        message=snapshot.message,
    )


def _write_dns_backup(provider: str, domain: str, raw: str, backup_dir: Path) -> Path:
    stamp = _datetime.datetime.now(_datetime.UTC).strftime("%Y%m%d_%H%M%S")
    path = backup_dir / provider / f"{domain}.{stamp}.xml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")
    return path


def _records_supported_by_provider(
    provider: str,
    records: tuple[ProviderDNSRecord, ...] | list[ProviderDNSRecord],
) -> tuple[ProviderDNSRecord, ...]:
    if provider != "namecheap":
        return tuple(records)
    return tuple(record for record in records if record.type in NAMECHEAP_SUPPORTED_RECORD_TYPES)


def _unsupported_record_changes(
    domain: str,
    provider: str,
    desired: tuple[ProviderDNSRecord, ...],
) -> tuple[DNSApplyChange, ...]:
    if provider != "namecheap":
        return ()
    changes = []
    for record in desired:
        if record.type in NAMECHEAP_SUPPORTED_RECORD_TYPES:
            continue
        changes.append(
            DNSApplyChange(
                domain,
                record.name,
                record.type,
                "skip",
                "-",
                record.value,
                "skipped",
                f"{provider} API does not support this record type",
            )
        )
    return tuple(changes)


def _record_changes(
    domain: str,
    existing: tuple[ProviderDNSRecord, ...],
    desired: tuple[ProviderDNSRecord, ...],
    *,
    mail_policy: str,
) -> tuple[DNSApplyChange, ...]:
    next_records = merge_dns_records(existing, desired, mail_policy=mail_policy)
    existing_set = {_record_identity(record) for record in existing}
    next_set = {_record_identity(record) for record in next_records}
    changes: list[DNSApplyChange] = []
    for identity in sorted(next_set - existing_set):
        name, record_type, value = identity
        changes.append(
            DNSApplyChange(
                domain,
                name,
                record_type,
                "add",
                "-",
                value,
                "todo",
                "record will be added",
            )
        )
    for identity in sorted(existing_set - next_set):
        name, record_type, value = identity
        changes.append(
            DNSApplyChange(
                domain,
                name,
                record_type,
                "remove",
                value,
                "-",
                "todo",
                "AMPG-managed old record will be removed",
            )
        )
    return tuple(changes)


def _apply_status(changes: tuple[DNSApplyChange, ...]) -> str:
    return "todo" if any(change.status == "todo" for change in changes) else "ready"


def _managed_record_keys(
    desired: tuple[ProviderDNSRecord, ...],
) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for record in desired:
        keys.setdefault(_record_name(record.name), set()).add(record.type)
    return keys


def _is_managed_record(
    record: ProviderDNSRecord,
    managed_keys: dict[str, set[str]],
    *,
    mail_policy: str,
) -> bool:
    normalized = _normalize_provider_record(record)
    name = _record_name(normalized.name)
    record_type = normalized.type
    desired_types = managed_keys.get(name, set())
    if record_type in desired_types:
        if name == "@" and record_type == "TXT":
            return normalized.value.lower().startswith("v=spf1")
        if name == "@" and record_type == "CAA":
            return "letsencrypt.org" in normalized.value.lower()
        return True
    if mail_policy == "disabled" and record_type in {"MX", "MXE"}:
        return True
    if name in {"www", "gemini", "reticulum"} and desired_types.intersection({"A", "AAAA"}):
        return record_type in {"A", "AAAA", "CNAME", "ALIAS"}
    return False


def _normalize_provider_record(record: ProviderDNSRecord) -> ProviderDNSRecord:
    return ProviderDNSRecord(
        name=_record_name(record.name),
        type=record.type.upper(),
        value=record.value.strip(),
        ttl=int(record.ttl or DEFAULT_TTL),
        mx_pref=record.mx_pref,
    )


def _record_name(name: str) -> str:
    normalized = name.strip().rstrip(".").lower()
    return normalized or "@"


def _record_identity(record: ProviderDNSRecord) -> tuple[str, str, str]:
    normalized = _normalize_provider_record(record)
    return normalized.name, normalized.type, normalized.value


def _record_sort_key(record: ProviderDNSRecord) -> tuple[str, str, str]:
    normalized = _normalize_provider_record(record)
    return normalized.name, normalized.type, normalized.value


def _url_host(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    host = parsed.hostname
    if host:
        return host
    if "://" in value:
        return ""
    return value.strip().strip("/")


def _dns_provider(provider: str, *, credentials: Path, client_ip: str | None):
    if provider == "namecheap":
        return NamecheapDNSProvider(credentials=credentials, client_ip=client_ip)
    raise ValueError(f"unsupported DNS provider {provider!r}")


class NamecheapDNSProvider:
    name = "namecheap"

    def __init__(self, *, credentials: Path, client_ip: str | None = None):
        self.credentials = credentials
        self.config = _read_key_value_credentials(credentials)
        self.username = (
            self.config.get("dns_namecheap_username")
            or self.config.get("namecheap_username")
            or self.config.get("username")
            or self.config.get("api_user")
        )
        self.api_key = (
            self.config.get("dns_namecheap_api_key")
            or self.config.get("namecheap_api_key")
            or self.config.get("api_key")
        )
        self.client_ip = (
            client_ip
            or self.config.get("dns_namecheap_client_ip")
            or os.environ.get("AMPG_NAMECHEAP_CLIENT_IP")
            or os.environ.get("SUCH_HQ_PUBLIC_IP")
        )
        if not self.username:
            raise ValueError(f"missing Namecheap username in {credentials}")
        if not self.api_key:
            raise ValueError(f"missing Namecheap API key in {credentials}")
        if not self.client_ip:
            raise ValueError("Namecheap API requires --client-ip or AMPG_NAMECHEAP_CLIENT_IP")

    def get_hosts(self, domain: str) -> DNSZoneSnapshot:
        raw = self._request("namecheap.domains.dns.getHosts", self._domain_params(domain))
        root = ET.fromstring(raw)
        errors = _xml_errors(root)
        if root.get("Status") != "OK" or errors:
            message = "; ".join(errors) or root.get("Status") or "unknown Namecheap error"
            return DNSZoneSnapshot(self.name, domain, raw, (), "error", message)
        records = []
        for element in root.iter():
            if _xml_localname(element.tag) != "host":
                continue
            records.append(
                ProviderDNSRecord(
                    name=element.get("Name") or "@",
                    type=(element.get("Type") or "").upper(),
                    value=element.get("Address") or "",
                    ttl=int(element.get("TTL") or DEFAULT_TTL),
                    mx_pref=_optional_int(element.get("MXPref")),
                )
            )
        return DNSZoneSnapshot(
            self.name,
            domain,
            raw,
            tuple(records),
            "ok",
            "zone fetched from Namecheap",
        )

    def set_hosts(
        self,
        domain: str,
        records: tuple[ProviderDNSRecord, ...],
        *,
        mail_policy: str,
    ) -> None:
        params = self._domain_params(domain)
        if mail_policy == "disabled":
            params["EmailType"] = "MX"
        for index, record in enumerate(records, start=1):
            params[f"HostName{index}"] = record.name
            params[f"RecordType{index}"] = record.type
            params[f"Address{index}"] = record.value
            params[f"TTL{index}"] = str(record.ttl)
            if record.mx_pref is not None:
                params[f"MXPref{index}"] = str(record.mx_pref)
        raw = self._request("namecheap.domains.dns.setHosts", params)
        root = ET.fromstring(raw)
        errors = _xml_errors(root)
        success = any(
            element.get("IsSuccess") == "true"
            for element in root.iter()
            if _xml_localname(element.tag) == "DomainDNSSetHostsResult"
        )
        if root.get("Status") != "OK" or errors or not success:
            raise RuntimeError("; ".join(errors) or "Namecheap setHosts did not report success")

    def _domain_params(self, domain: str) -> dict[str, str]:
        sld, tld = _split_namecheap_domain(domain)
        return {"SLD": sld, "TLD": tld}

    def _request(self, command: str, params: dict[str, str]) -> str:
        request_params = {
            "ApiUser": self.username,
            "ApiKey": self.api_key,
            "UserName": self.username,
            "ClientIp": self.client_ip,
            "Command": command,
        }
        request_params.update(params)
        url = "https://api.namecheap.com/xml.response?" + urllib.parse.urlencode(request_params)
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode()


def _read_key_value_credentials(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(path)
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _split_namecheap_domain(domain: str) -> tuple[str, str]:
    sld, dot, tld = domain.partition(".")
    if not dot:
        raise ValueError(f"domain must contain a dot: {domain}")
    return sld, tld


def _xml_localname(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _xml_errors(root: ET.Element) -> list[str]:
    return [
        element.text or ""
        for element in root.iter()
        if _xml_localname(element.tag) == "Error" and element.text
    ]


def _optional_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None
