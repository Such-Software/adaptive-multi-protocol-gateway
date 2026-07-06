from __future__ import annotations

from dataclasses import dataclass


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
    notes: tuple[str, ...] = ()


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
