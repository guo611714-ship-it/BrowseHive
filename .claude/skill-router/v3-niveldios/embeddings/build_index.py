#!/usr/bin/env python3
"""
build_index.py — Construye los índices FAISS de skills.

Scanea SKILL.md en:
  - ~/.claude/skills/**/SKILL.md
  - ~/.claude/plugins/cache/**/SKILL.md
  - $REPO/.claude/skills/**/SKILL.md (si se pasa --repo o env REPO_ROOT)
  - $EXTRA_SKILL_DIRS (paths separados por ":")

Para cada SKILL.md extrae frontmatter (name, description) + cuerpo.
Genera 2 índices FAISS (Inner Product sobre vectores L2-normalizados ≡ cosine):
  - index_description.faiss  (embedding del field description, rápido)
  - index_full.faiss         (embedding del cuerpo+description, más preciso, fallback)

Cache: mtime check, sólo reembebe SKILL.md cambiadas o nuevas.

Modelo por defecto: paraphrase-multilingual-MiniLM-L12-v2 (118 MB, soporte español).
Fallback automático a all-MiniLM-L6-v2 (90 MB) o Gemini API si st falla.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

EMB_DIR = Path(__file__).resolve().parent
INDEX_DIR = EMB_DIR / "indexes"
INDEX_DIR.mkdir(exist_ok=True)

DESC_INDEX = INDEX_DIR / "index_description.faiss"
FULL_INDEX = INDEX_DIR / "index_full.faiss"
METADATA_FILE = INDEX_DIR / "metadata.json"
MANIFEST_FILE = INDEX_DIR / "manifest.json"
CACHE_FILE = INDEX_DIR / "embedding_cache.json"

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
FALLBACK_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MAX_BODY_CHARS = 2000


@dataclass
class SkillRecord:
    name: str
    description: str
    full_text: str
    file_path: str
    mtime: float
    source_tag: str  # user / plugin / repo / extra

    def cache_key(self) -> str:
        return f"{self.file_path}|{self.mtime}"


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------

def discover_skill_files(repo_root: Path | None) -> list[tuple[Path, str]]:
    """Devuelve [(path, source_tag), ...]"""
    results: list[tuple[Path, str]] = []
    home = Path.home()

    sources: list[tuple[Path, str]] = [
        (home / ".claude" / "skills", "user"),
        (home / ".claude" / "plugins" / "cache", "plugin"),
    ]
    if repo_root and (repo_root / ".claude" / "skills").exists():
        sources.append((repo_root / ".claude" / "skills", "repo"))

    extra = os.environ.get("EXTRA_SKILL_DIRS", "").strip()
    if extra:
        for p in extra.split(":"):
            p = p.strip()
            if p and Path(p).exists():
                sources.append((Path(p), "extra"))

    for root, tag in sources:
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            # skip __pycache__ / .git / node_modules
            if any(part.startswith(".") for part in skill_md.parts[len(root.parts):]):
                continue
            if any(p in skill_md.parts for p in ("node_modules", "__pycache__", ".git")):
                continue
            results.append((skill_md, tag))
    # dedupe por path absoluto
    seen: set[str] = set()
    unique: list[tuple[Path, str]] = []
    for p, tag in results:
        s = str(p.resolve())
        if s in seen:
            continue
        seen.add(s)
        unique.append((p, tag))
    return unique


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Devuelve (frontmatter_dict, body). Frontmatter YAML simple key:value sin nested."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    fm: dict = {}
    current_key = None
    current_buf: list[str] = []
    for line in raw.splitlines():
        # multi-line value continuation
        if current_key and (line.startswith(" ") or line.startswith("\t")):
            current_buf.append(line.strip())
            continue
        if current_key:
            fm[current_key] = " ".join(current_buf).strip()
            current_key = None
            current_buf = []
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if v:
                fm[k] = v
            else:
                current_key = k
                current_buf = []
    if current_key:
        fm[current_key] = " ".join(current_buf).strip()
    return fm, body


def parse_skill_file(path: Path, source_tag: str) -> SkillRecord | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    fm, body = parse_frontmatter(text)
    name = fm.get("name", "").strip().strip("'\"")
    if not name:
        # derive from parent dir
        name = path.parent.name
    description = fm.get("description", "").strip().strip("'\"")
    # full text = description + first MAX_BODY_CHARS of body
    body_clean = body.strip()
    if len(body_clean) > MAX_BODY_CHARS:
        body_clean = body_clean[:MAX_BODY_CHARS]
    full = f"{description}\n\n{body_clean}" if description else body_clean
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0
    return SkillRecord(
        name=name,
        description=description or name,
        full_text=full or name,
        file_path=str(path.resolve()),
        mtime=mtime,
        source_tag=source_tag,
    )


# ----------------------------------------------------------------------------
# Embedding backends
# ----------------------------------------------------------------------------

class STBackend:
    name = "sentence-transformers"

    def __init__(self, model_id: str):
        from sentence_transformers import SentenceTransformer
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        self.model = SentenceTransformer(model_id)
        try:
            self.dim = int(self.model.get_sentence_embedding_dimension())
        except Exception:
            self.dim = len(self.encode(["__probe__"])[0])
        self.model_id = model_id

    def encode(self, texts: list[str]):
        import numpy as np
        vecs = self.model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vecs.astype("float32")


class GeminiBackend:
    name = "gemini-embedding-001"

    def __init__(self):
        try:
            import google.generativeai as genai  # type: ignore
        except Exception as e:
            raise RuntimeError(f"google-generativeai no instalado: {e}")
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY no presente")
        genai.configure(api_key=api_key)
        self.genai = genai
        self.dim = 768
        self.model_id = "gemini-embedding-001"

    def encode(self, texts: list[str]):
        import numpy as np
        out = []
        for t in texts:
            r = self.genai.embed_content(model="models/embedding-001", content=t)
            v = r["embedding"]
            n = float(np.linalg.norm(v)) or 1.0
            out.append([x / n for x in v])
        return np.asarray(out, dtype="float32")


def select_backend(force: str | None = None):
    if force == "gemini":
        return GeminiBackend()
    try:
        return STBackend(DEFAULT_MODEL)
    except Exception as e:
        print(f"[build_index] WARN modelo {DEFAULT_MODEL} falló: {e}", file=sys.stderr)
        try:
            return STBackend(FALLBACK_MODEL)
        except Exception as e2:
            print(f"[build_index] WARN modelo fallback {FALLBACK_MODEL} falló: {e2}", file=sys.stderr)
            return GeminiBackend()


# ----------------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------------

def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {"model": None, "dim": None, "vectors_desc": {}, "vectors_full": {}}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache))


# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------

def build(
    repo_root: Path | None = None,
    force: bool = False,
    backend_force: str | None = None,
    verbose: bool = True,
) -> dict:
    import faiss
    import numpy as np

    t0 = time.time()
    files = discover_skill_files(repo_root)
    if verbose:
        print(f"[build_index] {len(files)} SKILL.md files descubiertas")

    records: list[SkillRecord] = []
    for path, tag in files:
        rec = parse_skill_file(path, tag)
        if rec:
            records.append(rec)

    if verbose:
        print(f"[build_index] {len(records)} parsed")

    if not records:
        raise RuntimeError("No se encontraron SKILL.md válidas")

    # init backend
    backend = select_backend(backend_force)
    if verbose:
        print(f"[build_index] backend={backend.name} model={backend.model_id} dim={backend.dim}")

    cache = load_cache()
    cache_valid = (
        not force
        and cache.get("model") == backend.model_id
        and cache.get("dim") == backend.dim
    )
    if not cache_valid:
        cache = {
            "model": backend.model_id,
            "dim": backend.dim,
            "vectors_desc": {},
            "vectors_full": {},
        }

    # determine which to (re)embed
    to_embed_desc: list[tuple[int, str]] = []
    to_embed_full: list[tuple[int, str]] = []
    for i, r in enumerate(records):
        ckey = r.cache_key()
        if ckey not in cache["vectors_desc"]:
            to_embed_desc.append((i, r.description))
        if ckey not in cache["vectors_full"]:
            to_embed_full.append((i, r.full_text))

    if verbose:
        print(f"[build_index] to embed desc={len(to_embed_desc)} full={len(to_embed_full)}")

    # batch encode
    if to_embed_desc:
        vecs = backend.encode([t for _, t in to_embed_desc])
        for (i, _), v in zip(to_embed_desc, vecs):
            cache["vectors_desc"][records[i].cache_key()] = v.tolist()
    if to_embed_full:
        vecs = backend.encode([t for _, t in to_embed_full])
        for (i, _), v in zip(to_embed_full, vecs):
            cache["vectors_full"][records[i].cache_key()] = v.tolist()

    # purge stale cache entries
    valid_keys = {r.cache_key() for r in records}
    for which in ("vectors_desc", "vectors_full"):
        cache[which] = {k: v for k, v in cache[which].items() if k in valid_keys}

    # build matrices in record order
    desc_mat = np.asarray([cache["vectors_desc"][r.cache_key()] for r in records], dtype="float32")
    full_mat = np.asarray([cache["vectors_full"][r.cache_key()] for r in records], dtype="float32")

    # FAISS IndexFlatIP sobre vectores ya normalizados (cosine)
    idx_desc = faiss.IndexFlatIP(backend.dim)
    idx_desc.add(desc_mat)
    idx_full = faiss.IndexFlatIP(backend.dim)
    idx_full.add(full_mat)

    faiss.write_index(idx_desc, str(DESC_INDEX))
    faiss.write_index(idx_full, str(FULL_INDEX))

    metadata = [
        {
            "id": i,
            "name": r.name,
            "description": r.description,
            "file_path": r.file_path,
            "source_tag": r.source_tag,
            "mtime": r.mtime,
        }
        for i, r in enumerate(records)
    ]
    METADATA_FILE.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    elapsed = time.time() - t0
    manifest = {
        "backend": backend.name,
        "model": backend.model_id,
        "dimension": backend.dim,
        "total_skills": len(records),
        "embedded_desc_new": len(to_embed_desc),
        "embedded_full_new": len(to_embed_full),
        "build_seconds": round(elapsed, 2),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "index_description_path": str(DESC_INDEX),
        "index_full_path": str(FULL_INDEX),
        "metadata_path": str(METADATA_FILE),
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))

    save_cache(cache)

    if verbose:
        print(f"[build_index] done in {elapsed:.1f}s total_skills={len(records)}")
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=str, default=os.environ.get("REPO_ROOT"))
    ap.add_argument("--force", action="store_true", help="rebuild from scratch")
    ap.add_argument(
        "--backend",
        choices=["st", "gemini"],
        default=None,
        help="forzar backend",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    repo = Path(args.repo).expanduser().resolve() if args.repo else None
    backend_force = args.backend if args.backend != "st" else None
    manifest = build(repo, force=args.force, backend_force=backend_force, verbose=not args.quiet)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
