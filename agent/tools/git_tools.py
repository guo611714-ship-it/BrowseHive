"""Git 安全工具 — 自动备份、变更摘要、回滚"""

import subprocess
import json
from typing import Dict, Any
from datetime import datetime
from pathlib import Path
from .tool_registry import tool


def _run_git(*args: str, cwd: str = None) -> Dict[str, Any]:
    """执行 git 命令"""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=cwd or ".",
            capture_output=True,
            timeout=30
        )
        # Windows: git 输出通常是 UTF-8，但 subprocess 默认用 GBK
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        return {
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": f"git command timeout: git {' '.join(args)}"}
    except Exception as e:
        return {"error": str(e)}


@tool("create_backup_branch", "创建备份分支（Agent操作前自动调用）")
def create_backup_branch(label: str = "agent") -> Dict[str, Any]:
    """
    在 Agent 操作前创建备份分支

    :param label: 分支标签（用于区分不同操作）
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    branch_name = f"backup/{label}/{ts}"

    # 确保在 git 仓库中
    check = _run_git("rev-parse", "--git-dir")
    if check.get("returncode", 1) != 0:
        return {"error": "当前目录不是 git 仓库", "branch": None}

    # 创建备份分支（不切换，仅创建引用）
    result = _run_git("branch", branch_name)
    if result.get("returncode", 0) != 0:
        return {"error": f"创建备份分支失败: {result.get('stderr', '')}", "branch": None}

    return {
        "branch": branch_name,
        "message": f"已创建备份分支 {branch_name}",
        "ok": True
    }


@tool("git_diff_summary", "生成变更摘要（支持指定基准分支）")
def git_diff_summary(since_branch: str = None) -> Dict[str, Any]:
    """
    生成变更摘要

    :param since_branch: 基准分支（可选，为空则显示工作区变更）
    """
    # 检查 git 仓库
    check = _run_git("rev-parse", "--git-dir")
    if check.get("returncode", 1) != 0:
        return {"error": "当前目录不是 git 仓库"}

    if since_branch:
        # 检查分支是否存在
        branch_check = _run_git("rev-parse", "--verify", since_branch)
        if branch_check.get("returncode", 1) != 0:
            return {"error": f"分支 {since_branch} 不存在"}

        # 统计变更
        stat_result = _run_git("diff", "--stat", since_branch)
        diff_result = _run_git("diff", "--numstat", since_branch)
        shortstat = _run_git("diff", "--shortstat", since_branch)
    else:
        # 工作区变更（暂存+未暂存）
        stat_result = _run_git("diff", "--stat")
        diff_result = _run_git("diff", "--numstat")
        shortstat = _run_git("diff", "--shortstat")

        # 加上暂存区
        staged_stat = _run_git("diff", "--cached", "--stat")
        staged_num = _run_git("diff", "--cached", "--numstat")
        staged_short = _run_git("diff", "--cached", "--shortstat")

    summary = {
        "since_branch": since_branch,
        "stat": stat_result.get("stdout", ""),
        "numstat": diff_result.get("stdout", ""),
        "shortstat": shortstat.get("stdout", ""),
        "files_changed": []
    }

    # 解析 numstat 获取文件列表
    numstat_output = diff_result.get("stdout", "")
    if numstat_output:
        for line in numstat_output.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) == 3:
                added, deleted, filepath = parts
                summary["files_changed"].append({
                    "file": filepath,
                    "added": int(added) if added != "-" else 0,
                    "deleted": int(deleted) if deleted != "-" else 0
                })

    if not since_branch:
        # 合并暂存区变更
        if staged_stat.get("stdout"):
            summary["staged_stat"] = staged_stat.get("stdout", "")
        if staged_short.get("stdout"):
            summary["staged_shortstat"] = staged_short.get("stdout", "")

    return summary


@tool("git_revert_to", "回滚到指定分支的快照（破坏性操作）")
def git_revert_to(branch_name: str) -> Dict[str, Any]:
    """
    回滚到指定分支的快照

    :param branch_name: 目标分支名称
    """
    check = _run_git("rev-parse", "--git-dir")
    if check.get("returncode", 1) != 0:
        return {"error": "当前目录不是 git 仓库"}

    # 验证分支存在
    branch_check = _run_git("rev-parse", "--verify", branch_name)
    if branch_check.get("returncode", 1) != 0:
        return {"error": f"分支 {branch_name} 不存在"}

    # 先保存当前 ref
    current_ref = _run_git("rev-parse", "HEAD")
    current_commit = current_ref.get("stdout", "unknown")

    # 执行 reset
    result = _run_git("reset", "--hard", branch_name)
    if result.get("returncode", 0) != 0:
        return {"error": f"回滚失败: {result.get('stderr', '')}"}

    return {
        "ok": True,
        "reverted_to": branch_name,
        "previous_commit": current_commit,
        "message": f"已回滚到 {branch_name}"
    }


@tool("git_log_oneline", "获取最近N条commit记录")
def git_log_oneline(n: int = 10) -> Dict[str, Any]:
    """
    获取最近 n 条 commit 记录

    :param n: 获取的commit数量
    """
    result = _run_git("log", f"--oneline", f"-{n}")
    if result.get("returncode", 0) != 0:
        return {"error": result.get("stderr", "git log failed")}

    commits = []
    for line in result.get("stdout", "").split("\n"):
        if line.strip():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append({"hash": parts[0], "message": parts[1]})

    return {"commits": commits, "count": len(commits)}
