"""内官监营造 — L3全栈测试执行器"""
import os
import re
import logging
import asyncio
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NeiguanjianAgent:
    """内官监营造 -- L3全栈测试执行器

    职责：接收翰林产出的业务代码+测试代码，执行全栈验证
    触发条件：skill 显式要求 / 翰林 Level 3-5 任务
    """

    L3_PROMPT = """你是内官监营造，工部侍郎，专司全栈工程执行与验收。

你的职责：
1. 执行 pytest 全栈测试（含集成测试、异步测试）
2. 分析覆盖率报告
3. 检查工程质量（lint、type check）
4. 生成验收报告

输入信息：
- 业务代码文件：{business_file}
- 测试代码文件：{test_file}
- 测试函数名：{test_names}
- 任务描述：{task_description}

输出 JSON 格式：
{{"status": "pass|fail|warned", "tests_passed": bool, "coverage_pct": float, "lint_errors": list[str], "report": str}}
"""

    async def execute(
        self,
        business_file: str,
        test_file: Optional[str] = None,
        test_names: Optional[List[str]] = None,
        task_description: str = "",
        group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """L3 全栈执行入口"""
        # 1. 执行 pytest
        pytest_result = await self._run_full_pytest(test_file, test_names)

        # 2. 覆盖率分析（如果有测试通过）
        coverage_result = None
        if pytest_result.get("passed_count", 0) > 0:
            coverage_result = await self._run_coverage(business_file, test_file)

        # 3. Lint 检查
        lint_result = await self._run_lint(business_file)

        # 4. 汇总报告
        return self._build_report(
            pytest_result, coverage_result, lint_result,
            business_file, test_file, group_id,
        )

    async def _run_full_pytest(
        self, test_file: Optional[str], test_names: Optional[List[str]]
    ) -> Dict[str, Any]:
        """执行全栈 pytest"""
        if not test_file or not os.path.exists(test_file):
            return {
                "passed": False,
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "output": f"test_file not found: {test_file}",
                "errors": [f"file not found: {test_file}"],
            }

        cmd_args = ["python", "-m", "pytest", test_file, "-v", "--tb=long", "--timeout=60", "-x"]
        if test_names:
            names = [n for n in test_names if n.strip()]
            if names:
                or_expr = " or ".join(names)
                cmd_args.extend(["-k", or_expr])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode("utf-8", errors="replace")
            err_text = stderr.decode("utf-8", errors="replace")
            combined = f"{output}\n{err_text}".strip()

            passed, failed, skipped = self._parse_pytest_counts(output)
            return {
                "passed": proc.returncode == 0,
                "passed_count": passed,
                "failed_count": failed,
                "skipped_count": skipped,
                "output": combined,
                "errors": self._parse_pytest_errors(output),
            }
        except asyncio.TimeoutError:
            return {
                "passed": False,
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "output": "pytest timeout (>60s)",
                "errors": ["pytest execution timed out"],
            }
        except Exception as e:
            logger.debug("pytest execution failed: %s", e)
            return {
                "passed": False,
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "output": "",
                "errors": [str(e)],
            }

    async def _run_coverage(
        self, business_file: Optional[str], test_file: Optional[str]
    ) -> Dict[str, Any]:
        """执行覆盖率分析"""
        if not test_file or not os.path.exists(test_file):
            return {"coverage_pct": 0.0, "missing_lines": ""}

        # 从业务文件提取目录作为 cov target
        cov_target = os.path.dirname(business_file) if business_file else "."
        if not cov_target:
            cov_target = "."

        cmd_args = [
            "python", "-m", "pytest", test_file,
            f"--cov={cov_target}", "--cov-report=term-missing", "-q",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode("utf-8", errors="replace")

            pct = self._parse_coverage_pct(output)
            missing = self._parse_coverage_missing(output)
            return {"coverage_pct": pct, "missing_lines": missing}
        except asyncio.TimeoutError:
            logger.debug("coverage timeout (>120s)")
            return {"coverage_pct": 0.0, "missing_lines": "coverage timed out"}
        except Exception as e:
            logger.debug("coverage failed: %s", e)
            return {"coverage_pct": 0.0, "missing_lines": str(e)}

    async def _run_lint(self, business_file: Optional[str]) -> Dict[str, Any]:
        """执行 ruff lint"""
        if not business_file or not os.path.exists(business_file):
            return {"errors": [f"file not found: {business_file}"], "error_count": 1}

        cmd_args = ["python", "-m", "ruff", "check", business_file, "--output-format=text"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode("utf-8", errors="replace").strip()

            errors = [line for line in output.splitlines() if line.strip()] if output else []
            return {"errors": errors, "error_count": len(errors)}
        except asyncio.TimeoutError:
            logger.debug("lint timeout (>30s)")
            return {"errors": ["ruff check timed out"], "error_count": 1}
        except Exception as e:
            logger.debug("lint failed: %s", e)
            return {"errors": [str(e)], "error_count": 1}

    def _build_report(
        self,
        pytest_result: Dict[str, Any],
        coverage_result: Optional[Dict[str, Any]],
        lint_result: Dict[str, Any],
        business_file: str,
        test_file: Optional[str],
        group_id: Optional[str],
    ) -> Dict[str, Any]:
        """汇总验收报告"""
        tests_passed = (
            pytest_result["passed"] and pytest_result["failed_count"] == 0
        )
        has_lint_issues = lint_result["error_count"] > 0

        if not tests_passed:
            status = "fail"
        elif has_lint_issues:
            status = "warned"
        else:
            status = "pass"

        coverage_pct = coverage_result["coverage_pct"] if coverage_result else 0.0

        # 构建报告文本
        lines = [
            f"=== 内官监验收报告 ===",
            f"业务文件: {business_file}",
            f"测试文件: {test_file or 'N/A'}",
            f"分组ID: {group_id or 'N/A'}",
            f"",
            f"--- pytest ---",
            f"状态: {'PASS' if tests_passed else 'FAIL'}",
            f"通过: {pytest_result['passed_count']}, "
            f"失败: {pytest_result['failed_count']}, "
            f"跳过: {pytest_result['skipped_count']}",
        ]

        if pytest_result["errors"]:
            lines.append(f"错误详情:")
            for err in pytest_result["errors"]:
                lines.append(f"  - {err}")

        if coverage_result:
            lines.extend([
                f"",
                f"--- 覆盖率 ---",
                f"覆盖率: {coverage_pct:.1f}%",
            ])
            if coverage_result["missing_lines"]:
                lines.append(f"未覆盖: {coverage_result['missing_lines'][:500]}")

        lines.extend([
            f"",
            f"--- Lint ---",
            f"Lint问题数: {lint_result['error_count']}",
        ])
        for err in lint_result["errors"][:10]:
            lines.append(f"  - {err}")
        if lint_result["error_count"] > 10:
            lines.append(f"  ... 共 {lint_result['error_count']} 个问题")

        lines.extend(["", f"最终判定: {status.upper()}"])

        return {
            "status": status,
            "tests_passed": tests_passed,
            "coverage_pct": coverage_pct,
            "lint_errors": lint_result["errors"],
            "report": "\n".join(lines),
            "pytest": {
                "passed_count": pytest_result["passed_count"],
                "failed_count": pytest_result["failed_count"],
                "skipped_count": pytest_result["skipped_count"],
            },
            "group_id": group_id,
        }

    @staticmethod
    def _parse_pytest_counts(output: str) -> tuple:
        """解析 pytest 输出中的 passed/failed/skipped 数量"""
        passed = failed = skipped = 0
        # 匹配 "X passed" / "Y failed" / "Z skipped"
        m_passed = re.search(r"(\d+) passed", output)
        m_failed = re.search(r"(\d+) failed", output)
        m_skipped = re.search(r"(\d+) skipped", output)
        if m_passed:
            passed = int(m_passed.group(1))
        if m_failed:
            failed = int(m_failed.group(1))
        if m_skipped:
            skipped = int(m_skipped.group(1))
        return passed, failed, skipped

    @staticmethod
    def _parse_pytest_errors(output: str) -> List[str]:
        """从 pytest verbose 输出中提取失败的测试名和错误摘要"""
        errors = []
        # 提取 FAILED 行
        for line in output.splitlines():
            if "FAILED" in line:
                errors.append(line.strip())
            elif "ERROR" in line and "collecting" in line.lower():
                errors.append(line.strip())
        return errors

    @staticmethod
    def _parse_coverage_pct(output: str) -> float:
        """解析覆盖率百分比"""
        # 匹配 "TOTAL    123    45    63%"
        m = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if m:
            return float(m.group(1))
        # 匹配单文件行中的百分比
        m2 = re.search(r"(\d+)%", output)
        if m2:
            return float(m2.group(1))
        return 0.0

    @staticmethod
    def _parse_coverage_missing(output: str) -> str:
        """提取 missing lines 摘要"""
        lines = []
        for line in output.splitlines():
            if "Missing" in line or "missing" in line:
                lines.append(line.strip())
        return "\n".join(lines) if lines else ""
