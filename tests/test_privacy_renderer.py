import unittest

from ampg.renderers import render_privacy_html


class PrivacyRendererTest(unittest.TestCase):
    def test_removes_scripts_event_handlers_and_inline_styles(self):
        html = (
            '<!doctype html><html><head><script src="app.js"></script></head>'
            '<body onload="boot()" style="color:red"><a onclick="x()" href="/ok">ok</a>'
            '<img src="https://example.com/x.png"><p>hello</p></body></html>'
        )

        rendered, stats = render_privacy_html(html)

        self.assertNotIn("<script", rendered)
        self.assertNotIn("onload", rendered)
        self.assertNotIn("onclick", rendered)
        self.assertNotIn("style=", rendered)
        self.assertNotIn("https://example.com/x.png", rendered)
        self.assertIn('<a href="/ok">ok</a>', rendered)
        self.assertIn("<p>hello</p>", rendered)
        self.assertEqual(stats.removed_active_tags, 1)
        self.assertEqual(stats.removed_event_handlers, 2)
        self.assertEqual(stats.removed_inline_styles, 1)
        self.assertEqual(stats.removed_remote_assets, 1)


if __name__ == "__main__":
    unittest.main()
