# Skill Router · Mission Control Dashboard

FastAPI + HTMX + Tailwind + Chart.js. Localhost-only (`127.0.0.1:9300`).
Lee `clusters.yaml` (v2/) y el audit JSONL (v3-niveldios/audit/log/).
Escribe SOLO en `clusters.yaml` (con backup .bak automatico) y en su propio `jobs/` dir.

---

## Quick start

```bash
# arrancar (background)
~/.claude/skill-router/v3-niveldios/dashboard/bin/router-dashboard start

# o tras el symlink (recomendado)
ln -sf ~/.claude/skill-router/v3-niveldios/dashboard/bin/router-dashboard ~/.local/bin/router-dashboard
router-dashboard start
router-dashboard status      # check + curl /health
router-dashboard logs        # tail -f
router-dashboard test        # pytest suite (7/7)
router-dashboard stop
router-dashboard restart
```

UI viva en:

| URL | Vista |
|---|---|
| http://127.0.0.1:9300/ | Overview — 4 cards live (clusters, hit-rate, ghosts, eventos) + chart 14d + top clusters/skills/gaps |
| http://127.0.0.1:9300/clusters | Tabla de los 20 clusters con stats por ventana |
| http://127.0.0.1:9300/clusters/{id} | Detail con YAML + stats + triggers + gate_reminder |
| http://127.0.0.1:9300/clusters/{id}/edit | Editor textarea con validacion server-side antes de escribir |
| http://127.0.0.1:9300/skills | Tabla skills enriquecida (active/ghost/missing) |
| http://127.0.0.1:9300/audit | Log viewer JSONL con filtros session/days/limit |
| http://127.0.0.1:9300/stats | Charts agregados (line + bar) + raw summary JSON |

JSON endpoints:

| URL | Devuelve |
|---|---|
| `GET /health` | `{status, version, clusters_count, clusters_yaml_exists, audit_log_files, last_event_ts, host, port, embeddings_dir_exists, evolve_dir_exists}` |
| `GET /stats/summary?days=7` | total_events, hit_rate, top_clusters, top_skills_suggested, top_skills_invoked, ghost_count, bypass_usage, blocked_tools |
| `GET /stats/clusters?days=7` | array por cluster (activations, skills_suggested, skills_invoked, invoke_rate, last_seen) |
| `GET /stats/daily?days=14` | serie temporal `[{date, count}]` |
| `GET /stats/gaps?days=14` | prompts sin cluster + samples |
| `GET /jobs?limit=20` | jobs lanzados desde la UI |
| `GET /jobs/{id}` | estado de un job concreto |

Acciones:

| URL | Que hace |
|---|---|
| `POST /clusters/{id}` (form `cluster_yaml=<yaml>`) | Backup + validate + write. 200/422 con `{ok, errors[], backup_path}` |
| `POST /actions/rebuild-embeddings` | Lanza job background contra `embeddings/bench/build_index.py` (no-op si Agent C aun no desplegado) |
| `POST /actions/evolve?dry_run=true` | Lanza `evolve/bin/router-evolve --dry-run` (no-op fallback) |

---

## Auth

- Bind: `127.0.0.1:9300` (override con `ROUTER_DASH_HOST` / `ROUTER_DASH_PORT`).
- No expone fuera del Mac. Sin tokens / cookies / login.

---

## Tests

```bash
router-dashboard test
# o
cd ~/.claude/skill-router/v3-niveldios/dashboard && ./venv/bin/python -m pytest tests/ -q
```

7/7 pytest (E2E con TestClient sobre la app real, filesystem aislado por fixture):

- T1 GET / -> 200 + 'skill router'
- T2 GET /clusters -> lista clusters reales
- T3 POST /clusters/{id} con YAML invalido -> 422 + NO escritura
- T4 POST /clusters/{id} valido -> backup .bak + write + reload
- T5 GET /audit con filtros -> aplica correctamente
- T6 POST /actions/rebuild-embeddings -> devuelve job_id + ejecuta runner background
- T7 GET /health -> JSON con campos canonicos

Screenshots visuales:

```bash
cd ~/.claude/skill-router/v3-niveldios/dashboard && ./venv/bin/python tests/capture_screenshots.py
# genera screenshots/{home,clusters,cluster_detail,audit}.png
```

---

## Filesystem contract

```
dashboard/
  app/
    main.py            FastAPI routes
    config.py          paths + bind
    clusters_io.py     load/validate/save clusters.yaml (jsonschema)
    audit_io.py        JSONL reader + aggregator
    skills_io.py       SKILL.md discovery + invocation enrichment
    jobs.py            async job runner (threading) para rebuild/evolve
    templates/         Jinja2 (base, home, clusters, cluster_detail, cluster_edit, skills, audit, stats, partials/)
  bin/router-dashboard control script (start/stop/restart/status/logs/test)
  tests/               pytest + conftest (filesystem aislado por session) + capture_screenshots.py
  venv/                Python 3.12 + fastapi, uvicorn[standard], jinja2, pyyaml, jsonschema, python-multipart, httpx, pytest, playwright
  backups/             clusters.yaml.bak-YYYYMMDD-HHMMSS (rotation manual)
  jobs/jobs.jsonl      append-only job audit
  log/dashboard.log    uvicorn stdout/stderr
  pid/dashboard.pid    PID activo
  screenshots/         home.png, clusters.png, cluster_detail.png, audit.png
```

Lee de:
- `~/.claude/skill-router/v2/clusters.yaml` (read-only salvo POST /clusters/{id})
- `~/.claude/skill-router/v3-niveldios/audit/log/*.jsonl` (read-only)
- `~/.claude/skills/*/SKILL.md` + `~/.claude/plugins/**/skills/*/SKILL.md` (read-only, scan a 1 nivel)

Escribe en:
- `~/.claude/skill-router/v2/clusters.yaml` (solo desde editor UI, siempre con backup en `dashboard/backups/`)
- `dashboard/{backups,jobs,log,pid}/`

---

## Live updates

- HTMX polling cada 15s sobre `#overview-cards` (`hx-get /partials/overview-cards hx-trigger every 15s`).
- Pages restantes: refresh manual (deliberado, evita carga innecesaria sobre disco).

---

## Despliegue VPS (futuro, NO implementar ahora)

Patron alineado con resto de paneles CKS (Phoenix, mando, oficina, sincro, hermes):

1. Container Python en host (no Docker — overkill para sidecar):
   ```bash
   # systemd unit /etc/systemd/system/router-dashboard.service
   [Service]
   ExecStart=/opt/skill-router-dashboard/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 9300
   ```
2. Traefik dynamic config (`/etc/traefik/dynamic/router-dashboard.yml`):
   ```yaml
   http:
     routers:
       router-dashboard:
         rule: "Host(`router.example.com`)"
         service: router-dashboard
         entryPoints: [websecure]
         tls: { certResolver: letsencrypt }
         middlewares: [tinyauth@file]
     services:
       router-dashboard:
         loadBalancer:
           servers:
             - url: "http://127.0.0.1:9300"
   ```
3. DNS Cloudflare: A `router.example.com -> your.vps.ip` (proxy gris, DNS only).
4. Verify: `curl -fsS https://router.example.com/health` con basic auth tinyauth.

NO hacerlo hasta que: (a) audit log tenga >7 dias de datos reales, (b) cluster editor probado contra prod local, (c) ADR redactado.

---

## Health JSON schema

```json
{
  "status": "ok",
  "version": "1.0.0",
  "clusters_count": 20,
  "clusters_yaml_path": "~/.claude/skill-router/v2/clusters.yaml",
  "clusters_yaml_exists": true,
  "audit_log_dir": "~/.claude/skill-router/v3-niveldios/audit/log",
  "audit_log_files": 0,
  "last_event_ts": null,
  "embeddings_dir_exists": true,
  "evolve_dir_exists": true,
  "host": "127.0.0.1",
  "port": 9300
}
```

`status` = `ok` salvo que `clusters.yaml` falle parseo (entonces `degraded`).

---

## Reglas duras respetadas

- NO toca codigo en `v2/`. Solo lectura del clusters.yaml + state.json.
- Edit clusters.yaml = backup `.bak-<timestamp>` SIEMPRE pre-write + validation jsonschema.
- venv local en `dashboard/venv/`, no global.
- Localhost-only por defecto; VPS solo via Traefik + basicauth.
- Tests aislan filesystem (conftest redirige paths a tmp_path_factory).
