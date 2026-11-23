"""
src/theme_analyze.py — Phase 4: Analysis and Keyword Extraction.

Offline analysis script running in .venv-sim.
Reads data/analysis/themes_<query_id>/tags.json and data/raw/sarvam_<query_id>.json.
Computes theme frequency, cross-language comparisons, group rates, distinctive themes,
TF-IDF keywords, and KeyBERT-style (MiniLM) embedding keywords.

Writes all CSVs, summary.json, and report.md to data/analysis/themes_<query_id>/
(or custom --out-dir).
"""

import argparse
import csv
import datetime
import json
import math
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.auto_document import KNOWN_BACKTRANSLATION_LIMITS
from src.similarity_core import (
    canonical_order,
    cosine_matrix,
    load_records,
    normalize_text,
    reliable,
    sha256_file,
    usable,
)
from src.theme_core import (
    build_distinctive_themes_rows,
    build_group_theme_rates_rows,
    build_keyword_df_rows,
    build_keyword_overlap_rows,
    build_language_vs_english_rows,
    build_stopwords,
    build_theme_frequency_rows,
    candidate_terms,
    load_codebook,
    select_top_k,
    tfidf_scores,
)

LIMITATIONS_TEXT = """## Limitations

1. Themes are tagged on English back-translations, not on the original-language text. Back-translation errors can add or remove themes; known problem records are listed, and the reliable view leaves them out.
2. The tagger is a language model. Requiring a verbatim evidence quote shows the quote exists in the text, not that the label is correct. The tagger model and whether it is the same model that wrote the answers are recorded in this report.
3. The codebook is a human-designed draft for this query. Ideas outside it appear only in the short "other_note" field.
4. Each language has one generated answer per query (one sample), so differences between languages cannot be separated from ordinary sampling variation.
5. Group sizes are small, and several groups have one to four languages. Rates are descriptive only and no significance tests are reported.
6. Keyword overlap reflects wording. Different back-translation phrasing lowers overlap even when the meaning is the same. Embedding-ranked keywords are ranked by similarity to the whole answer and are not a topic model.
7. All keyword analysis is on English back-translations; no native-script keywords are extracted.
8. These results describe one model on one query and do not generalize.
"""


def write_csv(path: Path, header: List[str], rows: List[List[Any]]) -> None:
    """Write rows to UTF-8 CSV with header, formatting None/NaN as empty string."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            formatted_row = []
            for val in row:
                if val is None:
                    formatted_row.append("")
                elif isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    formatted_row.append("")
                else:
                    formatted_row.append(str(val))
            writer.writerow(formatted_row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Theme analysis and keyword extraction (Phase 4).")
    parser.add_argument("--query-id", default="self_image_life_goal", help="Query ID to analyze")
    parser.add_argument("--top-k", type=int, default=10, help="Top K keywords per document (default: 10)")
    parser.add_argument("--rare-threshold", type=int, default=2, help="Threshold for rare themes (default: 2)")
    parser.add_argument("--no-embed-keywords", action="store_true", help="Skip embedding-based keywords")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size for embedding encoder")
    parser.add_argument("--models-dir", default=str(PROJECT_ROOT / "models"), help="Path to models folder")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "data" / "analysis"), help="Output directory")

    args = parser.parse_args()
    query_id = args.query_id
    out_dir = Path(args.out_dir).resolve()

    # Safety checks on paths per Rule R1 / R5
    data_raw_dir = (PROJECT_ROOT / "data" / "raw").resolve()
    sim_dir = (PROJECT_ROOT / "data" / "analysis" / "similarity_").resolve()

    if out_dir == data_raw_dir or str(out_dir).startswith(str(data_raw_dir) + os.sep):
        sys.exit(f"ERROR: Refusing to write inside data/raw: {out_dir}")
    if str(out_dir).startswith(str(sim_dir)):
        sys.exit(f"ERROR: Refusing to write inside similarity analysis folders: {out_dir}")

    # Dataset path & hash check
    dataset_path = PROJECT_ROOT / "data" / "raw" / f"sarvam_{query_id}.json"
    if not dataset_path.exists():
        sys.exit(f"ERROR: Dataset not found: {dataset_path}")
    initial_dataset_hash = sha256_file(dataset_path)

    # Codebook path
    codebook_path = PROJECT_ROOT / "config" / "codebooks" / f"{query_id}.json"
    if not codebook_path.exists():
        sys.exit(f"ERROR: Codebook not found: {codebook_path}")
    codebook = load_codebook(codebook_path)
    current_codebook_hash = sha256_file(codebook_path)
    theme_ids = [t["id"] for t in codebook["themes"]]

    # Languages config & grouping config
    lang_cfg_path = PROJECT_ROOT / "config" / "languages.json"
    groups_cfg_path = PROJECT_ROOT / "config" / "language_groups.json"
    if not lang_cfg_path.exists() or not groups_cfg_path.exists():
        sys.exit("ERROR: Missing language or group configuration files.")

    with open(lang_cfg_path, "r", encoding="utf-8") as f:
        langs_info = json.load(f)["languages"]
    ordered_22_codes = [e["code"] for e in langs_info]

    with open(groups_cfg_path, "r", encoding="utf-8") as f:
        groups_cfg = json.load(f)

    # Tags path
    default_tags_path = PROJECT_ROOT / "data" / "analysis" / f"themes_{query_id}" / "tags.json"
    if not default_tags_path.exists():
        sys.exit(f"ERROR: tags.json not found at {default_tags_path}. Run Phase 3 first.")

    with open(default_tags_path, "r", encoding="utf-8") as f:
        tags_data = json.load(f)

    tags_meta = tags_data.get("meta", {})
    recorded_ds_hash = tags_meta.get("dataset_sha256")
    recorded_cb_hash = tags_meta.get("codebook_sha256")

    if recorded_ds_hash != initial_dataset_hash:
        sys.exit(
            f"ERROR: tags.json dataset hash ({recorded_ds_hash}) does not match "
            f"current dataset file hash ({initial_dataset_hash})"
        )
    if recorded_cb_hash != current_codebook_hash:
        sys.exit(
            f"ERROR: tags.json codebook hash ({recorded_cb_hash}) does not match "
            f"current codebook file hash ({current_codebook_hash})"
        )

    # Output directory for query
    analysis_dir = out_dir if out_dir.name == f"themes_{query_id}" else out_dir / f"themes_{query_id}"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # If writing to a different out-dir, copy tags.json across
    target_tags_path = analysis_dir / "tags.json"
    if target_tags_path.resolve() != default_tags_path.resolve():
        shutil.copy2(default_tags_path, target_tags_path)

    # Load dataset records
    raw_records = load_records(dataset_path)
    records_by_code = {r["target_lang_code"]: r for r in raw_records}
    all_codes = canonical_order(lang_cfg_path)

    source_query_en = raw_records[0].get("source_query_en", "")

    # Parse tag statuses and presences
    tag_records = tags_data.get("records", {})
    verified_presence: Dict[str, Dict[str, bool]] = {}
    claimed_presence: Dict[str, Dict[str, bool]] = {}

    ok_codes: Set[str] = set()
    failed_codes: Dict[str, str] = {}
    skipped_codes: Dict[str, str] = {}

    total_claimed_count = 0
    total_verified_count = 0

    for code in all_codes:
        trec = tag_records.get(code)
        if not trec:
            skipped_codes[code] = "not_found_in_tags"
            continue
        status = trec.get("status")
        if status == "ok":
            ok_codes.add(code)
            themes_dict = trec.get("themes", {})
            v_dict: Dict[str, bool] = {}
            c_dict: Dict[str, bool] = {}
            for tid in theme_ids:
                tinfo = themes_dict.get(tid, {})
                c_pres = bool(tinfo.get("present", False))
                v_pres = bool(tinfo.get("evidence_verified", False)) and c_pres
                c_dict[tid] = c_pres
                v_dict[tid] = v_pres
                if c_pres:
                    total_claimed_count += 1
                if v_pres:
                    total_verified_count += 1
            verified_presence[code] = v_dict
            claimed_presence[code] = c_dict
        elif status == "skipped_unusable":
            skipped_codes[code] = "skipped_unusable"
        else:
            failed_codes[code] = str(status)

    overall_verification_rate = (
        (total_verified_count / total_claimed_count) if total_claimed_count > 0 else 1.0
    )

    # Determine views for the 22 languages
    # View 'all': ok in tagging and usable in English
    considered_all = [
        code for code in ordered_22_codes
        if code in ok_codes and usable(records_by_code.get(code, {}), "english")
    ]
    # View 'reliable': ok in tagging and reliable in English view
    considered_reliable = [
        code for code in ordered_22_codes
        if code in ok_codes and reliable(records_by_code.get(code, {}), "english", KNOWN_BACKTRANSLATION_LIMITS)
    ]

    # Excluded records list and reasons
    excluded_all = [
        {"code": c, "reason": skipped_codes.get(c) or failed_codes.get(c) or "unusable_english"}
        for c in ordered_22_codes if c not in considered_all
    ]
    excluded_reliable = [
        {"code": c, "reason": skipped_codes.get(c) or failed_codes.get(c) or "unreliable_english"}
        for c in ordered_22_codes if c not in considered_reliable
    ]

    # -------------------------------------------------------------------------
    # 1. Theme Matrices (23 rows x theme columns)
    # -------------------------------------------------------------------------
    for kind, pres_dict, fname in [
        ("verified", verified_presence, "theme_matrix_verified.csv"),
        ("claimed", claimed_presence, "theme_matrix_claimed.csv"),
    ]:
        matrix_rows = []
        for code in all_codes:
            if code in pres_dict:
                row = [code] + [1 if pres_dict[code].get(tid, False) else 0 for tid in theme_ids]
            else:
                row = [code] + ["" for _ in theme_ids]
            matrix_rows.append(row)
        write_csv(analysis_dir / fname, ["code"] + theme_ids, matrix_rows)

    # -------------------------------------------------------------------------
    # 2. Theme Frequency, Language vs English, Groups, Distinctive
    # -------------------------------------------------------------------------
    # theme_frequency.csv
    # We produce frequency table for both views or primary 'reliable' with view column
    # Section 3.7: Each is computed for views 'all' and 'reliable'
    tf_header = ["view", "theme_id", "n_considered", "n_present", "proportion", "en_present", "languages_present"]
    tf_rows = []
    for view_name, cons in [("all", considered_all), ("reliable", considered_reliable)]:
        rows = build_theme_frequency_rows(theme_ids, verified_presence, cons, baseline_code="en")
        for r in rows:
            tf_rows.append([view_name] + r)
    write_csv(analysis_dir / "theme_frequency.csv", tf_header, tf_rows)

    # language_vs_english.csv
    lve_header = ["view", "code", "n_themes", "jaccard_with_en", "themes_in_lang_not_en", "themes_in_en_not_lang", "verification_rate"]
    lve_rows = []
    for view_name, cons in [("all", considered_all), ("reliable", considered_reliable)]:
        rows = build_language_vs_english_rows(verified_presence, claimed_presence, cons, baseline_code="en")
        for r in rows:
            lve_rows.append([view_name] + r)
    write_csv(analysis_dir / "language_vs_english.csv", lve_header, lve_rows)

    # group_theme_rates.csv
    gtr_header = ["view", "grouping", "group", "theme", "n", "n_present", "rate"]
    gtr_rows = []
    for view_name, cons in [("all", considered_all), ("reliable", considered_reliable)]:
        rows = build_group_theme_rates_rows(theme_ids, verified_presence, groups_cfg, cons)
        for r in rows:
            gtr_rows.append([view_name] + r)
    write_csv(analysis_dir / "group_theme_rates.csv", gtr_header, gtr_rows)

    # distinctive_themes.csv
    dt_header = ["view", "theme", "type", "count", "languages"]
    dt_rows = []
    for view_name, cons in [("all", considered_all), ("reliable", considered_reliable)]:
        rows = build_distinctive_themes_rows(theme_ids, verified_presence, cons, rare_threshold=args.rare_threshold)
        for r in rows:
            dt_rows.append([view_name] + r)
    write_csv(analysis_dir / "distinctive_themes.csv", dt_header, dt_rows)

    # -------------------------------------------------------------------------
    # 3. Keyword Extraction (TF-IDF & MiniLM)
    # -------------------------------------------------------------------------
    stopwords = build_stopwords(PROJECT_ROOT / "config" / "stopwords_en.txt", source_query_en)
    stopwords_list = sorted(stopwords)

    # Documents per usable code (including en)
    doc_text_by_code: Dict[str, str] = {}
    for code, rec in records_by_code.items():
        if usable(rec, "english"):
            doc_text_by_code[code] = normalize_text(rec.get("back_translated_answer_en", ""))

    # Pre-extract candidate terms per document
    candidates_by_code: Dict[str, List[str]] = {
        code: candidate_terms(text, stopwords)
        for code, text in doc_text_by_code.items()
    }

    # TF-IDF scores
    # Corpus: all usable documents
    ordered_doc_codes = list(candidates_by_code.keys())
    docs_terms_list = [candidates_by_code[c] for c in ordered_doc_codes]
    tfidf_scores_list = tfidf_scores(docs_terms_list)
    tfidf_scored_by_code: Dict[str, Dict[str, float]] = {
        code: sc for code, sc in zip(ordered_doc_codes, tfidf_scores_list)
    }

    # Embedding KeyBERT-style scores (optional)
    embed_scored_by_code: Dict[str, Dict[str, float]] = {}
    if not args.no_embed_keywords:
        print("[Embedding] Loading MiniLM encoder for keyword extraction...")
        from src.similarity_embed import load_encoder, release_encoder
        encoder = load_encoder("minilm", models_dir=Path(args.models_dir))

        # Encode documents and candidate terms
        try:
            for code, text in doc_text_by_code.items():
                cands = candidates_by_code.get(code, [])
                if not cands or not text.strip():
                    embed_scored_by_code[code] = {}
                    continue

                # Encode doc and candidates
                doc_emb = encoder.encode([text], batch_size=1, show_progress_bar=False, normalize_embeddings=True)[0]
                cand_embs = encoder.encode(cands, batch_size=args.batch_size, show_progress_bar=False, normalize_embeddings=True)

                scores_dict: Dict[str, float] = {}
                for term, cand_emb in zip(cands, cand_embs):
                    sim = float(np.dot(doc_emb, cand_emb))
                    scores_dict[term] = sim
                embed_scored_by_code[code] = scores_dict
        finally:
            release_encoder(encoder)

    # Build keywords_per_language.csv
    # Columns: code, method, view, rank, keyword, score
    kw_per_lang_rows = []
    # For cross-language tables, collect top-k sets per view and method:
    # terms_by_lang_and_method: (view, method) -> dict[lang_code, set[term]]
    top_terms: Dict[Tuple[str, str], Dict[str, Set[str]]] = {}

    methods = [("tfidf", tfidf_scored_by_code)]
    if not args.no_embed_keywords:
        methods.append(("minilm", embed_scored_by_code))

    for view_name, cons in [("all", considered_all), ("reliable", considered_reliable)]:
        eval_codes = ["en"] + cons
        for method_name, scores_map in methods:
            lang_dict: Dict[str, Set[str]] = {}
            for code in eval_codes:
                scored = scores_map.get(code, {})
                selected = select_top_k(scored, args.top_k)
                lang_dict[code] = {term for term, _ in selected}
                for rank, (term, score) in enumerate(selected, start=1):
                    kw_per_lang_rows.append([
                        code, method_name, view_name, rank, term, f"{score:.4f}"
                    ])
            top_terms[(view_name, method_name)] = lang_dict

    write_csv(
        analysis_dir / "keywords_per_language.csv",
        ["code", "method", "view", "rank", "keyword", "score"],
        kw_per_lang_rows,
    )

    # keyword_df.csv
    # Columns: view, method, term, n_languages, languages, in_en, class
    kw_df_rows = []
    for (view_name, method_name), lang_dict in top_terms.items():
        cons = considered_all if view_name == "all" else considered_reliable
        k_rows = build_keyword_df_rows(lang_dict, cons, baseline_code="en")
        for r in k_rows:
            kw_df_rows.append([view_name, method_name] + r)
    write_csv(
        analysis_dir / "keyword_df.csv",
        ["view", "method", "term", "n_languages", "languages", "in_en", "class"],
        kw_df_rows,
    )

    # keyword_overlap_with_en.csv
    # Columns: view, method, code, jaccard_with_en, shared_terms
    kw_overlap_rows = []
    for (view_name, method_name), lang_dict in top_terms.items():
        cons = considered_all if view_name == "all" else considered_reliable
        k_rows = build_keyword_overlap_rows(lang_dict, cons, baseline_code="en")
        for r in k_rows:
            kw_overlap_rows.append([view_name, method_name] + r)
    write_csv(
        analysis_dir / "keyword_overlap_with_en.csv",
        ["view", "method", "code", "jaccard_with_en", "shared_terms"],
        kw_overlap_rows,
    )

    # -------------------------------------------------------------------------
    # 4. Summary JSON
    # -------------------------------------------------------------------------
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    import sklearn
    summary_data = {
        "query_id": query_id,
        "dataset_sha256": initial_dataset_hash,
        "codebook_path": str(codebook_path.relative_to(PROJECT_ROOT)),
        "codebook_sha256": current_codebook_hash,
        "prompt_template_path": tags_meta.get("prompt_template_path"),
        "prompt_template_sha256": tags_meta.get("prompt_template_sha256"),
        "tagger_model": tags_meta.get("tagger_model"),
        "tagger_digest": tags_meta.get("tagger_digest"),
        "tagger_is_generator": tags_meta.get("tagger_is_generator", False),
        "options": tags_meta.get("options", {}),
        "library_versions": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "sklearn": sklearn.__version__,
        },
        "counts": {
            "total_records": len(all_codes),
            "ok": len(ok_codes),
            "failed": len(failed_codes),
            "skipped": len(skipped_codes),
            "considered_all": len(considered_all),
            "considered_reliable": len(considered_reliable),
        },
        "exclusions": {
            "all_view": excluded_all,
            "reliable_view": excluded_reliable,
        },
        "overall_verification_rate": round(overall_verification_rate, 4),
        "parameters": {
            "top_k": args.top_k,
            "rare_threshold": args.rare_threshold,
            "embed_keywords": not args.no_embed_keywords,
        },
        "stopwords_count": len(stopwords_list),
        "stopwords_used": stopwords_list,
        "timestamp_utc": now_utc,
    }

    with open(analysis_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # 5. Report Markdown
    # -------------------------------------------------------------------------
    report_lines = [
        f"# Theme Coding and Keyword Extraction Report — `{query_id}`",
        "",
        f"- **Tagger Model**: `{tags_meta.get('tagger_model')}` (digest: `{tags_meta.get('tagger_digest')}`)",
        f"- **Self-Grading**: `{'YES (Generator == Tagger)' if tags_meta.get('tagger_is_generator') else 'NO (Independent Tagger)'}`",
        f"- **Generated At**: {now_utc}",
        f"- **Records Analyzed**: {len(ok_codes)} / {len(all_codes)} (Reliable view: {len(considered_reliable)} / 22 languages)",
        f"- **Overall Verification Rate**: {overall_verification_rate:.2%}",
        "",
        "## 1. Theme Frequency (Reliable View)",
        "",
        "| Theme ID | Considered | Present | Proportion | In English | Languages |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    # Add reliable frequency rows
    rel_freq = build_theme_frequency_rows(theme_ids, verified_presence, considered_reliable, baseline_code="en")
    for r in rel_freq:
        report_lines.append(f"| `{r[0]}` | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")

    report_lines.extend([
        "",
        "## 2. Language versus English (Reliable View)",
        "",
        "| Language | Themes Count | Jaccard with EN | Only in Language | Only in English | Verification Rate |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    rel_lve = build_language_vs_english_rows(verified_presence, claimed_presence, considered_reliable, baseline_code="en")
    for r in rel_lve:
        report_lines.append(f"| `{r[0]}` | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")

    report_lines.extend([
        "",
        "## 3. Distinctive Themes (Reliable View)",
        "",
        "| Theme | Type | Count | Languages |",
        "| --- | --- | --- | --- |",
    ])
    rel_dt = build_distinctive_themes_rows(theme_ids, verified_presence, considered_reliable, rare_threshold=args.rare_threshold)
    for r in rel_dt:
        report_lines.append(f"| `{r[0]}` | `{r[1]}` | {r[2]} | {r[3]} |")

    report_lines.extend([
        "",
        "## 4. Top Shared Keywords (Reliable View)",
        "",
        "| Method | Term | Languages Count | In English | Class |",
        "| --- | --- | --- | --- | --- |",
    ])
    for method_name in (["tfidf", "minilm"] if not args.no_embed_keywords else ["tfidf"]):
        lang_dict = top_terms.get(("reliable", method_name), {})
        df_rows = build_keyword_df_rows(lang_dict, considered_reliable, baseline_code="en")
        for r in df_rows:
            if r[4] == "shared":
                report_lines.append(f"| `{method_name}` | `{r[0]}` | {r[1]} | {r[3]} | `{r[4]}` |")

    report_lines.extend([
        "",
        LIMITATIONS_TEXT,
    ])

    with open(analysis_dir / "report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    # Final dataset hash check per Rule R5
    final_dataset_hash = sha256_file(dataset_path)
    if initial_dataset_hash != final_dataset_hash:
        sys.exit(f"CRITICAL ERROR: Dataset modified during analysis! {initial_dataset_hash} != {final_dataset_hash}")

    print(f"Analysis completed successfully. Outputs written to {analysis_dir}")


if __name__ == "__main__":
    main()
