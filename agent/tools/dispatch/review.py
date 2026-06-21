"""代码审查/验证逻辑 — _auto_verify

从 dispatcher.py 拆出，作为 Mixin 混入 SubagentDispatcher。
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ReviewMixin:
    """提供 _auto_verify 方法"""

    def _auto_verify(self, tools_used: List[str]) -> Dict[str, Any]:
        """自动验证子代理修改的文件语法"""
        import subprocess

        errors = []
        checked = 0

        # 获取工作区最近修改的 Python/JS 文件
        try:
            # 用 git diff 找到修改的文件
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=ACMR"],
                capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace"
            )
            if result.returncode == 0:
                for f in result.stdout.strip().split("\n"):
                    f = f.strip()
                    if not f:
                        continue
                    if f.endswith(".py"):
                        check = subprocess.run(
                            ["python", "-m", "py_compile", f],
                            capture_output=True, text=True, timeout=10,
                            encoding="utf-8", errors="replace"
                        )
                        checked += 1
                        if check.returncode != 0:
                            errors.append({"file": f, "error": check.stderr.strip()[:200]})
                    elif f.endswith((".js", ".ts")):
                        check = subprocess.run(
                            ["node", "--check", f],
                            capture_output=True, text=True, timeout=10,
                            encoding="utf-8", errors="replace"
                        )
                        checked += 1
                        if check.returncode != 0:
                            errors.append({"file": f, "error": check.stderr.strip()[:200]})
        except Exception as e:
            errors.append({"file": "*", "error": f"验证过程异常: {e}"})

        return {
            "passed": len(errors) == 0,
            "checked": checked,
            "errors": errors
        }
