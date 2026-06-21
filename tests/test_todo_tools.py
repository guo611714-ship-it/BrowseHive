"""todo_tools.py 测试 -- 任务规划Todolist管理器"""

import json
import os
from pathlib import Path
from agent.tools.todo_tools import TodoManager, get_todo_manager, update_todos


class TestTodoManager:
    """TodoManager 测试"""

    def test_init_empty(self, tmp_path):
        os.chdir(tmp_path)
        manager = TodoManager()
        assert manager.get_todos() == []

    def test_update_todos(self, tmp_path):
        os.chdir(tmp_path)
        manager = TodoManager()
        todos = [{"id": "1", "title": "task1", "status": "pending"}]
        result = manager.update_todos(todos)
        assert result["count"] == 1
        assert result["todos"][0]["title"] == "task1"

    def test_update_persists(self, tmp_path):
        os.chdir(tmp_path)
        manager = TodoManager()
        todos = [{"id": "1", "title": "task1", "status": "pending"}]
        manager.update_todos(todos)
        manager2 = TodoManager()
        assert len(manager2.get_todos()) == 1

    def test_only_one_in_progress(self, tmp_path):
        os.chdir(tmp_path)
        manager = TodoManager()
        todos = [
            {"id": "1", "title": "a", "status": "in_progress"},
            {"id": "2", "title": "b", "status": "in_progress"},
        ]
        result = manager.update_todos(todos)
        assert "error" in result

    def test_replace_all(self, tmp_path):
        os.chdir(tmp_path)
        manager = TodoManager()
        manager.update_todos([{"id": "1", "title": "old", "status": "pending"}])
        result = manager.update_todos([{"id": "2", "title": "new", "status": "pending"}])
        assert result["count"] == 1
        assert result["todos"][0]["title"] == "new"


class TestUpdateTodosFunction:
    """update_todos 顶层函数测试"""

    def test_update_todos_function(self, tmp_path):
        os.chdir(tmp_path)
        import agent.tools.todo_tools as mod
        mod._todo_manager = None
        result = update_todos([{"id": "1", "title": "task", "status": "pending"}])
        assert result["count"] == 1
        mod._todo_manager = None
