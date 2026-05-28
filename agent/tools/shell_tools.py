"""Shell 命令执行工具"""

import subprocess
import shlex
from typing import Dict, Any


def run_command(command: str, cwd: str = None, timeout: int = 30) -> Dict[str, Any]:
    """
    执行 shell 命令

    Args:
        command: 命令字符串
        cwd: 工作目录（默认当前目录）
        timeout: 超时时间（秒）

    Returns:
        {"stdout": "...", "stderr": "...", "returncode": 0}
    """
    try:
        result = subprocess.run(
            shlex.split(command),
            cwd=cwd or ".",
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return {
            "stdout": result.stdout[:10000],  # 限制输出大小
            "stderr": result.stderr[:10000],
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}
