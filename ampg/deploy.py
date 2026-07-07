from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex

from .activation import activation_steps, apply_preflight
from .apply import start_command, supervisor_target
from .addresses import effective_address_records
from .approvals import (
    ACTIVATION_ARTIFACT_KIND,
    GENERIC_PLATFORM,
    ApprovalInput,
    approval_check,
    load_approval_registry,
)
from .config import GatewayConfig
from .dns import dns_plan
from .health import health_plan
from .install_plan import (
    install_artifacts,
    install_package_actions,
    install_plan,
    install_state_copies,
    install_supervisor_actions,
)
from .plan import plan_artifacts
from .platforms import PlatformProvider, detect_platform
from .status import DaemonProbeFunc, doctor_gateway


@dataclass(frozen=True)
class DeployStep:
    stage: str
    status: str
    command: str
    message: str


@dataclass(frozen=True)
class DeployNextStep:
    stage: str
    command: str
    message: str


@dataclass(frozen=True)
class DeployPlan:
    status: str
    steps: tuple[DeployStep, ...]
    next_steps: tuple[DeployNextStep, ...]
    message: str


def deploy_plan(
    config: GatewayConfig,
    *,
    profile: str | None = None,
    protocols: tuple[str, ...] = (),
    platform_provider: PlatformProvider | None = None,
    platform_name: str | None = None,
    daemon_probe: DaemonProbeFunc | None = None,
) -> DeployPlan:
    command_context = _CommandContext(
        config_path=config.config_path,
        profile=profile,
        protocols=protocols,
        platform=platform_name,
    )
    steps = (
        _source_step(config),
        _build_step(config, command_context),
        _dns_step(config, command_context),
        _doctor_step(
            config,
            command_context,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        ),
        _daemon_step(
            config,
            command_context,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        ),
        _package_step(
            config,
            command_context,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        ),
        _artifact_step(config, command_context, platform_provider=platform_provider),
        _apply_preflight_step(
            config,
            command_context,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        ),
        _deploy_apply_step(
            config,
            command_context,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        ),
        _address_step(config, command_context),
        _health_step(config, command_context),
    )
    status = _overall_status(steps)
    return DeployPlan(
        status=status,
        steps=steps,
        next_steps=_next_steps(steps),
        message=_overall_message(status),
    )


@dataclass(frozen=True)
class _CommandContext:
    config_path: Path
    profile: str | None
    protocols: tuple[str, ...]
    platform: str | None

    def command(self, subcommand: str, *, platform: bool = False) -> str:
        parts = ["python3", "-m", "ampg", "--config", str(self.config_path), *subcommand.split()]
        if self.profile:
            parts.extend(["--profile", self.profile])
        for protocol in self.protocols:
            parts.extend(["--protocol", protocol])
        if platform and self.platform:
            parts.extend(["--platform", self.platform])
        return " ".join(shlex.quote(part) for part in parts)


def _source_step(config: GatewayConfig) -> DeployStep:
    missing = [site for site in config.sites if not site.source.path.exists()]
    not_dirs = [
        site
        for site in config.sites
        if site.source.path.exists() and not site.source.path.is_dir()
    ]
    if missing:
        names = ", ".join(site.id for site in missing)
        return DeployStep("source", "blocked", "-", f"source path is missing for {names}")
    if not_dirs:
        names = ", ".join(site.id for site in not_dirs)
        return DeployStep("source", "blocked", "-", f"source path is not a directory for {names}")
    return DeployStep("source", "ready", "-", "source trees are readable")


def _build_step(config: GatewayConfig, commands: _CommandContext) -> DeployStep:
    missing = _missing_outputs(config)
    if missing:
        return DeployStep(
            "build",
            "todo",
            commands.command("build"),
            f"build {len(missing)} protocol output(s)",
        )
    return DeployStep("build", "ready", commands.command("build"), "selected outputs are built")


def _dns_step(config: GatewayConfig, commands: _CommandContext) -> DeployStep:
    plan = dns_plan(config)
    command = "-" if plan.status == "skipped" else commands.command("dns plan")
    return DeployStep("dns", plan.status, command, plan.message)


def _doctor_step(
    config: GatewayConfig,
    commands: _CommandContext,
    *,
    platform_provider: PlatformProvider | None,
    daemon_probe: DaemonProbeFunc | None,
) -> DeployStep:
    issues = [
        issue
        for issue in doctor_gateway(
            config,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        )
        if issue.code != "output-missing"
    ]
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    if errors:
        return DeployStep(
            "doctor",
            "blocked",
            commands.command("doctor", platform=True),
            f"fix {len(errors)} configuration or daemon error(s)",
        )
    if warnings:
        return DeployStep(
            "doctor",
            "review",
            commands.command("doctor", platform=True),
            f"review {len(warnings)} warning(s)",
        )
    return DeployStep("doctor", "ready", commands.command("doctor", platform=True), "checks pass")


def _daemon_step(
    config: GatewayConfig,
    commands: _CommandContext,
    *,
    platform_provider: PlatformProvider | None,
    daemon_probe: DaemonProbeFunc | None,
) -> DeployStep:
    steps = install_plan(
        config,
        platform_provider=platform_provider,
        daemon_probe=daemon_probe,
    )
    blocked = [step for step in steps if step.status == "blocked"]
    planned = [step for step in steps if step.status == "planned"]
    if blocked:
        return DeployStep(
            "daemons",
            "blocked",
            commands.command("install-plan", platform=True),
            f"fix {len(blocked)} daemon setup blocker(s)",
        )
    if planned:
        return DeployStep(
            "daemons",
            "todo",
            commands.command("install-plan --write-artifacts", platform=True),
            f"review {len(planned)} daemon setup action(s)",
        )
    return DeployStep(
        "daemons",
        "ready",
        commands.command("install-plan", platform=True),
        "daemon setup is ready or adopted",
    )


def _package_step(
    config: GatewayConfig,
    commands: _CommandContext,
    *,
    platform_provider: PlatformProvider | None,
    daemon_probe: DaemonProbeFunc | None,
) -> DeployStep:
    actions = install_package_actions(
        config,
        platform_provider=platform_provider,
        daemon_probe=daemon_probe,
    )
    if not actions:
        return DeployStep("packages", "ready", "-", "no managed package installs are needed")
    blocked = [action for action in actions if action.status == "blocked"]
    planned = [action for action in actions if action.status == "planned"]
    manual = [action for action in planned if not action.command]
    if blocked:
        return DeployStep(
            "packages",
            "blocked",
            commands.command("install-plan", platform=True),
            f"fix {len(blocked)} package planning blocker(s)",
        )
    if manual:
        return DeployStep(
            "packages",
            "review",
            commands.command("install-plan", platform=True),
            f"install {len(manual)} package(s) with the local package manager",
        )
    if planned:
        return DeployStep(
            "packages",
            "todo",
            commands.command("deploy apply --stage packages --dry-run", platform=True),
            f"install {len(planned)} managed daemon package(s)",
        )
    return DeployStep(
        "packages",
        "ready",
        commands.command("deploy apply --stage packages --dry-run", platform=True),
        "managed daemon packages are installed",
    )


def _artifact_step(
    config: GatewayConfig,
    commands: _CommandContext,
    *,
    platform_provider: PlatformProvider | None,
) -> DeployStep:
    approvals = load_approval_registry(config)
    checks = [
        approval_check(candidate, approvals)
        for candidate in _approval_candidates(config, platform_provider)
    ]
    if not checks:
        return DeployStep("artifacts", "ready", "-", "no generated artifacts require approval")
    missing = [check for check in checks if check.status in {"missing", "stale"}]
    review = [check for check in checks if check.status == "review"]
    if missing:
        return DeployStep(
            "artifacts",
            "todo",
            commands.command("apply --dry-run --write-artifacts", platform=True),
            f"generate or refresh {len(missing)} review artifact(s)",
        )
    if review:
        return DeployStep(
            "artifacts",
            "review",
            commands.command("approvals approve --all", platform=True),
            f"review and approve {len(review)} artifact digest(s)",
        )
    return DeployStep(
        "artifacts",
        "ready",
        commands.command("approvals list", platform=True),
        "artifact digests are approved",
    )


def _address_step(config: GatewayConfig, commands: _CommandContext) -> DeployStep:
    records = effective_address_records(config)
    placeholders = [record for record in records if record.address_status == "placeholder"]
    if placeholders:
        names = ", ".join(f"{record.site_id}/{record.protocol}" for record in placeholders)
        return DeployStep(
            "addresses",
            "review",
            commands.command("deploy apply --stage addresses --dry-run"),
            f"capture or set generated transport address(es): {names}",
        )
    return DeployStep("addresses", "ready", commands.command("addresses list"), "addresses are known")


def _health_step(config: GatewayConfig, commands: _CommandContext) -> DeployStep:
    checks = health_plan(config)
    if not checks:
        return DeployStep("health", "ready", "-", "no published health checks are needed")
    blocked = [check for check in checks if check.status == "blocked"]
    review = [check for check in checks if check.status == "review"]
    planned = [check for check in checks if check.status == "planned"]
    if blocked:
        status = "todo" if _missing_outputs(config) else "blocked"
        return DeployStep(
            "health",
            status,
            commands.command("health-plan"),
            f"fix {len(blocked)} health check blocker(s)",
        )
    if review:
        return DeployStep(
            "health",
            "review",
            commands.command("deploy apply --stage addresses --dry-run"),
            f"resolve {len(review)} health check address review item(s)",
        )
    if planned:
        return DeployStep(
            "health",
            "todo",
            commands.command("deploy apply --stage health --dry-run"),
            f"run {len(planned)} published health check(s)",
        )
    return DeployStep("health", "ready", commands.command("health-plan"), "health checks are ready")


def _apply_preflight_step(
    config: GatewayConfig,
    commands: _CommandContext,
    *,
    platform_provider: PlatformProvider | None,
    daemon_probe: DaemonProbeFunc | None,
) -> DeployStep:
    activation = activation_steps(
        config,
        platform_provider=platform_provider,
        daemon_probe=daemon_probe,
    )
    preflight = apply_preflight(
        activation=activation,
        state_copies=install_state_copies(
            config,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        ),
        supervisor_actions=install_supervisor_actions(
            config,
            platform_provider=platform_provider,
            daemon_probe=daemon_probe,
        ),
    )
    status = preflight.status
    if status == "blocked" and _missing_outputs(config):
        status = "todo"
    return DeployStep(
        "apply-preflight",
        status,
        commands.command("apply --dry-run", platform=True),
        preflight.message,
    )


def _deploy_apply_step(
    config: GatewayConfig,
    commands: _CommandContext,
    *,
    platform_provider: PlatformProvider | None,
    daemon_probe: DaemonProbeFunc | None,
) -> DeployStep:
    provider = platform_provider or detect_platform()
    state_copies = install_state_copies(
        config,
        platform_provider=provider,
        daemon_probe=daemon_probe,
    )
    supervisor_actions = install_supervisor_actions(
        config,
        platform_provider=provider,
        daemon_probe=daemon_probe,
    )
    review = [
        item
        for item in (*state_copies, *supervisor_actions)
        if item.status != "planned"
    ]
    if review:
        return DeployStep(
            "deploy-apply",
            "review",
            commands.command("apply --dry-run", platform=True),
            f"review {len(review)} staged apply input(s)",
        )
    missing_state = [copy for copy in state_copies if not copy.target.exists()]
    if missing_state:
        return DeployStep(
            "deploy-apply",
            "todo",
            commands.command("deploy apply --stage state --dry-run", platform=True),
            f"copy {len(missing_state)} approved state artifact(s)",
        )
    missing_supervisors = [
        action
        for action in supervisor_actions
        if not supervisor_target(provider, action).exists()
    ]
    if missing_supervisors:
        return DeployStep(
            "deploy-apply",
            "todo",
            commands.command("deploy apply --stage supervisor --dry-run", platform=True),
            f"install {len(missing_supervisors)} approved supervisor file(s)",
        )
    if state_copies or supervisor_actions:
        runnable = [
            action
            for action in supervisor_actions
            if start_command(provider, action, supervisor_target(provider, action))
        ]
        if runnable:
            return DeployStep(
                "deploy-apply",
                "todo",
                commands.command("deploy apply --stage start --dry-run", platform=True),
                f"start {len(runnable)} AMPG-owned service(s)",
            )
        return DeployStep(
            "deploy-apply",
            "ready",
            commands.command("deploy apply --stage supervisor --dry-run", platform=True),
            "staged deploy files are applied",
        )
    return DeployStep(
        "deploy-apply",
        "ready",
        "-",
        "no managed deploy apply stages are needed",
    )


def _approval_candidates(
    config: GatewayConfig,
    platform_provider: PlatformProvider | None,
) -> list[ApprovalInput]:
    candidates: list[ApprovalInput] = []
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            for artifact in plan_artifacts(site, protocol):
                candidates.append(
                    ApprovalInput(
                        site_id=site.id,
                        protocol=protocol.name,
                        platform=GENERIC_PLATFORM,
                        kind=ACTIVATION_ARTIFACT_KIND,
                        path=artifact.path,
                        content=artifact.content,
                    )
                )
    candidates.extend(
        ApprovalInput(
            site_id=artifact.site_id,
            protocol=artifact.protocol,
            platform=artifact.platform,
            kind=artifact.kind,
            path=artifact.path,
            content=artifact.content,
        )
        for artifact in install_artifacts(config, platform_provider=platform_provider)
    )
    return candidates


def _missing_outputs(config: GatewayConfig) -> list[str]:
    missing: list[str] = []
    for site in config.sites:
        for protocol in site.protocols.values():
            if not protocol.enabled:
                continue
            marker = site.outputs.root / protocol.name / ".ampg-output"
            if not marker.exists():
                missing.append(f"{site.id}/{protocol.name}")
    return missing


def _next_steps(steps: tuple[DeployStep, ...]) -> tuple[DeployNextStep, ...]:
    actionable = [
        step
        for step in steps
        if step.status in {"todo", "review", "blocked"} and step.command != "-"
    ]
    return tuple(
        DeployNextStep(stage=step.stage, command=step.command, message=step.message)
        for step in actionable[:5]
    )


def _overall_status(steps: tuple[DeployStep, ...]) -> str:
    statuses = [step.status for step in steps]
    if "blocked" in statuses:
        return "blocked"
    if "todo" in statuses:
        return "todo"
    if "review" in statuses:
        return "review"
    return "ready"


def _overall_message(status: str) -> str:
    if status == "blocked":
        return "deployment has blockers that must be fixed"
    if status == "todo":
        return "deployment has setup steps to run"
    if status == "review":
        return "deployment is waiting for operator review"
    return "deployment plan is ready"
