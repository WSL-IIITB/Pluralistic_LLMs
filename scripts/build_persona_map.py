"""Adds `personaSimilarityMap` to public/data/default-run.json: a 2-D map of every persona answer.

One point per answer -- for each region, the generic answer ("without persona") and the male and female
persona answers ("with persona"), 18 in the default run. Each reply is embedded (all-MiniLM-L6-v2, the
model the backend uses for persona similarity) and projected to 2-D two ways:

  tsne  t-SNE on cosine distance, perplexity 5 (18 points), PCA start -> deterministic
  mds   classical (Torgerson) MDS on cosine distance -> keeps distances more faithfully

Coordinates are scaled into [-1, 1]. Needs sentence-transformers + scikit-learn, so run it with the
backend's interpreter:   backend/.venv/bin/python scripts/build_persona_map.py
(scripts/export_static_data.py calls it for you.)
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUN = os.path.join(ROOT, "public", "data", "default-run.json")
MODEL = "all-MiniLM-L6-v2"
CONDITIONS = (("baseline", "baselineReply"), ("male", "maleReply"), ("female", "femaleReply"))


def classical_mds(d: np.ndarray) -> np.ndarray:
    n = len(d)
    j = np.eye(n) - np.ones((n, n)) / n
    b = -0.5 * j @ (d**2) @ j
    vals, vecs = np.linalg.eigh(b)
    top = np.argsort(vals)[::-1][:2]
    return vecs[:, top] * np.sqrt(np.maximum(vals[top], 0))


def unit_box(y: np.ndarray) -> np.ndarray:
    y = y - y.mean(axis=0)
    return y / np.abs(y).max()


def excerpt(text: str, n: int = 260) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def build(similarity: dict) -> dict:
    from sentence_transformers import SentenceTransformer
    from sklearn.manifold import TSNE

    rows = []
    for region_id, rec in similarity.items():
        if rec.get("status") != "ok":
            continue
        for cond, key in CONDITIONS:
            if rec.get(key):
                rows.append((region_id, cond, rec[key]))
    emb = SentenceTransformer(MODEL).encode([t for _, _, t in rows], normalize_embeddings=True)
    dist = np.clip(1 - emb @ emb.T, 0, None)
    np.fill_diagonal(dist, 0)
    perplexity = min(5, max(2, len(rows) // 3))
    tsne = unit_box(
        TSNE(2, perplexity=perplexity, metric="cosine", init="pca", random_state=7, learning_rate="auto", max_iter=2000).fit_transform(emb)
    )
    mds = unit_box(classical_mds(dist))
    points = [
        {
            "regionId": rid,
            "condition": cond,
            "text": excerpt(text),
            "tsne": [round(float(tsne[i, 0]), 4), round(float(tsne[i, 1]), 4)],
            "mds": [round(float(mds[i, 0]), 4), round(float(mds[i, 1]), 4)],
        }
        for i, (rid, cond, text) in enumerate(rows)
    ]
    return {"embeddingModel": MODEL, "perplexity": perplexity, "points": points}


def main() -> None:
    with open(RUN, encoding="utf-8") as f:
        run = json.load(f)
    sim = run.get("personaSimilarity")
    if not sim:
        sys.exit("default-run.json has no personaSimilarity; nothing to map")
    run["personaSimilarityMap"] = build(sim)
    with open(RUN, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False)
    print(f"  personaSimilarityMap: {len(run['personaSimilarityMap']['points'])} points written to default-run.json")


if __name__ == "__main__":
    main()
