"""
llm_match.py — Semantic matching con Gemini Flash 2.0.

Toma un prompt en español de David + catálogo de clusters y devuelve
el mejor match con confidence score. Si falla (red, cuota, etc.),
retorna None para que el caller haga fallback al router V1.
"""

import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional


def _make_ssl_context() -> ssl.SSLContext:
    """Crea contexto SSL usando certifi si está disponible (fix macOS Python.org)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
# gemini-2.5-flash es el actual; gemini-2.5-flash-lite es más barato pero menos preciso.
# Si está fuera de servicio, fallback a gemini-flash-latest.
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_MODEL_FALLBACK = "gemini-flash-latest"
GEMINI_ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
)
TIMEOUT_SECONDS = 8.0
# Coste estimado Gemini 2.5 Flash: input $0.30 / 1M tokens, output $2.50 / 1M tokens.
# Prompt típico ~ 1500 input + 200 output tokens (incluye thinking).
COST_PER_CALL_USD = (1500 * 0.30 + 200 * 2.50) / 1_000_000  # ~0.000950 USD
# Con 100 calls/day → ~$2.85/mes. Con cache 1h y dedup → realista <$1/mes.


def get_api_key() -> Optional[str]:
    """Busca GEMINI_API_KEY en env y fallback en .env conocidos."""
    key = os.environ.get(GEMINI_API_KEY_ENV)
    if key and key.strip():
        return key.strip()
    # Fallback: leer de .env conocidos en orden de prioridad
    candidate_paths = [
        Path.home() / ".claude" / "skill-router" / "v2" / ".env",
        Path.home() / "Desktop" / "cks-system" / ".env.local",
        Path.home() / "Desktop" / "cks-system" / ".env",
        Path.home() / "Desktop" / "HACKER-CKS" / ".env",
        Path.home() / "Desktop" / "OPENCLAW" / ".env",
        Path.home() / ".env",
    ]
    for env_path in candidate_paths:
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                # Soportar `export GEMINI_API_KEY=...` y `GEMINI_API_KEY=...`
                if line.startswith("export "):
                    line = line[len("export "):]
                if line.startswith("GEMINI_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
        except OSError:
            continue
    return None


def hash_prompt(prompt: str, clusters_signature: str) -> str:
    """Hash determinístico de prompt + clusters para caché."""
    blob = f"{prompt.strip().lower()}||{clusters_signature}"
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def build_clusters_signature(clusters: Dict) -> str:
    """Hash de la config de clusters para invalidar caché si cambia el YAML."""
    blob = json.dumps(clusters, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:8]


def build_prompt(user_text: str, clusters: Dict, cwd: str = "") -> str:
    """Construye el prompt que se envía a Gemini Flash."""
    cluster_descriptions = []
    for name, spec in clusters.items():
        triggers = spec.get("triggers_natural", [])
        triggers_str = "; ".join(triggers[:6])
        desc = spec.get("description", "")
        cluster_descriptions.append(
            f'- "{name}": {desc}\n  Frases típicas: {triggers_str}'
        )
    catalog = "\n".join(cluster_descriptions)

    cwd_hint = ""
    if cwd:
        if "cks-system" in cwd:
            cwd_hint = "\nContexto: el usuario está en el proyecto cks-system (Car Key System)."
        elif "openclaw" in cwd.lower():
            cwd_hint = "\nContexto: el usuario está en el proyecto OpenClaw."

    return f"""Eres un router de skills para Claude Code. El usuario es David, CEO de Car Key System (España), NO es desarrollador. Habla español de España.

Recibirás un mensaje suyo y debes decidir qué CLUSTER de skills activar (o ninguno).

CLUSTERS DISPONIBLES:
{catalog}
{cwd_hint}

REGLAS:
1. Si el mensaje matchea claramente un cluster → devuelve cluster_match con confidence >= 0.7.
2. Si es ambiguo o no matchea ninguno → cluster_match: null, confidence < 0.5.
3. NUNCA inventes clusters que no estén en la lista.
4. Si el mensaje es trivial ("hola", "ok", "vale", "gracias"), devuelve null.
5. Si menciona explícitamente un nombre de cluster ("abre marketing", "vamos con finanzas"), confidence >= 0.85.
6. Devuelve SOLO JSON válido. Sin texto adicional. Sin markdown.

MENSAJE DEL USUARIO:
"{user_text[:1000]}"

RESPUESTA (JSON estricto):
{{
  "cluster_match": "nombre_cluster_o_null",
  "confidence": 0.0_a_1.0,
  "reason": "breve razón en español"
}}"""


def _call_gemini_once(prompt_text: str, api_key: str, model: str) -> Optional[Dict]:
    """Una sola llamada a Gemini con el modelo dado. None si falla."""
    url = GEMINI_ENDPOINT_TEMPLATE.format(model=model, key=api_key)
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "temperature": 0.1,
            # Gemini 2.5 Flash usa "thinking tokens" que cuentan aquí.
            # 1024 da margen para razonamiento + respuesta JSON breve.
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    ctx = _make_ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw)
            candidates = payload.get("candidates", [])
            if not candidates:
                return None
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                return None
            text = parts[0].get("text", "").strip()
            if not text:
                return None
            # Limpiar code fences si los hay
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            return json.loads(text)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def call_gemini(prompt_text: str, api_key: str) -> Optional[Dict]:
    """
    Llama a Gemini con modelo principal. Si falla con 404 (modelo deprecado)
    intenta fallback model. Si todo falla → None.
    """
    result = _call_gemini_once(prompt_text, api_key, GEMINI_MODEL)
    if result is not None:
        return result
    # Fallback model
    return _call_gemini_once(prompt_text, api_key, GEMINI_MODEL_FALLBACK)


def match_semantic(
    user_text: str,
    clusters: Dict,
    cwd: str = "",
    cache_lookup=None,
    cache_store=None,
) -> Optional[Dict]:
    """
    Match semántico con Gemini Flash.

    Returns:
        Dict con {cluster_match, confidence, reason, skills, cost_usd} o None si:
        - No hay API key
        - LLM falla
        - Confidence < threshold del cluster matcheado
    """
    api_key = get_api_key()
    if not api_key:
        return None

    sig = build_clusters_signature(clusters)
    p_hash = hash_prompt(user_text, sig)

    # Cache hit?
    if cache_lookup:
        cached = cache_lookup(p_hash)
        if cached:
            return cached

    prompt_text = build_prompt(user_text, clusters, cwd)
    result = call_gemini(prompt_text, api_key)
    if not result:
        return None

    cluster_name = result.get("cluster_match")
    confidence = float(result.get("confidence", 0))
    reason = result.get("reason", "")

    # Validar contra threshold del cluster
    if cluster_name and cluster_name in clusters:
        threshold = clusters[cluster_name].get("confidence_threshold", 0.7)
        if confidence < threshold:
            final = {
                "cluster_match": None,
                "confidence": confidence,
                "reason": f"Confidence {confidence:.2f} < threshold {threshold} para cluster `{cluster_name}`",
                "skills": [],
                "cost_usd": COST_PER_CALL_USD,
            }
        else:
            # Verificar cwd_required si aplica
            cwd_req = clusters[cluster_name].get("cwd_required")
            if cwd_req and cwd_req not in (cwd or ""):
                final = {
                    "cluster_match": None,
                    "confidence": confidence,
                    "reason": f"Cluster `{cluster_name}` requiere cwd contiene `{cwd_req}`",
                    "skills": [],
                    "cost_usd": COST_PER_CALL_USD,
                }
            else:
                final = {
                    "cluster_match": cluster_name,
                    "confidence": confidence,
                    "reason": reason,
                    "skills": clusters[cluster_name].get("skills", []),
                    "cost_usd": COST_PER_CALL_USD,
                }
    else:
        final = {
            "cluster_match": None,
            "confidence": confidence,
            "reason": reason or "Sin match claro",
            "skills": [],
            "cost_usd": COST_PER_CALL_USD,
        }

    # Store en cache
    if cache_store:
        cache_store(p_hash, final)

    return final


def estimate_monthly_cost(calls_per_day: int = 100) -> float:
    """Estima coste mensual con N llamadas/día."""
    return calls_per_day * 30 * COST_PER_CALL_USD
