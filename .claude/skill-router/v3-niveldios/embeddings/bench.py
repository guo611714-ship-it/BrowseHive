#!/usr/bin/env python3
"""
bench.py — Benchmark del retriever semántico.

25 queries con la skill esperada en top-1. Mide:
  - Top-1 accuracy
  - Top-3 accuracy
  - Mean Reciprocal Rank (MRR)
  - Latencia mediana, p95
  - Latencia warm-up (cold start)

Cada query lista 1 o más nombres válidos (aliases por plugin: `commit-work`,
`superpowers:commit-work`, `commit-commands:commit`). Match si el NOMBRE de
la skill en los top-K coincide con cualquiera de los aliases válidos.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from search import search_skills, warmup, manifest  # noqa: E402


# (query, [aliases válidos como top-1/top-K])
BENCH: list[tuple[str, list[str]]] = [
    ("voy a hacer commit y push", ["commit-work", "commit", "commit-push-pr"]),
    ("tengo que limpiar worktrees", ["worktree-sync-pro", "using-git-worktrees"]),
    ("necesito ejecutar query supabase", ["supabase", "cks-supabase-rls", "supabase-postgres-best-practices"]),
    ("edit SOUL maestro openclaw", ["openclaw-expert", "cks-session", "cks-stack"]),
    ("voy a debugear hermes credpool", ["systematic-debugging", "cks-debug-protocol"]),
    ("deploy a vercel cks-system", ["cks-deploy-checklist", "vercel:deploy", "cks-deploy", "deploy"]),
    ("crear un nuevo skill desde cero", ["skill-creator", "writing-skills", "skill-forge"]),
    ("revisar pull request en github", ["pr-review-toolkit:review-pr", "code-review", "code-review:code-review", "engineering-advanced-pr-review-expert"]),
    ("escribir tests unitarios antes de implementar", ["test-driven-development"]),
    ("planificar tareas para un feature complejo", ["writing-plans", "planning-with-files"]),
    ("auditar seguridad de una skill antes de instalar", ["engineering-advanced-skill-security-auditor"]),
    ("optimizar campaña de paid ads facebook", ["marketing-paid-ads", "paid-ads"]),
    ("analizar competidores y posicionamiento", ["competitor-profiling", "competitor-alternatives", "marketing-competitor-alternatives"]),
    ("diseñar arquitectura de microservicios", ["engineering-advanced-database-designer", "c4-architecture", "engineering:architecture", "engineering:system-design"]),
    ("escribir copy de landing page que convierta", ["copywriting", "marketing-copywriting", "marketing-page-cro", "page-cro"]),
    ("hacer email sequence onboarding", ["email-sequence", "marketing-email-sequence", "marketing:email-sequence"]),
    ("crear dashboard con KPIs ejecutivos", ["kpi-dashboard-design", "c-level-board-deck-builder", "data:build-dashboard"]),
    ("optimizar SEO técnico de la web", ["seo-audit", "marketing-seo-audit"]),
    ("brainstorming antes de meter código", ["brainstorming", "superpowers:brainstorming"]),
    ("crear una pull request con buenos commits", ["commit-push-pr", "commit-commands:commit-push-pr"]),
    ("verificar que el trabajo está terminado antes de cerrar", ["verification-before-completion", "superpowers:verification-before-completion", "cks-verify-done"]),
    ("formulario CKS para crear caso nuevo", ["cks-form-optimization"]),
    ("buscar procedimiento de Sergio para BMW", ["cks-sergio-api", "cks-procedure-quality"]),
    ("escribir post viral en LinkedIn", ["marketing-social-content", "marketing-x-twitter-growth", "social-content"]),
    ("ejecutar agentes en paralelo en worktrees aislados", ["dispatching-parallel-agents", "superpowers:dispatching-parallel-agents", "subagent-driven-development", "superpowers:subagent-driven-development"]),
]


def is_match(name: str, aliases: list[str]) -> bool:
    """Match flexible: exacto, sufijo tras ":", o prefijo "plugin:"."""
    n = name.lower()
    for a in aliases:
        a_low = a.lower()
        if n == a_low:
            return True
        # n="superpowers:commit-work" vs a="commit-work"
        if n.endswith(":" + a_low):
            return True
        # n="commit-work" vs a="superpowers:commit-work"
        if a_low.endswith(":" + n):
            return True
    return False


def run_bench(top_k: int = 5, threshold: float = 0.5, verbose: bool = True) -> dict:
    cold = warmup()
    if verbose:
        m = manifest()
        print(f"[bench] backend={m['backend']} model={m['model']} dim={m['dimension']} skills={m['total_skills']}")
        print(f"[bench] warmup (cold)={cold:.2f}s")

    latencies: list[float] = []
    top1_hits = 0
    top3_hits = 0
    rr_sum = 0.0
    per_query: list[dict] = []

    for query, aliases in BENCH:
        t0 = time.time()
        results = search_skills(query, top_k=top_k, threshold=threshold)
        dt_ms = (time.time() - t0) * 1000
        latencies.append(dt_ms)

        rank_hit = None
        for i, r in enumerate(results, start=1):
            if is_match(r["name"], aliases):
                rank_hit = i
                break

        if rank_hit == 1:
            top1_hits += 1
        if rank_hit and rank_hit <= 3:
            top3_hits += 1
        if rank_hit:
            rr_sum += 1.0 / rank_hit

        per_query.append({
            "query": query,
            "aliases": aliases,
            "top_returned": [r["name"] for r in results],
            "scores": [round(r["score"], 3) for r in results],
            "rank_hit": rank_hit,
            "latency_ms": round(dt_ms, 1),
        })

        if verbose:
            tag = "OK" if rank_hit == 1 else (f"top{rank_hit}" if rank_hit else "MISS")
            top_str = ", ".join(r["name"] for r in results[:3])
            print(f"  [{tag:>5}] {dt_ms:6.1f}ms  q={query!r:<55}  -> {top_str}")

    n = len(BENCH)
    metrics = {
        "n_queries": n,
        "top1_accuracy": round(top1_hits / n, 4),
        "top3_accuracy": round(top3_hits / n, 4),
        "mrr": round(rr_sum / n, 4),
        "latency_ms_median": round(statistics.median(latencies), 2),
        "latency_ms_p95": round(sorted(latencies)[int(0.95 * (n - 1))], 2),
        "latency_ms_mean": round(statistics.mean(latencies), 2),
        "cold_start_seconds": round(cold, 2),
    }
    if verbose:
        print()
        print(f"[bench] top1     = {metrics['top1_accuracy']*100:.1f}%")
        print(f"[bench] top3     = {metrics['top3_accuracy']*100:.1f}%   (target ≥ 80%)")
        print(f"[bench] MRR      = {metrics['mrr']:.3f}")
        print(f"[bench] latency  = p50 {metrics['latency_ms_median']}ms · p95 {metrics['latency_ms_p95']}ms  (target < 100ms)")

    return {"metrics": metrics, "per_query": per_query}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()
    res = run_bench(top_k=args.top, threshold=args.threshold, verbose=not args.json)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
