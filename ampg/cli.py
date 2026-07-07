from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .activation import (
    ApplyPreflight,
    ApplyPreflightItem,
    ActivationStep,
    activation_steps,
    apply_preflight,
    blocked_steps,
    write_activation_artifacts,
)
from .addresses import (
    AddressCaptureResult,
    AddressRecord,
    address_registry_path,
    capture_addresses,
    effective_address_records,
    set_address,
)
from .apply import (
    AddressApplyResult,
    StateApplyResult,
    StartApplyResult,
    SupervisorApplyResult,
    apply_addresses,
    apply_state,
    apply_start,
    apply_supervisor,
    format_command,
)
from .approvals import (
    ACTIVATION_ARTIFACT_KIND,
    GENERIC_PLATFORM,
    ApprovalCheck,
    ApprovalInput,
    ApprovalWriteResult,
    approval_check,
    approval_registry_path,
    approve_artifacts,
    load_approval_registry,
)
from .audit import audit_gateway
from .build import build_gateway
from .config import load_config
from .deploy import DeployPlan, DeployStep, DeployNextStep, deploy_plan
from .dns import (
    ConnectivityHint,
    DNSCheckResult,
    DNS_MODES,
    DNSPlan,
    DNSRecordPlan,
    FreeDomainHint,
    dns_check,
    dns_plan,
)
from .docsgen import generate_docs
from .health import HealthCheck, blocked_health_checks, health_plan
from .install_plan import (
    InstallStateCopy,
    InstallStep,
    InstallSupervisorAction,
    install_artifacts,
    blocked_install_steps,
    install_state_copies,
    install_supervisor_actions,
    install_plan,
    write_install_artifacts,
)
from .manifest import write_fixture_manifests
from .onboarding import PRESETS, init_site_config, parse_protocol_filters
from .plan import plan_artifacts, plan_gateway, write_plan_artifacts
from .platforms import PLATFORM_NAMES, platform_by_name
from .preview import PreviewServers, preview_endpoints, write_preview_fixture_manifests
from .route_manifest import (
    load_route_manifest,
    route_manifest_schema_json,
    validate_route_manifest,
)
from .route_policy import RouteExposure, RouteIssue, route_exposures, route_issues
from .selection import protocols_for_selection, select_profile, select_protocols
from .state_contract import StatePathContract, state_contract
from .status import DoctorIssue, TransportStatus, doctor_gateway, gateway_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ampg")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("gateway.toml"),
        help="Path to gateway TOML config.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    init_parser = subcommands.add_parser(
        "init",
        help="Create a gateway config for an existing site.",
    )
    init_subcommands = init_parser.add_subparsers(dest="init_command", required=True)
    init_site = init_subcommands.add_parser(
        "site",
        help="Create gateway.toml for an existing static HTML site.",
    )
    init_site.add_argument("site_id", help="Stable site id used in output/state paths.")
    init_site.add_argument("--domain", required=True, help="Canonical clearnet domain.")
    init_site.add_argument("--source", required=True, type=Path, help="Existing site source tree.")
    init_site.add_argument(
        "--source-kind",
        default="static-html",
        choices=("static-html",),
        help="Source adapter kind.",
    )
    init_site.add_argument(
        "--preset",
        choices=sorted(PRESETS),
        default="full",
        help="Transport preset to enable when --protocol is omitted.",
    )
    init_site.add_argument(
        "--protocol",
        action="append",
        default=[],
        help="Protocol to enable. May be repeated or comma-separated.",
    )
    init_site.add_argument(
        "--output-root",
        type=Path,
        help="Generated output root. Defaults to ./dist/<site>.",
    )
    init_site.add_argument(
        "--plan-root",
        type=Path,
        help="Generated review artifact root. Defaults to ./dist/ampg-plan.",
    )
    init_site.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing config file.",
    )
    deploy_parser = subcommands.add_parser(
        "deploy",
        help="Plan or run a guided site deployment.",
    )
    deploy_subcommands = deploy_parser.add_subparsers(dest="deploy_command", required=True)
    deploy_plan_parser = deploy_subcommands.add_parser(
        "plan",
        help="Show the simplest next steps for this deployment.",
    )
    _add_target_selection(deploy_plan_parser)
    deploy_plan_parser.add_argument(
        "--platform",
        choices=PLATFORM_NAMES,
        help="Override platform detection for deploy planning.",
    )
    deploy_apply_parser = deploy_subcommands.add_parser(
        "apply",
        help="Apply an approved deployment stage.",
    )
    _add_target_selection(deploy_apply_parser)
    deploy_apply_parser.add_argument(
        "--stage",
        choices=("state", "supervisor", "start", "addresses"),
        required=True,
        help="Deployment stage to apply.",
    )
    deploy_apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    deploy_apply_parser.add_argument(
        "--yes",
        action="store_true",
        help="Required for live stage application.",
    )
    deploy_apply_parser.add_argument(
        "--platform",
        choices=PLATFORM_NAMES,
        help="Override platform detection for deploy apply.",
    )
    dns_parser = subcommands.add_parser(
        "dns",
        help="Plan and check clearnet DNS records.",
    )
    dns_subcommands = dns_parser.add_subparsers(dest="dns_command", required=True)
    dns_plan_parser = dns_subcommands.add_parser(
        "plan",
        help="Show DNS and reachability steps for clearnet.",
    )
    _add_target_selection(dns_plan_parser)
    dns_plan_parser.add_argument(
        "--mode",
        choices=DNS_MODES,
        default="static",
        help="Use static A/AAAA records or dynamic DNS guidance.",
    )
    dns_plan_parser.add_argument("--ipv4", help="Public IPv4 address for static DNS.")
    dns_plan_parser.add_argument("--ipv6", help="Public IPv6 address for static DNS.")
    dns_plan_parser.add_argument(
        "--dynamic-hostname",
        help="Dynamic DNS hostname used in dynamic mode.",
    )
    dns_plan_parser.add_argument(
        "--behind-router",
        action="store_true",
        help="Include NAT/router/tunnel reachability hints.",
    )
    dns_plan_parser.add_argument(
        "--free-domain-hints",
        action="store_true",
        help="Include optional free subdomain registries to consider.",
    )
    dns_check_parser = dns_subcommands.add_parser(
        "check",
        help="Resolve clearnet domains and compare optional expected addresses.",
    )
    _add_target_selection(dns_check_parser)
    dns_check_parser.add_argument("--ipv4", help="Expected public IPv4 address.")
    dns_check_parser.add_argument("--ipv6", help="Expected public IPv6 address.")
    plan_parser = subcommands.add_parser("plan", help="Print a dry-run plan.")
    _add_target_selection(plan_parser)
    plan_parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Write generated config snippets to the configured plan root.",
    )
    status_parser = subcommands.add_parser(
        "status",
        help="Show enabled transport daemon decisions.",
    )
    _add_target_selection(status_parser)
    status_parser.add_argument(
        "--platform",
        choices=PLATFORM_NAMES,
        help="Override platform detection for dry-run checks.",
    )
    doctor_parser = subcommands.add_parser(
        "doctor",
        help="Check source, renderer, route, and daemon readiness.",
    )
    _add_target_selection(doctor_parser)
    doctor_parser.add_argument(
        "--platform",
        choices=PLATFORM_NAMES,
        help="Override platform detection for dry-run checks.",
    )
    apply_parser = subcommands.add_parser(
        "apply",
        help="Show or run the transport activation sequence.",
    )
    _add_target_selection(apply_parser)
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the activation sequence without changing services.",
    )
    apply_parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Write generated config snippets to the configured plan root.",
    )
    apply_parser.add_argument(
        "--platform",
        choices=PLATFORM_NAMES,
        help="Override platform detection for dry-run checks.",
    )
    approvals_parser = subcommands.add_parser(
        "approvals",
        help="Inspect or approve generated artifact digests.",
    )
    approvals_subcommands = approvals_parser.add_subparsers(
        dest="approvals_command",
        required=True,
    )
    approvals_list = approvals_subcommands.add_parser(
        "list",
        help="List generated artifacts and approval status.",
    )
    _add_target_selection(approvals_list)
    approvals_list.add_argument(
        "--platform",
        choices=PLATFORM_NAMES,
        help="Override platform detection for approval candidates.",
    )
    approvals_list.add_argument(
        "--kind",
        action="append",
        default=[],
        help="Limit to an approval kind. May be repeated or comma-separated.",
    )
    approvals_approve = approvals_subcommands.add_parser(
        "approve",
        help="Record approvals for reviewed artifact digests.",
    )
    _add_target_selection(approvals_approve)
    approvals_approve.add_argument(
        "--platform",
        choices=PLATFORM_NAMES,
        help="Override platform detection for approval candidates.",
    )
    approvals_approve.add_argument(
        "--kind",
        action="append",
        default=[],
        help="Limit to an approval kind. May be repeated or comma-separated.",
    )
    approvals_approve.add_argument(
        "--all",
        action="store_true",
        help="Approve all selected generated artifact kinds.",
    )
    install_plan_parser = subcommands.add_parser(
        "install-plan",
        help="Print managed daemon package, state, and supervisor steps.",
    )
    _add_target_selection(install_plan_parser)
    install_plan_parser.add_argument(
        "--platform",
        choices=PLATFORM_NAMES,
        help="Override platform detection for install planning.",
    )
    install_plan_parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Write managed daemon config and supervisor artifacts to the plan root.",
    )
    health_parser = subcommands.add_parser(
        "health-plan",
        help="Print fixture-based transport health checks.",
    )
    _add_target_selection(health_parser)
    health_parser.add_argument(
        "--mode",
        choices=("published", "preview"),
        default="published",
        help="Plan checks against published transport URLs or local preview URLs.",
    )
    health_parser.add_argument(
        "--base-port",
        type=int,
        default=19080,
        help="First loopback port assigned to preview health checks.",
    )
    health_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Loopback host for preview health checks.",
    )
    build_parser = subcommands.add_parser("build", help="Build enabled protocol outputs.")
    _add_target_selection(build_parser)
    fixture_parser = subcommands.add_parser("manifest", help="Write AMPB fixture manifests.")
    _add_target_selection(fixture_parser)
    addresses_parser = subcommands.add_parser(
        "addresses",
        help="Inspect or update captured transport addresses.",
    )
    addresses_subcommands = addresses_parser.add_subparsers(
        dest="addresses_command",
        required=True,
    )
    addresses_list = addresses_subcommands.add_parser(
        "list",
        help="Print effective configured, captured, derived, and placeholder addresses.",
    )
    _add_target_selection(addresses_list)
    addresses_capture = addresses_subcommands.add_parser(
        "capture",
        help="Capture generated transport addresses from daemon state files.",
    )
    _add_target_selection(addresses_capture)
    addresses_set = addresses_subcommands.add_parser(
        "set",
        help="Manually store a generated transport address in AMPG state.",
    )
    addresses_set.add_argument("--site", required=True, help="Site id to update.")
    addresses_set.add_argument(
        "--protocol",
        dest="address_protocol",
        required=True,
        help="Protocol name to update.",
    )
    addresses_set.add_argument("--url", required=True, help="Public transport URL or hostname.")
    addresses_set.add_argument(
        "--source",
        default="manual",
        help="Source label stored with the captured address.",
    )
    state_contract_parser = subcommands.add_parser(
        "state-contract",
        help="Print AMPG-owned state paths and daemon-written files.",
    )
    _add_target_selection(state_contract_parser)
    preview_parser = subcommands.add_parser("preview", help="Preview generated outputs locally.")
    preview_subcommands = preview_parser.add_subparsers(dest="preview_command", required=True)
    for preview_command in ("endpoints", "manifest", "serve"):
        command_parser = preview_subcommands.add_parser(
            preview_command,
            help=f"Preview {preview_command} for generated outputs.",
        )
        _add_target_selection(command_parser)
        command_parser.add_argument(
            "--base-port",
            type=int,
            default=19080,
            help="First loopback port assigned to enabled protocol outputs.",
        )
        command_parser.add_argument(
            "--host",
            default="127.0.0.1",
            help="Loopback host for preview URLs.",
        )
    routes_parser = subcommands.add_parser("routes", help="Explain route exposure policy.")
    routes_subcommands = routes_parser.add_subparsers(dest="routes_command", required=True)
    routes_explain = routes_subcommands.add_parser(
        "explain",
        help="Print per-protocol route decisions.",
    )
    _add_target_selection(routes_explain)
    routes_validate = routes_subcommands.add_parser(
        "validate",
        help="Fail when a public route has no compatible enabled protocol.",
    )
    _add_target_selection(routes_validate)
    manifest_parser = subcommands.add_parser(
        "route-manifest",
        help="Validate or print the app route manifest contract.",
    )
    manifest_subcommands = manifest_parser.add_subparsers(
        dest="route_manifest_command",
        required=True,
    )
    manifest_validate = manifest_subcommands.add_parser(
        "validate",
        help="Validate an ampg.route-manifest.v1 JSON file.",
    )
    manifest_validate.add_argument("path", type=Path, help="Route manifest JSON path.")
    manifest_schema = manifest_subcommands.add_parser(
        "schema",
        help="Print the JSON Schema for route manifests.",
    )
    manifest_schema.add_argument(
        "--output",
        type=Path,
        help="Write the JSON Schema to this path instead of stdout.",
    )
    audit_parser = subcommands.add_parser("audit", help="Audit source HTML quality.")
    audit_parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="Exit non-zero when warnings are found.",
    )
    docs_parser = subcommands.add_parser("docs", help="Generate or check generated docs.")
    docs_subcommands = docs_parser.add_subparsers(dest="docs_command", required=True)
    docs_generate = docs_subcommands.add_parser("generate", help="Generate docs from code.")
    docs_generate.add_argument(
        "--check",
        action="store_true",
        help="Fail if generated docs are stale instead of writing them.",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "docs":
            return _cmd_docs(args)
        if args.command == "route-manifest":
            return _cmd_route_manifest(args)
        config = _selected_config(load_config(args.config), args)
        if args.command == "plan":
            return _cmd_plan(config, write_artifacts=_write_artifacts_enabled(config, args))
        if args.command == "status":
            return _cmd_status(config, args)
        if args.command == "doctor":
            return _cmd_doctor(config, args)
        if args.command == "deploy":
            return _cmd_deploy(config, args)
        if args.command == "dns":
            return _cmd_dns(config, args)
        if args.command == "apply":
            return _cmd_apply(config, args)
        if args.command == "approvals":
            return _cmd_approvals(config, args)
        if args.command == "install-plan":
            return _cmd_install_plan(config, args)
        if args.command == "health-plan":
            return _cmd_health_plan(config, args)
        if args.command == "build":
            return _cmd_build(config)
        if args.command == "manifest":
            return _cmd_manifest(config)
        if args.command == "addresses":
            return _cmd_addresses(config, args)
        if args.command == "state-contract":
            return _cmd_state_contract(config)
        if args.command == "preview":
            return _cmd_preview(config, args)
        if args.command == "routes":
            return _cmd_routes(config, args)
        if args.command == "audit":
            return _cmd_audit(config, fail_on_warn=args.fail_on_warn)
    except Exception as exc:  # noqa: BLE001 - CLI should print concise failures.
        print(f"AMPG status=error message={exc}", file=sys.stderr)
        return 1
    return 1


def _cmd_init(args) -> int:
    if args.init_command == "site":
        result = init_site_config(
            config_path=args.config,
            site_id=args.site_id,
            domain=args.domain,
            source=args.source,
            source_kind=args.source_kind,
            preset=args.preset,
            protocols=parse_protocol_filters(args.protocol),
            output_root=args.output_root,
            plan_root=args.plan_root,
            force=args.force,
        )
        protocol_text = ",".join(result.protocols)
        print(
            "AMPG_INIT_SITE "
            f"status=written "
            f"path=\"{_quote(str(result.config_path))}\" "
            f"site={result.site_id} "
            f"domain={result.domain} "
            f"protocols={protocol_text}"
        )
        for profile in result.profiles:
            print(f"AMPG_INIT_PROFILE name={profile}")
        for protocol in ("clearnet", "tor", "i2p", "gemini"):
            enabled = protocol in result.protocols
            print(
                "AMPG_INIT_TOGGLE "
                f"protocol={protocol} "
                f"enabled={_bool(enabled)} "
                f"field=\"[site.protocols.{protocol}].enabled\""
            )
        config_arg = str(result.config_path)
        profile_arg = result.profiles[0] if result.profiles else "-"
        next_commands = [
            f"python3 -m ampg --config {config_arg} build",
            f"python3 -m ampg --config {config_arg} doctor",
            f"python3 -m ampg --config {config_arg} install-plan --profile {profile_arg} --write-artifacts",
            f"python3 -m ampg --config {config_arg} approvals list --profile {profile_arg}",
            f"python3 -m ampg --config {config_arg} apply --dry-run --profile {profile_arg}",
        ]
        for index, command in enumerate(next_commands, start=1):
            print(f"AMPG_INIT_NEXT step={index} command=\"{_quote(command)}\"")
        return 0
    return 1


def _cmd_deploy(config, args) -> int:
    if args.deploy_command == "plan":
        platform_provider = _platform_override(config, args)
        plan = deploy_plan(
            config,
            profile=getattr(args, "profile", None),
            protocols=parse_protocol_filters(getattr(args, "protocol", ())),
            platform_provider=platform_provider,
            platform_name=platform_provider.name if platform_provider else None,
        )
        for step in plan.steps:
            _print_deploy_step(step)
        for index, next_step in enumerate(plan.next_steps, start=1):
            _print_deploy_next(index, next_step)
        _print_deploy_summary(config, plan)
        return 1 if plan.status == "blocked" else 0
    if args.deploy_command == "apply":
        if not args.dry_run and not args.yes:
            print(
                'AMPG_DEPLOY_APPLY status=error message="live deploy apply requires --yes or rerun with --dry-run"',
                file=sys.stderr,
            )
            return 1
        platform_provider = _platform_override(config, args)
        if args.stage == "state":
            results = apply_state(
                config,
                dry_run=args.dry_run,
                platform_provider=platform_provider,
            )
            for result in results:
                _print_state_apply_result(result)
            blocked = [result for result in results if result.status == "blocked"]
            written = [result for result in results if result.status == "written"]
            planned = [result for result in results if result.status == "planned"]
            print(
                "AMPG_DEPLOY_APPLY_SUMMARY "
                f"stage=state "
                f"mode={'dry-run' if args.dry_run else 'live'} "
                f"results={len(results)} "
                f"planned={len(planned)} "
                f"written={len(written)} "
                f"blocked={len(blocked)}"
            )
            return 1 if blocked else 0
        if args.stage == "supervisor":
            results = apply_supervisor(
                config,
                dry_run=args.dry_run,
                platform_provider=platform_provider,
            )
            for result in results:
                _print_supervisor_apply_result(result)
            blocked = [result for result in results if result.status == "blocked"]
            written = [result for result in results if result.status == "written"]
            planned = [result for result in results if result.status == "planned"]
            print(
                "AMPG_DEPLOY_APPLY_SUMMARY "
                f"stage=supervisor "
                f"mode={'dry-run' if args.dry_run else 'live'} "
                f"results={len(results)} "
                f"planned={len(planned)} "
                f"written={len(written)} "
                f"blocked={len(blocked)}"
            )
            return 1 if blocked else 0
        if args.stage == "start":
            results = apply_start(
                config,
                dry_run=args.dry_run,
                platform_provider=platform_provider,
            )
            for result in results:
                _print_start_apply_result(result)
            blocked = [result for result in results if result.status == "blocked"]
            started = [result for result in results if result.status == "started"]
            planned = [result for result in results if result.status == "planned"]
            print(
                "AMPG_DEPLOY_APPLY_SUMMARY "
                f"stage=start "
                f"mode={'dry-run' if args.dry_run else 'live'} "
                f"results={len(results)} "
                f"planned={len(planned)} "
                f"started={len(started)} "
                f"blocked={len(blocked)}"
            )
            return 1 if blocked else 0
        if args.stage == "addresses":
            results = apply_addresses(config, dry_run=args.dry_run)
            for result in results:
                _print_address_apply_result(result)
            blocked = [result for result in results if result.status == "blocked"]
            written = [result for result in results if result.status == "written"]
            planned = [result for result in results if result.status == "planned"]
            skipped = [result for result in results if result.status == "skipped"]
            print(
                "AMPG_DEPLOY_APPLY_SUMMARY "
                f"stage=addresses "
                f"mode={'dry-run' if args.dry_run else 'live'} "
                f"results={len(results)} "
                f"planned={len(planned)} "
                f"written={len(written)} "
                f"skipped={len(skipped)} "
                f"blocked={len(blocked)} "
                f"registry=\"{_quote(str(address_registry_path(config)))}\""
            )
            return 1 if blocked else 0
    return 1


def _cmd_dns(config, args) -> int:
    if args.dns_command == "plan":
        plan = dns_plan(
            config,
            mode=args.mode,
            ipv4=args.ipv4,
            ipv6=args.ipv6,
            dynamic_hostname=args.dynamic_hostname,
            behind_router=args.behind_router,
            free_domain_hints=args.free_domain_hints,
        )
        for record in plan.records:
            _print_dns_record(record)
        for hint in plan.hints:
            _print_connectivity_hint(hint)
        for hint in plan.free_domains:
            _print_free_domain_hint(hint)
        _print_dns_summary(plan)
        return 1 if plan.status == "blocked" else 0

    if args.dns_command == "check":
        results = dns_check(config, ipv4=args.ipv4, ipv6=args.ipv6)
        for result in results:
            _print_dns_check(result)
        failed = [result for result in results if result.status in {"missing", "mismatch"}]
        print(
            "AMPG_DNS_CHECK_SUMMARY "
            f"checks={len(results)} "
            f"matched={sum(1 for result in results if result.status == 'matched')} "
            f"resolved={sum(1 for result in results if result.status == 'resolved')} "
            f"missing={sum(1 for result in results if result.status == 'missing')} "
            f"mismatch={sum(1 for result in results if result.status == 'mismatch')}"
        )
        return 1 if failed else 0

    return 1


def _cmd_apply(config, args) -> int:
    if not args.dry_run:
        print(
            'AMPG_APPLY status=error message="live apply is not implemented; rerun with --dry-run"',
            file=sys.stderr,
        )
        return 1

    platform_provider = _platform_override(config, args)
    write_artifacts = _write_artifacts_enabled(config, args)
    if write_artifacts:
        for path in write_activation_artifacts(config, platform_provider=platform_provider):
            print(f"AMPG_APPLY_ARTIFACT path={path} status=written")

    state_copies = install_state_copies(config, platform_provider=platform_provider)
    supervisor_actions = install_supervisor_actions(config, platform_provider=platform_provider)
    if write_artifacts:
        for copy in state_copies:
            _print_install_state_copy(copy)
        for action in supervisor_actions:
            _print_supervisor_action(action)

    steps = activation_steps(config, platform_provider=platform_provider)
    for step in steps:
        _print_activation_step(step)

    preflight = apply_preflight(
        activation=steps,
        state_copies=state_copies,
        supervisor_actions=supervisor_actions,
    )
    for item in preflight.items:
        if item.status in {"blocked", "review"}:
            _print_apply_preflight_item(item)
    _print_apply_preflight(preflight)

    print(
        "AMPG_APPLY_SUMMARY "
        "mode=dry-run "
        f"sites={len(config.sites)} "
        f"steps={len(steps)} "
        f"ready={sum(1 for step in steps if step.status == 'ready')} "
        f"review={sum(1 for step in steps if step.status == 'review')} "
        f"planned={sum(1 for step in steps if step.status == 'planned')} "
        f"blocked={len(blocked_steps(steps))}"
    )
    return 1 if preflight.status == "blocked" else 0


def _cmd_approvals(config, args) -> int:
    platform_provider = _platform_override(config, args)
    kinds = _kind_filter(args)
    candidates = _approval_candidates(config, platform_provider=platform_provider)
    if kinds:
        candidates = [candidate for candidate in candidates if candidate.kind in kinds]

    if args.approvals_command == "list":
        approvals = load_approval_registry(config)
        checks = [approval_check(candidate, approvals) for candidate in candidates]
        for check in checks:
            _print_approval_check(check)
        _print_approval_summary(
            mode="list",
            statuses=[check.status for check in checks],
            count=len(checks),
            registry=approval_registry_path(config),
        )
        return 0

    if args.approvals_command == "approve":
        if not args.all and not kinds:
            print(
                'AMPG_APPROVAL status=error message="pass --all or --kind before approving"',
                file=sys.stderr,
            )
            return 1
        results = approve_artifacts(config, candidates)
        for result in results:
            _print_approval_write_result(result)
        _print_approval_summary(
            mode="approve",
            statuses=[result.status for result in results],
            count=len(results),
            registry=approval_registry_path(config),
        )
        return 1 if any(result.status in {"missing", "stale"} for result in results) else 0

    return 1


def _cmd_install_plan(config, args) -> int:
    platform_provider = _platform_override(config, args)
    if _write_artifacts_enabled(config, args):
        for artifact in write_install_artifacts(
            config,
            platform_provider=platform_provider,
        ):
            print(
                "AMPG_INSTALL_ARTIFACT "
                f"site={artifact.site_id} "
                f"protocol={artifact.protocol} "
                f"platform={artifact.platform} "
                f"kind={artifact.kind} "
                f"path={artifact.path}"
            )
    steps = install_plan(config, platform_provider=platform_provider)
    for step in steps:
        _print_install_step(step)
    blocked = blocked_install_steps(steps)
    print(
        "AMPG_INSTALL_SUMMARY "
        f"sites={len(config.sites)} "
        f"steps={len(steps)} "
        f"planned={sum(1 for step in steps if step.status == 'planned')} "
        f"ready={sum(1 for step in steps if step.status == 'ready')} "
        f"skipped={sum(1 for step in steps if step.status == 'skipped')} "
        f"blocked={len(blocked)}"
    )
    return 1 if blocked else 0


def _cmd_health_plan(config, args) -> int:
    checks = health_plan(
        config,
        mode=args.mode,
        base_port=args.base_port,
        host=args.host,
    )
    for check in checks:
        _print_health_check(check)
    blocked = blocked_health_checks(checks)
    print(
        "AMPG_HEALTH_SUMMARY "
        f"mode={args.mode} "
        f"sites={len(config.sites)} "
        f"checks={len(checks)} "
        f"planned={sum(1 for check in checks if check.status == 'planned')} "
        f"review={sum(1 for check in checks if check.status == 'review')} "
        f"blocked={len(blocked)}"
    )
    return 1 if blocked else 0


def _add_target_selection(parser) -> None:
    parser.add_argument(
        "--profile",
        help="Named deployment profile from gateway config.",
    )
    parser.add_argument(
        "--protocol",
        action="append",
        default=[],
        help="Limit this command to one protocol. May be repeated or comma-separated.",
    )


def _selected_config(config, args):
    protocols = protocols_for_selection(
        config,
        raw_protocols=getattr(args, "protocol", None),
        profile_name=getattr(args, "profile", None),
    )
    return select_protocols(config, protocols)


def _write_artifacts_enabled(config, args) -> bool:
    if getattr(args, "write_artifacts", False):
        return True
    profile = select_profile(config, getattr(args, "profile", None))
    return bool(profile and profile.write_artifacts)


def _approval_candidates(config, *, platform_provider) -> list[ApprovalInput]:
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


def _kind_filter(args) -> set[str]:
    kinds: set[str] = set()
    for raw_kind in getattr(args, "kind", ()):
        kinds.update(kind.strip() for kind in raw_kind.split(",") if kind.strip())
    return kinds


def _cmd_status(config, args) -> int:
    statuses = gateway_status(config, platform_provider=_platform_override(config, args))
    for status in statuses:
        _print_transport_status(status)
    print(
        "AMPG_STATUS_SUMMARY "
        f"sites={len(config.sites)} "
        f"protocols={len(statuses)} "
        f"ok={sum(1 for status in statuses if status.status == 'ok')} "
        f"warnings={sum(1 for status in statuses if status.status == 'warn')} "
        f"errors={sum(1 for status in statuses if status.status == 'error')}"
    )
    return 0


def _cmd_doctor(config, args) -> int:
    platform_provider = _platform_override(config, args)
    statuses = gateway_status(config, platform_provider=platform_provider)
    issues = doctor_gateway(config, platform_provider=platform_provider, statuses=statuses)
    for status in statuses:
        _print_transport_status(status)
    for issue in issues:
        _print_doctor_issue(issue)
    errors = sum(1 for issue in issues if issue.severity == "error")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    print(
        "AMPG_DOCTOR_SUMMARY "
        f"sites={len(config.sites)} "
        f"checks={len(statuses) + len(issues)} "
        f"warnings={warnings} "
        f"errors={errors}"
    )
    return 1 if errors else 0


def _cmd_plan(config, *, write_artifacts: bool) -> int:
    for line in plan_gateway(config):
        artifact_text = ",".join(str(path) for path in line.artifacts) if line.artifacts else "-"
        print(
            "AMPG_PLAN "
            f"site={line.site_id} "
            f"protocol={line.protocol} "
            f"renderer={line.renderer} "
            f"output={line.output_root} "
            f"daemon={line.daemon} "
            f"policy={line.daemon_policy} "
            f"artifacts={artifact_text} "
            f"action=\"{line.action}\""
        )
    if write_artifacts:
        artifacts = write_plan_artifacts(config)
        for artifact in artifacts:
            print(f"AMPG_ARTIFACT path={artifact.path}")
    return 0


def _cmd_build(config) -> int:
    for result in build_gateway(config):
        extra = ""
        if result.privacy_stats is not None:
            stats = result.privacy_stats
            extra = (
                f" removed_active_tags={stats.removed_active_tags}"
                f" removed_event_handlers={stats.removed_event_handlers}"
                f" removed_inline_styles={stats.removed_inline_styles}"
                f" removed_remote_assets={stats.removed_remote_assets}"
            )
        print(
            "AMPG_BUILD "
            f"site={result.site_id} "
            f"protocol={result.protocol} "
            f"renderer={result.renderer} "
            f"output={result.output_root} "
            f"files={result.files_written}"
            f" skipped={result.files_skipped}"
            f"{extra}"
        )
    for manifest in write_fixture_manifests(config):
        print(
            "AMPG_MANIFEST "
            f"site={manifest.site_id} "
            f"path={manifest.path} "
            f"fixtures={manifest.fixture_count}"
        )
    return 0


def _print_health_check(check: HealthCheck) -> None:
    print(
        "AMPG_HEALTH_CHECK "
        f"site={check.site_id} "
        f"protocol={check.protocol} "
        f"mode={check.mode} "
        f"route={check.route} "
        f"url=\"{_quote(check.url)}\" "
        f"output_root=\"{_quote(str(check.output_root))}\" "
        f"output_path={check.output_path} "
        f"transport={check.transport} "
        f"profile={check.profile} "
        f"address_status={check.address_status} "
        f"status={check.status} "
        f"action={check.action} "
        f"command=\"{_quote(check.command)}\" "
        f"message=\"{_quote(check.message)}\""
    )


def _print_install_step(step: InstallStep) -> None:
    print(
        "AMPG_INSTALL_STEP "
        f"site={step.site_id} "
        f"protocol={step.protocol} "
        f"platform={step.platform} "
        f"stage={step.stage} "
        f"action={step.action} "
        f"target=\"{_quote(step.target)}\" "
        f"status={step.status} "
        f"command=\"{_quote(step.command)}\" "
        f"message=\"{_quote(step.message)}\""
    )


def _print_install_state_copy(copy: InstallStateCopy) -> None:
    print(
        "AMPG_APPLY_STATE_COPY "
        f"site={copy.site_id} "
        f"protocol={copy.protocol} "
        f"platform={copy.platform} "
        f"kind={copy.kind} "
        f"source=\"{_quote(str(copy.source))}\" "
        f"target=\"{_quote(str(copy.target))}\" "
        f"status={copy.status} "
        f"command=\"{_quote(copy.command)}\" "
        f"message=\"{_quote(copy.message)}\""
    )


def _print_supervisor_action(action: InstallSupervisorAction) -> None:
    print(
        "AMPG_APPLY_SUPERVISOR "
        f"site={action.site_id} "
        f"protocol={action.protocol} "
        f"platform={action.platform} "
        f"kind={action.kind} "
        f"service={action.service} "
        f"source=\"{_quote(str(action.source))}\" "
        f"status={action.status} "
        f"command=\"{_quote(action.command)}\" "
        f"message=\"{_quote(action.message)}\""
    )


def _print_apply_preflight(preflight: ApplyPreflight) -> None:
    print(
        "AMPG_APPLY_PREFLIGHT "
        f"status={preflight.status} "
        f"items={len(preflight.items)} "
        f"ready={preflight.ready} "
        f"review={preflight.review} "
        f"planned={preflight.planned} "
        f"skipped={preflight.skipped} "
        f"blocked={preflight.blocked} "
        f"message=\"{_quote(preflight.message)}\""
    )


def _print_apply_preflight_item(item: ApplyPreflightItem) -> None:
    print(
        "AMPG_APPLY_PREFLIGHT_ITEM "
        f"phase={item.phase} "
        f"site={item.site_id} "
        f"protocol={item.protocol} "
        f"status={item.status} "
        f"action={item.action} "
        f"target=\"{_quote(item.target)}\" "
        f"command=\"{_quote(item.command)}\" "
        f"message=\"{_quote(item.message)}\""
    )


def _print_deploy_step(step: DeployStep) -> None:
    print(
        "AMPG_DEPLOY_STEP "
        f"stage={step.stage} "
        f"status={step.status} "
        f"command=\"{_quote(step.command)}\" "
        f"message=\"{_quote(step.message)}\""
    )


def _print_deploy_next(index: int, next_step: DeployNextStep) -> None:
    print(
        "AMPG_DEPLOY_NEXT "
        f"step={index} "
        f"stage={next_step.stage} "
        f"command=\"{_quote(next_step.command)}\" "
        f"message=\"{_quote(next_step.message)}\""
    )


def _print_deploy_summary(config, plan: DeployPlan) -> None:
    statuses = [step.status for step in plan.steps]
    protocol_count = sum(
        1
        for site in config.sites
        for protocol in site.protocols.values()
        if protocol.enabled
    )
    print(
        "AMPG_DEPLOY_SUMMARY "
        f"status={plan.status} "
        f"sites={len(config.sites)} "
        f"protocols={protocol_count} "
        f"ready={statuses.count('ready')} "
        f"todo={statuses.count('todo')} "
        f"review={statuses.count('review')} "
        f"blocked={statuses.count('blocked')} "
        f"skipped={statuses.count('skipped')} "
        f"message=\"{_quote(plan.message)}\""
    )


def _print_state_apply_result(result: StateApplyResult) -> None:
    print(
        "AMPG_DEPLOY_STATE "
        f"site={result.site_id} "
        f"protocol={result.protocol} "
        f"platform={result.platform} "
        f"kind={result.kind} "
        f"mode={result.mode} "
        f"source=\"{_quote(str(result.source))}\" "
        f"target=\"{_quote(str(result.target))}\" "
        f"status={result.status} "
        f"message=\"{_quote(result.message)}\""
    )


def _print_supervisor_apply_result(result: SupervisorApplyResult) -> None:
    print(
        "AMPG_DEPLOY_SUPERVISOR "
        f"site={result.site_id} "
        f"protocol={result.protocol} "
        f"platform={result.platform} "
        f"kind={result.kind} "
        f"service={result.service} "
        f"mode={result.mode} "
        f"source=\"{_quote(str(result.source))}\" "
        f"target=\"{_quote(str(result.target))}\" "
        f"status={result.status} "
        f"command=\"{_quote(result.command)}\" "
        f"message=\"{_quote(result.message)}\""
    )


def _print_start_apply_result(result: StartApplyResult) -> None:
    return_code = "-" if result.return_code is None else str(result.return_code)
    print(
        "AMPG_DEPLOY_START "
        f"site={result.site_id} "
        f"protocol={result.protocol} "
        f"platform={result.platform} "
        f"kind={result.kind} "
        f"service={result.service} "
        f"mode={result.mode} "
        f"target=\"{_quote(str(result.target))}\" "
        f"status={result.status} "
        f"return_code={return_code} "
        f"command=\"{_quote(format_command(result.command))}\" "
        f"message=\"{_quote(result.message)}\""
    )


def _print_address_apply_result(result: AddressApplyResult) -> None:
    path = str(result.path) if result.path else "-"
    print(
        "AMPG_DEPLOY_ADDRESS "
        f"site={result.site_id} "
        f"protocol={result.protocol} "
        f"mode={result.mode} "
        f"status={result.status} "
        f"url=\"{_quote(result.url)}\" "
        f"source=\"{_quote(result.source)}\" "
        f"path=\"{_quote(path)}\" "
        f"message=\"{_quote(result.message)}\""
    )


def _print_dns_record(record: DNSRecordPlan) -> None:
    print(
        "AMPG_DNS_RECORD "
        f"site={record.site_id} "
        f"domain={record.domain} "
        f"name={record.name} "
        f"type={record.type} "
        f"value=\"{_quote(record.value)}\" "
        f"status={record.status} "
        f"message=\"{_quote(record.message)}\""
    )


def _print_connectivity_hint(hint: ConnectivityHint) -> None:
    print(
        "AMPG_CONNECTIVITY_HINT "
        f"method={hint.method} "
        f"status={hint.status} "
        f"command=\"{_quote(hint.command)}\" "
        f"message=\"{_quote(hint.message)}\""
    )


def _print_free_domain_hint(hint: FreeDomainHint) -> None:
    print(
        "AMPG_FREE_DOMAIN_HINT "
        f"provider=\"{_quote(hint.provider)}\" "
        f"suffixes=\"{_quote(','.join(hint.suffixes))}\" "
        f"fit=\"{_quote(hint.fit)}\" "
        f"records=\"{_quote(hint.records)}\" "
        f"workflow=\"{_quote(hint.workflow)}\" "
        f"status={hint.status} "
        f"url=\"{_quote(hint.url)}\" "
        f"message=\"{_quote(hint.message)}\""
    )


def _print_dns_summary(plan: DNSPlan) -> None:
    statuses = [record.status for record in plan.records]
    statuses.extend(hint.status for hint in plan.hints)
    print(
        "AMPG_DNS_SUMMARY "
        f"status={plan.status} "
        f"records={len(plan.records)} "
        f"hints={len(plan.hints)} "
        f"free_domain_hints={len(plan.free_domains)} "
        f"todo={statuses.count('todo')} "
        f"review={statuses.count('review')} "
        f"blocked={statuses.count('blocked')} "
        f"skipped={statuses.count('skipped')} "
        f"message=\"{_quote(plan.message)}\""
    )


def _print_dns_check(result: DNSCheckResult) -> None:
    resolved = ",".join(result.resolved) if result.resolved else "-"
    print(
        "AMPG_DNS_CHECK "
        f"site={result.site_id} "
        f"domain={result.domain} "
        f"family={result.family} "
        f"expected=\"{_quote(result.expected)}\" "
        f"resolved=\"{_quote(resolved)}\" "
        f"status={result.status} "
        f"message=\"{_quote(result.message)}\""
    )


def _print_approval_check(check: ApprovalCheck) -> None:
    candidate = check.candidate
    print(
        "AMPG_APPROVAL "
        f"site={candidate.site_id} "
        f"protocol={candidate.protocol} "
        f"platform={candidate.platform} "
        f"kind={candidate.kind} "
        f"path=\"{_quote(str(candidate.path))}\" "
        f"status={check.status} "
        f"sha256={check.digest} "
        f"message=\"{_quote(check.message)}\""
    )


def _print_approval_write_result(result: ApprovalWriteResult) -> None:
    candidate = result.candidate
    print(
        "AMPG_APPROVAL_WRITE "
        f"site={candidate.site_id} "
        f"protocol={candidate.protocol} "
        f"platform={candidate.platform} "
        f"kind={candidate.kind} "
        f"path=\"{_quote(str(candidate.path))}\" "
        f"status={result.status} "
        f"sha256={result.digest} "
        f"message=\"{_quote(result.message)}\""
    )


def _print_approval_summary(
    *,
    mode: str,
    statuses: list[str],
    count: int,
    registry: Path,
) -> None:
    print(
        "AMPG_APPROVAL_SUMMARY "
        f"mode={mode} "
        f"candidates={count} "
        f"approved={statuses.count('approved')} "
        f"review={statuses.count('review')} "
        f"written={statuses.count('written')} "
        f"current={statuses.count('current')} "
        f"missing={statuses.count('missing')} "
        f"stale={statuses.count('stale')} "
        f"registry=\"{_quote(str(registry))}\""
    )


def _print_activation_step(step: ActivationStep) -> None:
    print(
        "AMPG_APPLY_STEP "
        f"site={step.site_id} "
        f"protocol={step.protocol} "
        f"stage={step.stage} "
        f"action={step.action} "
        f"target={step.target} "
        f"status={step.status} "
        f"command=\"{_quote(step.command)}\" "
        f"message=\"{_quote(step.message)}\""
    )


def _print_transport_status(status: TransportStatus) -> None:
    executable_path = status.executable_path or "-"
    print(
        "AMPG_STATUS "
        f"site={status.site_id} "
        f"protocol={status.protocol} "
        f"renderer={status.renderer} "
        f"daemon={status.daemon} "
        f"policy={status.daemon_policy} "
        f"platform={status.platform} "
        f"supervisor={status.supervisor} "
        f"adapter={status.adapter} "
        f"backend={status.backend} "
        f"installed={_bool(status.installed)} "
        f"running={_bool(status.running)} "
        f"adoptable={_bool(status.adoptable)} "
        f"manageable={_bool(status.manageable)} "
        f"executable={executable_path} "
        f"status={status.status} "
        f"action={status.action} "
        f"message=\"{_quote(status.message)}\""
    )


def _print_doctor_issue(issue: DoctorIssue) -> None:
    print(
        "AMPG_DOCTOR "
        f"site={issue.site_id} "
        f"protocol={issue.protocol} "
        f"severity={issue.severity} "
        f"code={issue.code} "
        f"message=\"{_quote(issue.message)}\""
    )


def _cmd_manifest(config) -> int:
    for manifest in write_fixture_manifests(config):
        print(
            "AMPG_MANIFEST "
            f"site={manifest.site_id} "
            f"path={manifest.path} "
            f"fixtures={manifest.fixture_count}"
        )
    return 0


def _cmd_addresses(config, args) -> int:
    if args.addresses_command == "list":
        records = effective_address_records(config)
        for record in records:
            _print_address(record)
        print(
            "AMPG_ADDRESS_SUMMARY "
            f"sites={len(config.sites)} "
            f"addresses={len(records)} "
            f"configured={sum(1 for record in records if record.address_status == 'configured')} "
            f"captured={sum(1 for record in records if record.address_status == 'captured')} "
            f"derived={sum(1 for record in records if record.address_status == 'derived')} "
            f"placeholder={sum(1 for record in records if record.address_status == 'placeholder')} "
            f"registry={address_registry_path(config)}"
        )
        return 0

    if args.addresses_command == "capture":
        results = capture_addresses(config)
        for result in results:
            _print_address_capture(result)
        print(
            "AMPG_ADDRESS_CAPTURE_SUMMARY "
            f"sites={len(config.sites)} "
            f"results={len(results)} "
            f"captured={sum(1 for result in results if result.status == 'captured')} "
            f"configured={sum(1 for result in results if result.status == 'configured')} "
            f"skipped={sum(1 for result in results if result.status == 'skipped')} "
            f"missing={sum(1 for result in results if result.status == 'missing')} "
            f"registry={address_registry_path(config)}"
        )
        return 0

    if args.addresses_command == "set":
        record = set_address(
            config,
            site_id=args.site,
            protocol=args.address_protocol,
            url=args.url,
            source=args.source,
        )
        _print_address(record)
        print(f"AMPG_ADDRESS_SET status=written registry={address_registry_path(config)}")
        return 0

    return 1


def _cmd_state_contract(config) -> int:
    contracts = state_contract(config)
    for contract in contracts:
        _print_state_contract(contract)
    print(
        "AMPG_STATE_SUMMARY "
        f"sites={len(config.sites)} "
        f"entries={len(contracts)} "
        f"required={sum(1 for contract in contracts if contract.required)} "
        f"sensitive={sum(1 for contract in contracts if contract.sensitive)}"
    )
    return 0


def _print_state_contract(contract: StatePathContract) -> None:
    print(
        "AMPG_STATE "
        f"site={contract.site_id} "
        f"protocol={contract.protocol} "
        f"role={contract.role} "
        f"owner={contract.owner} "
        f"required={_bool(contract.required)} "
        f"sensitive={_bool(contract.sensitive)} "
        f"path=\"{_quote(str(contract.path))}\" "
        f"description=\"{_quote(contract.description)}\""
    )


def _print_address(record: AddressRecord) -> None:
    print(
        "AMPG_ADDRESS "
        f"site={record.site_id} "
        f"protocol={record.protocol} "
        f"url=\"{_quote(record.url)}\" "
        f"address_status={record.address_status} "
        f"source=\"{_quote(record.source)}\""
    )


def _print_address_capture(result: AddressCaptureResult) -> None:
    path = str(result.path) if result.path else "-"
    print(
        "AMPG_ADDRESS_CAPTURE "
        f"site={result.site_id} "
        f"protocol={result.protocol} "
        f"status={result.status} "
        f"url=\"{_quote(result.url)}\" "
        f"source=\"{_quote(result.source)}\" "
        f"path=\"{_quote(path)}\" "
        f"message=\"{_quote(result.message)}\""
    )


def _cmd_preview(config, args) -> int:
    endpoints = preview_endpoints(config, base_port=args.base_port, host=args.host)
    if args.preview_command == "endpoints":
        for endpoint in endpoints:
            _print_preview_endpoint(endpoint)
        print(
            "AMPG_PREVIEW_SUMMARY "
            f"sites={len(config.sites)} endpoints={len(endpoints)}"
        )
        return 0

    if args.preview_command == "manifest":
        for endpoint in endpoints:
            _print_preview_endpoint(endpoint)
        for result in write_preview_fixture_manifests(
            config,
            base_port=args.base_port,
            host=args.host,
        ):
            print(
                "AMPG_PREVIEW_MANIFEST "
                f"site={result.site_id} "
                f"path={result.path} "
                f"fixtures={result.fixture_count}"
            )
        return 0

    if args.preview_command == "serve":
        for endpoint in endpoints:
            _print_preview_endpoint(endpoint)
        with PreviewServers(endpoints) as servers:
            print(
                "AMPG_PREVIEW_SERVE "
                f"status=running endpoints={len(servers.endpoints)}"
            )
            servers.wait_forever()
        return 0

    return 1


def _print_preview_endpoint(endpoint) -> None:
    print(
        "AMPG_PREVIEW_ENDPOINT "
        f"site={endpoint.site_id} "
        f"protocol={endpoint.protocol} "
        f"renderer={endpoint.renderer} "
        f"url={endpoint.url} "
        f"root={endpoint.root} "
        f"status={endpoint.status}"
    )


def _cmd_routes(config, args) -> int:
    exposures = route_exposures(config)
    issues = route_issues(config)
    for exposure in exposures:
        _print_route_exposure(exposure)
    for issue in issues:
        _print_route_issue(issue)
    print(
        "AMPG_ROUTE_SUMMARY "
        f"sites={len(config.sites)} "
        f"routes={sum(len(site.interactions.routes) for site in config.sites)} "
        f"decisions={len(exposures)} "
        f"exposed={sum(1 for exposure in exposures if exposure.status == 'exposed')} "
        f"skipped={sum(1 for exposure in exposures if exposure.status == 'skipped')} "
        f"issues={len(issues)}"
    )
    if args.routes_command == "validate" and issues:
        return 1
    return 0


def _cmd_route_manifest(args) -> int:
    if args.route_manifest_command == "schema":
        content = route_manifest_schema_json()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(f"AMPG_ROUTE_MANIFEST_SCHEMA path={args.output}")
        else:
            print(content, end="")
        return 0

    if args.route_manifest_command == "validate":
        try:
            data = load_route_manifest(args.path)
        except ValueError:
            try:
                import json

                data = json.loads(args.path.read_text(encoding="utf-8"))
                issues = validate_route_manifest(data)
            except Exception as exc:  # noqa: BLE001 - CLI should print concise failures.
                print(
                    "AMPG_ROUTE_MANIFEST "
                    f"path={args.path} status=error message=\"{exc}\"",
                    file=sys.stderr,
                )
                return 1
            for issue in issues:
                print(
                    "AMPG_ROUTE_MANIFEST_ISSUE "
                    f"path={args.path} json_path={issue.path} "
                    f"code={issue.code} message=\"{issue.message}\""
                )
            print(
                "AMPG_ROUTE_MANIFEST "
                f"path={args.path} status=fail issues={len(issues)}"
            )
            return 1

        print(
            "AMPG_ROUTE_MANIFEST "
            f"path={args.path} schema={data['schema']} routes={len(data['routes'])} status=ok"
        )
        return 0

    return 1


def _print_route_exposure(exposure: RouteExposure) -> None:
    print(
        "AMPG_ROUTE "
        f"site={exposure.site_id} "
        f"protocol={exposure.protocol} "
        f"route_index={exposure.route_index} "
        f"route=\"{exposure.match}\" "
        f"source={exposure.source} "
        f"tier={exposure.tier} "
        f"identity={exposure.identity} "
        f"payments={exposure.payments} "
        f"realtime={str(exposure.realtime).lower()} "
        f"public_allowed={str(exposure.public_allowed).lower()} "
        f"max_tier={exposure.max_tier} "
        f"status={exposure.status} "
        f"reason=\"{exposure.reason}\""
    )


def _print_route_issue(issue: RouteIssue) -> None:
    print(
        "AMPG_ROUTE_ISSUE "
        f"site={issue.site_id} "
        f"route_index={issue.route_index} "
        f"route=\"{issue.match}\" "
        f"source={issue.source} "
        f"tier={issue.tier} "
        f"code={issue.code} "
        f"message=\"{issue.message}\""
    )


def _cmd_audit(config, *, fail_on_warn: bool) -> int:
    issues = audit_gateway(config)
    for issue in issues:
        print(
            "AMPG_AUDIT "
            f"site={issue.site_id} "
            f"severity={issue.severity} "
            f"code={issue.code} "
            f"path={issue.path} "
            f"message=\"{issue.message}\""
        )
    print(f"AMPG_AUDIT_SUMMARY issues={len(issues)}")
    if issues and fail_on_warn:
        return 1
    return 0


def _cmd_docs(args) -> int:
    if args.docs_command == "generate":
        changed = generate_docs(Path.cwd(), check=args.check)
        changed_text = ",".join(str(path) for path in changed) if changed else "-"
        mode = "check" if args.check else "write"
        print(f"AMPG_DOCS status=ok mode={mode} changed={changed_text}")
        return 0
    return 1


def _platform_override(config, args):
    if getattr(args, "platform", None):
        return platform_by_name(args.platform)
    profile = select_profile(config, getattr(args, "profile", None))
    if profile and profile.platform:
        return platform_by_name(profile.platform)
    return None


def _bool(value: bool) -> str:
    return str(value).lower()


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
