import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ampg.build import build_gateway
from ampg.cli import main
from ampg.config import load_config
from ampg.preview import preview_endpoints, write_preview_fixture_manifests


class PreviewTest(unittest.TestCase):
    def test_preview_manifest_rewrites_urls_to_loopback_and_preserves_published_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_config(Path(tmp))
            config = load_config(config_path)
            build_gateway(config)

            endpoints = preview_endpoints(config, base_port=19100)
            self.assertEqual(["clearnet", "tor"], [endpoint.protocol for endpoint in endpoints])
            self.assertEqual([19100, 19101], [endpoint.port for endpoint in endpoints])
            self.assertEqual(["ready", "ready"], [endpoint.status for endpoint in endpoints])

            results = write_preview_fixture_manifests(config, base_port=19100)
            self.assertEqual(1, len(results))
            self.assertEqual(4, results[0].fixture_count)

            data = json.loads(results[0].path.read_text(encoding="utf-8"))
            self.assertEqual("preview", data["mode"])
            by_protocol_path = {
                (fixture["protocol"], fixture.get("route", {}).get("fixture_path", "/")): fixture
                for fixture in data["fixtures"]
            }

            tor_root = by_protocol_path[("tor", "/")]
            self.assertEqual("http://127.0.0.1:19101/", tor_root["url"])
            self.assertEqual({"transport": "clearnet", "profile": "clearnet"}, tor_root["checks"])
            self.assertEqual("http://preview.onion/", tor_root["published"]["url"])
            self.assertEqual({"transport": "tor", "profile": "tor"}, tor_root["published"]["checks"])
            self.assertEqual("preview", tor_root["address_status"])
            self.assertEqual("ready", tor_root["preview"]["status"])

            tor_play = by_protocol_path[("tor", "/play/")]
            self.assertEqual("http://127.0.0.1:19101/play/", tor_play["url"])

    def test_preview_manifest_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = _write_config(Path(tmp))
            config = load_config(config_path)
            build_gateway(config)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = main(["--config", str(config_path), "preview", "manifest", "--base-port", "19200"])
            self.assertTrue((config.sites[0].outputs.root / "ampg-preview-fixture-manifest.json").exists())

        output = stdout.getvalue()
        self.assertEqual(0, status)
        self.assertIn("AMPG_PREVIEW_ENDPOINT site=preview protocol=clearnet", output)
        self.assertIn("AMPG_PREVIEW_ENDPOINT site=preview protocol=tor", output)
        self.assertIn("AMPG_PREVIEW_MANIFEST site=preview", output)

    def test_preview_endpoints_report_missing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(_write_config(Path(tmp)))

            endpoints = preview_endpoints(config)

        self.assertEqual(["missing-output", "missing-output"], [endpoint.status for endpoint in endpoints])


def _write_config(root: Path) -> Path:
    source = root / "site"
    source.mkdir()
    (source / "index.html").write_text("<h1>Preview</h1>", encoding="utf-8")
    config_path = root / "gateway.toml"
    config_path.write_text(
        """
[[site]]
id = "preview"
domain = "preview.test"

[site.source]
kind = "static-html"
path = "./site"
canonical_url = "https://preview.test"

[site.outputs]
root = "./out"
plan_root = "./plan"

[[site.interactions.route]]
match = "/play/*"
tier = "interactive-lite"

[site.protocols.clearnet]
enabled = true
renderer = "clearnet"

[site.protocols.tor]
enabled = true
renderer = "privacy-html"
""",
        encoding="utf-8",
    )
    return config_path


if __name__ == "__main__":
    unittest.main()
