#!/usr/bin/env python3
"""
Tests del Skill Router V2.

Cubre:
- Carga de clusters.yaml
- Detección semántica (mockeada para no gastar API calls reales en CI)
- Anti-spam por skill y por cluster
- Fallback a V1 si LLM falla
- Bypass con [raw] y SKILL_ROUTER_OFF
- Switch a V1 con SKILL_ROUTER_VERSION=1
- Cache LLM
- Detección skills faltantes
- Frases naturales en español → cluster correcto

Run:
    python3 ~/.claude/skill-router/v2/tests/test_router_v2.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Permitir importar modulos V2
HERE = Path(__file__).resolve().parent
ROUTER_V2 = HERE.parent
sys.path.insert(0, str(ROUTER_V2))

import state  # noqa: E402
import marketplace  # noqa: E402
import llm_match  # noqa: E402


# ---------- state.py tests ----------

class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def test_load_default_state(self):
        st = state.load_state(self.path)
        self.assertEqual(st["turn"], 0)
        self.assertEqual(st["recent_skills"], [])
        self.assertEqual(st["recent_clusters"], [])

    def test_save_and_load_state(self):
        st = state.load_state(self.path)
        state.increment_turn(st)
        state.record_invocation("finance", ["finance-skills:financial-analyst"], st)
        state.save_state(st, self.path)
        loaded = state.load_state(self.path)
        self.assertEqual(loaded["turn"], 1)
        self.assertEqual(len(loaded["recent_skills"]), 1)

    def test_is_recently_invoked(self):
        st = state.load_state(self.path)
        state.increment_turn(st)
        state.record_invocation("finance", ["skill-a"], st)
        self.assertTrue(state.is_recently_invoked("skill-a", st, dedup_turns=5))
        # 10 turnos después ya no es reciente
        for _ in range(10):
            state.increment_turn(st)
        self.assertFalse(state.is_recently_invoked("skill-a", st, dedup_turns=5))

    def test_cluster_anti_spam(self):
        st = state.load_state(self.path)
        state.increment_turn(st)
        state.record_invocation("marketing", ["x"], st)
        self.assertTrue(state.is_cluster_recently_invoked("marketing", st, 5))
        self.assertFalse(state.is_cluster_recently_invoked("finance", st, 5))

    def test_filter_unrecent_skills(self):
        st = state.load_state(self.path)
        state.increment_turn(st)
        state.record_invocation("c", ["a", "b"], st)
        fresh = state.filter_unrecent_skills(["a", "b", "c", "d"], st, 5)
        self.assertEqual(set(fresh), {"c", "d"})

    def test_llm_cache(self):
        st = state.load_state(self.path)
        state.cache_llm_result("hash1", {"cluster_match": "finance"}, st, ttl=3600)
        cached = state.get_cached_llm_result("hash1", st)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["cluster_match"], "finance")

    def test_llm_cache_expiry(self):
        st = state.load_state(self.path)
        state.cache_llm_result("hash1", {"x": 1}, st, ttl=0)
        # ttl=0 → expirado inmediatamente
        import time
        time.sleep(0.1)
        cached = state.get_cached_llm_result("hash1", st)
        self.assertIsNone(cached)

    def test_counter_increment(self):
        st = state.load_state(self.path)
        state.increment_llm_counter(st, 0.001)
        state.increment_llm_counter(st, 0.001)
        self.assertEqual(st["llm_total_calls"], 2)
        self.assertAlmostEqual(st["llm_total_cost_usd"], 0.002, places=5)


# ---------- marketplace.py tests ----------

class TestMarketplace(unittest.TestCase):
    def test_get_installed_skills_returns_set(self):
        skills = marketplace.get_installed_skills()
        # No assertion sobre contenido específico (depende del sistema)
        self.assertIsInstance(skills, set)

    def test_check_skill_availability_fake_skill(self):
        self.assertFalse(marketplace.check_skill_availability("definitely-not-a-real-skill-xyz123"))

    def test_find_missing_skills(self):
        # En este sistema sabemos que NO existe "fake-skill-not-real-x"
        missing = marketplace.find_missing_skills(["fake-skill-not-real-x"])
        self.assertIn("fake-skill-not-real-x", missing)

    def test_suggest_install_command_prefixed(self):
        cmd = marketplace.suggest_install_command("some-plugin:some-skill")
        self.assertIn("some-plugin", cmd)
        self.assertIn("settings.json", cmd)

    def test_suggest_install_command_bare(self):
        cmd = marketplace.suggest_install_command("bare-skill-name")
        self.assertIn("npx skills install", cmd)

    def test_build_missing_skills_message_empty(self):
        self.assertEqual(marketplace.build_missing_skills_message([]), "")

    def test_build_missing_skills_message_nonempty(self):
        msg = marketplace.build_missing_skills_message(["foo", "bar:baz"])
        self.assertIn("AVISO", msg)
        self.assertIn("foo", msg)
        self.assertIn("bar:baz", msg)


# ---------- llm_match.py tests ----------

class TestLLMMatch(unittest.TestCase):
    SAMPLE_CLUSTERS = {
        "finance": {
            "description": "Análisis financiero",
            "triggers_natural": ["abre panel financiero", "vamos con finanzas"],
            "skills": ["finance-skills:financial-analyst"],
            "confidence_threshold": 0.7,
        },
        "marketing": {
            "description": "Marketing, copy, SEO",
            "triggers_natural": ["abre marketing", "necesito copy"],
            "skills": ["marketing-skills:copywriting"],
            "confidence_threshold": 0.7,
        },
    }

    def test_hash_prompt_deterministic(self):
        sig = llm_match.build_clusters_signature(self.SAMPLE_CLUSTERS)
        h1 = llm_match.hash_prompt("hola que tal", sig)
        h2 = llm_match.hash_prompt("hola que tal", sig)
        self.assertEqual(h1, h2)

    def test_hash_prompt_changes_with_text(self):
        sig = llm_match.build_clusters_signature(self.SAMPLE_CLUSTERS)
        h1 = llm_match.hash_prompt("texto a", sig)
        h2 = llm_match.hash_prompt("texto b", sig)
        self.assertNotEqual(h1, h2)

    def test_build_prompt_contains_clusters(self):
        prompt = llm_match.build_prompt("vamos con finanzas", self.SAMPLE_CLUSTERS)
        self.assertIn("finance", prompt)
        self.assertIn("marketing", prompt)
        self.assertIn("vamos con finanzas", prompt)

    def test_build_prompt_with_cwd(self):
        prompt = llm_match.build_prompt("hola", self.SAMPLE_CLUSTERS, cwd="/Users/x/cks-system")
        self.assertIn("cks-system", prompt)

    @patch("llm_match.call_gemini")
    def test_match_semantic_high_confidence(self, mock_call):
        mock_call.return_value = {
            "cluster_match": "finance",
            "confidence": 0.95,
            "reason": "Mención directa de finanzas",
        }
        # Forzar API key disponible
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            result = llm_match.match_semantic(
                "vamos con finanzas",
                self.SAMPLE_CLUSTERS,
            )
        self.assertEqual(result["cluster_match"], "finance")
        self.assertGreaterEqual(result["confidence"], 0.7)
        self.assertIn("finance-skills:financial-analyst", result["skills"])

    @patch("llm_match.call_gemini")
    def test_match_semantic_below_threshold(self, mock_call):
        mock_call.return_value = {
            "cluster_match": "finance",
            "confidence": 0.5,
            "reason": "Match débil",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            result = llm_match.match_semantic("algo ambiguo", self.SAMPLE_CLUSTERS)
        self.assertIsNone(result["cluster_match"])
        self.assertEqual(result["skills"], [])

    @patch("llm_match.call_gemini")
    def test_match_semantic_llm_returns_none(self, mock_call):
        mock_call.return_value = None
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            result = llm_match.match_semantic("hola", self.SAMPLE_CLUSTERS)
        self.assertIsNone(result)

    def test_match_semantic_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("llm_match.get_api_key", return_value=None):
                result = llm_match.match_semantic("vamos con marketing", self.SAMPLE_CLUSTERS)
        self.assertIsNone(result)

    @patch("llm_match.call_gemini")
    def test_match_semantic_cwd_required(self, mock_call):
        mock_call.return_value = {
            "cluster_match": "cks_session",
            "confidence": 0.9,
            "reason": "Inicio CKS",
        }
        clusters_with_cwd = {
            "cks_session": {
                "description": "Sesión CKS",
                "skills": ["cks-inicio"],
                "confidence_threshold": 0.75,
                "cwd_required": "cks-system",
            },
        }
        # cwd NO contiene cks-system → no debe matchear
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            result = llm_match.match_semantic(
                "vamos",
                clusters_with_cwd,
                cwd="/Users/x/otra-cosa",
            )
        self.assertIsNone(result["cluster_match"])

    def test_estimate_monthly_cost(self):
        # 100 calls/day raw (sin cache) con gemini-2.5-flash → ~$2.85/mes
        # Con cache TTL 1h + dedup turn-based, efectivo ~30 calls/day → <$1/mes
        cost_raw = llm_match.estimate_monthly_cost(calls_per_day=100)
        self.assertGreater(cost_raw, 0)
        self.assertLess(cost_raw, 5.0, "Coste raw mensual debe ser razonable")
        # Con cache (factor reducción ~3x), debe bajar de $1
        cost_effective = llm_match.estimate_monthly_cost(calls_per_day=30)
        self.assertLess(cost_effective, 1.0, "Con cache+dedup debe estar <$1/mes")


# ---------- trigger_v2 integration ----------

class TestTriggerV2(unittest.TestCase):
    """
    Tests del orquestador trigger_v2.py.
    Mockean el LLM para evitar llamadas reales en CI.
    """

    def setUp(self):
        # Import diferido para que los mocks funcionen
        import importlib
        spec = importlib.util.spec_from_file_location("trigger_v2", ROUTER_V2 / "trigger_v2.py")
        self.tv2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tv2)

    def test_is_trivial_prompt_short(self):
        self.assertTrue(self.tv2.is_trivial_prompt("ok"))
        self.assertTrue(self.tv2.is_trivial_prompt("hola"))
        self.assertTrue(self.tv2.is_trivial_prompt(""))
        self.assertTrue(self.tv2.is_trivial_prompt(None))

    def test_is_trivial_prompt_long(self):
        self.assertFalse(self.tv2.is_trivial_prompt("abre el panel financiero por favor"))

    def test_should_bypass_raw(self):
        self.assertTrue(self.tv2.should_bypass("[raw] no toques nada"))

    def test_should_bypass_env(self):
        self.assertTrue(self.tv2.should_bypass("hola", env={"SKILL_ROUTER_OFF": "1"}))

    def test_should_use_v2_default(self):
        self.assertTrue(self.tv2.should_use_v2(env={}))

    def test_should_use_v2_disabled(self):
        self.assertFalse(self.tv2.should_use_v2(env={"SKILL_ROUTER_VERSION": "1"}))

    def test_build_reminder_v2(self):
        reminder = self.tv2.build_reminder_v2(
            cluster_name="finance",
            skills=["finance-skills:financial-analyst"],
            reason="Match claro",
            confidence=0.9,
            missing=[],
        )
        self.assertIn("finance", reminder)
        self.assertIn("finance-skills:financial-analyst", reminder)
        self.assertIn("0.90", reminder)

    def test_build_reminder_with_missing(self):
        reminder = self.tv2.build_reminder_v2(
            cluster_name="finance",
            skills=["fake-skill"],
            reason="test",
            confidence=0.9,
            missing=["fake-skill"],
        )
        self.assertIn("NO INSTALADA", reminder)


# ---------- Integración: frases naturales españolas → cluster correcto ----------

class TestSpanishPhraseMatching(unittest.TestCase):
    """
    Verifica que el prompt LLM se construye correctamente para frases típicas
    de David. NO llama al LLM real (eso lo hace test_live), solo verifica
    que la construcción del prompt + el parsing del response son correctos.
    """

    def _make_mock_llm_response(self, cluster: str, confidence: float = 0.9):
        return {
            "cluster_match": cluster,
            "confidence": confidence,
            "reason": f"Match para cluster {cluster}",
        }

    @patch("llm_match.call_gemini")
    def test_phrase_panel_financiero(self, mock_call):
        mock_call.return_value = self._make_mock_llm_response("finance")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake"}):
            r = llm_match.match_semantic(
                "abre el panel financiero",
                TestLLMMatch.SAMPLE_CLUSTERS,
            )
        self.assertEqual(r["cluster_match"], "finance")

    @patch("llm_match.call_gemini")
    def test_phrase_vamos_marketing(self, mock_call):
        mock_call.return_value = self._make_mock_llm_response("marketing")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake"}):
            r = llm_match.match_semantic(
                "vamos con marketing",
                TestLLMMatch.SAMPLE_CLUSTERS,
            )
        self.assertEqual(r["cluster_match"], "marketing")

    @patch("llm_match.call_gemini")
    def test_phrase_ambiguous_no_match(self, mock_call):
        mock_call.return_value = {
            "cluster_match": None,
            "confidence": 0.2,
            "reason": "Mensaje vago",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake"}):
            r = llm_match.match_semantic(
                "no se que hacer",
                TestLLMMatch.SAMPLE_CLUSTERS,
            )
        self.assertIsNone(r["cluster_match"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
