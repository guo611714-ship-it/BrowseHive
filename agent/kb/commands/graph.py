"""graph.py - Knowledge graph generation mixin."""

import json

from i18n import t
from ..utils import build_graph_from_index


class GraphMixin:
    """Mixin: knowledge graph generation commands."""

    def generate_graph(self):
        """Generate knowledge graph JSON data (for Obsidian plugins)"""
        index_file = self.index_dir / "documents.json"

        if not index_file.exists():
            print(f"[ERR] {t('error.index_missing')}")
            return

        with open(index_file, 'r', encoding='utf-8') as f:
            index = json.load(f)

        graph = build_graph_from_index(index)

        output_file = self.index_dir / "graph.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(graph, f, indent=2, ensure_ascii=False)

        print(f"[OK] {t('graph.done')}: {output_file}")
        print(f"   节点: {len(graph['nodes'])}, 边: {len(graph['edges'])}")
