"""list.py - Document listing mixin."""

from i18n import t


class ListMixin:
    """Mixin: document listing commands."""

    def list_documents(self):
        """List all documents in the knowledge base"""
        index = self._load_index()
        if not index["documents"]:
            print(f"[EMPTY] {t('list.empty')}")
            return self._ok([], msg=t('list.empty'))

        print(f"\n[KB] {t('list.title')} ({len(index['documents'])}):")
        print("=" * 80)

        for i, doc in enumerate(index["documents"], 1):
            print(f"{i}. {doc['title']}")
            print(f"   文件: {doc['path']}")
            print(f"   实体: {', '.join(doc['entities'][:3])}")
            print(f"   概念: {', '.join(doc['concepts'][:3])}")
            print()
        return self._ok(index["documents"])
