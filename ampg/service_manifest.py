from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from .bip340 import bip340_verify, tagged_hash as _tagged_hash
from .canonical_json import MAX_SAFE_INTEGER, canonicalize_jcs, strict_json_loads
from .capabilities import INTERACTION_TIERS


SERVICE_MANIFEST_SCHEMA = "amp.service-manifest.v1"
SERVICE_MANIFEST_SCHEMA_PATH = Path("schemas/amp.service-manifest.v1.schema.json")
DELEGATION_SCHEMA = "amp.service-key-delegation.v1"
SIGNATURE_ALGORITHM = "BIP340-secp256k1"
CANONICALIZATION = "RFC8785-JCS"

TRANSPORTS = ("clearnet", "tor", "i2p", "gemini", "ipfs", "reticulum")
PUBLIC_INTERACTION_TIERS = tuple(tier for tier in INTERACTION_TIERS if tier != "internal")
AUTH_METHODS = ("none", "nip98", "smirk-action", "smirk-session", "siwe", "http-session")
PAYMENT_METHODS = (
    "none",
    "smirk-wallet",
    "server-invoice",
    "payment-capability",
    "static-instructions",
)

MAX_ROUTES = 64
MAX_MANIFEST_BYTES = 256 * 1024
MAX_CLOCK_SKEW = timedelta(minutes=5)
HEX_32_RE = re.compile(r"^[0-9a-f]{64}$")
HEX_64_RE = re.compile(r"^[0-9a-f]{128}$")
SERVICE_ID_RE = re.compile(r"^amp:[0-9a-f]{64}$")
ONION_V3_RE = re.compile(r"^[a-z2-7]{56}\.onion$")
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

TOP_LEVEL_FIELDS = {"schema", "payload", "delegation", "signature"}
PAYLOAD_FIELDS = {
    "service_id",
    "name",
    "root_public_key",
    "api",
    "routes",
    "issued_at",
    "expires_at",
    "sequence",
    "previous_manifest_digest",
}
API_FIELDS = {"contract", "version", "schema_sha256"}
ROUTE_FIELDS = {
    "transport",
    "endpoint",
    "context",
    "interaction_tier",
    "priority",
    "auth",
    "payments",
    "capabilities",
}
SIGNATURE_FIELDS = {"algorithm", "canonicalization", "public_key", "value"}
DELEGATION_FIELDS = {"payload", "signature"}
DELEGATION_PAYLOAD_FIELDS = {
    "schema",
    "service_id",
    "root_public_key",
    "signing_public_key",
    "issued_at",
    "expires_at",
    "sequence",
}


@dataclass(frozen=True)
class ServiceManifestIssue:
    path: str
    code: str
    message: str


def read_service_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError(f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")
        data = strict_json_loads(raw.decode("utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"service manifest not found: {path}") from exc
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid service manifest JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid service manifest JSON: {path}: root must be an object")
    return data


def service_id_for_root_key(root_public_key: str) -> str:
    key = _decode_hex(root_public_key, 32, "root public key")
    return f"amp:{_tagged_hash('AMPG/service-id/v1', key).hex()}"


def service_manifest_digest(payload: dict[str, Any]) -> bytes:
    return _tagged_hash("AMPG/service-manifest/v1", canonicalize_jcs(payload))


def delegation_digest(payload: dict[str, Any]) -> bytes:
    return _tagged_hash("AMPG/service-key-delegation/v1", canonicalize_jcs(payload))


def validate_service_manifest(
    data: Any,
    *,
    now: datetime | None = None,
    minimum_sequence: int | None = None,
    minimum_delegation_sequence: int | None = None,
    expected_previous: str | None = None,
    verify_signature: bool = True,
) -> list[ServiceManifestIssue]:
    issues: list[ServiceManifestIssue] = []
    if not isinstance(data, dict):
        return [ServiceManifestIssue("$", "type", "service manifest must be a JSON object")]

    _unknown_fields("$", data, TOP_LEVEL_FIELDS, issues)
    _required_fields("$", data, {"schema", "payload", "signature"}, issues)
    if data.get("schema") != SERVICE_MANIFEST_SCHEMA:
        issues.append(
            ServiceManifestIssue(
                "$.schema", "schema", f"must be {SERVICE_MANIFEST_SCHEMA!r}"
            )
        )

    payload = data.get("payload")
    payload_times = _validate_payload(payload, issues)
    signature = data.get("signature")
    signing_key = _validate_signature_object("$.signature", signature, issues)
    root_key = payload.get("root_public_key") if isinstance(payload, dict) else None
    service_id = payload.get("service_id") if isinstance(payload, dict) else None

    delegation = data.get("delegation")
    delegation_times: tuple[datetime | None, datetime | None] = (None, None)
    if delegation is not None:
        delegation_times = _validate_delegation(
            delegation,
            root_key=root_key,
            service_id=service_id,
            signing_key=signing_key,
            issues=issues,
            verify_signature=verify_signature,
        )
    elif signing_key and root_key and signing_key != root_key:
        issues.append(
            ServiceManifestIssue(
                "$.delegation",
                "required",
                "a delegated signing key requires a root-signed delegation",
            )
        )
    elif signing_key and root_key and signing_key == root_key:
        pass

    if delegation is not None and signing_key and root_key and signing_key == root_key:
        issues.append(
            ServiceManifestIssue(
                "$.delegation",
                "unexpected",
                "delegation is only valid when the signing key differs from the root key",
            )
        )

    issued_at, expires_at = payload_times
    delegated_at, delegated_until = delegation_times
    if issued_at and expires_at and issued_at >= expires_at:
        issues.append(
            ServiceManifestIssue(
                "$.payload.expires_at", "range", "must be later than issued_at"
            )
        )
    if issued_at and delegated_at and issued_at < delegated_at:
        issues.append(
            ServiceManifestIssue(
                "$.payload.issued_at", "delegation-window", "precedes delegation validity"
            )
        )
    if expires_at and delegated_until and expires_at > delegated_until:
        issues.append(
            ServiceManifestIssue(
                "$.payload.expires_at", "delegation-window", "exceeds delegation validity"
            )
        )

    if now is not None:
        check_time = _as_utc(now)
        if issued_at and issued_at > check_time + MAX_CLOCK_SKEW:
            issues.append(
                ServiceManifestIssue(
                    "$.payload.issued_at", "not-yet-valid", "is too far in the future"
                )
            )
        if expires_at and expires_at <= check_time:
            issues.append(ServiceManifestIssue("$.payload.expires_at", "expired", "has expired"))
        if delegated_at and delegated_at > check_time + MAX_CLOCK_SKEW:
            issues.append(
                ServiceManifestIssue(
                    "$.delegation.payload.issued_at",
                    "not-yet-valid",
                    "delegation is too far in the future",
                )
            )
        if delegated_until and delegated_until <= check_time:
            issues.append(
                ServiceManifestIssue(
                    "$.delegation.payload.expires_at", "expired", "delegation has expired"
                )
            )

    sequence = payload.get("sequence") if isinstance(payload, dict) else None
    previous = payload.get("previous_manifest_digest") if isinstance(payload, dict) else None
    if minimum_sequence is not None and isinstance(sequence, int) and sequence < minimum_sequence:
        issues.append(
            ServiceManifestIssue(
                "$.payload.sequence",
                "rollback",
                f"must be at least the pinned sequence {minimum_sequence}",
            )
        )
    if expected_previous is not None and previous != expected_previous:
        issues.append(
            ServiceManifestIssue(
                "$.payload.previous_manifest_digest",
                "chain",
                "does not match the pinned previous manifest digest",
            )
        )

    delegation_sequence = None
    if isinstance(delegation, dict) and isinstance(delegation.get("payload"), dict):
        delegation_sequence = delegation["payload"].get("sequence")
    if (
        minimum_delegation_sequence is not None
        and isinstance(delegation_sequence, int)
        and delegation_sequence < minimum_delegation_sequence
    ):
        issues.append(
            ServiceManifestIssue(
                "$.delegation.payload.sequence",
                "rollback",
                f"must be at least the pinned delegation sequence {minimum_delegation_sequence}",
            )
        )

    if verify_signature and isinstance(payload, dict) and isinstance(signature, dict):
        try:
            digest = service_manifest_digest(payload)
        except (TypeError, ValueError):
            pass
        else:
            _verify_signed_payload("$.signature", signature, digest, issues)
    return issues


def service_manifest_json_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:amp:schema:service-manifest:v1",
        "title": "AMP Signed Service Manifest",
        "description": "Signed public identity and multi-transport route contract.",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "payload", "signature"],
        "properties": {
            "schema": {"const": SERVICE_MANIFEST_SCHEMA},
            "payload": {"$ref": "#/$defs/payload"},
            "delegation": {"$ref": "#/$defs/delegation"},
            "signature": {"$ref": "#/$defs/signature"},
        },
        "$defs": {
            "hex32": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "hex64": {"type": "string", "pattern": "^[0-9a-f]{128}$"},
            "timestamp": {"type": "string", "format": "date-time", "maxLength": 40},
            "signature": {
                "type": "object",
                "additionalProperties": False,
                "required": ["algorithm", "canonicalization", "public_key", "value"],
                "properties": {
                    "algorithm": {"const": SIGNATURE_ALGORITHM},
                    "canonicalization": {"const": CANONICALIZATION},
                    "public_key": {"$ref": "#/$defs/hex32"},
                    "value": {"$ref": "#/$defs/hex64"},
                },
            },
            "api": {
                "type": "object",
                "additionalProperties": False,
                "required": ["contract", "version", "schema_sha256"],
                "properties": {
                    "contract": {"type": "string", "minLength": 1, "maxLength": 120},
                    "version": {"type": "string", "minLength": 1, "maxLength": 40},
                    "schema_sha256": {"$ref": "#/$defs/hex32"},
                },
            },
            "route": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "transport",
                    "endpoint",
                    "context",
                    "interaction_tier",
                    "priority",
                    "auth",
                    "payments",
                ],
                "properties": {
                    "transport": {"enum": list(TRANSPORTS)},
                    "endpoint": {"type": "string", "minLength": 1, "maxLength": 2048},
                    "context": {"enum": list(TRANSPORTS)},
                    "interaction_tier": {"enum": list(PUBLIC_INTERACTION_TIERS)},
                    "priority": {"type": "integer", "minimum": 0, "maximum": 1000},
                    "auth": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"enum": list(AUTH_METHODS)},
                    },
                    "payments": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"enum": list(PAYMENT_METHODS)},
                    },
                    "capabilities": {
                        "type": "array",
                        "maxItems": 64,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1, "maxLength": 120},
                    },
                },
            },
            "payload": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "service_id",
                    "name",
                    "root_public_key",
                    "routes",
                    "issued_at",
                    "expires_at",
                    "sequence",
                ],
                "properties": {
                    "service_id": {"type": "string", "pattern": "^amp:[0-9a-f]{64}$"},
                    "name": {"type": "string", "minLength": 1, "maxLength": 120},
                    "root_public_key": {"$ref": "#/$defs/hex32"},
                    "api": {"$ref": "#/$defs/api"},
                    "routes": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_ROUTES,
                        "items": {"$ref": "#/$defs/route"},
                    },
                    "issued_at": {"$ref": "#/$defs/timestamp"},
                    "expires_at": {"$ref": "#/$defs/timestamp"},
                    "sequence": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_SAFE_INTEGER,
                    },
                    "previous_manifest_digest": {"$ref": "#/$defs/hex32"},
                },
            },
            "delegationPayload": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema",
                    "service_id",
                    "root_public_key",
                    "signing_public_key",
                    "issued_at",
                    "expires_at",
                    "sequence",
                ],
                "properties": {
                    "schema": {"const": DELEGATION_SCHEMA},
                    "service_id": {"type": "string", "pattern": "^amp:[0-9a-f]{64}$"},
                    "root_public_key": {"$ref": "#/$defs/hex32"},
                    "signing_public_key": {"$ref": "#/$defs/hex32"},
                    "issued_at": {"$ref": "#/$defs/timestamp"},
                    "expires_at": {"$ref": "#/$defs/timestamp"},
                    "sequence": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_SAFE_INTEGER,
                    },
                },
            },
            "delegation": {
                "type": "object",
                "additionalProperties": False,
                "required": ["payload", "signature"],
                "properties": {
                    "payload": {"$ref": "#/$defs/delegationPayload"},
                    "signature": {"$ref": "#/$defs/signature"},
                },
            },
        },
    }


def service_manifest_schema_json() -> str:
    return json.dumps(service_manifest_json_schema(), indent=2, sort_keys=True) + "\n"


def _validate_payload(
    payload: Any, issues: list[ServiceManifestIssue]
) -> tuple[datetime | None, datetime | None]:
    path = "$.payload"
    if not isinstance(payload, dict):
        issues.append(ServiceManifestIssue(path, "type", "must be an object"))
        return None, None
    _unknown_fields(path, payload, PAYLOAD_FIELDS, issues)
    _required_fields(
        path,
        payload,
        {
            "service_id",
            "name",
            "root_public_key",
            "routes",
            "issued_at",
            "expires_at",
            "sequence",
        },
        issues,
    )
    _string(path + ".name", payload.get("name"), issues, minimum=1, maximum=120)
    service_id = payload.get("service_id")
    root_key = payload.get("root_public_key")
    _pattern(path + ".service_id", service_id, SERVICE_ID_RE, issues)
    _pattern(path + ".root_public_key", root_key, HEX_32_RE, issues)
    if isinstance(service_id, str) and isinstance(root_key, str) and HEX_32_RE.fullmatch(root_key):
        expected = service_id_for_root_key(root_key)
        if service_id != expected:
            issues.append(
                ServiceManifestIssue(
                    path + ".service_id", "service-id", "does not match root_public_key"
                )
            )

    if "api" in payload:
        _validate_api(payload["api"], issues)
    _validate_routes(payload.get("routes"), issues)
    sequence = payload.get("sequence")
    _integer(path + ".sequence", sequence, issues, minimum=1, maximum=MAX_SAFE_INTEGER)
    if "previous_manifest_digest" in payload:
        _pattern(
            path + ".previous_manifest_digest",
            payload["previous_manifest_digest"],
            HEX_32_RE,
            issues,
        )
    issued_at = _timestamp(path + ".issued_at", payload.get("issued_at"), issues)
    expires_at = _timestamp(path + ".expires_at", payload.get("expires_at"), issues)
    try:
        canonicalize_jcs(payload)
    except (TypeError, ValueError) as exc:
        issues.append(ServiceManifestIssue(path, "canonicalization", str(exc)))
    return issued_at, expires_at


def _validate_api(value: Any, issues: list[ServiceManifestIssue]) -> None:
    path = "$.payload.api"
    if not isinstance(value, dict):
        issues.append(ServiceManifestIssue(path, "type", "must be an object"))
        return
    _unknown_fields(path, value, API_FIELDS, issues)
    _required_fields(path, value, API_FIELDS, issues)
    _string(path + ".contract", value.get("contract"), issues, minimum=1, maximum=120)
    _string(path + ".version", value.get("version"), issues, minimum=1, maximum=40)
    _pattern(path + ".schema_sha256", value.get("schema_sha256"), HEX_32_RE, issues)


def _validate_routes(value: Any, issues: list[ServiceManifestIssue]) -> None:
    path = "$.payload.routes"
    if not isinstance(value, list):
        issues.append(ServiceManifestIssue(path, "type", "must be an array"))
        return
    if not value:
        issues.append(ServiceManifestIssue(path, "range", "must contain at least one route"))
    if len(value) > MAX_ROUTES:
        issues.append(
            ServiceManifestIssue(path, "range", f"must contain at most {MAX_ROUTES} routes")
        )
    seen: set[tuple[str, str]] = set()
    for index, route in enumerate(value):
        route_path = f"{path}[{index}]"
        if not isinstance(route, dict):
            issues.append(ServiceManifestIssue(route_path, "type", "must be an object"))
            continue
        _unknown_fields(route_path, route, ROUTE_FIELDS, issues)
        _required_fields(
            route_path,
            route,
            {
                "transport",
                "endpoint",
                "context",
                "interaction_tier",
                "priority",
                "auth",
                "payments",
            },
            issues,
        )
        transport = route.get("transport")
        context = route.get("context")
        endpoint = route.get("endpoint")
        _enum(route_path + ".transport", transport, TRANSPORTS, issues)
        _enum(route_path + ".context", context, TRANSPORTS, issues)
        if isinstance(transport, str) and isinstance(context, str) and context != transport:
            issues.append(
                ServiceManifestIssue(
                    route_path + ".context", "context", "must match transport in v1"
                )
            )
        _enum(
            route_path + ".interaction_tier",
            route.get("interaction_tier"),
            PUBLIC_INTERACTION_TIERS,
            issues,
        )
        _integer(route_path + ".priority", route.get("priority"), issues, minimum=0, maximum=1000)
        _enum_array(route_path + ".auth", route.get("auth"), AUTH_METHODS, issues)
        _enum_array(route_path + ".payments", route.get("payments"), PAYMENT_METHODS, issues)
        if "capabilities" in route:
            _string_array(route_path + ".capabilities", route["capabilities"], issues)
        if isinstance(endpoint, str) and isinstance(transport, str) and transport in TRANSPORTS:
            _validate_endpoint(route_path + ".endpoint", transport, endpoint, issues)
            key = (transport, endpoint)
            if key in seen:
                issues.append(
                    ServiceManifestIssue(route_path, "duplicate", "duplicates another route")
                )
            seen.add(key)
        else:
            _string(route_path + ".endpoint", endpoint, issues, minimum=1, maximum=2048)


def _validate_endpoint(
    path: str, transport: str, endpoint: str, issues: list[ServiceManifestIssue]
) -> None:
    _string(path, endpoint, issues, minimum=1, maximum=2048)
    if not endpoint or len(endpoint) > 2048:
        return
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        issues.append(ServiceManifestIssue(path, "format", f"invalid endpoint: {exc}"))
        return
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        issues.append(
            ServiceManifestIssue(path, "format", "must not include credentials, query, or fragment")
        )
    host = (parsed.hostname or "").lower()
    allowed_schemes = {
        "clearnet": {"https"},
        "tor": {"http", "https"},
        "i2p": {"http", "https"},
        "gemini": {"gemini"},
        "ipfs": {"ipfs"},
        "reticulum": {"reticulum"},
    }[transport]
    if parsed.scheme.lower() not in allowed_schemes:
        issues.append(
            ServiceManifestIssue(
                path,
                "transport-endpoint",
                f"{transport} endpoint must use one of: {', '.join(sorted(allowed_schemes))}",
            )
        )
    if transport == "tor" and not ONION_V3_RE.fullmatch(host):
        issues.append(ServiceManifestIssue(path, "transport-endpoint", "must use a v3 .onion host"))
    elif transport == "i2p" and not host.endswith(".i2p"):
        issues.append(ServiceManifestIssue(path, "transport-endpoint", "must use an .i2p host"))
    elif transport in {"clearnet", "gemini"} and not host:
        issues.append(ServiceManifestIssue(path, "transport-endpoint", "must include a host"))
    elif transport == "ipfs" and not (parsed.netloc or parsed.path):
        issues.append(
            ServiceManifestIssue(path, "transport-endpoint", "must include an IPFS address")
        )
    elif transport == "reticulum" and not (parsed.netloc or parsed.path):
        issues.append(
            ServiceManifestIssue(path, "transport-endpoint", "must include a Reticulum destination")
        )
    if port is not None and not (1 <= port <= 65535):
        issues.append(ServiceManifestIssue(path, "range", "port must be between 1 and 65535"))


def _validate_signature_object(
    path: str, value: Any, issues: list[ServiceManifestIssue]
) -> str | None:
    if not isinstance(value, dict):
        issues.append(ServiceManifestIssue(path, "type", "must be an object"))
        return None
    _unknown_fields(path, value, SIGNATURE_FIELDS, issues)
    _required_fields(path, value, SIGNATURE_FIELDS, issues)
    if value.get("algorithm") != SIGNATURE_ALGORITHM:
        issues.append(
            ServiceManifestIssue(path + ".algorithm", "algorithm", f"must be {SIGNATURE_ALGORITHM}")
        )
    if value.get("canonicalization") != CANONICALIZATION:
        issues.append(
            ServiceManifestIssue(
                path + ".canonicalization",
                "canonicalization",
                f"must be {CANONICALIZATION}",
            )
        )
    public_key = value.get("public_key")
    _pattern(path + ".public_key", public_key, HEX_32_RE, issues)
    _pattern(path + ".value", value.get("value"), HEX_64_RE, issues)
    return public_key if isinstance(public_key, str) and HEX_32_RE.fullmatch(public_key) else None


def _validate_delegation(
    value: Any,
    *,
    root_key: Any,
    service_id: Any,
    signing_key: str | None,
    issues: list[ServiceManifestIssue],
    verify_signature: bool,
) -> tuple[datetime | None, datetime | None]:
    path = "$.delegation"
    if not isinstance(value, dict):
        issues.append(ServiceManifestIssue(path, "type", "must be an object"))
        return None, None
    _unknown_fields(path, value, DELEGATION_FIELDS, issues)
    _required_fields(path, value, DELEGATION_FIELDS, issues)
    payload = value.get("payload")
    signature = value.get("signature")
    delegation_key = _validate_signature_object(path + ".signature", signature, issues)
    if not isinstance(payload, dict):
        issues.append(ServiceManifestIssue(path + ".payload", "type", "must be an object"))
        return None, None
    _unknown_fields(path + ".payload", payload, DELEGATION_PAYLOAD_FIELDS, issues)
    _required_fields(path + ".payload", payload, DELEGATION_PAYLOAD_FIELDS, issues)
    if payload.get("schema") != DELEGATION_SCHEMA:
        issues.append(
            ServiceManifestIssue(path + ".payload.schema", "schema", f"must be {DELEGATION_SCHEMA}")
        )
    _pattern(path + ".payload.service_id", payload.get("service_id"), SERVICE_ID_RE, issues)
    _pattern(path + ".payload.root_public_key", payload.get("root_public_key"), HEX_32_RE, issues)
    _pattern(
        path + ".payload.signing_public_key",
        payload.get("signing_public_key"),
        HEX_32_RE,
        issues,
    )
    _integer(
        path + ".payload.sequence",
        payload.get("sequence"),
        issues,
        minimum=1,
        maximum=MAX_SAFE_INTEGER,
    )
    if service_id is not None and payload.get("service_id") != service_id:
        issues.append(
            ServiceManifestIssue(path + ".payload.service_id", "binding", "service mismatch")
        )
    if root_key is not None and payload.get("root_public_key") != root_key:
        issues.append(
            ServiceManifestIssue(path + ".payload.root_public_key", "binding", "root key mismatch")
        )
    if signing_key is not None and payload.get("signing_public_key") != signing_key:
        issues.append(
            ServiceManifestIssue(
                path + ".payload.signing_public_key", "binding", "signing key mismatch"
            )
        )
    if root_key is not None and delegation_key is not None and delegation_key != root_key:
        issues.append(
            ServiceManifestIssue(path + ".signature.public_key", "binding", "must be the root key")
        )
    issued_at = _timestamp(path + ".payload.issued_at", payload.get("issued_at"), issues)
    expires_at = _timestamp(path + ".payload.expires_at", payload.get("expires_at"), issues)
    if issued_at and expires_at and issued_at >= expires_at:
        issues.append(
            ServiceManifestIssue(
                path + ".payload.expires_at", "range", "must be later than issued_at"
            )
        )
    try:
        canonicalize_jcs(payload)
    except (TypeError, ValueError) as exc:
        issues.append(ServiceManifestIssue(path + ".payload", "canonicalization", str(exc)))
    if verify_signature and isinstance(signature, dict):
        try:
            digest = delegation_digest(payload)
        except (TypeError, ValueError):
            pass
        else:
            _verify_signed_payload(path + ".signature", signature, digest, issues)
    return issued_at, expires_at


def _verify_signed_payload(
    path: str,
    signature: dict[str, Any],
    digest: bytes,
    issues: list[ServiceManifestIssue],
) -> None:
    try:
        public_key = _decode_hex(signature.get("public_key"), 32, "public key")
        value = _decode_hex(signature.get("value"), 64, "signature")
    except (TypeError, ValueError):
        return
    if not bip340_verify(public_key, digest, value):
        issues.append(ServiceManifestIssue(path + ".value", "signature", "verification failed"))


def _timestamp(
    path: str, value: Any, issues: list[ServiceManifestIssue]
) -> datetime | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 40
        or not RFC3339_RE.fullmatch(value)
    ):
        issues.append(ServiceManifestIssue(path, "type", "must be an RFC 3339 timestamp string"))
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        issues.append(ServiceManifestIssue(path, "format", "must be an RFC 3339 timestamp"))
        return None
    if parsed.tzinfo is None:
        issues.append(ServiceManifestIssue(path, "format", "must include a UTC offset"))
        return None
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def _unknown_fields(
    path: str,
    value: dict[str, Any],
    allowed: set[str],
    issues: list[ServiceManifestIssue],
) -> None:
    for field in sorted(set(value) - allowed):
        issues.append(ServiceManifestIssue(f"{path}.{field}", "unknown-field", "unknown field"))


def _required_fields(
    path: str,
    value: dict[str, Any],
    required: set[str],
    issues: list[ServiceManifestIssue],
) -> None:
    for field in sorted(required - set(value)):
        issues.append(ServiceManifestIssue(f"{path}.{field}", "required", "missing required field"))


def _string(
    path: str,
    value: Any,
    issues: list[ServiceManifestIssue],
    *,
    minimum: int,
    maximum: int,
) -> None:
    if not isinstance(value, str):
        issues.append(ServiceManifestIssue(path, "type", "must be a string"))
    elif not minimum <= len(value) <= maximum:
        issues.append(
            ServiceManifestIssue(path, "range", f"length must be between {minimum} and {maximum}")
        )


def _pattern(
    path: str,
    value: Any,
    pattern: re.Pattern[str],
    issues: list[ServiceManifestIssue],
) -> None:
    if not isinstance(value, str):
        issues.append(ServiceManifestIssue(path, "type", "must be a string"))
    elif not pattern.fullmatch(value):
        issues.append(ServiceManifestIssue(path, "format", "has invalid format"))


def _enum(
    path: str,
    value: Any,
    allowed: tuple[str, ...],
    issues: list[ServiceManifestIssue],
) -> None:
    if value not in allowed:
        issues.append(
            ServiceManifestIssue(path, "enum", f"must be one of: {', '.join(allowed)}")
        )


def _integer(
    path: str,
    value: Any,
    issues: list[ServiceManifestIssue],
    *,
    minimum: int,
    maximum: int,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        issues.append(ServiceManifestIssue(path, "type", "must be an integer"))
    elif not minimum <= value <= maximum:
        issues.append(
            ServiceManifestIssue(path, "range", f"must be between {minimum} and {maximum}")
        )


def _enum_array(
    path: str,
    value: Any,
    allowed: tuple[str, ...],
    issues: list[ServiceManifestIssue],
) -> None:
    if not isinstance(value, list):
        issues.append(ServiceManifestIssue(path, "type", "must be an array"))
        return
    if not value:
        issues.append(ServiceManifestIssue(path, "range", "must not be empty"))
    seen: set[str] = set()
    for index, item in enumerate(value):
        _enum(f"{path}[{index}]", item, allowed, issues)
        if isinstance(item, str) and item in seen:
            issues.append(ServiceManifestIssue(f"{path}[{index}]", "duplicate", "duplicate value"))
        if isinstance(item, str):
            seen.add(item)
    if "none" in seen and len(seen) > 1:
        issues.append(ServiceManifestIssue(path, "combination", "none cannot be combined"))


def _string_array(path: str, value: Any, issues: list[ServiceManifestIssue]) -> None:
    if not isinstance(value, list):
        issues.append(ServiceManifestIssue(path, "type", "must be an array"))
        return
    if len(value) > 64:
        issues.append(ServiceManifestIssue(path, "range", "must contain at most 64 values"))
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        _string(item_path, item, issues, minimum=1, maximum=120)
        if isinstance(item, str) and item in seen:
            issues.append(ServiceManifestIssue(item_path, "duplicate", "duplicate value"))
        if isinstance(item, str):
            seen.add(item)


def _decode_hex(value: Any, size: int, label: str) -> bytes:
    if not isinstance(value, str) or len(value) != size * 2:
        raise ValueError(f"{label} must be {size} bytes of lowercase hex")
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be lowercase hex") from exc
    if value != value.lower():
        raise ValueError(f"{label} must be lowercase hex")
    return decoded
