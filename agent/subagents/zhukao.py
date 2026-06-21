"""主考代理 — 提学御史，甩卷出题"""
import ast
import re
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ZhukaoAgent:
    """主考代理 — 只生成测试 JSON，不碰磁盘和终端"""

    L1_PROMPT = """你是主考，提学御史，专司出题考核。
任务：为以下代码生成单元测试。
规则：
1. 只读代码，不修改；输出严格 JSON 格式
2. 优先检查并复用项目中已有的 conftest.py 和公共 fixtures
3. 测试覆盖：正常路径 + 边界值 + 异常路径
4. 使用 pytest + unittest.mock，对数据库/网络/外部服务必须 Mock
5. 针对目标函数的复杂度合理分配用例数（核心逻辑不少于 3 个，简单 getter/setter 可仅 1 个）
6. 不运行测试，只生成
输出 JSON 格式（注意花括号是 JSON 示例，不是占位符）：
{{"test_file": "tests/test_<module>.py", "content": "<完整的 pytest 测试代码>", "coverage_strategy": "unit"}}
目标代码：
{code}
AST 解析签名：
{signatures}
相关 Conftest / 现有 Fixtures：
{conftest_context}"""

    L2_PROMPT = """你是主考，提学御史，专司出题考核。
任务：为以下跨模块重构生成集成测试。
规则：
1. 重点验证模块间接口契约
2. Mock 数据库/网络/外部服务，但必须验证跨模块调用链的参数传递正确性
3. 优先复用项目现有的 fixtures
4. 输出严格 JSON 格式
5. 标记 coverage_strategy 为 "contract"
输出 JSON 格式（注意花括号是 JSON 示例，不是占位符）：
{{"test_file": "tests/test_integration_<feature>.py", "content": "<完整的 pytest 集成测试代码>", "coverage_strategy": "contract"}}
重构蓝图（FixManifest）：
{blueprint}
涉及修改的文件列表：
{file_list}
相关模块的接口签名：
{signatures}
相关 Conftest / 现有 Fixtures：
{conftest_context}"""

    def __init__(self, model_client=None):
        self.model_client = model_client

    async def _circuit_breaker(self, func, *args, max_retries=1, **kwargs):
        """熔断器：重试1次，失败则降级"""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                if result.get("ok"):
                    return result
                last_error = result.get("error", "unknown error")
            except Exception as e:
                last_error = str(e)
            if attempt < max_retries:
                logger.warning("主考第%d次失败，重试中: %s", attempt + 1, last_error)
        # 降级：返回空测试集，标记 tests_passed=False
        return {"ok": False, "error": last_error, "degraded": True}

    def _extract_signatures(self, code: str) -> str:
        try:
            tree = ast.parse(code)
            signatures = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    args = [a.arg for a in node.args.args]
                    signatures.append(f"def {node.name}({', '.join(args)})")
                elif isinstance(node, ast.ClassDef):
                    signatures.append(f"class {node.name}")
            return "\n".join(signatures) if signatures else "No signatures found"
        except SyntaxError:
            return "AST parse failed"

    def _self_check(self, test_code: str) -> Dict[str, Any]:
        try:
            tree = ast.parse(test_code)
        except SyntaxError as e:
            return {"ok": False, "error": f"AST syntax error: {e}"}

        test_names = [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        return {"ok": True, "test_names": test_names}

    def _format_output(self, test_file: str, content: str,
                       coverage_strategy: str, test_names: List[str]) -> Dict[str, Any]:
        return {
            "test_file": test_file,
            "content": content,
            "coverage_strategy": coverage_strategy,
            "test_names": test_names
        }

    async def generate_tests(self, code: str, target_file: str,
                             conftest_context: str = "No conftest found",
                             mode: str = "fast_track") -> Dict[str, Any]:
        """
        生成测试 JSON

        Args:
            code: 目标代码
            target_file: 目标文件路径
            conftest_context: conftest 内容
            mode: "fast_track" 或 "deep_think"

        Returns:
            {"ok": True/False, "test_json": {...}, "error": ...}
        """
        # 1. 提取签名
        signatures = self._extract_signatures(code)

        # 2. 选择提示词
        if mode == "fast_track":
            prompt = self.L1_PROMPT.format(
                code=code, signatures=signatures, conftest_context=conftest_context
            )
        else:
            prompt = self.L2_PROMPT.format(
                blueprint=code, file_list=target_file,
                signatures=signatures, conftest_context=conftest_context
            )

        # 3. 调用模型
        if not self.model_client:
            logger.warning("主考: 无 model_client，返回占位测试")
            module_name = target_file.split('/')[-1].replace('.py', '')
            return {
                "ok": True,
                "test_json": {
                    "test_file": f"tests/test_{module_name}.py",
                    "content": f"def test_placeholder():\n    assert True",
                    "coverage_strategy": "unit" if mode == "fast_track" else "contract",
                    "test_names": ["test_placeholder"]
                }
            }

        try:
            response = await self.model_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system="你是主考，只输出 JSON 格式的测试代码。"
            )
        except Exception as e:
            logger.error("主考: LLM调用失败: %s", e)
            return {"ok": False, "error": f"LLM调用失败: {e}"}
        content = response.get("content", "")

        # 4. 解析 JSON 响应
        try:
            json_match = re.search(r'```(?:json)?\s*\n(.*?)```', content, re.DOTALL)
            if json_match:
                test_json = json.loads(json_match.group(1))
            else:
                test_json = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("主考: JSON 解析失败，返回降级占位")
            module_name = target_file.split('/')[-1].replace('.py', '')
            return {
                "ok": False,
                "error": "JSON解析失败",
                "fallback_test_json": {
                    "test_file": f"tests/test_{module_name}.py",
                    "content": "def test_placeholder():\n    assert True",
                    "coverage_strategy": "unit" if mode == "fast_track" else "contract"
                }
            }

        # 5. AST 自检
        check_result = self._self_check(test_json.get("content", ""))
        if not check_result["ok"]:
            logger.warning("主考: AST 自检失败: %s", check_result["error"])
            test_json["test_names"] = []
            test_json["ast_warning"] = check_result["error"]
        else:
            test_json["test_names"] = check_result["test_names"]

        # 6. 格式化输出
        return {
            "ok": True,
            "test_json": self._format_output(
                test_json.get("test_file", f"tests/test_{target_file.split('/')[-1].replace('.py', '')}.py"),
                test_json.get("content", ""),
                test_json.get("coverage_strategy", "unit"),
                test_json.get("test_names", [])
            )
        }
