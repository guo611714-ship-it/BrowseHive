"""任务规划工具（Todolist）"""

from typing import List, Dict, Any
from pathlib import Path


class TodoManager:
    """跨回合存活的待办列表管理器"""

    def __init__(self):
        self.todos_file = Path(".todos.json")
        self._todos = self._load()

    def _load(self) -> List[Dict]:
        """加载 todo 列表"""
        if not self.todos_file.exists():
            return []
        try:
            import json
            with open(self.todos_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []

    def _save(self):
        """保存 todo 列表"""
        import json
        with open(self.todos_file, "w", encoding="utf-8") as f:
            json.dump(self._todos, f, indent=2, ensure_ascii=False)

    def get_todos(self) -> List[Dict]:
        """获取所有 todo"""
        return self._todos

    def update_todos(self, todos: List[Dict]) -> Dict[str, Any]:
        """
        更新待办列表（全量替换）

        Args:
            todos: 新 todo 列表，每个 todo 包含:
                   - id: 唯一标识
                   - title: 标题
                   - status: pending / in_progress / completed
                   - priority: 可选
                   - assignee: 可选

        Returns:
            更新后的列表
        """
        # 验证：同一时间只能有一个 in_progress
        in_progress = [t for t in todos if t.get("status") == "in_progress"]
        if len(in_progress) > 1:
            return {"error": "只能有一个任务处于 in_progress 状态"}

        self._todos = todos
        self._save()
        return {"todos": self._todos, "count": len(self._todos)}


def update_todos(todos: List[Dict]) -> Dict[str, Any]:
    """
    更新待办列表

    Args:
        todos: 新 todo 列表，每个 todo 包含:
               - id: 唯一标识
               - title: 标题
               - status: pending / in_progress / completed
               - priority: 可选
               - assignee: 可选

    Returns:
        {"todos": [...], "count": N} 或 {"error": "..."}
    """
    manager = get_todo_manager()
    return manager.update_todos(todos)


# 全局单例
_todo_manager = None

def get_todo_manager() -> TodoManager:
    """获取全局 TodoManager"""
    global _todo_manager
    if _todo_manager is None:
        _todo_manager = TodoManager()
    return _todo_manager
