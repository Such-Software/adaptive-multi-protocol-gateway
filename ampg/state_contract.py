from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import GatewayConfig, ProtocolConfig, SiteConfig


@dataclass(frozen=True)
class StatePathContract:
    site_id: str
    protocol: str
    role: str
    path: Path
    owner: str
    required: bool
    sensitive: bool
    description: str


def gateway_state_root(config: GatewayConfig) -> Path:
    if config.paths:
        return config.paths.state_dir
    return config.config_path.parent / ".ampg/state"


def protocol_state_dir(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> Path:
    return gateway_state_root(config) / site.id / protocol.name


def state_contract(config: GatewayConfig) -> list[StatePathContract]:
    contracts: list[StatePathContract] = []
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            contracts.extend(protocol_state_contract(config, site, protocol))
    return contracts


def protocol_state_contract(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> list[StatePathContract]:
    state_dir = protocol_state_dir(config, site, protocol)
    contracts = [
        _contract(
            site,
            protocol,
            role="state-dir",
            path=state_dir,
            owner="ampg",
            required=True,
            sensitive=False,
            description="AMPG-owned protocol state directory.",
        )
    ]
    if protocol.name == "tor":
        contracts.extend(_tor_contract(site, protocol, state_dir))
    elif protocol.name == "i2p":
        contracts.extend(_i2p_contract(site, protocol, state_dir))
    elif protocol.name == "gemini":
        contracts.extend(_gemini_contract(site, protocol, state_dir))
    elif protocol.name == "clearnet":
        contracts.extend(_clearnet_contract(site, protocol, state_dir))
    else:
        contracts.extend(_generic_contract(site, protocol, state_dir))
    return contracts


def address_capture_candidates(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> tuple[Path, ...]:
    candidates: list[Path] = []
    configured_file = protocol.options.get("address_file")
    if configured_file:
        path = Path(str(configured_file)).expanduser()
        if not path.is_absolute():
            path = config.config_path.parent / path
        candidates.append(path.resolve())
    candidates.extend(
        contract.path
        for contract in protocol_state_contract(config, site, protocol)
        if contract.role == "address-file"
    )
    return tuple(candidates)


def daemon_config_path(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> Path:
    state_dir = protocol_state_dir(config, site, protocol)
    if protocol.name == "tor":
        return state_dir / "torrc"
    if protocol.name == "i2p":
        return state_dir / "i2pd-tunnels.conf"
    if protocol.name == "clearnet":
        return state_dir / "nginx-server.conf"
    if protocol.name == "gemini":
        return state_dir / "agate-plan.txt"
    return state_dir / f"{protocol.daemon}-plan.txt"


def _tor_contract(
    site: SiteConfig,
    protocol: ProtocolConfig,
    state_dir: Path,
) -> list[StatePathContract]:
    return [
        _contract(
            site,
            protocol,
            role="daemon-config",
            path=state_dir / "torrc",
            owner="ampg",
            required=True,
            sensitive=False,
            description="Reviewed Tor config copied into managed state before start.",
        ),
        _contract(
            site,
            protocol,
            role="daemon-data",
            path=state_dir / "data",
            owner="daemon",
            required=True,
            sensitive=False,
            description="Tor DataDirectory.",
        ),
        _contract(
            site,
            protocol,
            role="identity-dir",
            path=state_dir / "hidden-service",
            owner="daemon",
            required=True,
            sensitive=True,
            description="Tor onion-service key material and hostname.",
        ),
        _contract(
            site,
            protocol,
            role="address-file",
            path=state_dir / "hidden-service/hostname",
            owner="daemon",
            required=True,
            sensitive=False,
            description="Onion hostname captured after Tor creates the hidden service.",
        ),
        _contract(
            site,
            protocol,
            role="address-file",
            path=state_dir / "hostname",
            owner="operator",
            required=False,
            sensitive=False,
            description="Optional adopted-daemon hostname export.",
        ),
        _contract(
            site,
            protocol,
            role="log-file",
            path=state_dir / "tor.log",
            owner="daemon",
            required=False,
            sensitive=False,
            description="Managed Tor log file.",
        ),
    ]


def _i2p_contract(
    site: SiteConfig,
    protocol: ProtocolConfig,
    state_dir: Path,
) -> list[StatePathContract]:
    key_file = str(protocol.options.get("keys_file", f"{site.id}-web.dat"))
    return [
        _contract(
            site,
            protocol,
            role="daemon-config",
            path=state_dir / "i2pd-tunnels.conf",
            owner="ampg",
            required=True,
            sensitive=False,
            description="Reviewed i2pd tunnel config copied into managed state before start.",
        ),
        _contract(
            site,
            protocol,
            role="daemon-data",
            path=state_dir / "data",
            owner="daemon",
            required=True,
            sensitive=False,
            description="Managed i2pd data directory.",
        ),
        _contract(
            site,
            protocol,
            role="identity-key",
            path=state_dir / "data" / key_file,
            owner="daemon",
            required=True,
            sensitive=True,
            description="I2P destination key file for the web tunnel.",
        ),
        _contract(
            site,
            protocol,
            role="address-file",
            path=state_dir / "hostname.txt",
            owner="daemon",
            required=True,
            sensitive=False,
            description="Preferred I2P hostname or b32 export captured after tunnel creation.",
        ),
        _contract(
            site,
            protocol,
            role="address-file",
            path=state_dir / "b32.txt",
            owner="daemon",
            required=False,
            sensitive=False,
            description="Alternate I2P b32 export captured after tunnel creation.",
        ),
        _contract(
            site,
            protocol,
            role="address-file",
            path=state_dir / "address.txt",
            owner="operator",
            required=False,
            sensitive=False,
            description="Optional adopted-daemon address export.",
        ),
    ]


def _gemini_contract(
    site: SiteConfig,
    protocol: ProtocolConfig,
    state_dir: Path,
) -> list[StatePathContract]:
    return [
        _contract(
            site,
            protocol,
            role="daemon-config",
            path=state_dir / "agate-plan.txt",
            owner="ampg",
            required=True,
            sensitive=False,
            description="Reviewed Agate launch values copied into managed state before start.",
        ),
        _contract(
            site,
            protocol,
            role="certificate",
            path=state_dir / f"{site.id}.crt",
            owner="ampg",
            required=True,
            sensitive=False,
            description="Gemini certificate.",
        ),
        _contract(
            site,
            protocol,
            role="identity-key",
            path=state_dir / f"{site.id}.key",
            owner="ampg",
            required=True,
            sensitive=True,
            description="Gemini private key.",
        ),
    ]


def _clearnet_contract(
    site: SiteConfig,
    protocol: ProtocolConfig,
    state_dir: Path,
) -> list[StatePathContract]:
    return [
        _contract(
            site,
            protocol,
            role="daemon-config",
            path=state_dir / "nginx-server.conf",
            owner="ampg",
            required=True,
            sensitive=False,
            description="Reviewed nginx config copied into managed state before start.",
        ),
        _contract(
            site,
            protocol,
            role="pid-file",
            path=state_dir / "nginx.pid",
            owner="daemon",
            required=False,
            sensitive=False,
            description="Managed nginx pid file.",
        ),
        _contract(
            site,
            protocol,
            role="log-file",
            path=state_dir / "nginx-error.log",
            owner="daemon",
            required=False,
            sensitive=False,
            description="Managed nginx error log.",
        ),
    ]


def _generic_contract(
    site: SiteConfig,
    protocol: ProtocolConfig,
    state_dir: Path,
) -> list[StatePathContract]:
    return [
        _contract(
            site,
            protocol,
            role="daemon-config",
            path=state_dir / f"{protocol.daemon}-plan.txt",
            owner="ampg",
            required=False,
            sensitive=False,
            description="Adapter-specific reviewed daemon config.",
        ),
        _contract(
            site,
            protocol,
            role="address-file",
            path=state_dir / "address.txt",
            owner="daemon",
            required=False,
            sensitive=False,
            description="Adapter-specific public address export.",
        ),
        _contract(
            site,
            protocol,
            role="address-file",
            path=state_dir / "hostname",
            owner="daemon",
            required=False,
            sensitive=False,
            description="Adapter-specific public hostname export.",
        ),
    ]


def _contract(
    site: SiteConfig,
    protocol: ProtocolConfig,
    *,
    role: str,
    path: Path,
    owner: str,
    required: bool,
    sensitive: bool,
    description: str,
) -> StatePathContract:
    return StatePathContract(
        site_id=site.id,
        protocol=protocol.name,
        role=role,
        path=path,
        owner=owner,
        required=required,
        sensitive=sensitive,
        description=description,
    )
