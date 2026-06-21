#!/usr/bin/env python3
"""kb-manager.py - Dual-track knowledge base CLI.
Track 1: Memory KB (~/.claude/projects/.../memory/knowledge/)
Track 2: Obsidian Vault (AI知识库/)
"""
from __future__ import annotations

import argparse, hashlib, json, os, re, subprocess, sys, tempfile, urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

VAULT_DIR: Path = Path(__file__).parent.resolve()
MEMORY_KB: Path = Path.home() / ".claude/projects/d--Users-lenovo-Desktop-claude-workspace/memory/knowledge"
IMPORT_DIR: Path = VAULT_DIR / "01-Import"
INDEX_DIR: Path = VAULT_DIR / "03-Index"
DOCS_JSON: Path = INDEX_DIR / "documents.json"
CONFIG_PATH: Path = VAULT_DIR / "config.json"
ENCODE: dict[str, Any] = dict(encoding="utf-8", errors="replace")

# --- Helpers ---
def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, **ENCODE) as f: return json.load(f)
    return {}

def content_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()[:12]

def slugify(title: str) -> str:
    s = re.sub(r"[^\w一-鿿\- ]", "", title).strip()
    return re.sub(r"\s+", "-", s)[:60] or "untitled"

def load_documents() -> list[dict[str, Any]]:
    if DOCS_JSON.exists():
        with open(DOCS_JSON, **ENCODE) as f: return json.load(f).get("documents", [])
    return []

def save_documents(docs: list[dict[str, Any]]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(INDEX_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", **ENCODE) as f:
            json.dump({"documents": docs}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(DOCS_JSON))
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise

def out(obj: Any) -> None:
    sys.stdout.buffer.write((json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode())

def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not m: return {}, text
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, m.group(2)

def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", **ENCODE) as f: f.write(content)

def unique_path(directory: Path, slug: str, ext: str = ".md") -> Path:
    """Return a unique file path, handling race conditions."""
    candidate = directory / f"{slug}{ext}"
    try:
        fd = os.open(str(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return candidate
    except FileExistsError:
        pass
    n = 2
    while True:
        candidate = directory / f"{slug}-{n}{ext}"
        try:
            fd = os.open(str(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return candidate
        except FileExistsError:
            n += 1

def read_file(path: Path) -> str:
    with open(path, **ENCODE) as f: return f.read()

def extract_snippet(text: str, query: str, ctx: int = 150) -> str:
    idx = text.lower().find(query.lower())
    if idx == -1: return text[:200]
    s, e = max(0, idx - ctx), min(len(text), idx + len(query) + ctx)
    snippet = text[s:e].strip()
    # Sanitize for JSON output: replace backslashes, strip control chars
    snippet = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", snippet)
    return ("..." if s > 0 else "") + snippet + ("..." if e < len(text) else "")

# --- NVIDIA API ---
def call_nvidia(prompt: str, config: dict[str, Any]) -> str | None:
    api_key_env = config.get("api_key_env", "NVIDIA_API_KEY")
    api_key = os.environ.get(api_key_env, "") or config.get("api_key", "")
    if not api_key: return None
    url = f"{config.get('base_url', 'https://integrate.api.nvidia.com/v1')}/chat/completions"
    payload = json.dumps({
        "model": config.get("model", "stepfun-ai/step-3.7-flash"),
        "max_tokens": config.get("max_tokens", 4096),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(url, data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[WARN] API failed: {e}", file=sys.stderr)
        return None

# --- Commands ---
def cmd_init(_: argparse.Namespace) -> None:
    dirs: list[Path] = [IMPORT_DIR, VAULT_DIR / "02-Notes", INDEX_DIR]
    for d in dirs: d.mkdir(parents=True, exist_ok=True)
    if not DOCS_JSON.exists(): save_documents([])
    out({"status": "ok", "directories": [str(d) for d in dirs]})

def cmd_analyze_text(args: argparse.Namespace) -> None:
    config: dict[str, Any] = load_config()
    title: str = args.title or "Untitled"
    category: str = args.category or "general"
    if args.file:
        p = Path(args.file)
        if not p.exists():
            out({"status": "error", "message": f"File not found: {args.file}"})
            return
        resolved = p.resolve()
        if not (str(resolved).startswith(str(VAULT_DIR) + os.sep) or str(resolved).startswith(str(Path.home()) + os.sep)):
            out({"status": "error", "message": f"File is outside allowed paths: {args.file}"})
            return
        content: str = read_file(p)
    elif args.text:
        content = args.text
    else:
        content = sys.stdin.read() if not sys.stdin.isatty() else ""
    analysis: dict[str, Any] | None = None
    if content.strip():
        resp = call_nvidia(
            "You are a knowledge analyst. Analyze this content and return ONLY a JSON object.\n"
            "JSON keys: concepts (list 3-8), entities (list 3-8), tags (list 3-8), "
            "summary (string), key_points (list 3-5).\n"
            f"Content:\n{content[:3000]}", config)
        if resp:
            try:
                cleaned = re.sub(r"```(?:json)?\s*", "", resp).strip()
                m = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if m: analysis = json.loads(m.group())
            except json.JSONDecodeError: pass
    if not analysis:
        analysis = {"concepts": [], "entities": [], "tags": [category],
                     "summary": content[:200], "key_points": []}
    now = datetime.now().strftime("%Y-%m-%d")
    tags_str = ", ".join(analysis.get("tags", []))
    kp = "\n".join(f"  - {pt}" for pt in analysis.get("key_points", []))
    cp = "\n".join(f"  - {c}" for c in analysis.get("concepts", []))
    markdown = f"""---
title: "{title}"
category: "{category}"
tags: [{tags_str}]
date: "{now}"
source: "kb-manager analyze-text"
---

# {title}

> Category: {category} | Tags: {tags_str} | Date: {now}

## Overview

{analysis.get('summary', content[:500])}

## Key Concepts

{cp}

## Key Points

{kp}

## Full Content

{content}
"""
    slug = slugify(title)
    out_path = unique_path(IMPORT_DIR, slug)
    filename = out_path.name
    write_file(out_path, markdown)
    docs = load_documents()
    rel = f"01-Import/{filename}"
    entry: dict[str, Any] = {"path": rel, "title": title, "category": category,
             "entities": analysis.get("entities", []), "concepts": analysis.get("concepts", []),
             "tags": analysis.get("tags", []), "hash": content_hash(content),
             "created": datetime.now().isoformat()}
    existing: int | None = next((i for i, d in enumerate(docs) if d.get("path") == rel), None)
    if existing is not None: docs[existing] = entry
    else: docs.append(entry)
    save_documents(docs)
    out({"status": "ok", "path": str(out_path), "title": title,
         "concepts_count": len(analysis.get("concepts", [])), "tags": analysis.get("tags", [])})

def _search_track(track_name: str, directory: Path, query: str, ignore_files: list[str] | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not directory.exists(): return results
    ignore: set[str] = set(ignore_files or [])
    for f in directory.rglob("*.md"):
        if f.name in ignore: continue
        try: text = read_file(f)
        except Exception: continue
        if query not in text.lower(): continue
        fm, _ = parse_frontmatter(text)
        title = fm.get("title", f.stem) if track_name == "vault" else f.stem
        if track_name == "memory":
            hm = re.search(r"^#\s+(.+)", text, re.MULTILINE)
            if hm: title = hm.group(1)
        score = text.lower().count(query) / max(len(text), 1) * 100
        results.append({"source": track_name, "title": title, "path": str(f),
                         "snippet": extract_snippet(text, query), "score": round(score, 2)})
    return results

def cmd_unified_search(args: argparse.Namespace) -> None:
    q: str = args.query.lower()
    results = _search_track("memory", MEMORY_KB, q, ["INDEX.md"])
    results += _search_track("vault", IMPORT_DIR, q)
    results.sort(key=lambda r: r["score"], reverse=True)
    out(results)

def cmd_sync_memory_to_kb(args: argparse.Namespace) -> None:
    mem: Path = Path(args.memory_dir) if args.memory_dir else MEMORY_KB
    if not mem.exists():
        out({"status": "error", "message": f"Not found: {mem}"})
        return
    existing: set[str] = set()
    if IMPORT_DIR.exists():
        for f in IMPORT_DIR.rglob("*.md"):
            try: existing.add(content_hash(read_file(f)))
            except Exception: pass
    docs = load_documents()
    imported: int = 0
    skipped: int = 0
    for f in mem.rglob("*.md"):
        if f.name == "INDEX.md": continue
        try: content = read_file(f)
        except Exception: continue
        h = content_hash(content)
        if h in existing: skipped += 1; continue
        existing.add(h)
        fm, _ = parse_frontmatter(content)
        title = f.stem or fm.get("title", "Untitled")
        cat = fm.get("category", "general")
        slug = slugify(title)
        out_path = unique_path(IMPORT_DIR, slug)
        write_file(out_path, content)
        docs.append({"path": f"01-Import/{out_path.name}", "title": title, "category": cat,
                      "entities": [], "concepts": [], "tags": [cat], "hash": h,
                      "created": datetime.now().isoformat(), "source": "memory-sync"})
        imported += 1
    save_documents(docs)
    out({"status": "ok", "imported": imported, "skipped": skipped})

def cmd_sync_kb_to_memory(args: argparse.Namespace) -> None:
    mem: Path = Path(args.memory_dir) if args.memory_dir else MEMORY_KB
    mem.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if mem.exists():
        for f in mem.rglob("*.md"):
            try: existing.add(content_hash(read_file(f)))
            except Exception: pass
    synced: int = 0
    skipped: int = 0
    if not IMPORT_DIR.exists():
        out({"status": "ok", "synced": 0, "skipped": 0}); return
    for f in IMPORT_DIR.rglob("*.md"):
        try: content = read_file(f)
        except Exception: continue
        h = content_hash(content)
        if h in existing: skipped += 1; continue
        existing.add(h)
        fm, _ = parse_frontmatter(content)
        cat_dir = mem / fm.get("category", "general")
        cat_dir.mkdir(parents=True, exist_ok=True)
        write_file(cat_dir / f.name, content)
        synced += 1
    _rebuild_memory_index(mem)
    out({"status": "ok", "synced": synced, "skipped": skipped})

def _rebuild_memory_index(mem: Path) -> None:
    lines: list[str] = ["# 知识库索引\n"]
    for cat in sorted(mem.iterdir()):
        if not cat.is_dir(): continue
        try:
            files = sorted(cat.glob("*.md"))
            if not files: continue
            lines.append(f"\n## {cat.name}\n")
            for f in files: lines.append(f"- [{f.stem}]({cat.name}/{f.name})")
        except Exception: continue
    write_file(mem / "INDEX.md", "\n".join(lines) + "\n")

def cmd_rebuild_index(args: argparse.Namespace) -> None:
    mem: Path = Path(args.memory_dir) if args.memory_dir else MEMORY_KB
    if not mem.exists():
        out({"status": "error", "message": f"Not found: {mem}"}); return
    _rebuild_memory_index(mem)
    out({"status": "ok", "path": str(mem / "INDEX.md")})

def cmd_backup(_: argparse.Namespace) -> None:
    try:
        subprocess.run(["git", "add", "-A", "--", ":(exclude).env", ":(exclude)*.env"], cwd=str(VAULT_DIR), timeout=60)
        msg = f"kb-manager backup {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        r = subprocess.run(["git", "commit", "-m", msg], cwd=str(VAULT_DIR),
                           capture_output=True, timeout=60, encoding="utf-8", errors="replace")
        out({"status": "ok", "message": "Backup committed" if r.returncode == 0 else "Nothing to commit"})
    except FileNotFoundError:
        out({"status": "error", "message": "git not found"})
    except Exception as e:
        out({"status": "error", "message": str(e)})

def _auto_categorize(file_path: Path, default: str, content: str, config: dict[str, Any]) -> str:
    hints: dict[str, str] = {"ai":"ai","ml":"ai","model":"ai","llm":"ai","code":"programming",
             "dev":"programming","python":"programming","tool":"tools","domain":"domain"}
    for part in file_path.parts:
        if part.lower() in hints: return hints[part.lower()]
    resp = call_nvidia(
        f"Categorize into one: ai,programming,tools,domain,references. Return ONLY category name.\n\n{content[:500]}",
        config)
    if resp and resp.strip().lower() in ("ai","programming","tools","domain","references"):
        return resp.strip().lower()
    return default

def cmd_batch_import(args: argparse.Namespace) -> None:
    src: Path = Path(args.folder)
    if not src.exists() or not src.is_dir():
        out({"status": "error", "message": f"Not a directory: {args.folder}"}); return
    to_mem: bool = args.to_memory
    cat_default: str = args.category or "general"
    mem: Path = Path(args.memory_dir) if args.memory_dir else MEMORY_KB
    config: dict[str, Any] = load_config()
    existing: set[str] = set()
    if IMPORT_DIR.exists():
        for f in IMPORT_DIR.rglob("*.md"):
            try: existing.add(content_hash(read_file(f)))
            except Exception: pass
    if to_mem and mem.exists():
        for f in mem.rglob("*.md"):
            try: existing.add(content_hash(read_file(f)))
            except Exception: pass
    docs = load_documents()
    imported: int = 0
    skipped: int = 0
    errors: list[str] = []
    for fp in sorted(src.rglob("*")):
        if not fp.is_file() or fp.suffix.lower() not in (".md", ".txt"): continue
        try: content = read_file(fp)
        except Exception as e: errors.append(f"{fp.name}: {e}"); continue
        h = content_hash(content)
        if h in existing: skipped += 1; continue
        existing.add(h)
        title = fp.stem
        cat = _auto_categorize(fp, cat_default, content, config)
        slug = slugify(title)
        now = datetime.now().strftime("%Y-%m-%d")
        md = f'---\ntitle: "{title}"\ncategory: "{cat}"\ndate: "{now}"\nsource: "kb-manager batch-import"\n---\n\n# {title}\n\n{content}\n'
        out_path = unique_path(IMPORT_DIR, slug)
        write_file(out_path, md)
        docs.append({"path": f"01-Import/{out_path.name}", "title": title, "category": cat,
                      "entities": [], "concepts": [], "tags": [cat], "hash": h,
                      "created": datetime.now().isoformat(), "source": "batch-import"})
        if to_mem:
            (mem / cat).mkdir(parents=True, exist_ok=True)
            write_file(mem / cat / out_path.name, md)
        imported += 1
    save_documents(docs)
    if to_mem: _rebuild_memory_index(mem)
    out({"status": "ok", "imported": imported, "skipped": skipped, "errors": errors[:10]})

def cmd_list(_: argparse.Namespace) -> None:
    docs = load_documents()
    out({"total": len(docs), "documents": docs})

# --- Main ---
def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print("Usage: python kb-manager.py <command> [options]")
        print()
        print("Commands:")
        print("  init                          Initialize vault directories")
        print("  list                          List all documents")
        print("  analyze-text --title T --category C --file F  AI deep analysis")
        print("  unified-search <question>     Search both Memory + KB")
        print("  batch-import <folder>         Batch import documents")
        print("  sync-memory-to-kb --memory-dir D  Memory -> KB sync")
        print("  sync-kb-to-memory --memory-dir D  KB -> Memory sync")
        print("  rebuild-index --memory-dir D  Rebuild Memory INDEX.md")
        print("  backup                        Git auto-backup")
        sys.exit(0)
    p = argparse.ArgumentParser(description="KB Manager - Dual-track knowledge base CLI")
    s = p.add_subparsers(dest="command")
    s.add_parser("init", help="Create directory structure")
    pa = s.add_parser("analyze-text", help="Analyze and import content")
    pa.add_argument("--title", default=None)
    pa.add_argument("--category", default="general")
    pa.add_argument("--file", default=None)
    pa.add_argument("--text", default=None)
    ps = s.add_parser("unified-search", help="Search both tracks")
    ps.add_argument("query")
    s.add_parser("sync-memory-to-kb", help="Sync memory to vault").add_argument("--memory-dir", default=None)
    s.add_parser("sync-kb-to-memory", help="Sync vault to memory").add_argument("--memory-dir", default=None)
    pr = s.add_parser("rebuild-index", help="Rebuild memory INDEX.md")
    pr.add_argument("--memory-dir", default=None)
    s.add_parser("backup", help="Git backup vault")
    pb = s.add_parser("batch-import", help="Import folder of documents")
    pb.add_argument("folder")
    pb.add_argument("--to-memory", action="store_true")
    pb.add_argument("--category", default="general")
    pb.add_argument("--memory-dir", default=None)
    s.add_parser("list", help="List all documents")
    args = p.parse_args()
    if not args.command: p.print_help(); sys.exit(1)
    cmds: dict[str, Any] = {"init": cmd_init, "analyze-text": cmd_analyze_text, "unified-search": cmd_unified_search,
            "sync-memory-to-kb": cmd_sync_memory_to_kb, "sync-kb-to-memory": cmd_sync_kb_to_memory,
            "rebuild-index": cmd_rebuild_index, "backup": cmd_backup, "batch-import": cmd_batch_import,
            "list": cmd_list}
    cmds[args.command](args)

if __name__ == "__main__":
    main()
