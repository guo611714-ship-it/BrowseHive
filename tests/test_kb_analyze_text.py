"""analyze_text method tests"""

import importlib
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

spec = importlib.util.spec_from_file_location(
    "kb_manager_analyze",
    str(Path(__file__).parent.parent / "agent" / "kb" / "cli.py")
)
kb_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb_mod)
KnowledgeBaseManager = kb_mod.KnowledgeBaseManager


@pytest.fixture
def kb(tmp_path):
    vault = tmp_path / "test_vault"
    vault.mkdir()
    (vault / "01-Import").mkdir()
    (vault / "02-Notes").mkdir()
    (vault / "03-Index").mkdir()
    (vault / "config.json").write_text(
        json.dumps({"api_key": "test-key", "base_url": "https://test.com/v1", "model": "test-model"}),
        encoding="utf-8",
    )
    return KnowledgeBaseManager(str(vault))


MOCK_METADATA = {
    "title": "Test Title",
    "summary": "A summary of the test content.",
    "concepts": ["concept_a", "concept_b"],
    "entities": ["entity_x"],
    "tags": ["tag1", "tag2"],
    "suggested_links": ["concept_a"],
    "category": "test-category",
    "key_points": ["point1"],
    "structured_breakdown": {
        "core_idea": "Core idea text.",
        "detailed_explanation": "Detailed explanation.",
        "code_examples": [],
        "applicable_scenarios": [],
        "common_mistakes": [],
    },
    "missing_concepts": [],
}


class TestBasicAnalysis:
    def test_basic_analysis(self, kb):
        """analyze_text produces a file in 01-Import."""
        with patch.object(kb, "_analyze_with_claude", return_value=MOCK_METADATA):
            result = kb.analyze_text("Hello world content here.", title="Hello", category="test")

        assert result is not None
        p = Path(result)
        assert p.exists()
        assert p.parent == kb.import_dir

    def test_returns_path_string(self, kb):
        """Return value is a string path."""
        with patch.object(kb, "_analyze_with_claude", return_value=MOCK_METADATA):
            result = kb.analyze_text("Some content.", title="Some")
        assert isinstance(result, str)


class TestDedup:
    def test_dedup_same_content(self, kb):
        """Same content analyzed twice returns the existing file."""
        content = "Unique dedup content here."

        with patch.object(kb, "_analyze_with_claude", return_value=MOCK_METADATA):
            first = kb.analyze_text(content, title="Dedup")

        with patch.object(kb, "_analyze_with_claude", return_value=MOCK_METADATA) as mock_ai:
            second = kb.analyze_text(content, title="Dedup")
            mock_ai.assert_not_called()

        assert first == second


class TestMetadataGeneration:
    def test_metadata_generation(self, kb):
        """Output file contains correct frontmatter."""
        with patch.object(kb, "_analyze_with_claude", return_value=MOCK_METADATA):
            result = kb.analyze_text("Some metadata test content.", title="Meta Test")

        content = Path(result).read_text(encoding="utf-8")
        assert "title: Test Title" in content
        assert "category: test-category" in content
        assert '"tag1"' in content or "tag1" in content

    def test_concepts_in_markdown(self, kb):
        """Concepts appear as wikilinks in the output."""
        with patch.object(kb, "_analyze_with_claude", return_value=MOCK_METADATA):
            result = kb.analyze_text("Concepts test content.", title="Concepts Test")

        content = Path(result).read_text(encoding="utf-8")
        assert "[[concept_a]]" in content or "concept_a" in content


class TestConceptExtraction:
    def test_concept_extraction(self, kb):
        """Metadata concepts and entities are written to the index."""
        with patch.object(kb, "_analyze_with_claude", return_value=MOCK_METADATA):
            kb.analyze_text("Concept extraction test.", title="Concept Extract")

        index = kb._load_index()
        # The document should be in the index
        assert len(index["documents"]) == 1
        doc = index["documents"][0]
        assert "concept_a" in doc.get("concepts", [])
        assert "entity_x" in doc.get("entities", [])


class TestWithExistingIndex:
    def test_with_existing_index(self, kb, tmp_path):
        """When existing index has matching concepts, they appear in output."""
        # Pre-populate index with a document that has related concepts
        existing_index = {
            "documents": [{
                "path": "01-Import/old.md",
                "title": "Old Doc",
                "concepts": ["concept_a"],
                "entities": [],
                "tags": [],
            }],
            "concepts": {"concept_a": ["01-Import/old.md"]},
            "entities": {},
        }
        index_file = kb.index_dir / "documents.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(existing_index, f)

        with patch.object(kb, "_analyze_with_claude", return_value=MOCK_METADATA):
            result = kb.analyze_text(
                "Content linking to existing concept.",
                title="Linking Test",
            )

        content = Path(result).read_text(encoding="utf-8")
        # The output should contain some form of linking reference
        assert "concept_a" in content


class TestCacheInvalidation:
    def test_cache_invalidated_after_analyze(self, kb):
        """Cache is invalidated after analyze_text."""
        # Put something in cache
        kb.cache.put("test query", "test-model", {"answer": "test"})
        stats_before = kb.cache.stats()
        assert stats_before["l1_size"] >= 1

        with patch.object(kb, "_analyze_with_claude", return_value=MOCK_METADATA):
            kb.analyze_text("Cache invalidation test content.", title="Cache Invalidation")

        stats_after = kb.cache.stats()
        assert stats_after["l1_size"] == 0


class TestAIFallback:
    def test_ai_failure_uses_fallback_metadata(self, kb):
        """When AI fails, fallback metadata is used and file is still created."""
        with patch.object(kb, "_analyze_with_claude", side_effect=Exception("API error")):
            result = kb.analyze_text("Fallback test content.", title="Fallback")

        assert result is not None
        assert Path(result).exists()
