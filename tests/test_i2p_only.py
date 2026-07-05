import tempfile
import unittest
from pathlib import Path

from ampg.build import build_gateway
from ampg.config import load_config
from ampg.plan import plan_gateway


class I2POnlyTest(unittest.TestCase):
    def test_existing_html_source_can_build_only_i2p(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "index.html").write_text(
                '<html><body onload="boot()"><script src="app.js"></script><h1>Hi</h1></body></html>',
                encoding="utf-8",
            )
            (source / "app.js").write_text("boot()", encoding="utf-8")
            config_path = root / "gateway.toml"
            config_path.write_text(
                """
[[site]]
id = "i2p_only"
domain = "example.test"

[site.source]
kind = "static-html"
path = "./source"

[site.outputs]
root = "./out"
plan_root = "./plan"

[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
daemon = "i2pd"
daemon_policy = "auto"
local_port = 19081
keys_file = "example-web.dat"
tunnel_name = "example-web"
max_asset_bytes = 1024
script_policy = "strip"
""",
                encoding="utf-8",
            )

            config = load_config(config_path)
            plan = plan_gateway(config)
            results = build_gateway(config)

            self.assertEqual([line.protocol for line in plan], ["i2p"])
            self.assertEqual([result.protocol for result in results], ["i2p"])
            self.assertTrue((root / "out/i2p/index.html").exists())
            self.assertFalse((root / "out/clearnet").exists())
            self.assertFalse((root / "out/i2p/app.js").exists())
            rendered = (root / "out/i2p/index.html").read_text(encoding="utf-8")
            self.assertNotIn("<script", rendered)
            self.assertNotIn("onload", rendered)


if __name__ == "__main__":
    unittest.main()
