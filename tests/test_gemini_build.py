import tempfile
import unittest
from pathlib import Path

from ampg.build import build_gateway
from ampg.config import load_config
from ampg.plan import plan_gateway, write_plan_artifacts


class GeminiBuildTest(unittest.TestCase):
    def test_existing_html_source_can_build_only_gemini(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "index.html").write_text(
                '<h1>Home</h1><p><a href="about.html">About</a></p><script>bad()</script>',
                encoding="utf-8",
            )
            (source / "about.html").write_text("<h1>About</h1>", encoding="utf-8")
            (source / "app.js").write_text("bad()", encoding="utf-8")
            config_path = root / "gateway.toml"
            config_path.write_text(
                """
[[site]]
id = "gemini_only"
domain = "example.test"

[site.source]
kind = "static-html"
path = "./source"

[site.outputs]
root = "./out"
plan_root = "./plan"

[site.protocols.gemini]
enabled = true
renderer = "gemtext"
daemon = "agate"
daemon_policy = "auto"
port = 1965
max_asset_bytes = 1024
""",
                encoding="utf-8",
            )

            config = load_config(config_path)
            plan = plan_gateway(config)
            artifacts = write_plan_artifacts(config)
            results = build_gateway(config)

            self.assertEqual([line.protocol for line in plan], ["gemini"])
            self.assertEqual([result.protocol for result in results], ["gemini"])
            self.assertEqual(len(artifacts), 1)
            self.assertTrue((root / "out/gemini/index.gmi").exists())
            self.assertTrue((root / "out/gemini/about.gmi").exists())
            self.assertFalse((root / "out/gemini/app.js").exists())
            self.assertFalse((root / "out/clearnet").exists())
            gemtext = (root / "out/gemini/index.gmi").read_text(encoding="utf-8")
            self.assertIn("# Home", gemtext)
            self.assertIn("=> about.gmi About", gemtext)
            self.assertNotIn("bad", gemtext)
            agate_plan = (root / "plan/gemini_only/gemini/agate-plan.txt").read_text()
            self.assertIn("daemon = agate", agate_plan)
            self.assertIn("content_root =", agate_plan)


if __name__ == "__main__":
    unittest.main()
