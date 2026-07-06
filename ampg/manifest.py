from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .config import GatewayConfig, ProtocolConfig, SiteConfig


SCHEMA = "ampg.fixture-manifest.v1"


@dataclass(frozen=True)
class ManifestWriteResult:
    site_id: str
    path: Path
    fixture_count: int


def fixture_manifest(site: SiteConfig) -> dict[str, Any]:
    fixtures = [
        _fixture_entry(site, protocol)
        for protocol in site.protocols.values()
        if protocol.enabled
    ]
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


def _fixture_entry(site: SiteConfig, protocol: ProtocolConfig) -> dict[str, Any]:
    url, address_status = _fixture_url(site, protocol)
    transport = _transport_for(protocol.name)
    return {
        "protocol": protocol.name,
        "renderer": protocol.renderer,
        "url": url,
        "address_status": address_status,
        "output_path": protocol.name,
        "checks": {
            "transport": transport,
            "profile": transport,
        },
    }


def _transport_for(protocol_name: str) -> str:
    if protocol_name in {"clearnet", "tor", "i2p", "gemini", "reticulum", "ipfs"}:
        return protocol_name
    return protocol_name


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
