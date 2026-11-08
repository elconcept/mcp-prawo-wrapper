"""Local unit checks; live HTML smoke tests are run through MCP against PrawMi."""
import unittest

from server import article_id, ruling_slug, safe_slug, fold


class PmiParsersTest(unittest.TestCase):
    def test_article_identifiers(self):
        for raw in ("23", "art-23", "art. 23"):
            self.assertEqual(article_id(raw), "art-23")
        self.assertEqual(article_id("4a"), "art-4a")
        self.assertEqual(article_id("art-4a"), "art-4a")

    def test_safe_slugs(self):
        self.assertEqual(safe_slug("kodeks-postepowania-karnego"), "kodeks-postepowania-karnego")
        for bad in ("/../../etc/passwd", "https://evil.com", "../ustawa"):
            with self.assertRaises(ValueError):
                safe_slug(bad)

    def test_ruling_signature(self):
        self.assertEqual(ruling_slug("XII Ko 26/23"), "xii-ko-26-23")
        self.assertEqual(ruling_slug("III OSK 533/24"), "iii-osk-533-24")
        self.assertEqual(ruling_slug("Sygn. akt XII Ko 26/23"), "xii-ko-26-23")

    def test_polish_normalization(self):
        self.assertEqual(fold("Postępowanie karne"), "postepowanie karne")


if __name__ == "__main__":
    unittest.main()
