import tempfile
import unittest
from pathlib import Path

from ampg.audit import audit_gateway
from ampg.config import load_config


class AuditTest(unittest.TestCase):
    def test_reports_semantic_html_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "index.html").write_text(
                '<h1>Title</h1><h3>Skipped</h3><img src="x.png"><a href="page.html"></a>',
                encoding="utf-8",
            )
            config_path = root / "gateway.toml"
            config_path.write_text(
                """
[[site]]
id = "example"
domain = "example.test"

[site.source]
kind = "static-html"
path = "./source"

[site.outputs]
root = "./out"
""",
                encoding="utf-8",
            )

            issues = audit_gateway(load_config(config_path))
            codes = {issue.code for issue in issues}

            self.assertIn("heading_level_skip", codes)
            self.assertIn("missing_alt", codes)
            self.assertIn("empty_link_text", codes)


if __name__ == "__main__":
    unittest.main()
