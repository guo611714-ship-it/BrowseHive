"""Shell 命令执行工具"""

import subprocess
import shlex
from typing import Dict, Any
from .tool_registry import tool


@tool("run_command", "执行Shell命令")
def run_command(command: str, cwd: str = None, timeout: int = 30) -> Dict[str, Any]:
    """
    执行 shell 命令

    :param command: 命令字符串
    :param cwd: 工作目录（默认当前目录）
    :param timeout: 超时时间（秒）
    """
    try:
        result = subprocess.run(
            shlex.split(command),
            cwd=cwd or ".",
            capture_output=True,
            timeout=timeout
        )
        # 手动解码，避免 Windows GBK 编码问题
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

        return {
            "stdout": stdout[:10000],  # 限制输出大小
            "stderr": stderr[:10000],
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}
