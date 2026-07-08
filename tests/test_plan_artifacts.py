import tempfile
import unittest
from pathlib import Path

from ampg.config import load_config
from ampg.plan import plan_gateway, write_plan_artifacts


class PlanArtifactsTest(unittest.TestCase):
    def test_writes_tor_and_i2p_artifacts(self):
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

[site.outputs]
root = "./out"
plan_root = "./plan"

[site.protocols.tor]
enabled = true
renderer = "privacy-html"
daemon = "tor"
daemon_policy = "auto"
local_port = 19080
hidden_service_dir = "/var/lib/ampg/tor/example"

[site.protocols.i2p]
enabled = true
renderer = "privacy-html"
daemon = "i2pd"
daemon_policy = "auto"
local_port = 19081
keys_file = "example-web.dat"
tunnel_name = "example-web"

[site.protocols.gemini]
enabled = true
renderer = "gemtext"
daemon = "agate"
daemon_policy = "auto"
port = 1965
""",
                encoding="utf-8",
            )

            config = load_config(config_path)
            lines = plan_gateway(config)
            artifacts = write_plan_artifacts(config)

            self.assertEqual(len(lines), 3)
            self.assertEqual(len(artifacts), 5)

            torrc = root / "plan/example/tor/torrc-snippet.conf"
            tor_nginx = root / "plan/example/tor/nginx-loopback.conf"
            i2p_tunnel = root / "plan/example/i2p/i2pd-tunnel.conf"
            i2p_nginx = root / "plan/example/i2p/nginx-loopback.conf"
            agate_plan = root / "plan/example/gemini/agate-plan.txt"

            self.assertIn("HiddenServicePort 80 127.0.0.1:19080", torrc.read_text())
            self.assertIn("listen 127.0.0.1:19080;", tor_nginx.read_text())
            self.assertIn("[example-web]", i2p_tunnel.read_text())
            self.assertIn("type = http", i2p_tunnel.read_text())
            self.assertIn("inport = 80", i2p_tunnel.read_text())
            self.assertIn("keys = example-web.dat", i2p_tunnel.read_text())
            self.assertIn("listen 127.0.0.1:19081;", i2p_nginx.read_text())
            self.assertIn("daemon = agate", agate_plan.read_text())


if __name__ == "__main__":
    unittest.main()
