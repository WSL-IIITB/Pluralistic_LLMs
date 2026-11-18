"""
Cross-Lingual Similarity Analysis CLI.

Computes semantic similarity across the 22 Indic languages and against the
English baseline for generated answers, in both Native (LaBSE) and English
(all-MiniLM-L6-v2) embedding spaces.

Usage:
  .venv-sim/bin/python -m src.analyze_similarity --query-id <id> [--batch-size 8]
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
from src.similarity_embed import (
    encode_texts,
    get_peak_memory_mb,
    load_encoder,
    release_encoder,
)

# Import KNOWN_BACKTRANSLATION_LIMITS dynamically from src.auto_document
try:
    from src.auto_document import KNOWN_BACKTRANSLATION_LIMITS
except Exception as e:
    raise ImportError(
        f"Failed to import KNOWN_BACKTRANSLATION_LIMITS from src.auto_document: {e}"
    )

CAVEATS_TEXT = """## Limitations & Caveats

1. LaBSE is trained mainly on translation pairs and is documented as weaker for similarity between sentence pairs that are not translations of each other. The answers here are independent generations, so native-space similarity should be read with that in mind.
2. English-space similarity depends on back-translation. Back-translation errors can create apparent divergence; known broken cases (for example `mni-IN`, and cases flagged by the back-translation validator) are listed.
3. Each language has one generated answer (one sample at one temperature). Differences between languages cannot be separated from ordinary sampling variation without repeated samples.
4. Encoder coverage of Bodo, Dogri, Kashmiri, Manipuri and Santali is unverified or limited; the alignment probe result is shown for each language.
5. The family and script groupings are small (several groups have 1 to 4 languages), so group means are descriptive only.
6. Sindhi may be answered in Devanagari while its config script is Perso-Arabic; its script-group placement follows the config.
7. A single query's result says nothing general about the model.
"""


def write_csv(path: Path, header: List[str], rows: List[List[Any]]) -> None:
    """Write UTF-8 CSV with given header and rows."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def run_alignment_probe(
    labse_model,
    query_id: str,
    records: Dict[str, Dict[str, Any]],
    lang_order: List[str],
    raw_dir: Path,
) -> Dict[str, str]:
    """
    Compute alignment probe for LaBSE across the 22 Indic languages:
    pos = cosine(LaBSE(source_query_en of query A), LaBSE(translated_query of L in query A))
    neg = cosine(LaBSE(source_query_en of query A), LaBSE(translated_query of L in dataset B))
    Returns {lang_code: "PASS" | "FAIL" | "unavailable"}
    """
    # Find other datasets in raw_dir
    other_files = [
        f
        for f in raw_dir.glob("sarvam_*.json")
        if f.name != f"sarvam_{query_id}.json"
    ]
    if not other_files:
        return {
            code: "unavailable (no other dataset)"
            for code in lang_order
            if code != "en"
        }

    # Load other datasets
    other_records_list = []
    for of in other_files:
        try:
            recs = {r["target_lang_code"]: r for r in load_records(of)}
            other_records_list.append(recs)
        except Exception:
            pass

    if not other_records_list:
        return {
            code: "unavailable (failed to load other datasets)"
            for code in lang_order
            if code != "en"
        }

    # Encode source_query_en
    src_en = records["en"].get("source_query_en", "")
    src_emb, _ = encode_texts(labse_model, [src_en])
    src_vec = src_emb[0]

    probe_results = {}
    for code in lang_order:
        if code == "en":
            continue
        trans_a = records.get(code, {}).get("translated_query", "")
        # Get translations from other datasets
        other_trans = [
            orecs.get(code, {}).get("translated_query", "")
            for orecs in other_records_list
            if orecs.get(code, {}).get("translated_query")
        ]

        if not trans_a or not other_trans:
            probe_results[code] = "unavailable"
            continue

        all_trans = [trans_a] + other_trans
        embs, _ = encode_texts(labse_model, all_trans)

        pos_sim = float(np.dot(src_vec, embs[0]))
        neg_sims = [float(np.dot(src_vec, e)) for e in embs[1:]]
        max_neg = max(neg_sims) if neg_sims else -1.0

        probe_results[code] = "PASS" if pos_sim > max_neg else "FAIL"

    return probe_results


def analyze_query(
    query_id: str,
    batch_size: int = 8,
    models_dir: Optional[Path] = None,
    out_dir_base: Optional[Path] = None,
    no_plots: bool = False,
) -> Dict[str, Any]:
    dataset_path = PROJECT_ROOT / "data" / "raw" / f"sarvam_{query_id}.json"
    if not dataset_path.exists():
        sys.exit(f"Error: Dataset file not found at {dataset_path}")

    # 1. SHA-256 at start
    sha_start = sha256_file(dataset_path)

    # Output directory check
    base_out = out_dir_base or (PROJECT_ROOT / "data" / "analysis")
    out_dir = base_out / f"similarity_{query_id}"
    raw_dir_resolved = (PROJECT_ROOT / "data" / "raw").resolve()
    if raw_dir_resolved in out_dir.resolve().parents or out_dir.resolve() == raw_dir_resolved:
        sys.exit(f"Error: Refusing output directory inside data/raw: {out_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # 2. Load records and configs
    records_list = load_records(dataset_path)
    records_by_code = {r["target_lang_code"]: r for r in records_list}

    languages_cfg_path = PROJECT_ROOT / "config" / "languages.json"
    order = canonical_order(languages_cfg_path)

    # Read language names and groups
    with open(languages_cfg_path, "r", encoding="utf-8") as f:
        lang_cfg_data = json.load(f)
    code_to_name = {entry["code"]: entry["name"] for entry in lang_cfg_data["languages"]}
    code_to_name["en"] = "English"

    groups_cfg_path = PROJECT_ROOT / "config" / "language_groups.json"
    with open(groups_cfg_path, "r", encoding="utf-8") as f:
        groups_cfg = json.load(f)

    # Build code to family & script mapping
    code_to_family = {}
    for fam, mems in groups_cfg.get("families", {}).items():
        for m in mems:
            code_to_family[m] = fam
    code_to_family["en"] = "N/A"

    code_to_script = {}
    for sc, mems in groups_cfg.get("scripts", {}).items():
        for m in mems:
            code_to_script[m] = sc
    code_to_script["en"] = "Latin"

    # Build usable masks and reliability sets
    usable_native = np.zeros(len(order), dtype=bool)
    usable_english = np.zeros(len(order), dtype=bool)
    reliable_native = np.zeros(len(order), dtype=bool)
    reliable_english = np.zeros(len(order), dtype=bool)

    reasons_native: Dict[str, List[str]] = {}
    reasons_english: Dict[str, List[str]] = {}

    for idx, code in enumerate(order):
        rec = records_by_code.get(code)
        if not rec:
            reasons_native[code] = ["missing_record"]
            reasons_english[code] = ["missing_record"]
            continue

        # Usable
        u_nat = usable(rec, "native")
        u_eng = usable(rec, "english")
        usable_native[idx] = u_nat
        usable_english[idx] = u_eng

        # Reliable
        r_nat, r_nat_reasons = reliable(rec, "native", KNOWN_BACKTRANSLATION_LIMITS)
        r_eng, r_eng_reasons = reliable(rec, "english", KNOWN_BACKTRANSLATION_LIMITS)
        reliable_native[idx] = r_nat
        reliable_english[idx] = r_eng

        if not r_nat:
            reasons_native[code] = r_nat_reasons
        if not r_eng:
            reasons_english[code] = r_eng_reasons

    # Check baseline usability
    en_idx = order.index("en")
    if not usable_native[en_idx]:
        sys.exit(f"Error: English baseline 'en' is unusable in native space!")
    if not usable_english[en_idx]:
        sys.exit(f"Error: English baseline 'en' is unusable in English space!")

    # 3. Embeddings: Native Space (LaBSE)
    print(f"\n--- Processing Native Space (LaBSE) ---")
    labse = load_encoder("labse", models_dir)
    native_texts = [
        normalize_text(records_by_code[c].get("native_answer", ""))
        if usable_native[i] else ""
        for i, c in enumerate(order)
    ]
    emb_native, trunc_native = encode_texts(labse, native_texts, batch_size=batch_size)

    # Alignment probe
    print("Running alignment probe on 22 languages...")
    probe_results = run_alignment_probe(
        labse, query_id, records_by_code, order, PROJECT_ROOT / "data" / "raw"
    )

    release_encoder(labse)
    del labse

    # 4. Embeddings: English Space (all-MiniLM-L6-v2)
    print(f"\n--- Processing English Space (all-MiniLM-L6-v2) ---")
    minilm = load_encoder("minilm", models_dir)
    english_texts = [
        normalize_text(records_by_code[c].get("back_translated_answer_en", ""))
        if usable_english[i] else ""
        for i, c in enumerate(order)
    ]
    emb_english, trunc_english = encode_texts(minilm, english_texts, batch_size=batch_size)

    release_encoder(minilm)
    del minilm

    # 5. Compute Matrices
    matrix_native = cosine_matrix(emb_native, usable_native)
    matrix_english = cosine_matrix(emb_english, usable_english)

    # Metrics
    sim_en_native = sim_to_baseline(matrix_native, order, baseline="en")
    sim_en_english = sim_to_baseline(matrix_english, order, baseline="en")

    mean_others_native = mean_sim_to_others(matrix_native, order, exclude=("en",))
    mean_others_english = mean_sim_to_others(matrix_english, order, exclude=("en",))

    # Cross-space agreement (Spearman)
    # All view
    nat_vec_all = [sim_en_native[c] for c in order if c != "en"]
    eng_vec_all = [sim_en_english[c] for c in order if c != "en"]
    spearman_all = spearman(nat_vec_all, eng_vec_all)

    # Reliable view
    nat_vec_rel = [
        sim_en_native[c] if (reliable_native[order.index(c)] and reliable_english[order.index(c)]) else None
        for c in order if c != "en"
    ]
    eng_vec_rel = [
        sim_en_english[c] if (reliable_native[order.index(c)] and reliable_english[order.index(c)]) else None
        for c in order if c != "en"
    ]
    spearman_rel = spearman(nat_vec_rel, eng_vec_rel)

    # 6. Group Statistics
    groups_data = []
    # Native - All
    for g in group_stats(matrix_native, order, groups_cfg["families"]):
        groups_data.append(["all", "native", "families", g["group"], g["n"], g["mean_sim_to_en"], g["std"], g["min"], g["max"], g["within_mean"], g["between_mean"]])
    for g in group_stats(matrix_native, order, groups_cfg["scripts"]):
        groups_data.append(["all", "native", "scripts", g["group"], g["n"], g["mean_sim_to_en"], g["std"], g["min"], g["max"], g["within_mean"], g["between_mean"]])

    # English - All
    for g in group_stats(matrix_english, order, groups_cfg["families"]):
        groups_data.append(["all", "english", "families", g["group"], g["n"], g["mean_sim_to_en"], g["std"], g["min"], g["max"], g["within_mean"], g["between_mean"]])
    for g in group_stats(matrix_english, order, groups_cfg["scripts"]):
        groups_data.append(["all", "english", "scripts", g["group"], g["n"], g["mean_sim_to_en"], g["std"], g["min"], g["max"], g["within_mean"], g["between_mean"]])

    # Masked matrices for Reliable view
    matrix_native_rel = cosine_matrix(emb_native, reliable_native)
    matrix_english_rel = cosine_matrix(emb_english, reliable_english)

    # Native - Reliable
    for g in group_stats(matrix_native_rel, order, groups_cfg["families"]):
        groups_data.append(["reliable", "native", "families", g["group"], g["n"], g["mean_sim_to_en"], g["std"], g["min"], g["max"], g["within_mean"], g["between_mean"]])
    for g in group_stats(matrix_native_rel, order, groups_cfg["scripts"]):
        groups_data.append(["reliable", "native", "scripts", g["group"], g["n"], g["mean_sim_to_en"], g["std"], g["min"], g["max"], g["within_mean"], g["between_mean"]])

    # English - Reliable
    for g in group_stats(matrix_english_rel, order, groups_cfg["families"]):
        groups_data.append(["reliable", "english", "families", g["group"], g["n"], g["mean_sim_to_en"], g["std"], g["min"], g["max"], g["within_mean"], g["between_mean"]])
    for g in group_stats(matrix_english_rel, order, groups_cfg["scripts"]):
        groups_data.append(["reliable", "english", "scripts", g["group"], g["n"], g["mean_sim_to_en"], g["std"], g["min"], g["max"], g["within_mean"], g["between_mean"]])

    # 7. Write Outputs
    # a. npy and index
    np.save(out_dir / "embeddings_native.npy", emb_native)
    np.save(out_dir / "embeddings_english.npy", emb_english)
    with open(out_dir / "embedding_index.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "order": order,
                "usable_native": usable_native.tolist(),
                "usable_english": usable_english.tolist(),
                "reliable_native": reliable_native.tolist(),
                "reliable_english": reliable_english.tolist(),
            },
            f,
            indent=2,
        )

    # b. Matrices CSV
    def dump_matrix_csv(path: Path, mat: np.ndarray):
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([""] + order)
            for r_idx, code in enumerate(order):
                row = [code]
                for c_idx in range(len(order)):
                    v = mat[r_idx, c_idx]
                    row.append("" if np.isnan(v) else f"{v:.6f}")
                writer.writerow(row)

    dump_matrix_csv(out_dir / "matrix_native.csv", matrix_native)
    dump_matrix_csv(out_dir / "matrix_english.csv", matrix_english)

    # c. per_language.csv
    per_lang_rows = []
    for idx, code in enumerate(order):
        per_lang_rows.append([
            code,
            code_to_name.get(code, code),
            code_to_family.get(code, ""),
            code_to_script.get(code, ""),
            bool(usable_native[idx]),
            bool(usable_english[idx]),
            bool(reliable_native[idx]),
            bool(reliable_english[idx]),
            f"{sim_en_native[code]:.6f}" if sim_en_native.get(code) is not None else "",
            f"{sim_en_english[code]:.6f}" if sim_en_english.get(code) is not None else "",
            f"{mean_others_native[code]:.6f}" if mean_others_native.get(code) is not None else "",
            f"{mean_others_english[code]:.6f}" if mean_others_english.get(code) is not None else "",
            bool(trunc_native[idx]),
            bool(trunc_english[idx]),
            probe_results.get(code, ""),
        ])

    per_lang_header = [
        "code", "name", "family", "script_group",
        "usable_native", "usable_english",
        "in_reliable_native", "in_reliable_english",
        "sim_to_en_native", "sim_to_en_english",
        "mean_sim_to_others_native", "mean_sim_to_others_english",
        "truncated_native", "truncated_english",
        "probe_pass"
    ]
    write_csv(out_dir / "per_language.csv", per_lang_header, per_lang_rows)

    # d. groups.csv
    groups_header = ["view", "space", "grouping", "group", "n", "mean_sim_to_en", "std", "min", "max", "within_mean", "between_mean"]
    groups_formatted_rows = []
    for r in groups_data:
        fmt_r = [r[0], r[1], r[2], r[3], r[4]]
        for val in r[5:]:
            fmt_r.append(f"{val:.6f}" if val is not None else "")
        groups_formatted_rows.append(fmt_r)
    write_csv(out_dir / "groups.csv", groups_header, groups_formatted_rows)

    # 8. SHA-256 at end
    sha_end = sha256_file(dataset_path)
    if sha_start != sha_end:
        sys.exit(f"FATAL: Dataset {dataset_path} was modified during execution!")

    # e. summary.json
    summary_data = {
        "query_id": query_id,
        "dataset_path": str(dataset_path),
        "dataset_sha256_before": sha_start,
        "dataset_sha256_after": sha_end,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "encoders": {
            "native": {"hub_id": "sentence-transformers/LaBSE", "dim": 768},
            "english": {"hub_id": "sentence-transformers/all-MiniLM-L6-v2", "dim": 384},
        },
        "counts": {
            "total_records": len(order),
            "usable_native": int(np.sum(usable_native)),
            "usable_english": int(np.sum(usable_english)),
            "reliable_native": int(np.sum(reliable_native)),
            "reliable_english": int(np.sum(reliable_english)),
            "truncated_native": int(sum(trunc_native)),
            "truncated_english": int(sum(trunc_english)),
        },
        "exclusions": {
            "native_unreliable": reasons_native,
            "english_unreliable": reasons_english,
        },
        "spearman_agreement": {
            "all_view": spearman_all,
            "reliable_view": spearman_rel,
        },
    }
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    # f. report.md
    report_lines = [
        f"# Cross-Lingual Similarity Analysis: `{query_id}`",
        f"\n**Generated on:** {summary_data['timestamp_utc']}",
        f"\n## 1. Summary Statistics",
        f"- **Dataset SHA-256:** `{sha_end}`",
        f"- **Records:** {summary_data['counts']['total_records']} total | Usable Native: {summary_data['counts']['usable_native']} | Usable English: {summary_data['counts']['usable_english']}",
        f"- **Reliable Count:** Native: {summary_data['counts']['reliable_native']} | English: {summary_data['counts']['reliable_english']}",
        f"- **Cross-Space Spearman Rank Agreement:** All view: `{spearman_all:.4f}` | Reliable view: `{spearman_rel:.4f}`" if spearman_all and spearman_rel else f"- **Cross-Space Spearman Rank Agreement:** All: {spearman_all} | Reliable: {spearman_rel}",
        f"\n## 2. Per-Language Similarity",
        "| Code | Name | Family | Script | Sim to EN (Native) | Sim to EN (English) | Mean Sim to Others (Native) | Mean Sim to Others (English) | Reliable (Nat/Eng) | Probe Pass |",
        "| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for r in per_lang_rows:
        code, name, fam, sc, u_nat, u_eng, r_nat, r_eng, s_nat, s_eng, m_nat, m_eng, t_nat, t_eng, p_pass = r
        rel_str = f"{'Y' if r_nat else 'N'} / {'Y' if r_eng else 'N'}"
        report_lines.append(
            f"| `{code}` | {name} | {fam} | {sc} | {s_nat or 'N/A'} | {s_eng or 'N/A'} | {m_nat or 'N/A'} | {m_eng or 'N/A'} | {rel_str} | {p_pass} |"
        )

    report_lines.append("\n## 3. Group Statistics (View: Reliable)")
    report_lines.append("| Space | Grouping | Group | N | Mean Sim to EN | Std | Min | Max | Within Mean | Between Mean |")
    report_lines.append("| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for r in groups_formatted_rows:
        if r[0] == "reliable":
            report_lines.append(f"| {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} | {r[8]} | {r[9]} | {r[10]} |")

    report_lines.append(f"\n{CAVEATS_TEXT}")

    with open(out_dir / "report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    return summary_data


def main():
    parser = argparse.ArgumentParser(description="Cross-Lingual Similarity CLI")
    parser.add_argument("--query-id", type=str, default="self_image_life_goal", help="Query identifier")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size for encoding")
    parser.add_argument("--models-dir", type=str, default=None, help="Directory containing offline models")
    parser.add_argument("--out-dir", type=str, default=None, help="Base output directory")
    parser.add_argument("--no-plots", action="store_true", help="Skip plot generation")
    args = parser.parse_args()

    models_dir = Path(args.models_dir) if args.models_dir else None
    out_dir_base = Path(args.out_dir) if args.out_dir else None

    summary = analyze_query(
        query_id=args.query_id,
        batch_size=args.batch_size,
        models_dir=models_dir,
        out_dir_base=out_dir_base,
        no_plots=args.no_plots,
    )

    # Console Summary Table
    print("\n" + "=" * 60)
    print(f"SIMILARITY ANALYSIS SUMMARY: {args.query_id}")
    print("=" * 60)
    print(f"Records: {summary['counts']['total_records']} total")
    print(f"Usable:   Native={summary['counts']['usable_native']}, English={summary['counts']['usable_english']}")
    print(f"Reliable: Native={summary['counts']['reliable_native']}, English={summary['counts']['reliable_english']}")
    print(f"Truncated: Native={summary['counts']['truncated_native']}, English={summary['counts']['truncated_english']}")
    sp_all = summary['spearman_agreement']['all_view']
    sp_rel = summary['spearman_agreement']['reliable_view']
    print(f"Spearman Cross-Space Agreement:")
    print(f"  All View:      {sp_all:.4f}" if sp_all is not None else "  All View:      None")
    print(f"  Reliable View: {sp_rel:.4f}" if sp_rel is not None else "  Reliable View: None")
    print(f"Peak RSS: {get_peak_memory_mb():.2f} MB")
    print("=" * 60)


if __name__ == "__main__":
    main()
