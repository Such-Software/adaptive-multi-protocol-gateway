from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .config import GatewayConfig, ProtocolConfig, SiteConfig


SCHEMA = "ampg.address-registry.v1"
CAPTURE_PROTOCOLS = {"tor", "i2p", "reticulum", "ipfs"}


@dataclass(frozen=True)
class AddressRecord:
    site_id: str
    protocol: str
    url: str
    address_status: str
    source: str


@dataclass(frozen=True)
class AddressCaptureResult:
    site_id: str
    protocol: str
    status: str
    url: str
    source: str
    path: Path | None
    message: str


def address_registry_path(config: GatewayConfig) -> Path:
    if config.paths:
        return config.paths.state_dir / "addresses.json"
    return config.config_path.parent / ".ampg/state/addresses.json"


def load_address_registry(config: GatewayConfig) -> dict[tuple[str, str], AddressRecord]:
    path = address_registry_path(config)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid address registry {path}: {exc}") from exc
    if data.get("schema") != SCHEMA:
        raise ValueError(f"invalid address registry schema in {path}")
    records: dict[tuple[str, str], AddressRecord] = {}
    for raw_record in data.get("addresses", []):
        if not isinstance(raw_record, dict):
            continue
        record = AddressRecord(
            site_id=str(raw_record.get("site", "")),
            protocol=str(raw_record.get("protocol", "")),
            url=str(raw_record.get("url", "")),
            address_status=str(raw_record.get("address_status", "captured")),
            source=str(raw_record.get("source", "registry")),
        )
        if record.site_id and record.protocol and record.url:
            records[(record.site_id, record.protocol)] = record
    return records


def write_address_registry(
    config: GatewayConfig,
    records: dict[tuple[str, str], AddressRecord],
) -> Path:
    path = address_registry_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": SCHEMA,
        "addresses": [
            {
                "site": record.site_id,
                "protocol": record.protocol,
                "url": record.url,
                "address_status": record.address_status,
                "source": record.source,
            }
            for record in sorted(records.values(), key=lambda item: (item.site_id, item.protocol))
        ],
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def set_address(
    config: GatewayConfig,
    *,
    site_id: str,
    protocol: str,
    url: str,
    source: str = "manual",
) -> AddressRecord:
    _require_declared_protocol(config, site_id, protocol)
    records = load_address_registry(config)
    record = AddressRecord(
        site_id=site_id,
        protocol=protocol,
        url=normalize_address_url(protocol, url),
        address_status="captured",
        source=source,
    )
    records[(site_id, protocol)] = record
    write_address_registry(config, records)
    return record


def effective_address_records(config: GatewayConfig) -> list[AddressRecord]:
    registry = load_address_registry(config)
    records: list[AddressRecord] = []
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            configured = configured_address(site, protocol)
            if configured:
                records.append(configured)
                continue
            captured = registry.get((site.id, protocol.name))
            if captured:
                records.append(captured)
                continue
            records.append(_placeholder_or_derived_address(site, protocol))
    return records


def effective_address(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> AddressRecord | None:
    configured = configured_address(site, protocol)
    if configured:
        return configured
    return load_address_registry(config).get((site.id, protocol.name))


def configured_address(site: SiteConfig, protocol: ProtocolConfig) -> AddressRecord | None:
    raw_url = protocol.options.get("fixture_url") or protocol.options.get("browser_url")
    if raw_url is None:
        raw_url = _protocol_specific_configured_url(protocol)
    if raw_url:
        return AddressRecord(
            site_id=site.id,
            protocol=protocol.name,
            url=normalize_address_url(protocol.name, str(raw_url)),
            address_status="configured",
            source="config",
        )
    if protocol.name == "ipfs" and protocol.options.get("cid"):
        return AddressRecord(
            site_id=site.id,
            protocol=protocol.name,
            url=f"ipfs://{protocol.options['cid']}",
            address_status="configured",
            source="config",
        )
    return None


def _protocol_specific_configured_url(protocol: ProtocolConfig) -> Any:
    if protocol.name == "tor":
        onion_url = protocol.options.get("onion_url")
        if onion_url:
            return onion_url
        onion_location = protocol.options.get("onion_location")
        if onion_location and onion_location != "auto":
            return onion_location
        return None
    if protocol.name == "i2p":
        return protocol.options.get("i2p_url") or protocol.options.get("i2p_hostname")
    if protocol.name == "gemini":
        return protocol.options.get("gemini_url")
    if protocol.name == "reticulum":
        return protocol.options.get("rns_url")
    if protocol.name == "ipfs":
        return protocol.options.get("ipfs_url")
    if protocol.name == "clearnet":
        return protocol.options.get("url")
    return None


def capture_addresses(config: GatewayConfig) -> list[AddressCaptureResult]:
    records = load_address_registry(config)
    results: list[AddressCaptureResult] = []
    changed = False
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            result = _capture_protocol_address(config, site, protocol)
            results.append(result)
            if result.status == "captured":
                records[(site.id, protocol.name)] = AddressRecord(
                    site_id=site.id,
                    protocol=protocol.name,
                    url=result.url,
                    address_status="captured",
                    source=result.source,
                )
                changed = True
    if changed:
        write_address_registry(config, records)
    return results


def normalize_address_url(protocol: str, value: str) -> str:
    address = value.strip()
    if protocol == "tor":
        return _with_scheme(address, "http")
    if protocol == "i2p":
        return _with_scheme(address, "http")
    if protocol == "gemini":
        return _with_scheme(address, "gemini")
    if protocol == "reticulum":
        return _with_scheme(address, "rns")
    if protocol == "ipfs":
        if address.startswith(("/ipfs/", "/ipns/")):
            return address
        return _with_scheme(address, "ipfs")
    if protocol == "clearnet":
        return _with_scheme(address, "https")
    return _with_trailing_slash(address)


def _capture_protocol_address(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> AddressCaptureResult:
    configured = configured_address(site, protocol)
    if configured:
        return AddressCaptureResult(
            site_id=site.id,
            protocol=protocol.name,
            status="configured",
            url=configured.url,
            source=configured.source,
            path=None,
            message="address is set in config; registry unchanged",
        )

    candidates = _address_file_candidates(config, site, protocol)
    if protocol.name not in CAPTURE_PROTOCOLS and not protocol.options.get("address_file"):
        return AddressCaptureResult(
            site_id=site.id,
            protocol=protocol.name,
            status="skipped",
            url="",
            source="-",
            path=None,
            message="protocol address is derived from site config",
        )

    for path in candidates:
        if not path.exists():
            continue
        raw_value = _first_nonempty_line(path)
        if not raw_value:
            continue
        url = normalize_address_url(protocol.name, raw_value)
        return AddressCaptureResult(
            site_id=site.id,
            protocol=protocol.name,
            status="captured",
            url=url,
            source=f"file:{path}",
            path=path,
            message="captured public transport address",
        )
    candidate_text = ", ".join(str(path) for path in candidates)
    return AddressCaptureResult(
        site_id=site.id,
        protocol=protocol.name,
        status="missing",
        url="",
        source="-",
        path=None,
        message=f"no address file found; checked {candidate_text}",
    )


def _address_file_candidates(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> tuple[Path, ...]:
    configured_file = protocol.options.get("address_file")
    candidates: list[Path] = []
    if configured_file:
        path = Path(str(configured_file)).expanduser()
        if not path.is_absolute():
            path = config.config_path.parent / path
        candidates.append(path.resolve())

    state_dir = _state_dir(config, site, protocol)
    if protocol.name == "tor":
        candidates.extend(
            [
                state_dir / "hidden-service/hostname",
                state_dir / "hostname",
                state_dir / "address.txt",
            ]
        )
    elif protocol.name == "i2p":
        candidates.extend(
            [
                state_dir / "hostname.txt",
                state_dir / "b32.txt",
                state_dir / "address.txt",
            ]
        )
    else:
        candidates.extend([state_dir / "address.txt", state_dir / "hostname"])
    return tuple(candidates)


def _placeholder_or_derived_address(site: SiteConfig, protocol: ProtocolConfig) -> AddressRecord:
    if protocol.name == "clearnet":
        url = site.source.canonical_url or f"https://{site.domain}/"
        return AddressRecord(site.id, protocol.name, _with_trailing_slash(url), "derived", "site")
    if protocol.name == "tor":
        return AddressRecord(
            site.id,
            protocol.name,
            f"http://{site.id}.onion/",
            "placeholder",
            "placeholder",
        )
    if protocol.name == "i2p":
        return AddressRecord(
            site.id,
            protocol.name,
            f"http://{site.id}.i2p/",
            "placeholder",
            "placeholder",
        )
    if protocol.name == "gemini":
        return AddressRecord(site.id, protocol.name, f"gemini://{site.domain}/", "derived", "site")
    if protocol.name == "reticulum":
        return AddressRecord(site.id, protocol.name, f"rns://{site.id}", "placeholder", "placeholder")
    if protocol.name == "ipfs":
        return AddressRecord(site.id, protocol.name, f"/ipfs/{site.id}", "placeholder", "placeholder")
    return AddressRecord(site.id, protocol.name, f"https://{site.domain}/", "derived", "site")


def _require_declared_protocol(config: GatewayConfig, site_id: str, protocol: str) -> None:
    for site in config.sites:
        if site.id != site_id:
            continue
        if protocol not in site.protocols:
            raise ValueError(f"{site_id}: protocol {protocol!r} is not declared")
        return
    raise ValueError(f"unknown site {site_id!r}")


def _state_dir(config: GatewayConfig, site: SiteConfig, protocol: ProtocolConfig) -> Path:
    root = config.paths.state_dir if config.paths else config.config_path.parent / ".ampg/state"
    return root / site.id / protocol.name


def _first_nonempty_line(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value:
            return value
    return ""


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
