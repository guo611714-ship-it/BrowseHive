"""config模块测试"""

from agent.config import (
    PROJECT_ROOT, AGENT_DIR, TOOLS_DIR, DISPATCH_DIR,
    DATA_DIR, MEMORY_DIR, TEAM_DIR,
)


def test_project_root_is_absolute():
    assert PROJECT_ROOT.is_absolute()


def test_agent_dir_is_subdir_of_project_root():
    assert AGENT_DIR == PROJECT_ROOT / "agent"
    assert AGENT_DIR.exists()


def test_tools_dir():
    assert TOOLS_DIR == AGENT_DIR / "tools"


def test_dispatch_dir():
    assert DISPATCH_DIR == TOOLS_DIR / "dispatch"


def test_data_dir():
    assert DATA_DIR == PROJECT_ROOT / ".team"


def test_memory_dir():
    assert MEMORY_DIR == DATA_DIR / "memory"


def test_team_dir_equals_data_dir():
    assert TEAM_DIR == DATA_DIR
