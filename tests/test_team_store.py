"""team_store模块测试"""

import json
import pytest
from pathlib import Path
from agent.team_store import TeamStore, MessageBus, get_team_store, get_message_bus


@pytest.fixture
def bus(tmp_path):
    """创建临时MessageBus"""
    return MessageBus(tmp_path / "inbox", use_memory=True)


@pytest.fixture
def store(tmp_path):
    """创建临时TeamStore"""
    return TeamStore(tmp_path / ".team")


class TestMessageBus:
    def test_send_and_read(self, bus):
        bus.send("bob", {"from": "alice", "content": "Hello"})
        messages = bus.read("bob")
        assert len(messages) == 1
        assert messages[0]["from"] == "alice"
        assert messages[0]["content"] == "Hello"

    def test_read_empty(self, bus):
        messages = bus.read("nobody")
        assert messages == []

    def test_broadcast(self, bus):
        bus.broadcast(["alice", "bob"], {"content": "Alert!"})
        alice_msgs = bus.read("alice")
        bob_msgs = bus.read("bob")
        assert len(alice_msgs) == 1
        assert len(bob_msgs) == 1
        assert alice_msgs[0]["content"] == "Alert!"

    def test_read_clears_inbox(self, bus):
        bus.send("b", {"content": "msg"})
        bus.read("b")
        assert bus.read("b") == []


class TestTeamStore:
    def test_add_teammate(self, store):
        store.add_teammate("agent1", "coder", "coding")
        t = store.get_teammate("agent1")
        assert t is not None
        assert t["role"] == "coder"

    def test_remove_teammate(self, store):
        store.add_teammate("agent1", "coder", "coding")
        store.remove_teammate("agent1")
        assert store.get_teammate("agent1") is None

    def test_update_status(self, store):
        store.add_teammate("agent1", "coder", "coding")
        store.update_status("agent1", "busy")
        assert store.get_teammate("agent1")["status"] == "busy"

    def test_persistence(self, tmp_path):
        path = tmp_path / ".team"
        s1 = TeamStore(path)
        s1.add_teammate("a1", "role1", "type1")
        s2 = TeamStore(path)
        assert s2.get_teammate("a1") is not None


class TestSingletons:
    def test_get_team_store_returns_same(self, tmp_path, monkeypatch):
        import agent.team_store as ts
        monkeypatch.setattr(ts, "_team_store_instance", None)
        s1 = ts.get_team_store(tmp_path / "team1")
        s2 = ts.get_team_store(tmp_path / "team2")  # team2 ignored, returns s1
        assert s1 is s2
        ts._team_store_instance = None

    def test_get_message_bus_returns_same(self, tmp_path, monkeypatch):
        import agent.team_store as ts
        monkeypatch.setattr(ts, "_message_bus_instance", None)
        b1 = ts.get_message_bus(tmp_path / "team1")
        b2 = ts.get_message_bus(tmp_path / "team2")
        assert b1 is b2
        ts._message_bus_instance = None
