import unittest

from ampg.renderers import render_gemtext, render_micron


class GemtextRendererTest(unittest.TestCase):
    def test_converts_basic_html_to_gemtext(self):
        html = """
<!doctype html>
<html>
  <head><script>ignored()</script></head>
  <body>
    <h1>Hello</h1>
    <p>Read the <a href="about.html">about page</a>.</p>
    <ul><li>One</li><li>Two</li></ul>
    <img src="logo.png" alt="Logo">
  </body>
</html>
"""

        gemtext = render_gemtext(
            html,
            rewrite_link=lambda href: href.replace(".html", ".gmi"),
        )

        self.assertIn("# Hello", gemtext)
        self.assertIn("Read the about page.", gemtext)
        self.assertIn("=> about.gmi about page", gemtext)
        self.assertIn("- One", gemtext)
        self.assertIn("- Two", gemtext)
        self.assertIn("=> logo.png Image: Logo", gemtext)
        self.assertNotIn("ignored", gemtext)

    def test_converts_basic_html_to_micron(self):
        html = """
<html>
  <body>
    <h1>Hello</h1>
    <p>Read the <a href="about.html">about page</a>.</p>
    <script>ignored()</script>
  </body>
</html>
"""

        micron = render_micron(
            html,
            rewrite_link=lambda href: href.replace(".html", ".mu"),
        )

        # Micron, not Gemtext: headings are `>` by depth and links are inline
        # as `[label`url], not standalone "=> url label" lines.
        self.assertIn(">Hello", micron)
        self.assertNotIn("# Hello", micron)
        self.assertIn("`[about page`about.mu]", micron)
        self.assertNotIn("=> about.mu", micron)
        self.assertNotIn("ignored", micron)

    def test_micron_escapes_content_that_would_become_markup(self):
        html = (
            "<p>&gt;Free Beer</p>"
            "<p>price is 3 `BTC`</p>"
            "<h2>Sub</h2>"
            "<pre>literal `backticks` stay</pre>"
        )

        micron = render_micron(html)

        # A line starting with a structural character must not become a heading.
        self.assertIn("\\>Free Beer", micron)
        # Backticks in content must not open a formatting run.
        self.assertIn("3 \\`BTC\\`", micron)
        # Headings and literal blocks still render as real micron.
        self.assertIn(">>Sub", micron)
        self.assertIn("`=", micron)
        self.assertIn("literal `backticks` stay", micron)

    def test_micron_emphasis_uses_toggle_pairs(self):
        micron = render_micron("<p>a <strong>b</strong> c <em>d</em></p>")

        self.assertIn("`!b`!", micron)
        self.assertIn("`*d`*", micron)


if __name__ == "__main__":
    unittest.main()
