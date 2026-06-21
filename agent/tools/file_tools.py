"""文件操作工具 - 使用装饰器自动注册"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from .tool_registry import tool

# 工作区根目录，需在 AgentLoop 启动时调用 set_workspace 设置
WORKSPACE_ROOT: Path = Path.cwd().resolve()


def set_workspace(root: Path):
    """设置工作区根目录（AgentLoop 初始化时调用）"""
    global WORKSPACE_ROOT
    WORKSPACE_ROOT = Path(root).resolve()


def _validate_path(path: str) -> Optional[Path]:
    """验证路径是否在工作区内，返回 Path 对象或 None"""
    p = Path(path).expanduser().resolve()
    try:
        p.relative_to(WORKSPACE_ROOT)
        return p
    except ValueError:
        return None


@tool("read_file", "读取文件内容（限工作区内）")
def read_file(path: str, start_line: int = None, end_line: int = None) -> Dict[str, Any]:
    """
    读取文件内容（限工作区）

    :param path: 文件路径（相对或绝对，但必须在工作区内）
    :param start_line: 起始行号（可选，从1开始）
    :param end_line: 结束行号（可选）
    """
    try:
        p = _validate_path(path)
        if p is None:
            return {"error": f"Access denied: path outside workspace"}
        if not p.exists():
            return {"error": f"File not found: {path}"}

        with open(p, "r", encoding="utf-8") as f:
            if start_line or end_line:
                lines = f.readlines()
                start = (start_line or 1) - 1
                end = end_line or len(lines)
                content = "".join(lines[start:end])
            else:
                content = f.read()

        return {
            "content": content[:50000],  # 限制大小
            "lines": len(content.splitlines()),
            "size": len(content),
            "path": str(p)
        }
    except Exception as e:
        return {"error": str(e)}


@tool("write_file", "写入文件内容（限工作区内）")
def write_file(path: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
    """
    写入文件（在工作区内）

    :param path: 文件路径（相对或绝对，但必须在工作区内）
    :param content: 文件内容
    :param overwrite: 是否覆盖（False则追加）
    """
    try:
        p = _validate_path(path)
        if p is None:
            return {"error": f"Access denied: path outside workspace"}

        p.parent.mkdir(parents=True, exist_ok=True)

        mode = "w" if overwrite else "a"
        with open(p, mode, encoding="utf-8") as f:
            f.write(content)

        return {
            "path": str(p),
            "size": len(content)
        }
    except Exception as e:
        return {"error": str(e)}


@tool("edit_file", "编辑文件（替换指定文本）")
def edit_file(path: str, old_string: str, new_string: str) -> Dict[str, Any]:
    """
    编辑文件（替换文本，限制在工作区）

    :param path: 文件路径
    :param old_string: 旧文本
    :param new_string: 新文本
    """
    try:
        p = _validate_path(path)
        if p is None:
            return {"error": f"Access denied: path outside workspace"}
        if not p.exists():
            return {"error": f"File not found: {path}"}

        content = p.read_text(encoding="utf-8")
        if old_string not in content:
            return {"error": f"Old string not found in {path}"}

        new_content = content.replace(old_string, new_string, 1)  # 只替换第一次出现
        p.write_text(new_content, encoding="utf-8")

        return {
            "edited": True,
            "path": str(p),
            "replaces": 1
        }
    except Exception as e:
        return {"error": str(e)}


@tool("glob", "按模式搜索文件")
def glob(pattern: str, base_dir: str = ".") -> List[str]:
    """
    路径模式匹配（限工作区内）

    :param pattern: glob 模式（如 "**/*.py"）
    :param base_dir: 基础目录
    """
    try:
        base = _validate_path(base_dir)
        if base is None:
            return {"error": f"路径不在工作区内: {base_dir}"}
        files = [str(f.relative_to(base)) for f in base.glob(pattern) if f.is_file()]
        return files[:1000]  # 限制结果数量
    except Exception as e:
        return {"error": str(e)}


@tool("grep", "在文件中搜索内容（正则表达式）")
def grep(pattern: str, path: str = ".", glob_pattern: str = None,
         case_sensitive: bool = False, max_matches: int = 100) -> List[Dict]:
    """
    内容搜索

    :param pattern: 搜索模式（正则）
    :param path: 搜索目录
    :param glob_pattern: 限制文件类型（如 "*.py"）
    :param case_sensitive: 是否大小写敏感
    :param max_matches: 最大匹配数
    """
    import re
    try:
        base = Path(path)
        regex = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
        matches = []

        # 确定搜索范围
        if glob_pattern:
            files = list(base.rglob(glob_pattern))
        else:
            files = [f for f in base.rglob("*") if f.is_file()]

        for file in files:
            try:
                with open(file, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            matches.append({
                                "file": str(file.relative_to(base)),
                                "line": i,
                                "content": line.strip()[:200]  # 截断
                            })
                            if len(matches) >= max_matches:
                                return matches
            except:
                continue

        return matches
    except Exception as e:
        return {"error": str(e)}
