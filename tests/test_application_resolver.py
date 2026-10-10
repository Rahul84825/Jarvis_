import unittest
from core.os.application_resolver import application_resolver, TargetType, ResolvedTarget

class TestApplicationResolver(unittest.TestCase):
    def test_domain_url_detection(self):
        targets = [
            ("wellmeds.in", "https://wellmeds.in"),
            ("google.com", "https://google.com"),
            ("youtube.com", "https://youtube.com"),
            ("chatgpt.com", "https://chatgpt.com"),
            ("github.com", "https://github.com"),
            ("https://docs.python.org", "https://docs.python.org"),
            ("http://localhost:3000", "http://localhost:3000"),
            ("www.wikipedia.org", "https://www.wikipedia.org")
        ]
        for raw, expected_url in targets:
            res = application_resolver.resolve(raw)
            self.assertEqual(res.target_type, TargetType.URL, f"Failed for {raw}")
            self.assertEqual(res.url, expected_url, f"URL mismatch for {raw}")

    def test_known_website_target(self):
        # Targets that are known pure websites
        res = application_resolver.resolve("wellmeds")
        self.assertIn(res.target_type, [TargetType.WEBSITE, TargetType.URL])
        self.assertIn("wellmeds.in", res.url)

        res_yt = application_resolver.resolve("youtube")
        self.assertIn(res_yt.target_type, [TargetType.WEBSITE, TargetType.URL])
        self.assertIn("youtube.com", res_yt.url)

    def test_app_with_website_fallback(self):
        # Spotify has configured fallback: https://open.spotify.com
        res = application_resolver.resolve("spotify")
        # Depending on whether Spotify is installed on this test machine:
        if res.is_installed:
            self.assertEqual(res.target_type, TargetType.APPLICATION)
        else:
            self.assertEqual(res.target_type, TargetType.WEBSITE_FALLBACK)
            self.assertEqual(res.url, "https://open.spotify.com")

    def test_common_apps_resolution(self):
        res_chrome = application_resolver.resolve("chrome")
        self.assertIn(res_chrome.target_type, [TargetType.APPLICATION, TargetType.WEBSITE_FALLBACK])

        res_vscode = application_resolver.resolve("vscode")
        self.assertIn(res_vscode.target_type, [TargetType.APPLICATION, TargetType.WEBSITE_FALLBACK])

    def test_search_resolution(self):
        res = application_resolver.resolve_search("Python tutorials", "youtube")
        self.assertEqual(res.target_type, TargetType.SEARCH)
        self.assertIn("youtube.com/results?search_query=Python+tutorials", res.url)

        res_g = application_resolver.resolve_search("React hooks", "google")
        self.assertEqual(res_g.target_type, TargetType.SEARCH)
        self.assertIn("google.com/search?q=React+hooks", res_g.url)

if __name__ == "__main__":
    unittest.main()
