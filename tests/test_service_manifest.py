from __future__ import annotations

import contextlib
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

from ampg.cli import main
from ampg import bip340
from ampg import service_manifest as sm


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests/fixtures/amp.service-manifest.v1.golden.json"


def golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_sign(secret: int, message: bytes) -> tuple[str, str]:
    point = bip340.point_mul(secret, bip340.SECP256K1_GENERATOR)
    assert point is not None
    adjusted = secret if point[1] % 2 == 0 else bip340.SECP256K1_ORDER - secret
    public_key = point[0].to_bytes(32, "big")
    secret_bytes = adjusted.to_bytes(32, "big")
    aux_hash = bip340.tagged_hash("BIP0340/aux", bytes(32))
    masked = bytes(left ^ right for left, right in zip(secret_bytes, aux_hash))
    nonce = int.from_bytes(
        bip340.tagged_hash("BIP0340/nonce", masked + public_key + message), "big"
    ) % bip340.SECP256K1_ORDER
    nonce_point = bip340.point_mul(nonce, bip340.SECP256K1_GENERATOR)
    assert nonce_point is not None
    adjusted_nonce = nonce if nonce_point[1] % 2 == 0 else bip340.SECP256K1_ORDER - nonce
    r = nonce_point[0].to_bytes(32, "big")
    challenge = int.from_bytes(
        bip340.tagged_hash("BIP0340/challenge", r + public_key + message), "big"
    ) % bip340.SECP256K1_ORDER
    signature = r + (
        (adjusted_nonce + challenge * adjusted) % bip340.SECP256K1_ORDER
    ).to_bytes(32, "big")
    assert sm.bip340_verify(public_key, message, signature)
    return public_key.hex(), signature.hex()


class ServiceManifestTest(unittest.TestCase):
    def test_official_bip340_vector(self):
        public_key = bytes.fromhex(
            "f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"
        )
        signature = bytes.fromhex(
            "e907831f80848d1069a5371b402410364bdf1c5f8307b0084c55f1ce2dca821"
            "525f66a4a85ea8b71e482a74f382d2ce5ebeee8fdb2172f477df4900d310536c0"
        )
        self.assertTrue(sm.bip340_verify(public_key, bytes(32), signature))
        self.assertFalse(sm.bip340_verify(public_key, bytes([1]) + bytes(31), signature))

    def test_cross_language_golden_vector(self):
        fixture = golden()
        manifest = fixture["manifest"]

        self.assertEqual(
            fixture["canonical_payload_utf8"].encode(),
            sm.canonicalize_jcs(manifest["payload"]),
        )
        self.assertEqual(
            fixture["payload_digest"], sm.service_manifest_digest(manifest["payload"]).hex()
        )
        self.assertEqual(
            [],
            sm.validate_service_manifest(
                manifest, now=datetime(2027, 1, 1, tzinfo=timezone.utc)
            ),
        )

    def test_jcs_uses_utf16_property_order_and_rejects_floats(self):
        self.assertEqual(
            '{"😀":2,"\ue000":1}'.encode(),
            sm.canonicalize_jcs({"\ue000": 1, "😀": 2}),
        )
        with self.assertRaisesRegex(TypeError, "floating-point"):
            sm.canonicalize_jcs({"value": 1.5})
        with self.assertRaisesRegex(ValueError, "safe range"):
            sm.canonicalize_jcs({"value": sm.MAX_SAFE_INTEGER + 1})

    def test_strict_loader_rejects_duplicate_keys_and_floats(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            sm.strict_json_loads('{"schema":"one","schema":"two"}')
        with self.assertRaisesRegex(ValueError, "floating-point"):
            sm.strict_json_loads('{"sequence":1.0}')

    def test_manifest_file_size_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.json"
            path.write_bytes(b" " * (sm.MAX_MANIFEST_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "exceeds"):
                sm.read_service_manifest(path)

    def test_tampering_expiration_and_rollback_fail_closed(self):
        manifest = deepcopy(golden()["manifest"])
        manifest["payload"]["routes"][0]["endpoint"] = "https://changed.example/"
        issues = sm.validate_service_manifest(
            manifest,
            now=datetime(2040, 1, 1, tzinfo=timezone.utc),
            minimum_sequence=2,
            expected_previous="22" * 32,
        )
        codes = {issue.code for issue in issues}
        self.assertTrue({"signature", "expired", "rollback", "chain"}.issubset(codes))

    def test_timestamp_format_is_strict(self):
        manifest = deepcopy(golden()["manifest"])
        manifest["payload"]["issued_at"] = "20260101T00:00:00Z"
        issues = sm.validate_service_manifest(manifest, verify_signature=False)
        self.assertIn(
            "$.payload.issued_at",
            {issue.path for issue in issues if issue.code == "type"},
        )

    def test_internal_routes_and_transport_mismatches_are_rejected(self):
        manifest = deepcopy(golden()["manifest"])
        route = manifest["payload"]["routes"][1]
        route["interaction_tier"] = "internal"
        route["endpoint"] = "https://example.com/"
        route["context"] = "clearnet"

        issues = sm.validate_service_manifest(manifest, verify_signature=False)
        by_path = {issue.path: issue.code for issue in issues}
        self.assertEqual("enum", by_path["$.payload.routes[1].interaction_tier"])
        self.assertEqual("transport-endpoint", by_path["$.payload.routes[1].endpoint"])
        self.assertEqual("context", by_path["$.payload.routes[1].context"])

    def test_delegated_signer_is_bound_to_root_and_validity_window(self):
        manifest = deepcopy(golden()["manifest"])
        root_secret = int(golden()["test_secret_key"], 16)
        signing_secret = 4
        signing_key, _ = test_sign(signing_secret, bytes(32))
        delegation_payload = {
            "schema": sm.DELEGATION_SCHEMA,
            "service_id": manifest["payload"]["service_id"],
            "root_public_key": manifest["payload"]["root_public_key"],
            "signing_public_key": signing_key,
            "issued_at": "2025-12-01T00:00:00Z",
            "expires_at": "2037-01-01T00:00:00Z",
            "sequence": 1,
        }
        root_key, delegation_signature = test_sign(
            root_secret, sm.delegation_digest(delegation_payload)
        )
        signing_key, manifest_signature = test_sign(
            signing_secret, sm.service_manifest_digest(manifest["payload"])
        )
        manifest["delegation"] = {
            "payload": delegation_payload,
            "signature": {
                "algorithm": sm.SIGNATURE_ALGORITHM,
                "canonicalization": sm.CANONICALIZATION,
                "public_key": root_key,
                "value": delegation_signature,
            },
        }
        manifest["signature"] = {
            "algorithm": sm.SIGNATURE_ALGORITHM,
            "canonicalization": sm.CANONICALIZATION,
            "public_key": signing_key,
            "value": manifest_signature,
        }

        self.assertEqual(
            [],
            sm.validate_service_manifest(
                manifest, now=datetime(2027, 1, 1, tzinfo=timezone.utc)
            ),
        )
        rollback = sm.validate_service_manifest(
            manifest,
            now=datetime(2027, 1, 1, tzinfo=timezone.utc),
            minimum_delegation_sequence=2,
        )
        self.assertIn(
            "$.delegation.payload.sequence",
            {issue.path for issue in rollback if issue.code == "rollback"},
        )

    def test_schema_is_generated_and_cli_validates_and_digests(self):
        manifest = golden()["manifest"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            schema_path = Path(tmp) / "schema.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                validate_status = main(
                    ["service-manifest", "validate", str(path), "--at", "2027-01-01T00:00:00Z"]
                )
                digest_status = main(["service-manifest", "digest", str(path)])
                schema_status = main(
                    ["service-manifest", "schema", "--output", str(schema_path)]
                )
            generated_schema = schema_path.read_text(encoding="utf-8")

        self.assertEqual((0, 0, 0), (validate_status, digest_status, schema_status))
        output = stdout.getvalue()
        self.assertIn("schema=amp.service-manifest.v1", output)
        self.assertIn(f"digest={golden()['payload_digest']}", output)
        self.assertEqual(sm.service_manifest_schema_json(), generated_schema)

    def test_generated_schema_file_matches_code(self):
        schema_path = ROOT / "schemas/amp.service-manifest.v1.schema.json"
        self.assertEqual(sm.service_manifest_schema_json(), schema_path.read_text(encoding="utf-8"))

    def test_standalone_example_matches_golden_manifest(self):
        example = json.loads((ROOT / "examples/service-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(golden()["manifest"], example)


if __name__ == "__main__":
    unittest.main()
