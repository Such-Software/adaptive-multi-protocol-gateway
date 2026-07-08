from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSource:
    kind: str
    discovery: str
    lifecycle: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TransportAdapter:
    protocol: str
    daemon: str
    executable: str
    backend: str
    adopt_supported: bool
    managed_supported: bool
    default_ports: tuple[int, ...] = ()
    generated_artifacts: tuple[str, ...] = ()
    provider_sources: tuple[ProviderSource, ...] = ()
    notes: tuple[str, ...] = ()


COMMON_SERVICE_PROVIDER_SOURCES = (
    ProviderSource(
        kind="configured",
        discovery="explicit daemon config and approved generated snippets",
        lifecycle="operator-owned unless daemon_policy selects manage",
        notes=("Explicit config always wins over automatic discovery.",),
    ),
    ProviderSource(
        kind="system-adopted",
        discovery="running system daemon, service, or listen endpoint",
        lifecycle="operator-owned; AMPG may generate snippets but does not own the service",
        notes=("Used when daemon_policy is adopt or auto with a healthy daemon.",),
    ),
    ProviderSource(
        kind="system-managed",
        discovery="installed daemon binary on the selected platform",
        lifecycle="AMPG-owned state and AMPG-named supervisor entry",
        notes=("Used when daemon_policy is manage or auto and the platform can supervise it.",),
    ),
    ProviderSource(
        kind="platform-package",
        discovery="allowlisted package backend such as apt, brew, or pkg",
        lifecycle="installed only through reviewed deploy apply package stage",
        notes=("Package install is separate from state, supervisor, start, address, and health stages.",),
    ),
)


USERSPACE_PROVIDER_SOURCES = COMMON_SERVICE_PROVIDER_SOURCES + (
    ProviderSource(
        kind="bundled-sidecar",
        discovery="AMPG package or app resource provider directory",
        lifecycle="AMPG-owned process and state",
        notes=("Useful for old laptops, single-purpose boxes, and mobile-server shells.",),
    ),
)


TRANSPORT_ADAPTERS = (
    TransportAdapter(
        protocol="clearnet",
        daemon="nginx",
        executable="nginx",
        backend="http",
        adopt_supported=True,
        managed_supported=True,
        default_ports=(80, 443),
        generated_artifacts=("nginx server block snippet",),
        provider_sources=COMMON_SERVICE_PROVIDER_SOURCES,
        notes=(
            "Clearnet ingress is usually adopted because TLS and public vhost policy are operator-owned.",
        ),
    ),
    TransportAdapter(
        protocol="tor",
        daemon="tor",
        executable="tor",
        backend="hidden-service",
        adopt_supported=True,
        managed_supported=True,
        default_ports=(18080,),
        generated_artifacts=("torrc hidden-service snippet", "loopback HTTP server block"),
        provider_sources=USERSPACE_PROVIDER_SOURCES,
        notes=(
            "Adopted Tor keeps existing HiddenServiceDir material.",
            "Managed Tor stores onion service keys under AMPG state.",
        ),
    ),
    TransportAdapter(
        protocol="tor",
        daemon="arti",
        executable="arti",
        backend="hidden-service",
        adopt_supported=False,
        managed_supported=False,
        default_ports=(18080,),
        generated_artifacts=("future Arti onion-service config",),
        provider_sources=(
            ProviderSource(
                kind="bundled-sidecar",
                discovery="AMPG package or app resource provider directory",
                lifecycle="future AMPG-owned Arti onion-service process",
            ),
            ProviderSource(
                kind="configured",
                discovery="explicit arti binary path and onion-service config",
                lifecycle="future AMPG-owned or operator-owned by policy",
            ),
        ),
        notes=("Modeled as a future backend until the AMPG Arti adapter is implemented.",),
    ),
    TransportAdapter(
        protocol="i2p",
        daemon="i2pd",
        executable="i2pd",
        backend="server-tunnel",
        adopt_supported=True,
        managed_supported=True,
        default_ports=(18081,),
        generated_artifacts=("i2pd server tunnel snippet", "loopback HTTP server block"),
        provider_sources=USERSPACE_PROVIDER_SOURCES,
        notes=("Destination keys are transport identity material and must be preserved.",),
    ),
    TransportAdapter(
        protocol="gemini",
        daemon="agate",
        executable="agate",
        backend="gemini-server",
        adopt_supported=True,
        managed_supported=True,
        default_ports=(1965,),
        generated_artifacts=("Agate plan values",),
        provider_sources=USERSPACE_PROVIDER_SOURCES,
        notes=("Gemini serves generated Gemtext output directly.",),
    ),
    TransportAdapter(
        protocol="ipfs",
        daemon="ipfs",
        executable="ipfs",
        backend="content-addressed",
        adopt_supported=True,
        managed_supported=True,
        default_ports=(5001, 8080),
        generated_artifacts=("pin/add plan",),
        provider_sources=USERSPACE_PROVIDER_SOURCES,
        notes=("IPFS is content-addressed distribution, not an anonymity layer.",),
    ),
    TransportAdapter(
        protocol="reticulum",
        daemon="rnsd",
        executable="rnsd",
        backend="reticulum-page-service",
        adopt_supported=True,
        managed_supported=True,
        default_ports=(),
        generated_artifacts=("Reticulum page-service plan",),
        provider_sources=USERSPACE_PROVIDER_SOURCES
        + (
            ProviderSource(
                kind="operator-interface",
                discovery="explicit Reticulum interface configuration",
                lifecycle="operator-owned physical or link-layer interface",
                notes=("AMPG can manage page serving while interface setup may remain manual.",),
            ),
        ),
        notes=(
            "Reticulum is resilient/private routing, not an anonymity layer.",
            "Physical interfaces may require operator setup outside AMPG.",
        ),
    ),
)


def transport_adapter(protocol: str, daemon: str) -> TransportAdapter | None:
    for adapter in TRANSPORT_ADAPTERS:
        if adapter.protocol == protocol and adapter.daemon == daemon:
            return adapter
    return None


def fallback_transport_adapter(protocol: str, daemon: str) -> TransportAdapter:
    return TransportAdapter(
        protocol=protocol,
        daemon=daemon,
        executable=daemon,
        backend="unknown",
        adopt_supported=False,
        managed_supported=False,
        generated_artifacts=(),
        notes=("No AMPG adapter is registered for this protocol/daemon pair.",),
    )
