#!/usr/bin/env python3
"""
search.py — Búsqueda semántica sobre los índices FAISS.

Función pública: search_skills(query, top_k=5, threshold=0.5) -> list[dict]

Estrategia:
  1) Embeddear query.
  2) Buscar top_k en index_description (rápido).
  3) Si max(score) < threshold → consultar index_full y fusionar resultados.
  4) Retorna lista ordenada por score descendente.

El modelo se carga 1× en memoria por proceso (lazy singleton).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

EMB_DIR = Path(__file__).resolve().parent
INDEX_DIR = EMB_DIR / "indexes"

DESC_INDEX = INDEX_DIR / "index_description.faiss"
FULL_INDEX = INDEX_DIR / "index_full.faiss"
METADATA_FILE = INDEX_DIR / "metadata.json"
MANIFEST_FILE = INDEX_DIR / "manifest.json"


_state: dict[str, Any] = {
    "loaded": False,
    "manifest": None,
    "metadata": None,
    "index_desc": None,
    "index_full": None,
    "encoder": None,
}


def _load_encoder(model_id: str, backend_name: str):
    if backend_name == "sentence-transformers":
        from sentence_transformers import SentenceTransformer
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        return ("st", SentenceTransformer(model_id))
    if backend_name == "gemini-embedding-001":
        import google.generativeai as genai  # type: ignore
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY no presente")
        genai.configure(api_key=api_key)
        return ("gemini", genai)
    raise RuntimeError(f"Backend desconocido en manifest: {backend_name}")


def _ensure_loaded() -> None:
    if _state["loaded"]:
        return
    if not MANIFEST_FILE.exists():
        raise RuntimeError(
            f"Índice no construido. Ejecuta: python3 {EMB_DIR}/build_index.py"
        )
    import faiss
    manifest = json.loads(MANIFEST_FILE.read_text())
    metadata = json.loads(METADATA_FILE.read_text())
    idx_desc = faiss.read_index(str(DESC_INDEX))
    idx_full = faiss.read_index(str(FULL_INDEX))
    encoder = _load_encoder(manifest["model"], manifest["backend"])
    _state.update({
        "loaded": True,
        "manifest": manifest,
        "metadata": metadata,
        "index_desc": idx_desc,
        "index_full": idx_full,
        "encoder": encoder,
    })


def _encode(text: str):
    import numpy as np
    backend_kind, enc = _state["encoder"]
    if backend_kind == "st":
        v = enc.encode(
            [text],
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype("float32")
        return v
    if backend_kind == "gemini":
        r = enc.embed_content(model="models/embedding-001", content=text)
        v = r["embedding"]
        n = float(np.linalg.norm(v)) or 1.0
        v = np.asarray([[x / n for x in v]], dtype="float32")
        return v
    raise RuntimeError("encoder no inicializado")


def search_skills(
    query: str,
    top_k: int = 5,
    threshold: float = 0.5,
    use_full_fallback: bool = True,
) -> list[dict]:
    """Busca skills semánticamente similares a `query`.

    Args:
      query: texto natural (prompt del usuario, fragmento, etc.)
      top_k: cuántos resultados devolver (default 5)
      threshold: si max score en index_description < threshold → consulta index_full
      use_full_fallback: desactivar para forzar solo description

    Returns:
      Lista ordenada de dicts {name, score, source, file_path, description}
    """
    _ensure_loaded()
    q = _encode(query)
    metadata = _state["metadata"]
    idx_desc = _state["index_desc"]
    idx_full = _state["index_full"]

    # primary: description
    D, I = idx_desc.search(q, top_k)
    results: dict[int, dict] = {}
    max_desc = 0.0
    for rank, (score, idx) in enumerate(zip(D[0], I[0])):
        if idx < 0:
            continue
        s = float(score)
        if s > max_desc:
            max_desc = s
        m = metadata[idx]
        results[idx] = {
            "name": m["name"],
            "score": s,
            "source": "description",
            "file_path": m["file_path"],
            "description": m["description"],
            "rank_desc": rank,
        }

    if use_full_fallback and max_desc < threshold:
        D2, I2 = idx_full.search(q, top_k)
        for rank, (score, idx) in enumerate(zip(D2[0], I2[0])):
            if idx < 0:
                continue
            s = float(score)
            m = metadata[idx]
            prev = results.get(idx)
            if prev is None or s > prev["score"]:
                results[idx] = {
                    "name": m["name"],
                    "score": s,
                    "source": "full" if prev is None else "merged",
                    "file_path": m["file_path"],
                    "description": m["description"],
                    "rank_desc": prev["rank_desc"] if prev else None,
                    "rank_full": rank,
                }

    ordered = sorted(results.values(), key=lambda r: r["score"], reverse=True)
    return ordered[:top_k]


def warmup() -> float:
    t = time.time()
    _ensure_loaded()
    _encode("warmup")
    return time.time() - t


def manifest() -> dict:
    _ensure_loaded()
    return _state["manifest"]


def main():
    import argparse
    ap = argparse.ArgumentParser(description="FAISS semantic search over SKILL.md")
    ap.add_argument("query", nargs="+", help="texto a buscar")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-fallback", action="store_true")
    args = ap.parse_args()
    q = " ".join(args.query)
    out = search_skills(
        q,
        top_k=args.top,
        threshold=args.threshold,
        use_full_fallback=not args.no_fallback,
    )
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return
    print(f"\nQuery: {q}\n")
    if not out:
        print("(sin resultados)")
        return
    for i, r in enumerate(out, 1):
        src = r["source"]
        desc_short = (r["description"] or "")[:120].replace("\n", " ")
        print(f"  {i}. {r['name']:<45} score={r['score']:.3f}  src={src}")
        print(f"     {desc_short}")
        print(f"     {r['file_path']}")
        print()


if __name__ == "__main__":
    main()
