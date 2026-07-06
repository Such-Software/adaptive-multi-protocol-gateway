import json
import tempfile
import unittest
from pathlib import Path

from ampg.config import load_config
from ampg.manifest import fixture_manifest, write_fixture_manifests


class FixtureManifestTest(unittest.TestCase):
    def test_manifest_contains_route_checks_for_enabled_protocols(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "site"
            source.mkdir()
            (source / "index.html").write_text("<h1>Hi</h1>", encoding="utf-8")
            config_path = root / "gateway.toml"
            config_path.write_text(
                """
[[site]]
id = "example"
domain = "example.test"

[site.source]
kind = "static-html"
path = "./site"
canonical_url = "https://example.test"

[site.outputs]
root = "./out"
plan_root = "./plan"

[site.protocols.clearnet]
enabled = true
renderer = "clearnet"

[site.protocols.tor]
enabled = true
renderer = "privacy-html"
onion_location = "auto"

[site.protocols.i2p]
enabled = true
renderer = "privacy-html"

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

            config = load_config(config_path)
            manifest = fixture_manifest(config.sites[0])
            written = write_fixture_manifests(config)

            self.assertEqual("ampg.fixture-manifest.v1", manifest["schema"])
            self.assertEqual(["example"], [result.site_id for result in written])
            self.assertEqual(5, written[0].fixture_count)

            path = root / "out/ampg-fixture-manifest.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            by_protocol = {fixture["protocol"]: fixture for fixture in data["fixtures"]}

            self.assertEqual("https://example.test/", by_protocol["clearnet"]["url"])
            self.assertEqual("http://example.onion/", by_protocol["tor"]["url"])
            self.assertEqual("placeholder", by_protocol["tor"]["address_status"])
            self.assertEqual("gemini://example.test/", by_protocol["gemini"]["url"])
            self.assertEqual("ipfs://bafyexample", by_protocol["ipfs"]["url"])
            self.assertEqual({"transport": "ipfs", "profile": "ipfs"}, by_protocol["ipfs"]["checks"])
            self.assertEqual(
                {
                    "identity": "none",
                    "payments": "none",
                    "public_allowed": True,
                    "realtime": False,
                    "tier": "static",
                },
                by_protocol["ipfs"]["interaction"],
            )

    def test_manifest_includes_configured_interaction_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "site"
            source.mkdir()
            (source / "index.html").write_text("<h1>Store</h1>", encoding="utf-8")
            config_path = root / "gateway.toml"
            config_path.write_text(
                """
[[site]]
id = "store"
domain = "store.test"

[site.source]
kind = "static-html"
path = "./site"

[site.outputs]
root = "./out"
plan_root = "./plan"

[site.protocols.tor]
enabled = true
renderer = "privacy-html"
tier = "transactional"
identity = "http-session"
payments = "server-invoice"
""",
                encoding="utf-8",
            )

            config = load_config(config_path)
            manifest = fixture_manifest(config.sites[0])

        self.assertEqual(
            {
                "identity": "http-session",
                "payments": "server-invoice",
                "public_allowed": True,
                "realtime": False,
                "tier": "transactional",
            },
            manifest["fixtures"][0]["interaction"],
        )


if __name__ == "__main__":
    unittest.main()
