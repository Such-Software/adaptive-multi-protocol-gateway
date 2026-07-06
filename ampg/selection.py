from __future__ import annotations

from .config import GatewayConfig, SiteConfig


def parse_protocol_filters(raw_filters: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not raw_filters:
        return ()
    protocols: list[str] = []
    for raw_filter in raw_filters:
        for name in raw_filter.split(","):
            protocol = name.strip()
            if protocol and protocol not in protocols:
                protocols.append(protocol)
    return tuple(protocols)


def select_protocols(config: GatewayConfig, protocols: tuple[str, ...]) -> GatewayConfig:
    if not protocols:
        return config

    selected = set(protocols)
    declared = {
        protocol_name
        for site in config.sites
        for protocol_name in site.protocols
    }
    missing = selected - declared
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"selected protocol(s) not declared in config: {names}")

    enabled = {
        protocol_name
        for site in config.sites
        for protocol_name, protocol in site.protocols.items()
        if protocol.enabled
    }
    inactive = selected - enabled
    if inactive:
        names = ", ".join(sorted(inactive))
        raise ValueError(f"selected protocol(s) not enabled in config: {names}")

    sites = [
        SiteConfig(
            id=site.id,
            domain=site.domain,
            source=site.source,
            outputs=site.outputs,
            protocols={
                name: protocol
                for name, protocol in site.protocols.items()
                if name in selected
            },
            interactions=site.interactions,
        )
        for site in config.sites
    ]
    return GatewayConfig(config_path=config.config_path, sites=sites)
