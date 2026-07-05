import unittest

from ampg.renderers import render_gemtext


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


if __name__ == "__main__":
    unittest.main()
