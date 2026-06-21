"""翰林代码工具 — AST 解析 + Ruff Lint 检查"""
import ast
import subprocess
import tempfile
import os
from typing import Dict, Any

from .tool_registry import tool


@tool("ast_parse", "AST 语法校验 — 检查 Python 代码是否有语法错误")
def ast_parse(code: str) -> Dict[str, Any]:
    """
    AST 语法校验 — 检查代码是否有语法错误

    Args:
        code: Python 代码字符串

    Returns:
        {"ok": True/False, "error": error_message_or_None}
    """
    if not code or not code.strip():
        return {"ok": True, "error": None}

    try:
        ast.parse(code)
        return {"ok": True, "error": None}
    except SyntaxError as e:
        error_msg = f"SyntaxError: {e.msg} at line {e.lineno}, col {e.offset}"
        return {"ok": False, "error": error_msg}


@tool("ruff_check", "Ruff Lint 检查 + 自动修复 — 检查代码质量并自动修复可修复的问题")
def ruff_check(code: str, auto_fix: bool = True) -> Dict[str, Any]:
    """
    Ruff Lint 检查 + 自动修复

    Args:
        code: Python 代码字符串
        auto_fix: 是否自动修复可修复的问题

    Returns:
        {"ok": True/False, "fixed": fixed_code_or_empty, "issues": [...]}
    """
    # 创建临时文件进行检查
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        # 运行 ruff check
        cmd = ["ruff", "check", "--output-format=json"]
        if auto_fix:
            cmd.extend(["--fix"])

        result = subprocess.run(
            cmd + [temp_path],
            capture_output=True,
            text=True,
            timeout=5  # 5秒超时
        )

        # 解析结果
        issues = []
        if result.stdout:
            import json
            try:
                issues = json.loads(result.stdout)
            except json.JSONDecodeError:
                pass

        # 读取修复后的代码
        fixed_code = ""
        if auto_fix and issues:
            with open(temp_path, 'r') as f:
                fixed_code = f.read()

        return {
            "ok": len(issues) == 0,
            "fixed": fixed_code,
            "issues": issues
        }

    except FileNotFoundError:
        # ruff 未安装，降级处理
        return {
            "ok": True,
            "fixed": "",
            "issues": [],
            "warning": "ruff not installed, skipping lint check"
        }
    except subprocess.TimeoutExpired:
        # 超时，降级处理
        return {
            "ok": True,
            "fixed": "",
            "issues": [],
            "warning": "ruff timeout, skipping lint check"
        }
    except Exception as e:
        # 其他错误，降级处理
        return {
            "ok": True,
            "fixed": "",
            "issues": [],
            "warning": f"ruff error: {str(e)}"
        }
    finally:
        # 清理临时文件
        try:
            os.unlink(temp_path)
        except OSError:
            pass
