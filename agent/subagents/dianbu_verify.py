"""典簿验证逻辑 -- pytest 执行 + 结果解析"""
import logging
import re
import subprocess
import tempfile
import os
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class DianbuAgent:
    """典簿代理: 执行 pytest 并返回结构化结果"""

    async def execute(
        self,
        test_json: dict,
        target_file: str,
        test_names: List[str],
    ) -> Dict[str, Any]:
        """
        执行测试并返回结果

        Args:
            test_json: 包含 content(测试代码) 和 test_file(目标路径) 的字典
            target_file: 被测文件路径(信息记录用)
            test_names: 期望运行的测试名列表

        Returns:
            {"pass": bool, "output": str, "failed_tests": list, "error_evidence": str}
        """
        content = test_json.get("content", "")
        test_file = test_json.get("test_file", "")

        if not content:
            return {
                "pass": False,
                "output": "",
                "failed_tests": [],
                "error_evidence": "test_json missing 'content'",
            }
        if not test_file:
            return {
                "pass": False,
                "output": "",
                "failed_tests": [],
                "error_evidence": "test_json missing 'test_file'",
            }

        # 写测试文件
        self._write_test_file(test_file, content)
        logger.info("wrote test file: %s (%d bytes)", test_file, len(content))

        # 执行 pytest
        output, returncode = self._run_pytest(test_file)

        # 解析结果
        result = parse_pytest_output(output, test_names)
        result["output"] = output
        result["returncode"] = returncode

        if returncode != 0 and not result["failed_tests"]:
            # pytest 非零退出但未识别出具体失败测试 -- 记录原始输出
            result["error_evidence"] = output[-2000:] if len(output) > 2000 else output

        logger.info(
            "pytest result: passed=%s, failed_count=%d, returncode=%d",
            result["pass"], len(result["failed_tests"]), returncode,
        )
        return result

    def _write_test_file(self, test_file: str, content: str) -> None:
        """将测试代码写入指定路径, 自动创建父目录"""
        parent = os.path.dirname(test_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(content)

    def _run_pytest(self, test_file: str) -> tuple:
        """
        执行 pytest, 返回 (output, returncode)

        Returns:
            (stdout+stderr 合并字符串, 进程返回码)
        """
        cmd = [
            "python", "-m", "pytest",
            test_file,
            "-v", "--tb=long", "--timeout=30",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=os.path.dirname(test_file) or ".",
            )
            combined = proc.stdout + "\n" + proc.stderr
            return combined.strip(), proc.returncode
        except subprocess.TimeoutExpired:
            return "TIMEOUT: pytest execution exceeded 60s", -1
        except Exception as e:
            return f"EXEC_ERROR: {e}", -1


def parse_pytest_output(output: str, test_names: List[str]) -> Dict[str, Any]:
    """
    解析 pytest 输出, 提取结构化结果

    Args:
        output: pytest -v --tb=long 的输出
        test_names: 期望运行的测试名列表

    Returns:
        {"pass": bool, "failed_tests": [...], "error_evidence": "..."}
    """
    if not output.strip():
        return {"pass": False, "failed_tests": [], "error_evidence": "empty output"}

    # 超时检测
    if "timed out" in output.lower() or "timeout" in output.lower():
        return {
            "pass": False,
            "failed_tests": test_names[:],
            "error_evidence": "Test execution timed out",
        }

    # 全部通过: 有 passed 且没有 FAILED/ERROR
    has_passed = "passed" in output
    has_failed = "FAILED" in output
    has_error = "ERROR" in output and not has_passed

    if has_passed and not has_failed and not has_error:
        # 检查是否全是 skip/xfail
        all_skipped = _count_outcome(output, "skipped") > 0
        all_xfail = _count_outcome(output, "xfail") > 0
        if all_skipped or all_xfail:
            return {
                "pass": True,
                "failed_tests": [],
                "error_evidence": "All tests skipped or xfail (not failures)",
            }
        return {"pass": True, "failed_tests": [], "error_evidence": ""}

    # 提取失败的测试名
    failed_tests = []
    for name in test_names:
        # pytest FAILED 行格式: FAILED test_file.py::test_name - ...
        if f"FAILED" in output and name in output:
            failed_tests.append(name)
        # 也匹配 ERROR 行
        elif f"ERROR" in output and name in output:
            failed_tests.append(name)

    # 提取错误证据 -- 匹配多种异常类型
    error_evidence = _extract_error_evidence(output)

    return {
        "pass": False,
        "failed_tests": failed_tests,
        "error_evidence": error_evidence,
    }


def _count_outcome(output: str, keyword: str) -> int:
    """从 pytest 汇总行中提取某个 outcome 的数量, 如 '2 skipped'"""
    m = re.search(rf"(\d+)\s+{keyword}", output)
    return int(m.group(1)) if m else 0


def _extract_error_evidence(output: str) -> str:
    """从 pytest 输出中提取错误证据, 支持多种异常类型"""
    patterns = [
        # FAILED lines with traceback
        r"(FAILED .+?)\n={5,}",
        # AssertionError / AssertionError
        r"(.*?(?:Assert|Assert)ionError.*?)\n",
        # TypeError, ValueError, AttributeError, RuntimeError, etc.
        r"(.*?(?:TypeError|ValueError|AttributeError|RuntimeError|"
        r"ImportError|ModuleNotFoundError|KeyError|IndexError|"
        r"FileNotFoundError|PermissionError|OSError).*?)\n",
        # pytest error blocks
        r"(E\s+.+)",
        # Timeout
        r"(.*?timed out.*?)\n",
    ]

    collected = []
    for pattern in patterns:
        matches = re.findall(pattern, output, re.IGNORECASE)
        for m in matches:
            cleaned = m.strip()
            if cleaned and cleaned not in collected and len(cleaned) > 5:
                collected.append(cleaned)

    if collected:
        return "\n".join(collected[:10])

    # 降级: 取最后 1500 字符
    return output[-1500:] if len(output) > 1500 else output
