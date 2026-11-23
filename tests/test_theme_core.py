"""
Unit tests for theme_core.py using standard library unittest and synthetic data.
"""

import json
import math
import tempfile
import unittest
from pathlib import Path

from src.theme_core import (
    apply_verification,
    build_distinctive_themes_rows,
    build_group_theme_rates_rows,
    build_keyword_df_rows,
    build_keyword_overlap_rows,
    build_language_vs_english_rows,
    build_stopwords,
    build_theme_frequency_rows,
    candidate_terms,
    codebook_is_approved,
    cohens_kappa,
    jaccard,
    load_codebook,
    norm_for_match,
    parse_tag_response,
    percent_agreement,
    render_prompt,
    select_top_k,
    tfidf_scores,
    tokenize_segments,
    verify_evidence,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestThemeCore(unittest.TestCase):

    def test_codebook_loading_and_validation(self):
        # 1. Shipped codebooks load successfully
        cb1_path = PROJECT_ROOT / "config" / "codebooks" / "self_image_life_goal.json"
        cb2_path = PROJECT_ROOT / "config" / "codebooks" / "self_dev_tips.json"

        cb1 = load_codebook(cb1_path)
        cb2 = load_codebook(cb2_path)

        # Both codebooks have now been reviewed and APPROVED by user
        self.assertEqual(cb1["status"], "APPROVED")
        self.assertTrue(codebook_is_approved(cb1))
        self.assertEqual(len(cb1["themes"]), 6)

        self.assertEqual(cb2["status"], "APPROVED")
        self.assertTrue(codebook_is_approved(cb2))
        self.assertEqual(len(cb2["themes"]), 6)

        # 2. Validation edge cases with temporary files
        def make_cb(themes_list, status="DRAFT"):
            return {"query_id": "test", "version": 1, "status": status, "themes": themes_list}

        with tempfile.TemporaryDirectory() as td:
            # Bad id (starts with number or has special char)
            bad_id_cb = make_cb([
                {"id": "1_bad", "label": "L", "definition": "D"},
                {"id": "ok_two", "label": "L", "definition": "D"},
                {"id": "ok_three", "label": "L", "definition": "D"},
            ])
            p_bad_id = Path(td) / "bad_id.json"
            p_bad_id.write_text(json.dumps(bad_id_cb))
            with self.assertRaises(ValueError):
                load_codebook(p_bad_id)

            # Duplicate id
            dup_cb = make_cb([
                {"id": "theme_a", "label": "L", "definition": "D"},
                {"id": "theme_a", "label": "L2", "definition": "D2"},
                {"id": "theme_b", "label": "L", "definition": "D"},
            ])
            p_dup = Path(td) / "dup.json"
            p_dup.write_text(json.dumps(dup_cb))
            with self.assertRaises(ValueError):
                load_codebook(p_dup)

            # Empty definition
            empty_def_cb = make_cb([
                {"id": "theme_a", "label": "L", "definition": ""},
                {"id": "theme_b", "label": "L", "definition": "D"},
                {"id": "theme_c", "label": "L", "definition": "D"},
            ])
            p_empty = Path(td) / "empty.json"
            p_empty.write_text(json.dumps(empty_def_cb))
            with self.assertRaises(ValueError):
                load_codebook(p_empty)

            # Too few themes (2 themes < 3)
            too_few = make_cb([
                {"id": "theme_a", "label": "L", "definition": "D"},
                {"id": "theme_b", "label": "L", "definition": "D"},
            ])
            p_few = Path(td) / "few.json"
            p_few.write_text(json.dumps(too_few))
            with self.assertRaises(ValueError):
                load_codebook(p_few)

            # Too many themes (13 themes > 12)
            too_many = make_cb([
                {"id": f"t_{i}", "label": "L", "definition": "D"} for i in range(13)
            ])
            p_many = Path(td) / "many.json"
            p_many.write_text(json.dumps(too_many))
            with self.assertRaises(ValueError):
                load_codebook(p_many)

            # Approved check
            appr = make_cb([
                {"id": "theme_a", "label": "L", "definition": "D"},
                {"id": "theme_b", "label": "L", "definition": "D"},
                {"id": "theme_c", "label": "L", "definition": "D"},
            ], status="APPROVED")
            p_appr = Path(td) / "appr.json"
            p_appr.write_text(json.dumps(appr))
            cb_appr = load_codebook(p_appr)
            self.assertTrue(codebook_is_approved(cb_appr))

    def test_prompt_rendering_and_language_blindness(self):
        tmpl_path = PROJECT_ROOT / "config" / "prompts" / "theme_tagging_v1.txt"
        tmpl_text = tmpl_path.read_text(encoding="utf-8")

        cb_path = PROJECT_ROOT / "config" / "codebooks" / "self_image_life_goal.json"
        cb = load_codebook(cb_path)

        # 1. Blindness check on template:
        # Template must contain NONE of the 22 language names, codes, or script names
        lang_cfg_path = PROJECT_ROOT / "config" / "languages.json"
        with open(lang_cfg_path) as f:
            lang_cfg = json.load(f)

        tmpl_lower = tmpl_text.lower()
        for entry in lang_cfg["languages"]:
            code_lower = entry["code"].lower()
            name_lower = entry["name"].lower()
            script_lower = entry["script"].lower()
            self.assertNotIn(code_lower, tmpl_lower)
            self.assertNotIn(f" {name_lower} ", tmpl_lower)
            self.assertNotIn(f" {script_lower} ", tmpl_lower)

        # 2. Render prompt
        rendered = render_prompt(
            tmpl_text,
            query="Can you give an example of a life goal related to self-image?",
            codebook=cb,
            text="I practice exercise daily.",
        )

        # Rendered prompt must have single braces in the JSON format rule (no triple {{{ or quadrupled {{{{)
        self.assertIn('"themes": {"<theme_id>": {"present": true, "evidence": "<quote>"}, "<theme_id>": {"present": false, "evidence": ""}}, "other_note": "", "keywords": ["<keyword1>", "<keyword2>"]}', rendered)
        self.assertNotIn("{{{", rendered)
        self.assertNotIn("}}}", rendered)
        self.assertNotIn("{theme_lines}", rendered)
        self.assertNotIn("{query}", rendered)
        self.assertNotIn("{text}", rendered)

        # Must contain every theme id
        for t in cb["themes"]:
            self.assertIn(t["id"], rendered)

    def test_parse_tag_response(self):
        cb = {
            "themes": [
                {"id": "health", "label": "Health", "definition": "Body health"},
                {"id": "mind", "label": "Mind", "definition": "Mental health"},
                {"id": "skills", "label": "Skills", "definition": "Learning skills"},
            ]
        }

        # Valid JSON
        valid_raw = (
            '{\n'
            '  "themes": {\n'
            '    "health": {"present": true, "evidence": "I practice yoga"},\n'
            '    "mind": {"present": false, "evidence": ""},\n'
            '    "skills": {"present": false, "evidence": ""}\n'
            '  },\n'
            '  "other_note": "",\n'
            '  "keywords": ["yoga", "practice"]\n'
            '}'
        )
        parsed, note, err, kws = parse_tag_response(valid_raw, cb)
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        self.assertEqual(note, "")
        self.assertEqual(kws, ["yoga", "practice"])
        self.assertTrue(parsed["health"]["present"])
        self.assertEqual(parsed["health"]["evidence"], "I practice yoga")

        # Missing theme id
        missing_raw = '{"themes": {"health": {"present": true, "evidence": "e"}}, "other_note": ""}'
        parsed, _, err, _ = parse_tag_response(missing_raw, cb)
        self.assertIsNone(parsed)
        self.assertIn("missing themes", err)

        # Extra theme id
        extra_raw = (
            '{"themes": {"health": {"present": true, "evidence": "e"}, "mind": {"present": false, "evidence": ""}, '
            '"skills": {"present": false, "evidence": ""}, "extra_t": {"present": false, "evidence": ""}}, "other_note": ""}'
        )
        parsed, _, err, _ = parse_tag_response(extra_raw, cb)
        self.assertIsNone(parsed)
        self.assertIn("extra themes", err)

        # Non-boolean present
        bad_bool = '{"themes": {"health": {"present": "yes", "evidence": "e"}, "mind": {"present": false, "evidence": ""}, "skills": {"present": false, "evidence": ""}}, "other_note": ""}'
        parsed, _, err, _ = parse_tag_response(bad_bool, cb)
        self.assertIsNone(parsed)
        self.assertIn("boolean 'present'", err)

        # Non-string evidence
        bad_ev = '{"themes": {"health": {"present": true, "evidence": 123}, "mind": {"present": false, "evidence": ""}, "skills": {"present": false, "evidence": ""}}, "other_note": ""}'
        parsed, _, err, _ = parse_tag_response(bad_ev, cb)
        self.assertIsNone(parsed)
        self.assertIn("string 'evidence'", err)

        # Invalid JSON
        parsed, _, err, _ = parse_tag_response("not a json string", cb)
        self.assertIsNone(parsed)
        self.assertIn("JSON decode error", err)

    def test_evidence_verification(self):
        full_text = 'I practice "regular exercise" daily and meditation to improve my self-esteem.'

        # 1. Exact quote passes
        self.assertTrue(verify_evidence('"regular exercise"', full_text))

        # 2. Case and whitespace tolerance
        self.assertTrue(verify_evidence('  "REGULAR   EXERCISE"  ', full_text))

        # 3. Curly quotes against straight quotes
        curly_text = "I practice \u201cregular exercise\u201d daily."
        self.assertTrue(verify_evidence('"regular exercise"', curly_text))

        # 4. Leading / trailing ellipsis stripped and surrounding quotes stripped
        plain_text = 'I practice regular exercise and meditation daily to improve my self-esteem.'
        self.assertTrue(verify_evidence('...regular exercise and meditation...', plain_text))
        self.assertTrue(verify_evidence('"regular exercise and meditation"', plain_text))

        # 5. Paraphrase fails
        self.assertFalse(verify_evidence("working out regularly", full_text))

        # 6. Quote not in text fails
        self.assertFalse(verify_evidence("eating balanced diet", full_text))

        # 7. Empty evidence fails
        self.assertFalse(verify_evidence("", full_text))
        self.assertFalse(verify_evidence("   ", full_text))

        # 8. 41 words fails (> 40 limit)
        long_words = " ".join([f"word{i}" for i in range(41)])
        long_full = f"Start {long_words} end"
        self.assertFalse(verify_evidence(long_words, long_full))

        # 9. apply_verification helper
        themes_in = {
            "t1": {"present": True, "evidence": "regular exercise"},
            "t2": {"present": True, "evidence": "not found here"},
            "t3": {"present": False, "evidence": ""},
        }
        res = apply_verification(themes_in, full_text)
        self.assertTrue(res["t1"]["evidence_verified"])
        self.assertFalse(res["t2"]["evidence_verified"])
        self.assertFalse(res["t3"]["evidence_verified"])

    def test_tokens_and_candidates(self):
        # 1. Hyphenated words stay whole
        tokens = tokenize_segments("Self-esteem and well-being are key.")
        flat_tokens = [t for seg in tokens for t in seg]
        self.assertIn("self-esteem", flat_tokens)
        self.assertIn("well-being", flat_tokens)

        # 2. Bigrams do not cross punctuation (full stop, comma)
        # Text: "Good health, mental peace. Daily yoga."
        # Bigrams within segment 1: ("good health")
        # No bigrams like ("health mental")
        stopwords = {"are", "is", "and"}
        cands = candidate_terms("Good health, mental peace. Daily yoga.", stopwords)
        self.assertIn("good health", cands)
        self.assertIn("mental peace", cands)
        self.assertIn("daily yoga", cands)
        self.assertNotIn("health mental", cands)
        self.assertNotIn("peace daily", cands)

        # 3. Stopwords and query tokens excluded
        stopwords_file = PROJECT_ROOT / "config" / "stopwords_en.txt"
        sw = build_stopwords(stopwords_file, query_text="What is a good life goal?")
        self.assertIn("goal", sw)
        self.assertIn("life", sw)
        self.assertIn("good", sw)
        self.assertIn("what", sw)

        cands_sw = candidate_terms("A great life goal for health", sw)
        self.assertNotIn("life", cands_sw)
        self.assertNotIn("goal", cands_sw)
        self.assertIn("great", cands_sw)
        self.assertIn("health", cands_sw)
        self.assertNotIn("great life", cands_sw)  # bigram with stopword dropped

    def test_tfidf_scores_and_selection(self):
        # 3-document toy corpus:
        # Doc 0: ["yoga", "health"]
        # Doc 1: ["yoga", "mind"]
        # Doc 2: ["exercise", "health"]
        # N = 3
        # Term df:
        #   "yoga": df=2 -> idf = ln((1+3)/(1+2)) + 1 = ln(4/3) + 1 = 0.287682 + 1 = 1.287682
        #   "health": df=2 -> idf = ln((1+3)/(1+2)) + 1 = ln(4/3) + 1 = 1.287682
        #   "mind": df=1 -> idf = ln((1+3)/(1+1)) + 1 = ln(4/2) + 1 = ln(2) + 1 = 0.693147 + 1 = 1.693147
        #   "exercise": df=1 -> idf = ln(2) + 1 = 1.693147
        corpus = [
            ["yoga", "health"],
            ["yoga", "mind"],
            ["exercise", "health"],
        ]
        scores = tfidf_scores(corpus)
        self.assertEqual(len(scores), 3)

        expected_idf_mind = math.log(4.0 / 2.0) + 1.0
        expected_idf_yoga = math.log(4.0 / 3.0) + 1.0

        self.assertAlmostEqual(scores[1]["mind"], 1.0 * expected_idf_mind)
        self.assertAlmostEqual(scores[1]["yoga"], 1.0 * expected_idf_yoga)

        # De-duplication walk & tie-breaking
        # If bigram "daily yoga" has score 3.0, and unigram "yoga" has score 2.0, "yoga" must be dropped
        # Ties alphabetical: "apple" vs "banana" with same score
        scored_dict = {
            "daily yoga": 3.0,
            "yoga": 2.5,  # must be dropped because "yoga" is in "daily yoga"
            "daily": 2.0,  # must be dropped because "daily" is in "daily yoga"
            "banana": 1.5,
            "apple": 1.5,
            "meditation": 1.0,
        }
        selected = select_top_k(scored_dict, k=4)
        selected_terms = [t for t, s in selected]
        self.assertEqual(selected_terms, ["daily yoga", "apple", "banana", "meditation"])

    def test_theme_tables_and_metrics(self):
        # 5 languages: L1, L2, L3, L4, baseline 'en'
        # 3 themes: T1, T2, T3
        theme_ids = ["T1", "T2", "T3"]
        considered = ["L1", "L2", "L3", "L4"]  # non-en languages

        # Presence map:
        presence = {
            "L1": {"T1": True, "T2": False, "T3": False},
            "L2": {"T1": True, "T2": True, "T3": False},
            "L3": {"T1": False, "T2": True, "T3": False},
            "L4": {"T1": False, "T2": False, "T3": False},
            "en": {"T1": True, "T2": False, "T3": False},
        }
        claimed = {
            "L1": {"T1": True, "T2": False, "T3": False},
            "L2": {"T1": True, "T2": True, "T3": False},
            "L3": {"T1": False, "T2": True, "T3": True},  # claimed T3 but unverified
            "L4": {"T1": False, "T2": False, "T3": False},
            "en": {"T1": True, "T2": False, "T3": False},
        }

        # 1. Frequency rows
        freq_rows = build_theme_frequency_rows(theme_ids, presence, considered, baseline_code="en")
        self.assertEqual(len(freq_rows), 3)
        # T1: present in L1, L2 -> 2/4 = 0.5000, en_present = 1
        self.assertEqual(freq_rows[0][0], "T1")
        self.assertEqual(freq_rows[0][1], 4)
        self.assertEqual(freq_rows[0][2], 2)
        self.assertEqual(freq_rows[0][3], "0.5000")
        self.assertEqual(freq_rows[0][4], "1")
        # T3: present in 0/4 = 0.0000, en_present = 0
        self.assertEqual(freq_rows[2][2], 0)
        self.assertEqual(freq_rows[2][3], "0.0000")
        self.assertEqual(freq_rows[2][4], "0")

        # 2. Language vs English
        l_vs_en = build_language_vs_english_rows(presence, claimed, considered, baseline_code="en")
        # L1: themes={T1}, en={T1} -> Jaccard = 1/1 = 1.0000
        self.assertEqual(l_vs_en[0][0], "L1")
        self.assertEqual(l_vs_en[0][2], "1.0000")
        # L4: themes={}, en={T1} -> Jaccard = 0/1 = 0.0000
        self.assertEqual(l_vs_en[3][0], "L4")
        self.assertEqual(l_vs_en[3][2], "0.0000")
        # L3 verification rate: verified 1 (T2), claimed 2 (T2, T3) -> 1/2 = 0.5000
        self.assertEqual(l_vs_en[2][5], "0.5000")

        # 3. Group theme rates
        groups_cfg = {
            "families": {"G1": ["L1", "L2"], "G2": ["L3", "L4"]},
            "scripts": {"S1": ["L1", "L2", "L3"], "S2": ["L4"]},
        }
        grp_rows = build_group_theme_rates_rows(theme_ids, presence, groups_cfg, considered)
        # G1 on T1: L1(True), L2(True) -> 2/2 = 1.0000
        g1_t1 = [r for r in grp_rows if r[0] == "families" and r[1] == "G1" and r[2] == "T1"][0]
        self.assertEqual(g1_t1[5], "1.0000")

        # 4. Distinctive themes: threshold = 1
        # T1 present in 2 -> not rare
        # T2 present in 2 -> not rare
        # T3 present in 0 -> not rare_present (count > 0 required)
        # absent in <= 1:
        #   T1 absent in L3, L4 (2)
        #   T2 absent in L1, L4 (2)
        #   T3 absent in L1, L2, L3, L4 (4)
        dist_rows = build_distinctive_themes_rows(theme_ids, presence, considered, rare_threshold=2)
        # T1 present in 2 <= 2 -> rare_present
        # T2 present in 2 <= 2 -> rare_present
        types = [r[1] for r in dist_rows]
        self.assertIn("rare_present", types)

    def test_cohens_kappa_and_jaccard(self):
        # 1. Jaccard empty sets
        self.assertIsNone(jaccard(set(), set()))
        self.assertEqual(jaccard({"a"}, {"a"}), 1.0)
        self.assertEqual(jaccard({"a"}, {"b"}), 0.0)

        # 2. Cohen's kappa perfect agreement
        k_perf = cohens_kappa([1, 0, 1, 0], [1, 0, 1, 0])
        self.assertAlmostEqual(k_perf, 1.0)

        # 3. Hand-computed 2x2 example:
        # Rater A: [1, 1, 1, 1, 0, 0, 0, 0, 0, 0] (4 ones, 6 zeros)
        # Rater B: [1, 1, 1, 0, 1, 0, 0, 0, 0, 0] (4 ones, 6 zeros)
        # N = 10
        # Agreement: indices 0,1,2 (both 1), index 3 (diff), index 4 (diff), indices 5,6,7,8,9 (both 0)
        # Total agreement = 3 + 5 = 8 / 10 = 0.80
        # Marginals: A1=0.4, A0=0.6, B1=0.4, B0=0.6
        # Pe = (0.4 * 0.4) + (0.6 * 0.6) = 0.16 + 0.36 = 0.52
        # Kappa = (Po - Pe) / (1 - Pe) = (0.80 - 0.52) / (1 - 0.52) = 0.28 / 0.48 = 7/12 = 0.58333333333
        ra = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        rb = [1, 1, 1, 0, 1, 0, 0, 0, 0, 0]
        expected_kappa = 0.28 / 0.48
        self.assertAlmostEqual(cohens_kappa(ra, rb), expected_kappa)
        self.assertAlmostEqual(percent_agreement(ra, rb), 80.0)

        # 4. All labels same value -> undefined (Pe == 1.0) -> None
        self.assertIsNone(cohens_kappa([1, 1, 1], [1, 1, 1]))


if __name__ == "__main__":
    unittest.main()
