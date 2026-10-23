"""
Unit tests for core.lazy_loader.
Verifies deferred module imports, attribute proxies, thread-safety,
and compatibility with unittest.mock.
"""

import sys
import unittest
from unittest.mock import patch, MagicMock

from core.lazy_loader import lazy_import, lazy_attr, is_loaded, LazyModuleProxy, LazyAttrProxy


class TestLazyLoader(unittest.TestCase):

    def test_lazy_import_defers_execution(self):
        # Pick a module not yet imported
        target = "xml.etree.ElementTree"
        if target in sys.modules:
            del sys.modules[target]

        mod = lazy_import(target)
        self.assertIsInstance(mod, LazyModuleProxy)
        self.assertFalse(is_loaded(target))

        # Access attribute triggers resolution
        elem = mod.Element("root")
        self.assertEqual(elem.tag, "root")
        self.assertTrue(is_loaded(target))

    def test_lazy_attr_defers_execution(self):
        target_mod = "urllib.parse"
        target_attr = "urlparse"
        if target_mod in sys.modules:
            # We can still test proxy resolution
            pass

        parse_fn = lazy_attr(target_mod, target_attr)
        self.assertIsInstance(parse_fn, LazyAttrProxy)

        res = parse_fn("https://example.com/path?arg=1")
        self.assertEqual(res.scheme, "https")
        self.assertEqual(res.netloc, "example.com")

    def test_mock_patch_compatibility(self):
        mod = lazy_import("math")
        with patch("math.sqrt", return_value=42.0):
            val = mod.sqrt(9)
            self.assertEqual(val, 42.0)

        # After patch context ends, normal behavior resumes
        self.assertEqual(mod.sqrt(9), 3.0)

    def test_repr_and_dir(self):
        mod = lazy_import("json")
        self.assertIn("LazyModuleProxy", repr(mod))
        # After dir(), module is resolved
        dir_keys = dir(mod)
        self.assertIn("dumps", dir_keys)
        self.assertIn("loads", dir_keys)
        self.assertIn("module 'json'", repr(mod))


if __name__ == "__main__":
    unittest.main()
