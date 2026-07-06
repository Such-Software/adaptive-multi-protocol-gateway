from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import GatewayConfig, ProtocolConfig, SiteConfig
from .plan import plan_artifacts, write_plan_artifacts
from .platforms import PlatformProvider
from .status import (
    DaemonProbeFunc,
    TransportStatus,
    doctor_gateway,
    gateway_status,
)


@dataclass(frozen=True)
class ActivationStep:
    site_id: str
    protocol: str
    stage: str
    action: str
    target: str
    status: str
    message: str


def activation_steps(
    config: GatewayConfig,
    *,
    platform_provider: PlatformProvider | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> list[ActivationStep]:
    statuses = gateway_status(
        config,
        platform_provider=platform_provider,
        daemon_probe=daemon_probe,
    )
    status_by_protocol = {
        (status.site_id, status.protocol): status for status in statuses
    }
    steps: list[ActivationStep] = []

    for issue in doctor_gateway(
        config,
        platform_provider=platform_provider,
        daemon_probe=daemon_probe,
        statuses=statuses,
    ):
        if issue.code in {"daemon-status", "output-missing"}:
            continue
        steps.append(
            ActivationStep(
                site_id=issue.site_id,
                protocol=issue.protocol,
                stage="preflight",
                action="fix-issue",
                target="-",
                status=_issue_activation_status(issue.severity),
                message=f"{issue.code}: {issue.message}",
            )
        )

    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            output_ready = _output_ready(site, protocol)
            transport_status = status_by_protocol[(site.id, protocol.name)]
            steps.extend(
                _protocol_steps(
                    site,
                    protocol,
                    transport_status=transport_status,
                    output_ready=output_ready,
                )
            )

    return steps


def blocked_steps(steps: list[ActivationStep]) -> list[ActivationStep]:
    return [step for step in steps if step.status == "blocked"]


def _protocol_steps(
    site: SiteConfig,
    protocol: ProtocolConfig,
    *,
    transport_status: TransportStatus,
    output_ready: bool,
) -> list[ActivationStep]:
    output_root = site.outputs.root / protocol.name
    steps = [
        ActivationStep(
            site_id=site.id,
            protocol=protocol.name,
            stage="output",
            action="verify-output",
            target=str(output_root),
            status="ready" if output_ready else "blocked",
            message=(
                "generated output marker exists"
                if output_ready
                else "generated output is missing; run build before apply"
            ),
        )
    ]

    artifacts = plan_artifacts(site, protocol)
    if artifacts:
        for artifact in artifacts:
            steps.append(
                ActivationStep(
                    site_id=site.id,
                    protocol=protocol.name,
                    stage="artifact",
                    action="review-config",
                    target=str(artifact.path),
                    status="review",
                    message="review generated config before installing or reloading services",
                )
            )
    else:
        steps.append(
            ActivationStep(
                site_id=site.id,
                protocol=protocol.name,
                stage="artifact",
                action="review-config",
                target="-",
                status="planned",
                message="no generated config artifact is available for this adapter yet",
            )
        )

    steps.append(
        ActivationStep(
            site_id=site.id,
            protocol=protocol.name,
            stage="daemon",
            action=transport_status.action,
            target=protocol.daemon,
            status=_transport_activation_status(transport_status),
            message=transport_status.message,
        )
    )
    steps.append(
        ActivationStep(
            site_id=site.id,
            protocol=protocol.name,
            stage="health",
            action="check-transport",
            target=protocol.name,
            status=(
                "planned"
                if output_ready and transport_status.status != "error"
                else "blocked"
            ),
            message=(
                "verify generated site through this transport after apply"
                if output_ready and transport_status.status != "error"
                else "health check is blocked until output and daemon steps are ready"
            ),
        )
    )
    return steps


def _output_ready(site: SiteConfig, protocol: ProtocolConfig) -> bool:
    return ((site.outputs.root / protocol.name) / ".ampg-output").exists()


def _issue_activation_status(severity: str) -> str:
    if severity == "error":
        return "blocked"
    return "review"


def _transport_activation_status(status: TransportStatus) -> str:
    if status.status == "error":
        return "blocked"
    if status.action == "render-only" or status.status == "warn":
        return "review"
    return "ready"


def write_activation_artifacts(config: GatewayConfig) -> tuple[Path, ...]:
    return tuple(artifact.path for artifact in write_plan_artifacts(config))
