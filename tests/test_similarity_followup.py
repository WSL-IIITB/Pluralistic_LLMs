"""
Unit tests for follow-up cross-lingual similarity functionality:
- plan_download in src.similarity_embed
- collect_library_versions in src.analyze_similarity
"""

import unittest

from src.analyze_similarity import collect_library_versions
from src.similarity_embed import plan_download


class TestSimilarityFollowup(unittest.TestCase):

    def test_plan_download_scenarios(self):
        # 1. 100 MB against 10 GB free is ok
        # 100 MB = 100 * 1024 * 1024, 10 GB = 10 * 1024 * 1024 * 1024
        sz_100mb = 100 * 1024 * 1024
        free_10gb = 10 * 1024 * 1024 * 1024
        ok, total, msg = plan_download([sz_100mb], free_10gb)
        self.assertTrue(ok)
        self.assertEqual(total, sz_100mb)
        self.assertEqual(msg, "ok")

        # 2. 6 GB against 10 GB free is not ok (> 5 GB limit)
        sz_6gb = 6 * 1024 * 1024 * 1024
        ok, total, msg = plan_download([sz_6gb], free_10gb)
        self.assertFalse(ok)
        self.assertEqual(total, sz_6gb)
        self.assertIn("insufficient free disk space", msg)

        # 3. Exactly half is ok (5 GB against 10 GB free)
        sz_5gb = 5 * 1024 * 1024 * 1024
        ok, total, msg = plan_download([sz_5gb], free_10gb)
        self.assertTrue(ok)
        self.assertEqual(total, sz_5gb)
        self.assertEqual(msg, "ok")

        # 4. One unknown size (None) is not ok with "size unknown"
        ok, total, msg = plan_download([sz_100mb, None, 1024], free_10gb)
        self.assertFalse(ok)
        self.assertEqual(msg, "size unknown")

        # 5. Empty list is ok with total 0
        ok, total, msg = plan_download([], free_10gb)
        self.assertTrue(ok)
        self.assertEqual(total, 0)
        self.assertEqual(msg, "ok")

    def test_collect_library_versions(self):
        # 1. Default packages must be present
        default_names = (
            "numpy",
            "torch",
            "transformers",
            "sentence-transformers",
            "huggingface-hub",
        )
        versions = collect_library_versions()
        for name in default_names:
            self.assertIn(name, versions)
            # In .venv-sim, all these packages should be installed
            self.assertNotEqual(versions[name], "not installed")
            self.assertIsInstance(versions[name], str)

        # 2. Made-up package name maps to "not installed" without raising
        fake_pkg = "definitely_not_installed_pkg"
        custom_versions = collect_library_versions([fake_pkg, "numpy"])
        self.assertEqual(custom_versions[fake_pkg], "not installed")
        self.assertNotEqual(custom_versions["numpy"], "not installed")


if __name__ == "__main__":
    unittest.main()
