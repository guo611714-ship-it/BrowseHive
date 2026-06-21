"""翰林代码代理 — 双模运行 + AST/Ruff自检 + FixManifest飞轮"""
import re
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional

from fix_engine.manifest import FixItem

logger = logging.getLogger(__name__)


class CodeComplexityAnalyzer:
    """基于任务特征的代码复杂度极简评估"""

    # Level 1 关键词
    LINT_KEYWORDS = ["lint", "import", "格式化", "重命名", "补全", "格式化代码", "修复格式"]

    # Level 2 关键词
    SIMPLE_KEYWORDS = ["getter", "setter", "函数", "方法实现", "属性"]

    # Level 3 关键词
    MEDIUM_KEYWORDS = ["适配", "联动", "类方法", "接口实现"]

    # Level 4-5 关键词（重量级）
    HEAVY_KEYWORDS = [
        "重构", "架构", "设计模式", "算法", "核心",
        "优化性能", "提取基类", "模块化", "解耦"
    ]

    def assess(self, task_description: str, context_lines: int = 0) -> int:
        """
        评估任务复杂度

        Args:
            task_description: 任务描述文本
            context_lines: 上下文代码行数

        Returns:
            复杂度等级 1-5
        """
        task_lower = task_description.lower()

        # 空任务默认保守等级4
        if not task_lower.strip():
            return 4

        # Level 1: 极轻量 (Lint修复, 补全单行, 加import, 重命名)
        if any(kw in task_lower for kw in self.LINT_KEYWORDS):
            return 1

        # Level 4-5: 重量 (架构重构, 设计模式应用, 核心算法实现, 跨文件重构)
        # 必须在 Level 3 之前检查，否则 context_lines<200 会误捕获
        if any(kw in task_lower for kw in self.HEAVY_KEYWORDS):
            return 4

        # Level 2: 轻量 (纯函数实现, 单文件内修改, getter/setter)
        if context_lines < 50:
            if any(kw in task_lower for kw in self.SIMPLE_KEYWORDS):
                return 2
            # 简单任务，上下文小
            if context_lines < 30 and not any(kw in task_lower for kw in self.HEAVY_KEYWORDS):
                return 2

        # Level 3: 中等 (类方法实现, 跨2-3个函数的联动修改, 适配)
        if context_lines < 200 or any(kw in task_lower for kw in self.MEDIUM_KEYWORDS):
            return 3

        # 默认 Level 4-5
        return 4


class HanlinAgent:
    """翰林代码代理 — 专司核心逻辑修撰、架构重构与代码拟稿"""

    # 快稿模式提示词（Level 1-2）
    FAST_TRACK_PROMPT = """你是翰林，专司代码生成。

规则：
1. 直接输出代码，不解释
2. 写完后必须 ast.parse() 校验
3. 如有 lint 问题，ruff check --fix 自动修复
4. 输出格式：代码块 + 自检结果

任务："""

    # 深度模式提示词（Level 3-5）
    DEEP_THINK_PROMPT = """你是翰林，专司架构重构。

规则：
1. 先读取 git diff 理解变更上下文
2. 输出重构蓝图（要修改的文件列表 + 每个文件的具体改动）
3. 禁止循环调用 write_file，必须调用 fix_manifest
4. 输出格式：蓝图 + FixManifest JSON

任务："""

    def __init__(self, model_client=None):
        self.complexity_analyzer = CodeComplexityAnalyzer()
        self.model_client = model_client

    def _select_prompt(self, level: int) -> str:
        """根据复杂度选择提示词"""
        if level <= 2:
            return self.FAST_TRACK_PROMPT
        return self.DEEP_THINK_PROMPT

    def _extract_code_block(self, response: str) -> Optional[str]:
        """从响应中提取代码块"""
        pattern = r'```(?:python)?\s*\n(.*?)```'
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _self_check(self, code: str) -> Dict[str, Any]:
        """AST + Lint 自检"""
        try:
            from ..tools.code_tools import ast_parse, ruff_check
        except ImportError:
            return {"ok": True, "warning": "code_tools不可用，跳过自检"}

        # AST 校验
        ast_result = ast_parse(code)
        if not ast_result["ok"]:
            return {"ok": False, "error": ast_result["error"]}

        # Ruff 检查
        ruff_result = ruff_check(code)
        if not ruff_result["ok"]:
            # 如果有修复后的代码，返回修复后的
            if ruff_result.get("fixed"):
                return {"ok": True, "fixed": ruff_result["fixed"]}
            return {"ok": False, "error": ruff_result.get("issues", [])}

        return {"ok": True}

    def _parse_fix_manifest(self, response: str, group_id: str) -> List[FixItem]:
        """从 LLM 响应中提取 FixManifest JSON 并转为 FixItem 列表"""
        # 尝试提取 JSON 块（```json ... ``` 或 ``` ... ```）
        json_match = re.search(r'```(?:json)?\s*\n(.*?)```', response, re.DOTALL)
        if not json_match:
            # 尝试直接匹配 JSON 对象
            json_match = re.search(r'\{[\s\S]*"fix_manifest"[\s\S]*\}', response)
        if not json_match:
            logger.warning("翰林: 响应中未找到 FixManifest JSON")
            return []

        raw = json_match.group(1) if json_match.lastindex else json_match.group(0)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("翰林: FixManifest JSON 解析失败: %s (raw[:200]=%s)", e, raw[:200])
            return []

        # 支持 fix_manifest 包裹格式或直接 tasks 格式
        manifest = data.get("fix_manifest", data)
        tasks = manifest.get("tasks", [])
        items = []
        for t in tasks:
            items.append(FixItem(
                id=t.get("id", f"auto-{len(items)}"),
                file=t.get("file", "unknown.py"),
                description=t.get("description", ""),
                agent_type=t.get("agent_type", "neiguan_yingzao"),
                line_start=t.get("line_start"),
                line_end=t.get("line_end"),
                context=t.get("context"),
                priority=t.get("priority", 0),
                metadata=t.get("metadata", {}),
                group_id=group_id,
            ))
        return items

    async def execute(self, task: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行代码任务（快稿模式：写码→主考出题→典簿阅卷）

        Args:
            task: 任务描述
            context: 上下文信息（可选）

        Returns:
            {"status": "success"/"error", "result": ..., "level": ...}
        """
        context = context or {}
        context_lines = context.get("context_lines", 0)
        code = context.get("code", "")
        target_file = context.get("target_file", "unknown.py")

        # 1. 评估复杂度
        level = self.complexity_analyzer.assess(task, context_lines)

        # 2. 生成 group_id（贯穿同一批次修复项）
        task_hash = hashlib.md5(task.encode()).hexdigest()[:8]
        group_id = f"fast-{task_hash}" if level <= 2 else f"deep-{task_hash}"

        # 3. 选择提示词
        prompt = self._select_prompt(level)

        # 3. 调用模型生成代码
        if self.model_client:
            full_prompt = f"{prompt}\n\n任务：{task}"
            try:
                response = await self.model_client.chat(
                    messages=[{"role": "user", "content": full_prompt}],
                    system="你是翰林，专司代码生成。直接输出代码，不解释。"
                )
                generated = self._extract_code_block(response.get("content", ""))
                if generated:
                    code = generated
            except Exception as e:
                logger.error("翰林: LLM调用失败(生成): %s", e)

        # 4. 自检闭环
        if code:
            check_result = self._self_check(code)
            if not check_result["ok"] and self.model_client:
                error_msg = str(check_result['error'])
                fix_prompt = f"{prompt}\n\n任务：{task}\n\n之前生成的代码有错误：{error_msg}\n请修复后重新输出。"
                try:
                    response = await self.model_client.chat(
                        messages=[{"role": "user", "content": fix_prompt}],
                        system="你是翰林，专司代码生成。修复代码错误后直接输出。"
                    )
                    fixed = self._extract_code_block(response.get("content", ""))
                    if fixed:
                        code = fixed
                except Exception as e:
                    logger.error("翰林: LLM调用失败(修复): %s", e)
            elif not check_result["ok"]:
                logger.warning("翰林: AST 自检失败且无 model_client: %s", check_result["error"])

        # 5. 快稿模式：调用主考出题
        test_json = None
        tests_passed = False
        circuit_breaker_triggered = False
        if level <= 2 and code:
            from .zhukao import ZhukaoAgent
            zhukao = ZhukaoAgent(model_client=self.model_client)

            # 读取 conftest（如果存在）
            conftest_context = "No conftest found"
            try:
                from pathlib import Path
                conftest_path = Path("tests/conftest.py")
                if conftest_path.exists():
                    conftest_context = conftest_path.read_text(encoding="utf-8")[:2000]
            except Exception:
                pass

            # 主考生成测试（带熔断器）
            test_result = await zhukao._circuit_breaker(
                zhukao.generate_tests,
                code=code,
                target_file=target_file,
                conftest_context=conftest_context,
                mode="fast_track"
            )
            if test_result.get("degraded"):
                circuit_breaker_triggered = True
                test_result = {"ok": False, "degraded": True}
            elif test_result["ok"]:
                test_json = test_result["test_json"]
                tests_passed = True

        # 6. 深度模式：解析 FixManifest
        fix_items: List[FixItem] = []
        if level >= 3 and self.model_client:
            deep_prompt = f"{self.DEEP_THINK_PROMPT}\n\n任务：{task}"
            try:
                response = await self.model_client.chat(
                    messages=[{"role": "user", "content": deep_prompt}],
                    system="你是翰林，专司架构重构。输出蓝图 + FixManifest JSON。"
                )
                fix_items = self._parse_fix_manifest(response.get("content", ""), group_id)
            except Exception as e:
                logger.error("翰林: LLM调用失败(深度模式): %s", e)

        return {
            "status": "success",
            "level": level,
            "task": task,
            "test_json": test_json,
            "tests_passed": tests_passed,
            "circuit_breaker_triggered": circuit_breaker_triggered,
            "fix_items": fix_items,
            "group_id": group_id,
            "message": f"翰林已接收任务，复杂度 Level {level}"
        }
