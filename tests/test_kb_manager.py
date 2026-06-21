"""KnowledgeBaseManager 核心测试

通过 importlib 动态导入 agent/kb/cli.py。
"""

import json
import hashlib
import importlib
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# 动态导入 agent/kb/cli.py
spec = importlib.util.spec_from_file_location(
    "kb_manager",
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
        encoding="utf-8"
    )
    return KnowledgeBaseManager(str(vault))


@pytest.fixture
def kb_no_config(tmp_path):
    vault = tmp_path / "no_config_vault"
    vault.mkdir()
    return KnowledgeBaseManager(str(vault))


class TestInit:
    def test_creates_directories(self, kb):
        assert kb.import_dir.exists()
        assert kb.notes_dir.exists()
        assert kb.index_dir.exists()

    def test_loads_config(self, kb):
        assert kb.config["api_key"] == "test-key"
        assert kb.config["model"] == "test-model"

    def test_default_config_when_missing(self, kb_no_config):
        assert kb_no_config.config.get("model") == "stepfun-ai/step-3.7-flash"


class TestHashFunctions:
    def test_get_file_hash(self, kb, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        h1 = kb._get_file_hash(f)
        h2 = kb._get_file_hash(f)
        assert h1 == h2
        assert len(h1) == 16

    def test_content_hash(self, kb):
        h1 = kb._content_hash("hello")
        h2 = kb._content_hash("hello")
        h3 = kb._content_hash("world")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 8


class TestExtractTitle:
    def test_with_title(self, kb):
        assert kb._extract_title("# My Title\nSome content") == "My Title"

    def test_no_title_with_fallback(self, kb):
        assert kb._extract_title("Just content", fallback="default") == "default"

    def test_empty_content(self, kb):
        assert kb._extract_title("", fallback="empty") == "empty"


class TestExtractText:
    def test_md_file(self, kb, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Hello\nContent", encoding="utf-8")
        assert kb._extract_text(f) == "# Hello\nContent"

    def test_txt_file(self, kb, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("plain text", encoding="utf-8")
        assert kb._extract_text(f) == "plain text"

    def test_unsupported_format(self, kb, tmp_path):
        f = tmp_path / "test.xyz"
        f.write_text("data", encoding="utf-8")
        with pytest.raises(ValueError, match="不支持的文件类型"):
            kb._extract_text(f)


class TestConfigSet:
    def test_set_api_key(self, kb):
        kb.config_set("api-key", "new-key")
        assert kb.config["api_key"] == "new-key"

    def test_set_model(self, kb):
        kb.config_set("model", "gpt-4")
        assert kb.config["model"] == "gpt-4"

    def test_persists_to_file(self, kb):
        kb.config_set("api-key", "persist-test")
        reloaded = KnowledgeBaseManager(str(kb.vault_path))
        assert reloaded.config["api_key"] == "persist-test"


class TestIndex:
    def test_load_index_empty(self, kb):
        index = kb._load_index()
        assert index["documents"] == []
        assert index["concepts"] == {}

    def test_update_index(self, kb):
        doc_path = kb.import_dir / "test.md"
        doc_path.write_text("content", encoding="utf-8")
        metadata = {
            "title": "Test Doc",
            "concepts": ["concept1", "concept2"],
            "entities": ["Entity1"],
            "tags": ["tag1"],
        }
        kb._update_index(doc_path, metadata)
        index = kb._load_index()
        assert len(index["documents"]) == 1
        assert index["documents"][0]["title"] == "Test Doc"
        assert "concept1" in index["concepts"]

    def test_list_documents_empty(self, kb, capsys):
        kb.list_documents()
        captured = capsys.readouterr()
        assert "知识库为空" in captured.out or "EMPTY" in captured.out


class TestGenerateGraph:
    def test_empty_graph(self, kb, capsys):
        kb.generate_graph()
        captured = capsys.readouterr()
        assert "请先导入" in captured.out or "ERR" in captured.out

    def test_generates_graph(self, kb):
        index_file = kb.index_dir / "documents.json"
        index_file.write_text(json.dumps({
            "documents": [{"path": "test.md", "title": "Test", "concepts": ["A"], "entities": ["E"], "tags": []}],
            "concepts": {"A": ["test.md"]},
            "entities": {"E": ["test.md"]},
        }, ensure_ascii=False), encoding="utf-8")

        kb.generate_graph()
        graph_file = kb.index_dir / "graph.json"
        assert graph_file.exists()
        graph = json.loads(graph_file.read_text(encoding="utf-8"))
        assert len(graph["nodes"]) >= 2
        assert len(graph["edges"]) >= 1


class TestQuery:
    def test_empty_index(self, kb, capsys):
        kb.query("test question")
        captured = capsys.readouterr()
        assert "未建立索引" in captured.out or "ERR" in captured.out

    def test_keyword_matching(self, kb):
        index_file = kb.index_dir / "documents.json"
        index_file.write_text(json.dumps({
            "documents": [
                {"path": "a.md", "title": "Python Tutorial", "concepts": ["python"], "entities": [], "tags": ["coding"], "summary": "Learn Python"},
                {"path": "b.md", "title": "Java Guide", "concepts": ["java"], "entities": [], "tags": ["coding"], "summary": "Learn Java"},
            ],
            "concepts": {},
            "entities": {},
        }, ensure_ascii=False), encoding="utf-8")

        (kb.import_dir / "a.md").write_text("# Python Tutorial\nContent", encoding="utf-8")

        kb.config["api_key"] = ""
        result = kb.query("Python", limit=5, rerank=False)
        # query 返回 _ok(candidates) 格式: {"code": 200, "data": [...]}
        if isinstance(result, dict) and "data" in result:
            candidates = result["data"]
        elif isinstance(result, list):
            candidates = result
        else:
            candidates = []
        assert len(candidates) > 0
        first = candidates[0] if isinstance(candidates, list) else candidates
        assert first["doc"]["title"] == "Python Tutorial"


class TestGetModel:
    def test_default_model(self, kb_no_config):
        assert kb_no_config._get_model() == "stepfun-ai/step-3.7-flash"

    def test_configured_model(self, kb):
        assert kb._get_model() == "test-model"
