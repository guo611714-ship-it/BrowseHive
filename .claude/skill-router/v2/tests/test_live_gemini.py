#!/usr/bin/env python3
"""
Test LIVE de integración con Gemini Flash.

Hace llamadas REALES a la API. Coste estimado: ~$0.002 por ejecución completa.
Skipea si no hay GEMINI_API_KEY disponible.

Run:
    python3 ~/.claude/skill-router/v2/tests/test_live_gemini.py
"""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTER_V2 = HERE.parent
sys.path.insert(0, str(ROUTER_V2))

import yaml  # noqa: E402
import llm_match  # noqa: E402

CLUSTERS_YAML = ROUTER_V2 / "clusters.yaml"

# Frases naturales españolas → cluster esperado
TEST_PHRASES = [
    ("abre el panel financiero", "finance"),
    ("vamos con finanzas", "finance"),
    ("necesito analizar las métricas SaaS", "finance"),
    ("vamos a hacer un pitch deck para inversores", "pitch"),
    ("necesito preparar la presentación de fundraising", "pitch"),
    ("hoy va de revisar PRs", "pr_review"),
    ("audita este pull request", "pr_review"),
    ("necesito investigar la librería de Stripe", "research"),
    ("vamos con marketing", "marketing"),
    ("ideas de copy para landing", "marketing"),
    ("lanza varios agentes en paralelo", "agenthub"),
    # Frases ambiguas → no match
    ("hola", None),
    ("ok perfecto gracias", None),
    ("no se que hacer", None),
]


class TestLiveGemini(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_key = llm_match.get_api_key()
        if not cls.api_key:
            raise unittest.SkipTest("No GEMINI_API_KEY available — skip live tests")

        cls.clusters_config = yaml.safe_load(CLUSTERS_YAML.read_text())
        cls.clusters = cls.clusters_config.get("clusters", {})

    def test_all_phrases(self):
        """Mide accuracy del matching semántico contra fixtures."""
        correct = 0
        incorrect = []
        for phrase, expected in TEST_PHRASES:
            result = llm_match.match_semantic(phrase, self.clusters)
            actual = result["cluster_match"] if result else None

            match = (actual == expected)
            # También aceptar None vs ambiguo (confidence baja)
            if expected is None and result and not result["cluster_match"]:
                match = True

            if match:
                correct += 1
            else:
                incorrect.append({
                    "phrase": phrase,
                    "expected": expected,
                    "actual": actual,
                    "confidence": result.get("confidence") if result else None,
                    "reason": result.get("reason") if result else "(no result)",
                })

        total = len(TEST_PHRASES)
        accuracy = correct / total
        print(f"\n=== Accuracy: {correct}/{total} ({accuracy*100:.0f}%) ===")
        if incorrect:
            print("Misses:")
            for m in incorrect:
                print(f"  '{m['phrase']}' expected={m['expected']} actual={m['actual']} (conf={m['confidence']})")
                print(f"     reason: {m['reason']}")

        # Aceptamos >=80% accuracy (es matching semántico, no exacto)
        self.assertGreaterEqual(accuracy, 0.8, f"Accuracy {accuracy*100:.0f}% < 80%")


if __name__ == "__main__":
    unittest.main(verbosity=2)
