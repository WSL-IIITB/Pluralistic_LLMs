"""
Unit tests for similarity_core.py using standard library unittest and synthetic data.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.similarity_core import (
    canonical_order,
    cosine_matrix,
    group_stats,
    load_records,
    mean_sim_to_others,
    normalize_text,
    reliable,
    sha256_file,
    sim_to_baseline,
    spearman,
    usable,
)


class TestSimilarityCore(unittest.TestCase):

    def test_normalize_text(self):
        # 1. Bold markers removed
        self.assertEqual(normalize_text("This is **bold** text."), "This is bold text.")

        # 2. List markers at line starts removed; digits inside sentences untouched
        raw = (
            "1. First item\n"
            "2) Second item\n"
            "- Third item\n"
            "* Fourth item\n"
            "• Fifth item\n"
            "Normal sentence with 3.14 and step 2) inside."
        )
        expected = (
            "First item Second item Third item Fourth item Fifth item "
            "Normal sentence with 3.14 and step 2) inside."
        )
        self.assertEqual(normalize_text(raw), expected)

        # 3. Collapse whitespace and newlines
        self.assertEqual(normalize_text("  Lots   of \n\n  spaces   \t here!  "), "Lots of spaces here!")

        # 4. Script preservation (Devanagari, Perso-Arabic, Ol Chiki)
        devanagari = "1. **आत्म-सुधार** जीवन का लक्ष्य है।\n2) अभ्यास करें।"
        expected_dev = "आत्म-सुधार जीवन का लक्ष्य है। अभ्यास करें।"
        self.assertEqual(normalize_text(devanagari), expected_dev)

        perso_arabic = "- **خود اعتمادی** ضروری ہے۔"
        expected_pa = "خود اعتمادی ضروری ہے۔"
        self.assertEqual(normalize_text(perso_arabic), expected_pa)

        ol_chiki = "• ᱚᱞ ᱪᱤᱠᱤ ᱯᱟᱹᱨᱥᱤ"
        expected_ol = "ᱚᱞ ᱪᱤᱠᱤ ᱯᱟᱹᱨᱥᱤ"
        self.assertEqual(normalize_text(ol_chiki), expected_ol)

        # 5. Empty and None handling
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")

    def test_usable_and_reliable(self):
        # Usable checks
        rec_ok = {
            "target_lang_code": "hi-IN",
            "native_answer": "नमस्ते",
            "back_translated_answer_en": "Hello",
            "generation_failed": False,
        }
        self.assertTrue(usable(rec_ok, "native"))
        self.assertTrue(usable(rec_ok, "english"))

        rec_failed = {"target_lang_code": "hi-IN", "native_answer": "नमस्ते", "generation_failed": True}
        self.assertFalse(usable(rec_failed, "native"))

        rec_empty = {"target_lang_code": "hi-IN", "native_answer": "   \n\t  ", "generation_failed": False}
        self.assertFalse(usable(rec_empty, "native"))

        # Reliable checks
        # OK case
        rel_ok, reasons = reliable(rec_ok, "native")
        self.assertTrue(rel_ok)
        self.assertEqual(reasons, [])

        # English OK case
        rec_ok_en = dict(rec_ok)
        rec_ok_en["validation"] = {"back_translation": {"status": "OK"}}
        rel_ok_en, reasons = reliable(rec_ok_en, "english")
        self.assertTrue(rel_ok_en)
        self.assertEqual(reasons, [])

        # Review required
        rec_rev = dict(rec_ok)
        rec_rev["review_required"] = True
        rel_rev, reasons = reliable(rec_rev, "native")
        self.assertFalse(rel_rev)
        self.assertIn("review_required", reasons)

        # Back translation status FLAGGED
        rec_flagged = dict(rec_ok)
        rec_flagged["validation"] = {"back_translation": {"status": "FLAGGED"}}
        rel_bt, reasons = reliable(rec_flagged, "english")
        self.assertFalse(rel_bt)
        self.assertIn("back_translation_status_FLAGGED", reasons)

        # Known BT limits
        rec_limit = dict(rec_ok_en)
        rec_limit["target_lang_code"] = "mni-IN"
        rel_lim, reasons = reliable(rec_limit, "english", known_bt_limits={"mni-IN"})
        self.assertFalse(rel_lim)
        self.assertIn("known_backtranslation_limit", reasons)

        # en record is always reliable if usable
        rec_en = {
            "target_lang_code": "en",
            "native_answer": "Self improvement",
            "back_translated_answer_en": "Self improvement",
            "review_required": True,  # even if review_required is true
        }
        rel_en_nat, _ = reliable(rec_en, "native")
        rel_en_eng, _ = reliable(rec_en, "english")
        self.assertTrue(rel_en_nat)
        self.assertTrue(rel_en_eng)

    def test_cosine_matrix(self):
        # 3 synthetic unit vectors in R^3
        v0 = np.array([1.0, 0.0, 0.0])
        v1 = np.array([0.0, 1.0, 0.0])  # orthogonal to v0
        v2 = np.array([1.0, 0.0, 0.0])  # identical to v0
        embeddings = np.array([v0, v1, v2])

        # All usable
        mask = np.array([True, True, True])
        mat = cosine_matrix(embeddings, mask)
        self.assertAlmostEqual(mat[0, 0], 1.0)
        self.assertAlmostEqual(mat[0, 1], 0.0)
        self.assertAlmostEqual(mat[0, 2], 1.0)
        self.assertTrue(np.allclose(mat, mat.T))

        # With unusable row 1
        mask_unusable = np.array([True, False, True])
        mat_unusable = cosine_matrix(embeddings, mask_unusable)
        self.assertTrue(np.isnan(mat_unusable[1, :]).all())
        self.assertTrue(np.isnan(mat_unusable[:, 1]).all())
        self.assertAlmostEqual(mat_unusable[0, 2], 1.0)

        # Non-unit norm raises ValueError
        non_unit = np.array([[2.0, 0.0, 0.0]])
        with self.assertRaises(ValueError):
            cosine_matrix(non_unit, np.array([True]))

    def test_metrics_and_group_stats(self):
        # Hand-calculated example with 4 items: L0, L1, L2, and baseline 'en'
        # Order: ['L0', 'L1', 'L2', 'en']
        # Let similarities be:
        #        L0    L1    L2    en
        #  L0  [1.0,  0.8,  0.6,  0.5]
        #  L1  [0.8,  1.0,  0.4,  0.7]
        #  L2  [0.6,  0.4,  1.0,  0.9]
        #  en  [0.5,  0.7,  0.9,  1.0]
        order = ["L0", "L1", "L2", "en"]
        matrix = np.array(
            [
                [1.0, 0.8, 0.6, 0.5],
                [0.8, 1.0, 0.4, 0.7],
                [0.6, 0.4, 1.0, 0.9],
                [0.5, 0.7, 0.9, 1.0],
            ],
            dtype=np.float64,
        )

        # sim_to_baseline:
        # L0: 0.5, L1: 0.7, L2: 0.9
        sim_en = sim_to_baseline(matrix, order, baseline="en")
        self.assertAlmostEqual(sim_en["L0"], 0.5)
        self.assertAlmostEqual(sim_en["L1"], 0.7)
        self.assertAlmostEqual(sim_en["L2"], 0.9)
        self.assertNotIn("en", sim_en)

        # mean_sim_to_others (excluding 'en' and self):
        # For L0: others are L1(0.8) and L2(0.6) -> mean = (0.8 + 0.6)/2 = 0.7
        # For L1: others are L0(0.8) and L2(0.4) -> mean = (0.8 + 0.4)/2 = 0.6
        # For L2: others are L0(0.6) and L1(0.4) -> mean = (0.6 + 0.4)/2 = 0.5
        mean_others = mean_sim_to_others(matrix, order, exclude=("en",))
        self.assertAlmostEqual(mean_others["L0"], 0.7)
        self.assertAlmostEqual(mean_others["L1"], 0.6)
        self.assertAlmostEqual(mean_others["L2"], 0.5)

        # group_stats:
        # Group G1 = ['L0', 'L1']
        # Usable members: L0, L1 (n = 2)
        # sim_to_en = [0.5, 0.7] -> mean = 0.6, std(pop) = 0.1, min = 0.5, max = 0.7
        # within_mean: pair (L0, L1) = 0.8
        # outside: non-baseline outside is L2
        # between_mean: pairs (L0, L2)=0.6, (L1, L2)=0.4 -> mean = 0.5
        groups = {"G1": ["L0", "L1"]}
        stats = group_stats(matrix, order, groups, baseline="en")
        self.assertEqual(len(stats), 1)
        g1 = stats[0]
        self.assertEqual(g1["n"], 2)
        self.assertAlmostEqual(g1["mean_sim_to_en"], 0.6)
        self.assertAlmostEqual(g1["std"], 0.1)
        self.assertAlmostEqual(g1["min"], 0.5)
        self.assertAlmostEqual(g1["max"], 0.7)
        self.assertAlmostEqual(g1["within_mean"], 0.8)
        self.assertAlmostEqual(g1["between_mean"], 0.5)

    def test_spearman(self):
        # Perfect monotonic agreement
        x1 = [1.0, 2.0, 3.0, 4.0, 5.0]
        y1 = [10.0, 20.0, 30.0, 40.0, 50.0]
        self.assertAlmostEqual(spearman(x1, y1), 1.0)

        # Perfect inverted agreement
        y_rev = [50.0, 40.0, 30.0, 20.0, 10.0]
        self.assertAlmostEqual(spearman(x1, y_rev), -1.0)

        # Ties with average ranks
        # x = [1, 2, 2, 4] -> ranks: [1, 2.5, 2.5, 4]
        # y = [1, 2, 3, 4] -> ranks: [1, 2, 3, 4]
        # hand calculation:
        # mean_x = 2.5, var_x = (1.5^2 + 0 + 0 + 1.5^2)/4 = 4.5/4 = 1.125
        # mean_y = 2.5, var_y = (1.5^2 + 0.5^2 + 0.5^2 + 1.5^2)/4 = 5.0/4 = 1.25
        # cov = (-1.5*-1.5 + 0*-0.5 + 0*0.5 + 1.5*1.5)/4 = 4.5/4 = 1.125
        # corr = 1.125 / sqrt(1.125 * 1.25) = 1.125 / 1.185854 = 0.948683298
        x_ties = [1.0, 2.0, 2.0, 4.0]
        y_ties = [1.0, 2.0, 3.0, 4.0]
        expected_corr = 1.125 / math.sqrt(1.125 * 1.25)
        self.assertAlmostEqual(spearman(x_ties, y_ties), expected_corr)

        # Less than 3 pairs -> None
        self.assertIsNone(spearman([1.0, 2.0], [2.0, 3.0]))

        # NaN handling drops pairs
        x_nan = [1.0, float("nan"), 3.0, 4.0]
        y_nan = [10.0, 20.0, 30.0, 40.0]
        self.assertAlmostEqual(spearman(x_nan, y_nan), 1.0)

        # Zero variance -> None
        self.assertIsNone(spearman([2.0, 2.0, 2.0, 2.0], [1.0, 2.0, 3.0, 4.0]))

    def test_config_integrity(self):
        # Check that config/language_groups.json covers all 22 codes exactly once in families & scripts
        base_dir = Path(__file__).resolve().parent.parent
        with open(base_dir / "config" / "languages.json") as f:
            lang_cfg = json.load(f)
        codes = [entry["code"] for entry in lang_cfg["languages"]]
        self.assertEqual(len(codes), 22)

        with open(base_dir / "config" / "language_groups.json") as f:
            grp_cfg = json.load(f)

        # Check families
        fam_codes = []
        for fam, member_list in grp_cfg["families"].items():
            fam_codes.extend(member_list)
        self.assertEqual(sorted(fam_codes), sorted(codes))
        self.assertEqual(len(fam_codes), 22)
        self.assertNotIn("en", fam_codes)

        # Check scripts
        script_codes = []
        for script, member_list in grp_cfg["scripts"].items():
            script_codes.extend(member_list)
        self.assertEqual(sorted(script_codes), sorted(codes))
        self.assertEqual(len(script_codes), 22)
        self.assertNotIn("en", script_codes)

        # Canonical order helper
        order = canonical_order(base_dir / "config" / "languages.json")
        self.assertEqual(order, codes + ["en"])
        self.assertEqual(len(order), 23)


if __name__ == "__main__":
    unittest.main()
