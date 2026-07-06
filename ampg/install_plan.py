from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import GatewayConfig, ProtocolConfig, SiteConfig
from .platforms import PlatformProvider, detect_platform
from .state_contract import daemon_config_path, protocol_state_dir
from .status import DaemonProbeFunc, TransportStatus, gateway_status
from .transports import fallback_transport_adapter, transport_adapter


@dataclass(frozen=True)
class InstallStep:
    site_id: str
    protocol: str
    platform: str
    stage: str
    action: str
    target: str
    status: str
    command: str
    message: str


@dataclass(frozen=True)
class InstallArtifact:
    site_id: str
    protocol: str
    platform: str
    kind: str
    path: Path
    content: str


def install_plan(
    config: GatewayConfig,
    *,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> list[InstallStep]:
    provider = platform_provider or detect_platform()
    statuses = gateway_status(
        config,
        platform_provider=provider,
        daemon_probe=daemon_probe,
    )
    status_by_protocol = {
        (status.site_id, status.protocol): status for status in statuses
    }
    steps: list[InstallStep] = []
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            status = status_by_protocol[(site.id, protocol.name)]
            steps.extend(_protocol_install_steps(config, site, protocol, provider, status))
    return steps


def blocked_install_steps(steps: list[InstallStep]) -> list[InstallStep]:
    return [step for step in steps if step.status == "blocked"]


def install_artifacts(
    config: GatewayConfig,
    *,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> list[InstallArtifact]:
    provider = platform_provider or detect_platform()
    statuses = gateway_status(
        config,
        platform_provider=provider,
        daemon_probe=daemon_probe,
    )
    status_by_protocol = {
        (status.site_id, status.protocol): status for status in statuses
    }
    artifacts: list[InstallArtifact] = []
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            status = status_by_protocol[(site.id, protocol.name)]
            artifacts.extend(_protocol_install_artifacts(config, site, protocol, provider, status))
    return artifacts


def write_install_artifacts(
    config: GatewayConfig,
    *,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> list[InstallArtifact]:
    artifacts = install_artifacts(
        config,
        platform_provider=platform_provider,
        daemon_probe=daemon_probe,
    )
    for artifact in artifacts:
        artifact.path.parent.mkdir(parents=True, exist_ok=True)
        artifact.path.write_text(artifact.content, encoding="utf-8")
    return artifacts


def _protocol_install_steps(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
    status: TransportStatus,
) -> list[InstallStep]:
    if status.action == "adopt-existing":
        return [
            _step(
                site,
                protocol,
                provider,
                stage="daemon",
                action="adopt-existing",
                target=protocol.daemon,
                status="skipped",
                command="-",
                message="existing daemon is running; no AMPG-owned install is planned",
            )
        ]
    if status.action == "render-only":
        return [
            _step(
                site,
                protocol,
                provider,
                stage="daemon",
                action="render-only",
                target=protocol.daemon,
                status="skipped",
                command="-",
                message="external policy renders outputs and review artifacts only",
            )
        ]

    if status.action != "manage-owned" or status.status == "error":
        return [
            _step(
                site,
                protocol,
                provider,
                stage="daemon",
                action=status.action,
                target=protocol.daemon,
                status="blocked",
                command="-",
                message=status.message,
            )
        ]

    adapter = transport_adapter(protocol.name, protocol.daemon)
    adapter = adapter or fallback_transport_adapter(protocol.name, protocol.daemon)
    package_steps = [
        _package_step(site, protocol, provider, protocol.daemon, installed=status.installed)
    ]
    package_steps.extend(
        _package_step(site, protocol, provider, support_daemon, installed=False)
        for support_daemon in _support_daemons(protocol)
    )
    return [
        *package_steps,
        _step(
            site,
            protocol,
            provider,
            stage="state",
            action="create-state",
            target=str(_state_dir(config, provider, site, protocol)),
            status="planned",
            command=_mkdir_command(provider, _state_dir(config, provider, site, protocol)),
            message="create AMPG-owned state directory for daemon config, keys, and logs",
        ),
        _step(
            site,
            protocol,
            provider,
            stage="config",
            action="write-managed-config",
            target=str(daemon_config_path(config, site, protocol)),
            status="planned",
            command="-",
            message=f"write managed {adapter.backend} config after plan review",
        ),
        _step(
            site,
            protocol,
            provider,
            stage="supervisor",
            action="configure-supervisor",
            target=_service_name(site, protocol),
            status="planned",
            command=_supervisor_command(provider, site, protocol),
            message=f"register AMPG-owned service with {provider.process_supervisor}",
        ),
        _step(
            site,
            protocol,
            provider,
            stage="health",
            action="check-transport",
            target=protocol.name,
            status="planned",
            command="-",
            message="verify generated site through the managed transport after start",
        ),
    ]


def _protocol_install_artifacts(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
    status: TransportStatus,
) -> list[InstallArtifact]:
    if status.action != "manage-owned" or status.status == "error":
        return []

    artifacts = [
        _artifact(
            site,
            protocol,
            provider,
            kind="daemon-config",
            filename=_daemon_config_filename(protocol),
            content=_daemon_config_content(config, site, protocol, provider),
        ),
        _artifact(
            site,
            protocol,
            provider,
            kind="daemon-supervisor",
            filename=_supervisor_filename(provider, protocol.daemon),
            content=_supervisor_content(
                config,
                site,
                protocol,
                provider,
                service_suffix=protocol.daemon,
                command=_daemon_start_command(config, site, protocol, provider),
            ),
        ),
    ]
    if protocol.name in {"tor", "i2p"}:
        artifacts.extend(
            (
                _artifact(
                    site,
                    protocol,
                    provider,
                    kind="loopback-config",
                    filename="nginx-loopback.conf",
                    content=_managed_nginx_loopback_content(config, site, protocol, provider),
                ),
                _artifact(
                    site,
                    protocol,
                    provider,
                    kind="loopback-supervisor",
                    filename=_supervisor_filename(provider, "nginx-loopback"),
                    content=_supervisor_content(
                        config,
                        site,
                        protocol,
                        provider,
                        service_suffix="nginx-loopback",
                        command=_loopback_start_command(config, site, protocol, provider),
                    ),
                ),
            )
        )
    return artifacts


def _package_step(
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
    daemon: str,
    *,
    installed: bool,
) -> InstallStep:
    package = _package_name(provider, daemon)
    return _step(
        site,
        protocol,
        provider,
        stage="package",
        action="ensure-package",
        target=package,
        status="ready" if installed else "planned",
        command="-" if installed else _package_command(provider, package),
        message=(
            f"{daemon} executable is already present"
            if installed
            else f"install package providing {daemon}"
        ),
    )


def _support_daemons(protocol: ProtocolConfig) -> tuple[str, ...]:
    if protocol.name in {"tor", "i2p"}:
        return ("nginx",)
    return ()


def _package_name(provider: PlatformProvider, daemon: str) -> str:
    if provider.name == "macos-launchd" and daemon == "ipfs":
        return "kubo"
    return daemon


def _package_command(provider: PlatformProvider, package: str) -> str:
    if provider.name == "android-termux":
        return f"pkg install {package}"
    if provider.name == "linux-systemd":
        return f"sudo apt install {package}"
    if provider.name == "macos-launchd":
        return f"brew install {package}"
    if provider.name == "linux-user":
        return f"install {package} with the user package manager"
    return "-"


def _mkdir_command(provider: PlatformProvider, path: Path) -> str:
    prefix = "sudo " if provider.can_write_system_config else ""
    return f"{prefix}mkdir -p {path}"


def _supervisor_command(
    provider: PlatformProvider,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> str:
    service = _service_name(site, protocol)
    if provider.name == "android-termux":
        return f"sv-enable {service}"
    if provider.name == "linux-systemd":
        return f"sudo systemctl enable --now {service}.service"
    if provider.name == "macos-launchd":
        return f"launchctl bootstrap gui/$UID ~/Library/LaunchAgents/org.ampg.{service}.plist"
    if provider.name == "linux-user":
        return f"run {service} under the user supervisor"
    return "-"


def _state_dir(
    config: GatewayConfig,
    provider: PlatformProvider,
    site: SiteConfig,
    protocol: ProtocolConfig,
) -> Path:
    return protocol_state_dir(config, site, protocol)


def _artifact_dir(
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
) -> Path:
    return site.outputs.plan_root / site.id / protocol.name / "managed" / provider.name


def _service_name(site: SiteConfig, protocol: ProtocolConfig) -> str:
    return f"ampg-{site.id}-{protocol.name}"


def _artifact_service_name(
    site: SiteConfig,
    protocol: ProtocolConfig,
    service_suffix: str,
) -> str:
    return f"{_service_name(site, protocol)}-{service_suffix}"


def _daemon_config_filename(protocol: ProtocolConfig) -> str:
    if protocol.name == "tor":
        return "torrc"
    if protocol.name == "i2p":
        return "i2pd-tunnels.conf"
    if protocol.name == "gemini":
        return "agate-plan.txt"
    if protocol.name == "clearnet":
        return "nginx-server.conf"
    return f"{protocol.daemon}-plan.txt"


def _daemon_config_content(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
) -> str:
    state_dir = _state_dir(config, provider, site, protocol)
    if protocol.name == "tor":
        port = int(protocol.options.get("local_port", 18080))
        hidden_service_dir = state_dir / "hidden-service"
        return f"""# Generated by AMPG. Review before installing.
DataDirectory {state_dir / "data"}
HiddenServiceDir {hidden_service_dir}/
HiddenServicePort 80 127.0.0.1:{port}
Log notice file {state_dir / "tor.log"}
"""
    if protocol.name == "i2p":
        port = int(protocol.options.get("local_port", 18081))
        key_file = protocol.options.get("keys_file", f"{site.id}-web.dat")
        tunnel_name = protocol.options.get("tunnel_name", f"{site.id}-web")
        return f"""# Generated by AMPG. Review before installing.
[{tunnel_name}]
type = server
host = 127.0.0.1
port = {port}
keys = {state_dir / str(key_file)}
"""
    if protocol.name == "gemini":
        port = int(protocol.options.get("port", 1965))
        return f"""# Generated by AMPG. Review before installing.
daemon = agate
hostname = {site.domain}
listen = [::]:{port}
content_root = {site.outputs.root / protocol.name}
certificate = {state_dir / f"{site.id}.crt"}
private_key = {state_dir / f"{site.id}.key"}
"""
    if protocol.name == "clearnet":
        return _managed_nginx_server_content(config, site, protocol, provider)
    return f"""# Generated by AMPG. Review before installing.
daemon = {protocol.daemon}
protocol = {protocol.name}
content_root = {site.outputs.root / protocol.name}
state_dir = {state_dir}
"""


def _managed_nginx_server_content(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
) -> str:
    state_dir = _state_dir(config, provider, site, protocol)
    return f"""# Generated by AMPG. Review before installing.
worker_processes 1;
error_log {state_dir / "nginx-error.log"} notice;
pid {state_dir / "nginx.pid"};

events {{
    worker_connections 128;
}}

http {{
    access_log {state_dir / "nginx-access.log"};
    server {{
        listen 80;
        listen [::]:80;
        server_name {site.domain} www.{site.domain};
        root {site.outputs.root / protocol.name};
        index index.html;

        location / {{
            try_files $uri $uri/ /index.html;
        }}
    }}
}}
"""


def _managed_nginx_loopback_content(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
) -> str:
    state_dir = _state_dir(config, provider, site, protocol)
    port = int(protocol.options.get("local_port", 18080 if protocol.name == "tor" else 18081))
    return f"""# Generated by AMPG. Review before installing.
worker_processes 1;
error_log {state_dir / "nginx-loopback-error.log"} notice;
pid {state_dir / "nginx-loopback.pid"};

events {{
    worker_connections 128;
}}

http {{
    access_log {state_dir / "nginx-loopback-access.log"};
    server {{
        listen 127.0.0.1:{port};
        server_name _;
        root {site.outputs.root / protocol.name};
        index index.html;

        location / {{
            try_files $uri $uri/ /index.html;
        }}
    }}
}}
"""


def _supervisor_filename(provider: PlatformProvider, service_suffix: str) -> str:
    if provider.name == "linux-systemd":
        return f"{service_suffix}.service"
    if provider.name == "macos-launchd":
        return f"org.ampg.{service_suffix}.plist"
    return f"{service_suffix}.run"


def _supervisor_content(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
    *,
    service_suffix: str,
    command: str,
) -> str:
    service_name = _artifact_service_name(site, protocol, service_suffix)
    if provider.name == "linux-systemd":
        return f"""# Generated by AMPG. Review before installing.
[Unit]
Description=AMPG {protocol.name} {service_suffix} for {site.id}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={_state_dir(config, provider, site, protocol)}
ExecStart=/bin/sh -lc '{_shell_single_quote(command)}'
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    if provider.name == "macos-launchd":
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>org.ampg.{service_name}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>-lc</string>
    <string>{_xml_escape(command)}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
"""
    shell = "/data/data/com.termux/files/usr/bin/sh" if provider.name == "android-termux" else "/bin/sh"
    return f"""#!{shell}
# Generated by AMPG. Review before installing.
set -eu
mkdir -p {_state_dir(config, provider, site, protocol)}
{command}
"""


def _daemon_start_command(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
) -> str:
    state_dir = _state_dir(config, provider, site, protocol)
    if protocol.name == "tor":
        return f"exec tor -f {state_dir / 'torrc'}"
    if protocol.name == "i2p":
        return f"exec i2pd --datadir={state_dir / 'data'} --tunconf={state_dir / 'i2pd-tunnels.conf'}"
    if protocol.name == "gemini":
        port = int(protocol.options.get("port", 1965))
        return (
            "exec agate "
            f"--content {site.outputs.root / protocol.name} "
            f"--addr [::]:{port} "
            f"--hostname {site.domain} "
            f"--certs {state_dir}"
        )
    if protocol.name == "clearnet":
        return f"exec nginx -c {state_dir / 'nginx-server.conf'} -g 'daemon off;'"
    return f"exec {protocol.daemon}"


def _loopback_start_command(
    config: GatewayConfig,
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
) -> str:
    state_dir = _state_dir(config, provider, site, protocol)
    return f"exec nginx -c {state_dir / 'nginx-loopback.conf'} -g 'daemon off;'"


def _artifact(
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
    *,
    kind: str,
    filename: str,
    content: str,
) -> InstallArtifact:
    return InstallArtifact(
        site_id=site.id,
        protocol=protocol.name,
        platform=provider.name,
        kind=kind,
        path=_artifact_dir(site, protocol, provider) / filename,
        content=content,
    )


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _shell_single_quote(value: str) -> str:
    return value.replace("'", "'\\''")


def _step(
    site: SiteConfig,
    protocol: ProtocolConfig,
    provider: PlatformProvider,
    *,
    stage: str,
    action: str,
    target: str,
    status: str,
    command: str,
    message: str,
) -> InstallStep:
    return InstallStep(
        site_id=site.id,
        protocol=protocol.name,
        platform=provider.name,
        stage=stage,
        action=action,
        target=target,
        status=status,
        command=command,
        message=message,
    )
