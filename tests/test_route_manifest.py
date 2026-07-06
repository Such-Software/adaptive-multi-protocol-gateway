import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ampg.capabilities import IDENTITY_ADAPTERS, INTERACTION_TIERS, PAYMENT_ADAPTERS
from ampg.cli import main
from ampg.metadata import (
    IDENTITY_ADAPTERS as METADATA_IDENTITY_ADAPTERS,
    INTERACTION_TIERS as METADATA_INTERACTION_TIERS,
    PAYMENT_ADAPTERS as METADATA_PAYMENT_ADAPTERS,
)
from ampg.route_manifest import (
    route_manifest_schema_json,
    validate_route_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


class RouteManifestTest(unittest.TestCase):
    def test_example_route_manifest_is_valid(self):
        data = json.loads((ROOT / "examples/route-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual([], validate_route_manifest(data))

    def test_route_catalog_generator_matches_example_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "route-manifest.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "tools/generate_route_manifest.py",
                    "examples/route-catalog.json",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual("", result.stderr)
            self.assertEqual(0, result.returncode)
            self.assertEqual(
                (ROOT / "examples/route-manifest.json").read_text(encoding="utf-8"),
                output.read_text(encoding="utf-8"),
            )

            check_result = subprocess.run(
                [
                    sys.executable,
                    "tools/generate_route_manifest.py",
                    "examples/route-catalog.json",
                    str(output),
                    "--check",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual("", check_result.stderr)
            self.assertEqual(0, check_result.returncode)

    def test_invalid_route_manifest_reports_all_contract_issues(self):
        issues = validate_route_manifest(
            {
                "schema": "wrong",
                "default_tier": "magic",
                "deny_routes": ["admin/*"],
                "extra": True,
                "routes": [
                    {
                        "match": "play/*",
                        "tier": "paid",
                        "identity": "cookie-ish",
                        "payments": "coin",
                        "realtime": "yes",
                        "public_allowed": "no",
                        "extra": True,
                    },
                    [],
                ],
            }
        )

        by_path = {issue.path: issue for issue in issues}
        self.assertEqual("unknown-field", by_path["$.extra"].code)
        self.assertEqual("schema", by_path["$.schema"].code)
        self.assertEqual("enum", by_path["$.default_tier"].code)
        self.assertEqual("pattern", by_path["$.deny_routes[0]"].code)
        self.assertEqual("unknown-field", by_path["$.routes[0].extra"].code)
        self.assertEqual("pattern", by_path["$.routes[0].match"].code)
        self.assertEqual("enum", by_path["$.routes[0].tier"].code)
        self.assertEqual("enum", by_path["$.routes[0].identity"].code)
        self.assertEqual("enum", by_path["$.routes[0].payments"].code)
        self.assertEqual("type", by_path["$.routes[0].realtime"].code)
        self.assertEqual("type", by_path["$.routes[0].public_allowed"].code)
        self.assertEqual("type", by_path["$.routes[1]"].code)

    def test_route_manifest_validate_cli(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            status = main(["route-manifest", "validate", "examples/route-manifest.json"])

        self.assertEqual(0, status)
        self.assertIn("schema=ampg.route-manifest.v1 routes=4 status=ok", stdout.getvalue())

    def test_route_manifest_validate_cli_reports_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "routes.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "ampg.route-manifest.v1",
                        "routes": [{"match": "play/*", "tier": "paid"}],
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["route-manifest", "validate", str(path)])

        output = stdout.getvalue()
        self.assertEqual(1, status)
        self.assertIn("json_path=$.routes[0].match code=pattern", output)
        self.assertIn("json_path=$.routes[0].tier code=enum", output)
        self.assertIn("status=fail issues=2", output)

    def test_route_manifest_schema_file_matches_generated_schema(self):
        schema_path = ROOT / "schemas/ampg.route-manifest.v1.schema.json"

        self.assertEqual(
            route_manifest_schema_json(),
            schema_path.read_text(encoding="utf-8"),
        )

    def test_route_manifest_schema_cli_can_write_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schema.json"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["route-manifest", "schema", "--output", str(path)])

            self.assertEqual(0, status)
            self.assertEqual(route_manifest_schema_json(), path.read_text(encoding="utf-8"))
            self.assertIn(f"AMPG_ROUTE_MANIFEST_SCHEMA path={path}", stdout.getvalue())

    def test_capability_constants_match_generated_metadata(self):
        self.assertEqual(
            tuple(tier.name for tier in METADATA_INTERACTION_TIERS),
            INTERACTION_TIERS,
        )
        self.assertEqual(
            tuple(adapter.name for adapter in METADATA_IDENTITY_ADAPTERS),
            IDENTITY_ADAPTERS,
        )
        self.assertEqual(
            tuple(adapter.name for adapter in METADATA_PAYMENT_ADAPTERS),
            PAYMENT_ADAPTERS,
        )


if __name__ == "__main__":
    unittest.main()
