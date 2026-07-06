from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any

from .config import GatewayConfig, ProtocolConfig, SiteConfig
from .manifest import fixture_manifest


PREVIEW_MANIFEST_NAME = "ampg-preview-fixture-manifest.json"


@dataclass(frozen=True)
class PreviewEndpoint:
    site_id: str
    protocol: str
    renderer: str
    root: Path
    host: str
    port: int
    url: str
    status: str


@dataclass(frozen=True)
class PreviewManifestWriteResult:
    site_id: str
    path: Path
    fixture_count: int


def preview_endpoints(
    config: GatewayConfig,
    *,
    base_port: int = 19080,
    host: str = "127.0.0.1",
) -> list[PreviewEndpoint]:
    endpoints: list[PreviewEndpoint] = []
    offset = 0
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            port = int(protocol.options.get("preview_port", base_port + offset))
            root = site.outputs.root / protocol.name
            status = "ready" if (root / ".ampg-output").exists() else "missing-output"
            endpoints.append(
                PreviewEndpoint(
                    site_id=site.id,
                    protocol=protocol.name,
                    renderer=protocol.renderer,
                    root=root,
                    host=host,
                    port=port,
                    url=f"http://{host}:{port}/",
                    status=status,
                )
            )
            offset += 1
    return endpoints


def preview_fixture_manifest(
    config: GatewayConfig,
    site: SiteConfig,
    endpoints: list[PreviewEndpoint],
) -> dict[str, Any]:
    by_protocol = {
        endpoint.protocol: endpoint
        for endpoint in endpoints
        if endpoint.site_id == site.id
    }
    manifest = fixture_manifest(config, site)
    manifest["mode"] = "preview"
    for fixture in manifest["fixtures"]:
        endpoint = by_protocol[fixture["protocol"]]
        published_url = fixture["url"]
        published_checks = dict(fixture["checks"])
        fixture_path = fixture.get("route", {}).get("fixture_path", "/")
        fixture["published"] = {
            "url": published_url,
            "checks": published_checks,
            "address_status": fixture["address_status"],
        }
        fixture["preview"] = {
            "mode": "loopback-http",
            "root": str(endpoint.root),
            "status": endpoint.status,
        }
        fixture["url"] = _preview_url(endpoint.url, fixture_path)
        fixture["address_status"] = "preview"
        fixture["checks"] = {
            "transport": "clearnet",
            "profile": "clearnet",
        }
    return manifest


def write_preview_fixture_manifests(
    config: GatewayConfig,
    *,
    base_port: int = 19080,
    host: str = "127.0.0.1",
) -> list[PreviewManifestWriteResult]:
    endpoints = preview_endpoints(config, base_port=base_port, host=host)
    results: list[PreviewManifestWriteResult] = []
    for site in config.sites:
        manifest = preview_fixture_manifest(config, site, endpoints)
        path = preview_manifest_path(site)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        results.append(
            PreviewManifestWriteResult(
                site_id=site.id,
                path=path,
                fixture_count=len(manifest["fixtures"]),
            )
        )
    return results


def preview_manifest_path(site: SiteConfig) -> Path:
    return site.outputs.root / PREVIEW_MANIFEST_NAME


class PreviewServers(AbstractContextManager):
    def __init__(self, endpoints: list[PreviewEndpoint]) -> None:
        self.endpoints = endpoints
        self._servers: list[ThreadingHTTPServer] = []
        self._threads: list[threading.Thread] = []

    def __enter__(self) -> "PreviewServers":
        for endpoint in self.endpoints:
            if endpoint.status != "ready":
                raise FileNotFoundError(
                    f"{endpoint.site_id}/{endpoint.protocol}: output root is not built: {endpoint.root}"
                )
            handler = partial(SimpleHTTPRequestHandler, directory=str(endpoint.root))
            server = ThreadingHTTPServer((endpoint.host, endpoint.port), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._servers.append(server)
            self._threads.append(thread)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        for server in self._servers:
            server.shutdown()
            server.server_close()
        for thread in self._threads:
            thread.join(timeout=2)

    def wait_forever(self) -> None:
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            return


def _preview_url(base_url: str, fixture_path: str) -> str:
    if not fixture_path or fixture_path == "/":
        return base_url
    return base_url.rstrip("/") + "/" + fixture_path.lstrip("/")
