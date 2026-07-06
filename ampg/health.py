from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import GatewayConfig, SiteConfig
from .manifest import fixture_manifest
from .preview import preview_endpoints, preview_fixture_manifest


@dataclass(frozen=True)
class HealthCheck:
    site_id: str
    protocol: str
    mode: str
    url: str
    output_root: Path
    output_path: str
    transport: str
    profile: str
    address_status: str
    route: str
    status: str
    action: str
    command: str
    message: str


def health_plan(
    config: GatewayConfig,
    *,
    mode: str = "published",
    base_port: int = 19080,
    host: str = "127.0.0.1",
) -> list[HealthCheck]:
    if mode not in {"published", "preview"}:
        raise ValueError(f"unsupported health mode {mode!r}")

    endpoints = preview_endpoints(config, base_port=base_port, host=host) if mode == "preview" else []
    checks: list[HealthCheck] = []
    for site in config.sites:
        manifest = _manifest_for_mode(site, mode=mode, endpoints=endpoints)
        for fixture in manifest["fixtures"]:
            checks.append(_health_check(site, fixture, mode=mode))
    return checks


def blocked_health_checks(checks: list[HealthCheck]) -> list[HealthCheck]:
    return [check for check in checks if check.status == "blocked"]


def _manifest_for_mode(
    site: SiteConfig,
    *,
    mode: str,
    endpoints,
) -> dict[str, Any]:
    if mode == "preview":
        return preview_fixture_manifest(site, endpoints)
    return fixture_manifest(site)


def _health_check(site: SiteConfig, fixture: dict[str, Any], *, mode: str) -> HealthCheck:
    protocol = str(fixture["protocol"])
    output_root = site.outputs.root / protocol
    route = str(fixture.get("route", {}).get("fixture_path", "/"))
    transport = str(fixture["checks"]["transport"])
    profile = str(fixture["checks"]["profile"])
    address_status = str(fixture["address_status"])
    output_ready = (output_root / ".ampg-output").exists()
    preview_status = fixture.get("preview", {}).get("status")

    if not output_ready or preview_status == "missing-output":
        status = "blocked"
        action = "build-output"
        message = f"generated output is missing: {output_root}"
    elif address_status == "placeholder":
        status = "review"
        action = "configure-address"
        message = "fixture uses a placeholder address; update protocol URL after daemon identity exists"
    else:
        status = "planned"
        action = "check-fixture"
        message = (
            "verify fixture through the local preview server"
            if mode == "preview"
            else "verify fixture through the selected transport/profile after services start"
        )

    return HealthCheck(
        site_id=site.id,
        protocol=protocol,
        mode=mode,
        url=str(fixture["url"]),
        output_root=output_root,
        output_path=str(fixture["output_path"]),
        transport=transport,
        profile=profile,
        address_status=address_status,
        route=route,
        status=status,
        action=action,
        command=_check_command(str(fixture["url"]), transport=transport, profile=profile),
        message=message,
    )


def _check_command(url: str, *, transport: str, profile: str) -> str:
    if transport == "clearnet":
        return f"curl -fsSL {url}"
    if transport == "tor":
        return f"curl --proxy socks5h://127.0.0.1:9050 -fsSL {url}"
    if transport == "i2p":
        return f"curl --proxy http://127.0.0.1:4444 -fsSL {url}"
    if transport == "gemini":
        return f"gemini fetch {url}"
    if transport == "ipfs":
        return f"ipfs cat {url}"
    if transport == "reticulum":
        return f"rns-fetch {url}"
    return f"fetch {url} with {profile}"
