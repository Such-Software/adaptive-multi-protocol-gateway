import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from ampg.cli import main
from ampg.config import load_config
from ampg.route_policy import route_exposures, route_issues


class RoutePolicyTest(unittest.TestCase):
    def test_route_exposure_explains_exposed_denied_and_tier_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_app_config(Path(tmp)))

            exposures = route_exposures(config)
        by_protocol_route = {
            (exposure.protocol, exposure.match): exposure
            for exposure in exposures
        }

        self.assertEqual("route-manifest", by_protocol_route[("tor", "/play/*")].source)
        self.assertEqual("exposed", by_protocol_route[("tor", "/play/*")].status)
        self.assertEqual("exposed", by_protocol_route[("gemini", "/play/*")].status)
        self.assertEqual("skipped", by_protocol_route[("ipfs", "/play/*")].status)
        self.assertEqual(
            "tier interactive-lite exceeds protocol max_tier static",
            by_protocol_route[("ipfs", "/play/*")].reason,
        )

        self.assertEqual("skipped", by_protocol_route[("tor", "/checkout/*")].status)
        self.assertEqual(
            "tier transactional exceeds protocol max_tier interactive-lite",
            by_protocol_route[("tor", "/checkout/*")].reason,
        )

        self.assertEqual("skipped", by_protocol_route[("tor", "/admin/*")].status)
        self.assertEqual(
            "matched deny_route /admin/*",
            by_protocol_route[("tor", "/admin/*")].reason,
        )

        issues = route_issues(config)
        self.assertEqual(["/checkout/*"], [issue.match for issue in issues])
        self.assertEqual("no-compatible-protocol", issues[0].code)

    def test_route_validate_exits_nonzero_for_unsupported_public_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_app_config(Path(tmp))
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["--config", str(config_path), "routes", "validate"])

        output = stdout.getvalue()
        self.assertEqual(1, status)
        self.assertIn("AMPG_ROUTE site=app protocol=tor route_index=0 route=\"/play/*\"", output)
        self.assertIn("AMPG_ROUTE_ISSUE site=app route_index=1 route=\"/checkout/*\"", output)
        self.assertIn("AMPG_ROUTE_SUMMARY sites=1 routes=3 decisions=9 exposed=2 skipped=7 issues=1", output)

    def test_route_explain_exits_zero_with_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_app_config(Path(tmp))
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["--config", str(config_path), "routes", "explain"])

        self.assertEqual(0, status)
        self.assertIn("issues=1", stdout.getvalue())

    def test_route_manifest_requires_routes_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "site"
            source.mkdir()
            (source / "index.html").write_text("<h1>App</h1>", encoding="utf-8")
            (root / "routes.json").write_text(
                '{"schema": "ampg.route-manifest.v1"}',
                encoding="utf-8",
            )
            config_path = root / "gateway.toml"
            config_path.write_text(
                """
[[site]]
id = "app"
domain = "app.test"

[site.source]
kind = "static-html"
path = "./site"

[site.outputs]
root = "./out"
plan_root = "./plan"

[site.interactions]
route_manifest = "./routes.json"

[site.protocols.tor]
enabled = true
renderer = "privacy-html"
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "missing required routes array"):
                load_config(config_path)


def _write_app_config(root: Path) -> Path:
    source = root / "site"
    source.mkdir()
    (source / "index.html").write_text("<h1>App</h1>", encoding="utf-8")
    (root / "routes.json").write_text(
        """
{
  "schema": "ampg.route-manifest.v1",
  "default_tier": "interactive-lite",
  "deny_routes": ["/admin/*"],
  "routes": [
    {"match": "/play/*"},
    {"match": "/checkout/*", "tier": "transactional"},
    {"match": "/admin/*", "tier": "static"}
  ]
}
""",
        encoding="utf-8",
    )
    config_path = root / "gateway.toml"
    config_path.write_text(
        """
[[site]]
id = "app"
domain = "app.test"

[site.source]
kind = "static-html"
path = "./site"

[site.outputs]
root = "./out"
plan_root = "./plan"

[site.interactions]
route_manifest = "./routes.json"

[site.protocols.tor]
enabled = true
renderer = "privacy-html"
max_tier = "interactive-lite"

[site.protocols.gemini]
enabled = true
renderer = "gemtext"

[site.protocols.ipfs]
enabled = true
renderer = "clearnet"
cid = "bafyexample"
""",
        encoding="utf-8",
    )
    return config_path


if __name__ == "__main__":
    unittest.main()
