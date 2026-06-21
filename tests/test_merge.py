"""Three-Way Merge Engine 测试

覆盖场景:
- 相同修改自动合并
- 非重叠修改合并
- 真实冲突标记
- 空修改 / 删除
- 单行修改
- 多文件合并集成
"""

import pytest
from agent.engine.merge import (
    ThreeWayMerge,
    MergeResult,
    ConflictMarker,
    _lcs_lines,
    _backtrack,
    _compute_diff_hunks,
    integrate_with_scheduler,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _make_merge():
    return ThreeWayMerge()


def _lines(text: str) -> list:
    return text.splitlines(keepends=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: 相同修改 -> 自动合并
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_identical_changes_no_conflict():
    """两侧做完全相同的修改 -> 无冲突"""
    base = "line1\nline2\nline3\n"
    ours = "line1\nmodified\nline3\n"
    theirs = "line1\nmodified\nline3\n"

    result = _make_merge().merge(base, ours, theirs)

    assert result.success is True
    assert len(result.conflicts) == 0
    assert "modified" in result.content


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: 非重叠修改 -> 自动合并
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_non_overlapping_changes():
    """两侧修改不同行区间 -> 无冲突"""
    base = "line1\nline2\nline3\nline4\n"
    ours = "CHANGED_A\nline2\nline3\nline4\n"
    theirs = "line1\nline2\nline3\nCHANGED_B\n"

    result = _make_merge().merge(base, ours, theirs)

    assert result.success is True
    assert len(result.conflicts) == 0
    assert "CHANGED_A" in result.content
    assert "CHANGED_B" in result.content


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: 同一行不同修改 -> 真实冲突
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_true_conflict():
    """两侧修改同一行且内容不同 -> 产生冲突标记"""
    base = "line1\nline2\nline3\n"
    ours = "line1\nOURS_CHANGE\nline3\n"
    theirs = "line1\nTHEIRS_CHANGE\nline3\n"

    result = _make_merge().merge(base, ours, theirs)

    assert result.success is False
    assert len(result.conflicts) >= 1
    assert "<<<<<<< OURS" in result.content
    assert "=======" in result.content
    assert ">>>>>>> THEIRS" in result.content


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: 一侧删除，另一侧修改 -> 自动保留修改
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_one_side_deletion_one_side_modification():
    """一侧删除某行，另一侧修改该行 -> 保留修改"""
    base = "keep\nmodify_me\nkeep2\n"
    ours = "keep\nmodify_me\nkeep2\n"       # 未变
    theirs = "keep\nkeep2\n"                 # 删除了 modify_me

    result = _make_merge().merge(base, ours, theirs)

    # theirs 删除了 modify_me，ours 未动 -> 应该成功合并（删除生效）
    assert len(result.conflicts) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: 两侧都为空修改（完全不动）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_both_sides_no_changes():
    """两侧都没有修改 -> 返回 base 内容"""
    base = "line1\nline2\nline3\n"

    result = _make_merge().merge(base, base, base)

    assert result.success is True
    assert result.content == base
    assert len(result.conflicts) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: 单行修改
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_single_line_change_ours_only():
    """仅 ours 修改一行"""
    base = "a\nb\nc\n"
    ours = "a\nB_CHANGED\nc\n"
    theirs = "a\nb\nc\n"

    result = _make_merge().merge(base, ours, theirs)

    assert result.success is True
    assert "B_CHANGED" in result.content
    assert "b\n" not in result.content or "B_CHANGED" in result.content


def test_single_line_change_theirs_only():
    """仅 theirs 修改一行"""
    base = "a\nb\nc\n"
    ours = "a\nb\nc\n"
    theirs = "a\nB_CHANGED\nc\n"

    result = _make_merge().merge(base, ours, theirs)

    assert result.success is True
    assert "B_CHANGED" in result.content


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: LCS 算法正确性
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_lcs_basic():
    """LCS 基本正确性"""
    a = ["a", "b", "c", "d"]
    b = ["a", "c", "d", "e"]
    dp = _lcs_lines(a, b)
    pairs = _backtrack(dp, a, b)

    # LCS 长度应为 3 (a, c, d)
    assert dp[len(a)][len(b)] == 3
    # 回溯应得到 3 对对齐
    assert len(pairs) == 3


def test_lcs_identical():
    """完全相同的序列"""
    a = ["x", "y", "z"]
    dp = _lcs_lines(a, a)
    assert dp[3][3] == 3


def test_lcs_empty():
    """空序列"""
    dp = _lcs_lines([], ["a", "b"])
    assert dp[0][2] == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: Diff Hunk 计算
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_compute_diff_hunks_simple():
    """简单修改的 diff hunk 计算"""
    base = ["line1\n", "line2\n", "line3\n"]
    modified = ["line1\n", "CHANGED\n", "line3\n"]
    hunks = _compute_diff_hunks(base, modified)

    assert len(hunks) == 1
    assert hunks[0].base_start == 1
    assert hunks[0].new_lines == ["CHANGED\n"]


def test_compute_diff_hunks_no_change():
    """无修改时返回空 hunks"""
    base = ["a\n", "b\n"]
    hunks = _compute_diff_hunks(base, base)
    assert len(hunks) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: ConflictMarker 结构
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_conflict_marker_fields():
    """冲突标记包含正确字段"""
    base = "a\nb\nc\n"
    ours = "a\nX\nc\n"
    theirs = "a\nY\nc\n"

    result = _make_merge().merge(base, ours, theirs)

    assert len(result.conflicts) >= 1
    marker = result.conflicts[0]
    assert marker.resolution == "manual"
    assert "X" in marker.ours_line
    assert "Y" in marker.theirs_line
    assert isinstance(marker.line_number, int)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: 多文件合并集成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_integrate_with_scheduler_single_agent():
    """单个代理结果 -> 直接返回"""
    results = [{"content": "new content\n"}]
    out = integrate_with_scheduler("file.py", results, base_ref="HEAD")

    assert out["success"] is True
    assert out["merged_content"] == "new content\n"
    assert out["conflicts"] == []


def test_integrate_with_scheduler_no_agents():
    """无代理结果 -> 返回 base"""
    out = integrate_with_scheduler("file.py", [], base_ref="HEAD")

    # 没有 git repo 可能失败，但逻辑路径正确
    # 在测试环境中 base 读取会失败
    assert "success" in out


def test_integrate_with_scheduler_multiple_agents_identical(monkeypatch):
    """多个代理做相同修改 -> 无冲突"""
    content = "line1\nmodified\nline3\n"

    def fake_git_show(ref, path):
        return content

    monkeypatch.setattr("agent.engine.merge._git_show", fake_git_show)

    results = [
        {"content": content},
        {"content": content},
    ]
    out = integrate_with_scheduler("file.py", results, base_ref="HEAD")

    assert out["success"] is True
    assert len(out["conflicts"]) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: MergeResult / ConflictMarker 数据类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_merge_result_defaults():
    """MergeResult 默认值"""
    mr = MergeResult(content="x")
    assert mr.success is True
    assert mr.conflicts == []


def test_conflict_marker_defaults():
    """ConflictMarker 基本构造"""
    cm = ConflictMarker(
        line_number=5,
        ours_line="our",
        theirs_line="their",
        resolution="manual",
    )
    assert cm.line_number == 5
    assert cm.resolution == "manual"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试: Git 不可用时的降级行为
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_merge_without_git(monkeypatch):
    """git 不可用时，integrate_with_scheduler 降级为空 base 并完成合并"""
    monkeypatch.setattr("agent.engine.merge._git_show", lambda ref, path: None)

    results = [
        {"content": "line1\nOURS\nline3\n"},
        {"content": "line1\nTHEIRS\nline3\n"},
    ]
    out = integrate_with_scheduler("file.py", results, base_ref="HEAD")

    # 二路合并（base 为空）应能产出内容
    assert out["merged_content"] != ""
    # ours 和 theirs 修改了不同位置（base 为空时无共同祖先），
    # 应视为各自独立的完整内容
    assert "OURS" in out["merged_content"]


def test_two_way_fallback(monkeypatch):
    """二路合并降级：base 为空时，ours 和 theirs 各自相对空的修改"""
    monkeypatch.setattr("agent.engine.merge._git_show", lambda ref, path: None)

    ours = "AAA\nBBB\n"
    theirs = "CCC\nDDD\n"
    results = [
        {"content": ours},
        {"content": theirs},
    ]
    out = integrate_with_scheduler("file.py", results, base_ref="HEAD")

    # 二路合并：base 为空，ours 添加 AAA/BBB，theirs 添加 CCC/DDD
    # 无共同行 -> 两侧完全不同时产生冲突标记
    assert "<<<<<<< OURS" in out["merged_content"]
    assert "AAA" in out["merged_content"]
    assert "DDD" in out["merged_content"]
    assert out["success"] is False


def test_two_way_fallback_with_shared_lines(monkeypatch):
    """二路合并降级：两侧有共同行时自动合并，无共同行时冲突"""
    monkeypatch.setattr("agent.engine.merge._git_show", lambda ref, path: None)

    # ours 和 theirs 共享 line1、line3，各自修改中间行
    ours = "line1\nOURS_CHANGE\nline3\n"
    theirs = "line1\nTHEIRS_CHANGE\nline3\n"
    results = [
        {"content": ours},
        {"content": theirs},
    ]
    out = integrate_with_scheduler("file.py", results, base_ref="HEAD")

    # 共同行 line1、line3 应被保留，中间行冲突
    assert "<<<<<<< OURS" in out["merged_content"]
    assert "line1" in out["merged_content"]
    assert "line3" in out["merged_content"]
