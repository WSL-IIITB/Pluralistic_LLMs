"""
Embedding layer for cross-lingual similarity analysis.

Runs in .venv-sim (uses sentence-transformers).
Loads models offline from models/labse and models/all-MiniLM-L6-v2.
Provides encoder loading, batch encoding, memory tracking, explicit release,
--download mode, and --selftest mode.
"""

import argparse
import gc
import json
import os
import resource
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.similarity_core import (
    canonical_order,
    cosine_matrix,
    load_records,
    normalize_text,
    sha256_file,
)

LABSE_HUB_ID = "sentence-transformers/LaBSE"
MINILM_HUB_ID = "sentence-transformers/all-MiniLM-L6-v2"

LABSE_LOCAL_DIR = PROJECT_ROOT / "models" / "labse"
MINILM_LOCAL_DIR = PROJECT_ROOT / "models" / "all-MiniLM-L6-v2"

EXPECTED_DIMS = {
    "labse": 768,
    "minilm": 384,
}


def plan_download(
    file_sizes: Sequence[Optional[int]], free_bytes: int
) -> Tuple[bool, int, str]:
    """
    Plan a download given a list of file sizes and available free disk bytes.
    Rules:
      - If any size is None: ok=False, message="size unknown"
      - If total_bytes > free_bytes / 2: ok=False, message="insufficient free disk space"
      - Otherwise: ok=True, message="ok"
    """
    total_bytes = 0
    for sz in file_sizes:
        if sz is None:
            return False, total_bytes, "size unknown"
        total_bytes += sz

    allowed_limit = free_bytes / 2.0
    if total_bytes > allowed_limit:
        msg = (
            f"insufficient free disk space: planned {total_bytes} bytes exceeds "
            f"half of free space ({free_bytes // 2} bytes)"
        )
        return False, total_bytes, msg

    return True, total_bytes, "ok"


def get_peak_memory_mb() -> float:
    """Return peak resident memory (RSS) in megabytes."""
    # On Linux, ru_maxrss is in kilobytes
    usage_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage_kb / 1024.0


def release_encoder(model) -> None:
    """Explicitly release model and collect garbage."""
    mem_before = get_peak_memory_mb()
    del model
    gc.collect()
    mem_after = get_peak_memory_mb()
    print(f"[Memory] Released encoder. Peak RSS: {mem_after:.2f} MB (was {mem_before:.2f} MB)")


def load_encoder(model_type: str, models_dir: Optional[Path] = None):
    """
    Load encoder from local folder with no network access.
    model_type: 'labse' or 'minilm'
    """
    from sentence_transformers import SentenceTransformer

    mem_before = get_peak_memory_mb()
    base_dir = models_dir or (PROJECT_ROOT / "models")
    if model_type == "labse":
        local_path = base_dir / "labse"
        expected_dim = EXPECTED_DIMS["labse"]
    elif model_type == "minilm":
        local_path = base_dir / "all-MiniLM-L6-v2"
        expected_dim = EXPECTED_DIMS["minilm"]
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    if not local_path.exists():
        raise FileNotFoundError(f"Model path does not exist: {local_path}. Run with --download first.")

    # Force local-only loading
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    print(f"[Memory] Before loading {model_type}: peak RSS {mem_before:.2f} MB")
    model = SentenceTransformer(str(local_path), device="cpu")
    dim = model.get_sentence_embedding_dimension()
    if dim != expected_dim:
        raise ValueError(f"Model {model_type} embedding dim {dim} != expected {expected_dim}")

    mem_after = get_peak_memory_mb()
    print(f"[Memory] Loaded {model_type} (dim={dim}). Peak RSS: {mem_after:.2f} MB")
    return model


def encode_texts(
    model, texts: List[str], batch_size: int = 8
) -> Tuple[np.ndarray, List[bool]]:
    """
    Encode a list of texts into float32 L2-normalised vectors.
    Detects truncation by tokenising without truncation and comparing
    against the model's max_seq_length.
    Returns:
      embeddings: np.ndarray of shape (N, dim), unit norm
      truncated_flags: List[bool] of length N
    """
    if not texts:
        return np.empty((0, model.get_sentence_embedding_dimension()), dtype=np.float32), []

    # Detect truncation
    tokenizer = model.tokenizer
    max_len = model.max_seq_length
    truncated_flags = []
    for t in texts:
        tokens = tokenizer.encode(t, truncation=False, add_special_tokens=True)
        truncated_flags.append(len(tokens) > max_len)

    # Encode with sentence-transformers
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)

    # Verify unit norm
    for idx, vec in enumerate(embeddings):
        norm = float(np.linalg.norm(vec))
        if abs(norm - 1.0) > 1e-5:
            # Re-normalise explicitly if slight numerical drift
            embeddings[idx] = vec / (norm + 1e-12)

    return embeddings, truncated_flags


def download_models(
    models_dir: Optional[Path] = None, dry_run: bool = False
) -> None:
    """Download only the required files for CPU inference using huggingface_hub."""
    from huggingface_hub import HfApi, hf_hub_download

    target_dir = models_dir or (PROJECT_ROOT / "models")

    # 1. all-MiniLM-L6-v2 files
    minilm_files = [
        "config.json",
        "config_sentence_transformers.json",
        "modules.json",
        "sentence_bert_config.json",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "tokenizer.json",
        "vocab.txt",
        "1_Pooling/config.json",
        "model.safetensors",
    ]

    # 2. LaBSE files
    labse_files = [
        "config.json",
        "config_sentence_transformers.json",
        "modules.json",
        "sentence_bert_config.json",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "tokenizer.json",
        "vocab.txt",
        "1_Pooling/config.json",
        "2_Dense/config.json",
        "2_Dense/model.safetensors",
        "model.safetensors",
    ]

    # Pre-download check: query HF Hub metadata for all files in both repos
    api = HfApi()
    print("Fetching repository metadata from Hugging Face Hub...")
    try:
        minilm_info = api.model_info(repo_id=MINILM_HUB_ID, files_metadata=True)
        labse_info = api.model_info(repo_id=LABSE_HUB_ID, files_metadata=True)
    except Exception as e:
        sys.exit(f"Error: Failed to fetch model metadata from Hugging Face Hub: {e}")

    minilm_meta_sizes = {s.rfilename: s.size for s in minilm_info.siblings}
    labse_meta_sizes = {s.rfilename: s.size for s in labse_info.siblings}

    # Collect sizes
    planned_items = []  # tuples of (repo, filename, size)
    all_sizes: List[Optional[int]] = []

    for f in minilm_files:
        sz = minilm_meta_sizes.get(f)
        planned_items.append((MINILM_HUB_ID, f, sz))
        all_sizes.append(sz)

    for f in labse_files:
        sz = labse_meta_sizes.get(f)
        planned_items.append((LABSE_HUB_ID, f, sz))
        all_sizes.append(sz)

    # Print table
    print("\n" + "=" * 70)
    print(f"{'Repository':<38} | {'Filename':<20} | {'Size (bytes)':<10}")
    print("-" * 70)
    total_minilm = 0
    total_labse = 0
    for repo, fname, sz in planned_items:
        sz_str = str(sz) if sz is not None else "UNKNOWN"
        print(f"{repo:<38} | {fname:<20} | {sz_str:<10}")
        if repo == MINILM_HUB_ID and sz is not None:
            total_minilm += sz
        elif repo == LABSE_HUB_ID and sz is not None:
            total_labse += sz

    print("-" * 70)
    print(f"Total {MINILM_HUB_ID}: {total_minilm:,} bytes ({total_minilm / (1024*1024):.2f} MB)")
    print(f"Total {LABSE_HUB_ID}: {total_labse:,} bytes ({total_labse / (1024*1024):.2f} MB)")
    overall_total = sum(s for s in all_sizes if s is not None)
    print(f"Overall Total Planned: {overall_total:,} bytes ({overall_total / (1024*1024):.2f} MB)")
    print("=" * 70 + "\n")

    # Get free disk space on nearest existing parent folder of target_dir
    check_dir = target_dir
    while not check_dir.exists():
        check_dir = check_dir.parent

    usage = shutil.disk_usage(check_dir)
    free_bytes = usage.free
    print(f"Nearest existing directory for disk check: {check_dir}")
    print(f"Available free disk space: {free_bytes:,} bytes ({free_bytes / (1024*1024*1024):.2f} GiB)")
    print(f"Allowed download limit (half): {free_bytes // 2:,} bytes ({(free_bytes // 2) / (1024*1024*1024):.2f} GiB)")

    ok, total_bytes, msg = plan_download(all_sizes, free_bytes)
    if not ok:
        print(f"\nDownload guard FAILED: {msg}")
        sys.exit(1)

    print(f"Download guard PASSED ({msg}).")

    if dry_run:
        print("\n[Dry Run] --dry-run enabled. No files will be downloaded and no folders created.")
        sys.exit(0)

    # Proceed with real download
    target_dir.mkdir(parents=True, exist_ok=True)
    minilm_dir = target_dir / "all-MiniLM-L6-v2"
    labse_dir = target_dir / "labse"

    print(f"\nDownloading {MINILM_HUB_ID} to {minilm_dir}...")
    for f in minilm_files:
        print(f"  Fetching {f}...")
        hf_hub_download(
            repo_id=MINILM_HUB_ID,
            filename=f,
            local_dir=minilm_dir,
            local_dir_use_symlinks=False,
        )

    print(f"\nDownloading {LABSE_HUB_ID} to {labse_dir}...")
    for f in labse_files:
        print(f"  Fetching {f}...")
        hf_hub_download(
            repo_id=LABSE_HUB_ID,
            filename=f,
            local_dir=labse_dir,
            local_dir_use_symlinks=False,
        )

    print("\nAll model files downloaded successfully.")


def run_selftest(models_dir: Optional[Path] = None) -> bool:
    """
    Run self-test suite per Section 4 (Phase 3 prompt):
    a. Embedding dimensions & unit norms
    b. Determinism (5 strings encoded twice, diff < 1e-6)
    c. English sanity with all-MiniLM-L6-v2
    d. Alignment probe with LaBSE on real data (22 languages)
    """
    all_passed = True
    test_strings = [
        "Can you give an example of a life goal related to self-image?",
        "Regular exercise and a balanced diet promote long-term well-being.",
        "आत्म-सुधार जीवन का एक महत्वपूर्ण हिस्सा है।",
        "স্ব-উন্নয়ন জীবনের একটি অপরিহার্য দিক।",
        "1. Setting personal boundaries. 2. Cultivating self-compassion.",
    ]

    print("=== SELF-TEST: English Encoder (all-MiniLM-L6-v2) ===")
    minilm = load_encoder("minilm", models_dir)

    # a. Dimension & unit norms
    emb1, trunc1 = encode_texts(minilm, test_strings)
    dim_ok = emb1.shape[1] == EXPECTED_DIMS["minilm"]
    norms_ok = all(abs(np.linalg.norm(v) - 1.0) <= 1e-5 for v in emb1)
    status_a = "PASS" if (dim_ok and norms_ok) else "FAIL"
    print(f"[Check a] Dimension ({emb1.shape[1]}) & Norms: {status_a}")
    if status_a == "FAIL":
        all_passed = False

    # b. Determinism
    emb2, _ = encode_texts(minilm, test_strings)
    max_diff = float(np.max(np.abs(emb1 - emb2)))
    status_b = "PASS" if max_diff < 1e-6 else "FAIL"
    print(f"[Check b] Determinism (max diff {max_diff:.2e} < 1e-6): {status_b}")
    if status_b == "FAIL":
        all_passed = False

    # c. English Sanity
    s_base = "A healthy lifestyle with exercise"
    s_pos = "Regular exercise and a good diet"
    s_neg = "The stock market closed higher today"
    sanity_embs, _ = encode_texts(minilm, [s_base, s_pos, s_neg])
    sim_pos = float(np.dot(sanity_embs[0], sanity_embs[1]))
    sim_neg = float(np.dot(sanity_embs[0], sanity_embs[2]))
    status_c = "PASS" if sim_pos > sim_neg else "FAIL"
    print(f"[Check c] English sanity (pos={sim_pos:.4f} > neg={sim_neg:.4f}): {status_c}")
    if status_c == "FAIL":
        all_passed = False

    # Release minilm
    release_encoder(minilm)
    del minilm

    print("\n=== SELF-TEST: Native Encoder (LaBSE) ===")
    labse = load_encoder("labse", models_dir)

    # a. Dimension & unit norms
    lemb1, ltrunc1 = encode_texts(labse, test_strings)
    ldim_ok = lemb1.shape[1] == EXPECTED_DIMS["labse"]
    lnorms_ok = all(abs(np.linalg.norm(v) - 1.0) <= 1e-5 for v in lemb1)
    status_la = "PASS" if (ldim_ok and lnorms_ok) else "FAIL"
    print(f"[Check a] Dimension ({lemb1.shape[1]}) & Norms: {status_la}")
    if status_la == "FAIL":
        all_passed = False

    # b. Determinism
    lemb2, _ = encode_texts(labse, test_strings)
    lmax_diff = float(np.max(np.abs(lemb1 - lemb2)))
    status_lb = "PASS" if lmax_diff < 1e-6 else "FAIL"
    print(f"[Check b] Determinism (max diff {lmax_diff:.2e} < 1e-6): {status_lb}")
    if status_lb == "FAIL":
        all_passed = False

    # d. Alignment probe on real data
    print("\n[Check d] Alignment Probe Table (22 languages):")
    ds_path_a = PROJECT_ROOT / "data" / "raw" / "sarvam_self_image_life_goal.json"
    ds_path_b = PROJECT_ROOT / "data" / "raw" / "sarvam_self_dev_tips.json"

    if not ds_path_a.exists() or not ds_path_b.exists():
        print("  Datasets missing for probe. FAIL")
        all_passed = False
    else:
        records_a = {r["target_lang_code"]: r for r in load_records(ds_path_a)}
        records_b = {r["target_lang_code"]: r for r in load_records(ds_path_b)}

        source_en_a = records_a["en"]["source_query_en"]
        source_emb_a, _ = encode_texts(labse, [source_en_a])
        src_vec_a = source_emb_a[0]

        lang_codes = canonical_order(PROJECT_ROOT / "config" / "languages.json")
        lang_codes = [c for c in lang_codes if c != "en"]

        print(f"{'Code':<8} | {'Pos Sim':<10} | {'Neg Sim':<10} | {'Status'}")
        print("-" * 42)
        probe_fails = 0
        for code in lang_codes:
            trans_a = records_a.get(code, {}).get("translated_query", "")
            trans_b = records_b.get(code, {}).get("translated_query", "")

            embs, _ = encode_texts(labse, [trans_a, trans_b])
            pos_sim = float(np.dot(src_vec_a, embs[0]))
            neg_sim = float(np.dot(src_vec_a, embs[1]))
            p_pass = pos_sim > neg_sim
            p_status = "PASS" if p_pass else "FAIL"
            if not p_pass:
                probe_fails += 1
            print(f"{code:<8} | {pos_sim:<10.4f} | {neg_sim:<10.4f} | {p_status}")

        print(f"\nAlignment probe complete: {22 - probe_fails}/22 passed (Evidence only).")

    # Release labse
    release_encoder(labse)
    del labse

    overall = "PASS" if all_passed else "FAIL"
    print(f"\nOverall Self-Test Result: {overall}")
    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Similarity embedding layer CLI")
    parser.add_argument("--download", action="store_true", help="Download model weights")
    parser.add_argument("--dry-run", action="store_true", help="Dry run for download guard (requires --download)")
    parser.add_argument("--selftest", action="store_true", help="Run self-test suite")
    parser.add_argument("--models-dir", type=str, default=None, help="Directory for models")
    args = parser.parse_args()

    if args.dry_run and not args.download:
        parser.error("--dry-run requires --download")

    models_dir = Path(args.models_dir) if args.models_dir else None

    if args.download:
        download_models(models_dir=models_dir, dry_run=args.dry_run)

    if args.selftest:
        ok = run_selftest(models_dir)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
