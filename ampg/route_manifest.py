from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .capabilities import IDENTITY_ADAPTERS, INTERACTION_TIERS, PAYMENT_ADAPTERS


ROUTE_MANIFEST_SCHEMA = "ampg.route-manifest.v1"
ROUTE_MANIFEST_SCHEMA_PATH = Path("schemas/ampg.route-manifest.v1.schema.json")

TOP_LEVEL_FIELDS = {"schema", "default_tier", "deny_routes", "routes"}
ROUTE_FIELDS = {"match", "tier", "identity", "payments", "realtime", "public_allowed"}


@dataclass(frozen=True)
class RouteManifestIssue:
    path: str
    code: str
    message: str


def load_route_manifest(path: Path, *, site_id: str | None = None) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        label = f"{site_id}: " if site_id else ""
        raise ValueError(f"{label}route manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        label = f"{site_id}: " if site_id else ""
        raise ValueError(f"{label}invalid route manifest JSON: {path}: {exc}") from exc

    issues = validate_route_manifest(data)
    if issues:
        label = f"{site_id}: " if site_id else ""
        joined = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        raise ValueError(f"{label}invalid route manifest: {path}: {joined}")
    return data


def validate_route_manifest(data: Any) -> list[RouteManifestIssue]:
    issues: list[RouteManifestIssue] = []
    if not isinstance(data, dict):
        return [
            RouteManifestIssue(
                path="$",
                code="type",
                message="route manifest must be a JSON object",
            )
        ]

    _unknown_fields("$", data, TOP_LEVEL_FIELDS, issues)
    schema = data.get("schema")
    if schema != ROUTE_MANIFEST_SCHEMA:
        issues.append(
            RouteManifestIssue(
                path="$.schema",
                code="schema",
                message=f"must be {ROUTE_MANIFEST_SCHEMA!r}",
            )
        )

    if "default_tier" in data:
        _enum_field("$.default_tier", data["default_tier"], INTERACTION_TIERS, issues)

    if "deny_routes" in data:
        _string_array("$.deny_routes", data["deny_routes"], issues, require_slash=True)

    routes = data.get("routes")
    if routes is None:
        issues.append(
            RouteManifestIssue(
                path="$.routes",
                code="required",
                message="missing required routes array",
            )
        )
        return issues
    if not isinstance(routes, list):
        issues.append(
            RouteManifestIssue(
                path="$.routes",
                code="type",
                message="must be an array",
            )
        )
        return issues

    for index, route in enumerate(routes):
        _route_entry(f"$.routes[{index}]", route, issues)
    return issues


def route_manifest_json_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:ampg:schema:route-manifest:v1",
        "title": "AMPG Route Manifest",
        "description": "Route policy contract emitted by applications for AMPG.",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "routes"],
        "properties": {
            "schema": {"const": ROUTE_MANIFEST_SCHEMA},
            "default_tier": {"$ref": "#/$defs/interactionTier"},
            "deny_routes": {
                "type": "array",
                "items": {"$ref": "#/$defs/routePattern"},
                "default": [],
            },
            "routes": {
                "type": "array",
                "items": {"$ref": "#/$defs/routePolicy"},
            },
        },
        "$defs": {
            "interactionTier": {"enum": list(INTERACTION_TIERS)},
            "identityAdapter": {"enum": list(IDENTITY_ADAPTERS)},
            "paymentAdapter": {"enum": list(PAYMENT_ADAPTERS)},
            "routePattern": {
                "type": "string",
                "minLength": 1,
                "pattern": "^/",
            },
            "routePolicy": {
                "type": "object",
                "additionalProperties": False,
                "required": ["match"],
                "properties": {
                    "match": {"$ref": "#/$defs/routePattern"},
                    "tier": {"$ref": "#/$defs/interactionTier"},
                    "identity": {"$ref": "#/$defs/identityAdapter", "default": "none"},
                    "payments": {"$ref": "#/$defs/paymentAdapter", "default": "none"},
                    "realtime": {"type": "boolean", "default": False},
                    "public_allowed": {"type": "boolean", "default": True},
                },
            },
        },
    }


def route_manifest_schema_json() -> str:
    return json.dumps(route_manifest_json_schema(), indent=2, sort_keys=True) + "\n"


def _route_entry(path: str, value: Any, issues: list[RouteManifestIssue]) -> None:
    if not isinstance(value, dict):
        issues.append(
            RouteManifestIssue(path=path, code="type", message="route entry must be an object")
        )
        return
    _unknown_fields(path, value, ROUTE_FIELDS, issues)
    if "match" not in value:
        issues.append(
            RouteManifestIssue(
                path=f"{path}.match",
                code="required",
                message="missing required route match",
            )
        )
    else:
        _route_pattern(f"{path}.match", value["match"], issues)

    if "tier" in value:
        _enum_field(f"{path}.tier", value["tier"], INTERACTION_TIERS, issues)
    if "identity" in value:
        _enum_field(f"{path}.identity", value["identity"], IDENTITY_ADAPTERS, issues)
    if "payments" in value:
        _enum_field(f"{path}.payments", value["payments"], PAYMENT_ADAPTERS, issues)
    if "realtime" in value:
        _bool_field(f"{path}.realtime", value["realtime"], issues)
    if "public_allowed" in value:
        _bool_field(f"{path}.public_allowed", value["public_allowed"], issues)


def _unknown_fields(
    path: str,
    data: dict[str, Any],
    allowed: set[str],
    issues: list[RouteManifestIssue],
) -> None:
    for field in sorted(set(data) - allowed):
        issues.append(
            RouteManifestIssue(
                path=f"{path}.{field}",
                code="unknown-field",
                message="unknown field",
            )
        )


def _enum_field(
    path: str,
    value: Any,
    allowed: tuple[str, ...],
    issues: list[RouteManifestIssue],
) -> None:
    if value not in allowed:
        joined = ", ".join(allowed)
        issues.append(
            RouteManifestIssue(
                path=path,
                code="enum",
                message=f"must be one of: {joined}",
            )
        )


def _string_array(
    path: str,
    value: Any,
    issues: list[RouteManifestIssue],
    *,
    require_slash: bool = False,
) -> None:
    if not isinstance(value, list):
        issues.append(RouteManifestIssue(path=path, code="type", message="must be an array"))
        return
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if require_slash:
            _route_pattern(item_path, item, issues)
        elif not isinstance(item, str) or not item:
            issues.append(
                RouteManifestIssue(
                    path=item_path,
                    code="type",
                    message="must be a non-empty string",
                )
            )


def _route_pattern(path: str, value: Any, issues: list[RouteManifestIssue]) -> None:
    if not isinstance(value, str) or not value:
        issues.append(
            RouteManifestIssue(path=path, code="type", message="must be a non-empty string")
        )
        return
    if not value.startswith("/"):
        issues.append(
            RouteManifestIssue(path=path, code="pattern", message="must start with /")
        )


def _bool_field(path: str, value: Any, issues: list[RouteManifestIssue]) -> None:
    if not isinstance(value, bool):
        issues.append(RouteManifestIssue(path=path, code="type", message="must be boolean"))
