"""dag_tools.py 测试 — DAG 任务编排引擎：依赖管理与拓扑排序"""

import json
import pytest
import asyncio
from pathlib import Path
from agent.tools.dag_tools import DAGExecutor, TaskNode


class TestAddTask:
    def test_add_single_task(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="读取文件"))
        assert "a" in dag.tasks
        assert dag.tasks["a"].name == "读取文件"

    def test_add_task_with_dependencies(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1"))
        dag.add_task(TaskNode(id="b", name="t2", dependencies=["a"]))
        assert "a" in dag._adj
        assert dag._adj["a"] == ["b"]

    def test_add_dependency_updates_graph(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1"))
        dag.add_task(TaskNode(id="b", name="t2"))
        dag.add_dependency("a", "b")
        assert "a" in dag.tasks["b"].dependencies
        assert "b" in dag._adj["a"]


class TestTopologicalSort:
    def test_linear_chain(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1"))
        dag.add_task(TaskNode(id="b", name="t2", dependencies=["a"]))
        dag.add_task(TaskNode(id="c", name="t3", dependencies=["b"]))
        layers = dag._topological_sort()
        assert len(layers) == 3
        assert layers[0] == ["a"]
        assert layers[2] == ["c"]

    def test_parallel_tasks_same_layer(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1"))
        dag.add_task(TaskNode(id="b", name="t2"))
        dag.add_task(TaskNode(id="c", name="t3", dependencies=["a", "b"]))
        layers = dag._topological_sort()
        assert len(layers) == 2
        assert set(layers[0]) == {"a", "b"}
        assert layers[1] == ["c"]


class TestCycleDetection:
    def test_direct_cycle_raises(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1", dependencies=["b"]))
        dag.add_task(TaskNode(id="b", name="t2", dependencies=["a"]))
        with pytest.raises(ValueError, match="循环依赖"):
            dag._topological_sort()

    def test_indirect_cycle_raises(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1", dependencies=["c"]))
        dag.add_task(TaskNode(id="b", name="t2", dependencies=["a"]))
        dag.add_task(TaskNode(id="c", name="t3", dependencies=["b"]))
        with pytest.raises(ValueError, match="循环依赖"):
            dag._topological_sort()


class TestReadyTasks:
    def test_first_layer_has_no_deps(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1"))
        dag.add_task(TaskNode(id="b", name="t2", dependencies=["a"]))
        layers = dag._topological_sort()
        ready = layers[0]
        for nid in ready:
            assert dag.tasks[nid].dependencies == []


class TestRunDag:
    def test_all_tasks_succeed(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1"))
        dag.add_task(TaskNode(id="b", name="t2", dependencies=["a"]))

        async def execute(node):
            return f"{node.name} done"

        result = asyncio.run(dag.run_dag(execute))
        assert result["summary"]["done"] == 2
        assert result["summary"]["failed"] == 0
        assert result["results"]["a"] == "t1 done"

    def test_failure_skips_dependents(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1"))
        dag.add_task(TaskNode(id="b", name="t2", dependencies=["a"]))

        async def execute(node):
            if node.id == "a":
                raise RuntimeError("boom")
            return "ok"

        result = asyncio.run(dag.run_dag(execute))
        assert result["summary"]["failed"] == 1
        assert result["summary"]["skipped"] == 1
        assert dag.tasks["b"].status == "skipped"

    def test_sync_execute_fn(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1"))

        def execute(node):
            return "sync result"

        result = asyncio.run(dag.run_dag(execute))
        assert result["results"]["a"] == "sync result"


class TestSerialize:
    def test_save_and_load(self, tmp_path):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="t1"))
        dag.add_task(TaskNode(id="b", name="t2", dependencies=["a"]))
        path = str(tmp_path / "dag.json")
        dag.save(path)

        loaded = DAGExecutor.load(path)
        assert "a" in loaded.tasks
        assert loaded.tasks["b"].dependencies == ["a"]
        assert loaded._adj["a"] == ["b"]

    def test_to_dict(self):
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="x", name="test"))
        d = dag.to_dict()
        assert "tasks" in d
        assert "adjacency" in d
        assert "x" in d["tasks"]
