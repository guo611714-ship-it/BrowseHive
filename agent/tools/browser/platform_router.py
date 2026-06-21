"""三级漏斗智能平台路由器

L1: 正则拦截层 (0ms, 0成本) — 关键词硬匹配
L2: 轻量相似度层 (~5ms) — TF-IDF关键词加权匹配
L3: LLM编排器 (~300ms) — 深度理解，输出执行蓝图

Phase 2: L2向量层 + 熔断降级 + 反馈闭环
"""

import re
import json
import time
import logging
import random
import threading
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


# ─── 平台能力画像 ───────────────────────────────────────────────

PLATFORM_PROFILES: Dict[str, Dict[str, Any]] = {
    "deepseek": {
        "strengths": ["code", "reasoning", "math"],
        "speed": "fast",
        "cost": "low",
        "description": "代码生成、逻辑推理、数学证明",
    },
    "chatglm": {
        "strengths": ["academic", "knowledge_graph", "chinese"],
        "speed": "medium",
        "cost": "low",
        "description": "学术知识、知识图谱、中文理解",
    },
    "doubao": {
        "strengths": ["daily", "chinese_fluent", "general"],
        "speed": "very_fast",
        "cost": "low",
        "description": "日常对话、中文流畅、通用能力",
    },
}


# ─── 数据结构 ────────────────────────────────────────────────────

@dataclass
class RouteResult:
    """路由结果"""
    level: str                    # "L1" | "L2" | "L3"
    platforms: List[str]          # 选中的平台列表
    mode: str                     # "fast" | "deep"
    category: str                 # "code" | "academic" | "daily" | "reasoning" | "knowledge" | "general"
    confidence: float = 1.0       # 路由置信度 0-1
    reason: str = ""              # 路由原因


@dataclass
class ExecutionBlueprint:
    """执行蓝图"""
    route_result: RouteResult
    query: str
    fallback_platforms: List[str] = field(default_factory=lambda: ["doubao"])


# ─── L1 正则拦截层 ──────────────────────────────────────────────

L1_RULES = [
    # 代码类 → deepseek
    {
        "patterns": [
            r"写.*函数", r"实现.*算法", r"调试.*代码", r"代码.*问题",
            r"python|javascript|java|c\+\+|typescript|go|rust",
            r"api.*接口", r"sql.*查询", r"正则表达式", r"写.*脚本",
            r"bug.*修复", r"重构.*代码", r"单元测试", r"编译.*错误",
            r"报错.*解决", r"程序.*运行",
        ],
        "platforms": ["deepseek"],
        "mode": "fast",
        "category": "code",
    },
    # 推理类 → deepseek
    {
        "patterns": [
            r"逻辑.*推理", r"数学.*证明", r"计算.*过程",
            r"分析.*原因", r"为什么.*是", r"推导",
        ],
        "platforms": ["deepseek"],
        "mode": "deep",
        "category": "reasoning",
    },
    # 学术类 → chatglm
    {
        "patterns": [
            r"论文.*解读", r"解读.*论文", r"文献.*综述", r"学术.*写作",
            r"研究.*方法", r"引用.*格式", r"摘要.*写作",
            r"文献.*检索", r"学术.*规范",
        ],
        "platforms": ["chatglm"],
        "mode": "fast",
        "category": "academic",
    },
    # 知识类 → chatglm
    {
        "patterns": [
            r"什么是", r"原理.*是", r"概念.*解释",
            r"历史.*背景", r"定义.*是", r"区别.*是什么",
        ],
        "platforms": ["chatglm"],
        "mode": "fast",
        "category": "knowledge",
    },
    # 日常类 → doubao
    {
        "patterns": [
            r"写.*邮件", r"翻译.*成", r"总结.*一下",
            r"创意.*写作", r"帮我.*写", r"润色.*文章",
            r"改写.*这段", r"写.*通知", r"写.*报告",
        ],
        "platforms": ["doubao"],
        "mode": "fast",
        "category": "daily",
    },
]


def l1_route(query: str) -> Optional[RouteResult]:
    """L1正则拦截：0ms，命中即返回"""
    if not query or not query.strip():
        return None
    for rule in L1_RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, query, re.IGNORECASE):
                return RouteResult(
                    level="L1",
                    platforms=rule["platforms"],
                    mode=rule["mode"],
                    category=rule["category"],
                    confidence=1.0,
                    reason=f"正则命中: {pattern}",
                )
    return None


# ─── L2 轻量相似度层 ──────────────────────────────────────────

# TF-IDF-like关键词权重（手动调优，无需训练）
_CATEGORY_KEYWORDS: Dict[str, Dict[str, float]] = {
    "code": {
        "代码": 2.0, "函数": 2.0, "算法": 1.8, "编程": 2.0, "调试": 2.0,
        "python": 2.0, "javascript": 2.0, "java": 2.0, "c++": 2.0, "typescript": 2.0,
        "api": 1.5, "接口": 1.5, "sql": 1.8, "数据库": 1.5, "脚本": 1.8,
        "bug": 2.0, "修复": 1.5, "重构": 1.8, "测试": 1.5, "编译": 1.8,
        "报错": 1.5, "运行": 1.0, "程序": 1.5, "开发": 1.5, "实现": 1.2,
        "class": 1.5, "module": 1.5, "import": 1.5, "def": 1.8, "async": 1.5,
        "git": 1.5, "docker": 1.5, "linux": 1.2, "命令行": 1.2, "终端": 1.2,
        "排序": 1.5, "查找": 1.5, "遍历": 1.5, "递归": 1.8, "迭代": 1.5,
        "数据结构": 1.8, "链表": 1.8, "二叉树": 1.8, "图论": 1.8, "栈溢出": 1.8, "队列": 1.5,
    },
    "reasoning": {
        "推理": 2.0, "逻辑": 2.0, "证明": 2.0, "数学": 1.8, "计算": 1.5,
        "分析": 1.2, "为什么": 1.5, "原因": 1.5, "推导": 2.0, "论证": 2.0,
        "假设": 1.5, "结论": 1.5, "前提": 1.5, "归纳": 1.8, "演绎": 1.8,
        "概率": 1.5, "统计": 1.5, "方程": 1.5, "公式": 1.5, "定理": 1.8,
    },
    "academic": {
        "论文": 2.0, "学术": 2.0, "文献": 2.0, "研究": 1.5, "引用": 2.0,
        "综述": 2.0, "摘要": 1.8, "期刊": 1.8, "会议": 1.5, "发表": 1.5,
        "参考文献": 2.0, "doi": 2.0, "索引": 1.5, "影响因子": 1.8, "审稿": 1.8,
        "投稿": 1.8, "学术规范": 2.0, "写作": 1.0, "毕业": 1.5, "学位": 1.5,
    },
    "knowledge": {
        "什么是": 2.0, "原理": 1.8, "概念": 1.8, "定义": 1.8, "解释": 1.5,
        "历史": 1.5, "背景": 1.2, "区别": 1.5, "比较": 1.2, "分类": 1.5,
        "了解": 1.5, "理论": 1.5, "学说": 1.5, "流派": 1.5, "发展": 1.0,
        "演变": 1.5, "起源": 1.5, "本质": 1.5, "特征": 1.2, "属性": 1.2,
    },
    "daily": {
        "邮件": 2.0, "翻译": 2.0, "总结": 1.5, "写作": 1.5, "创意": 1.8,
        "润色": 2.0, "改写": 1.8, "通知": 1.8, "报告": 1.2, "方案": 1.2,
        "计划": 1.2, "安排": 1.2, "建议": 1.0, "推荐": 1.0, "选择": 1.0,
        "比较": 1.0, "优缺点": 1.2, "攻略": 1.5, "指南": 1.5, "教程": 1.2,
    },
}


def _tokenize(query: str) -> List[str]:
    """分词：中文按2-4字滑窗 + 英文按空格"""
    tokens = []
    # 英文单词
    for word in re.split(r'[\s,.;:!?，。；：！？]+', query):
        if len(word) > 1 and all(c.isascii() for c in word):
            tokens.append(word.lower())
    # 中文滑窗（2-4字）
    chinese_chars = re.findall(r'[一-鿿]+', query)
    for segment in chinese_chars:
        for n in (2, 3, 4):
            for i in range(len(segment) - n + 1):
                tokens.append(segment[i:i+n])
    return tokens


def _compute_similarity(query: str, category: str) -> float:
    """计算query与category的加权相似度"""
    keywords = _CATEGORY_KEYWORDS.get(category, {})
    if not keywords:
        return 0.0

    tokens = _tokenize(query)
    if not tokens:
        return 0.0

    score = 0.0
    for token in tokens:
        if token in keywords:
            score += keywords[token]
        else:
            # 子串匹配（仅单向：关键词作为子串出现在token中）
            for kw, weight in keywords.items():
                if len(kw) >= 2 and kw in token:
                    score += weight * 0.5
                    break

    # 归一化到0-1（0.5因子：需匹配约50%权重才满分）
    max_possible = sum(keywords.values())
    return min(score / max(max_possible * 0.5, 1.0), 1.0)


def l2_route(query: str) -> Optional[RouteResult]:
    """L2轻量相似度层：~5ms，TF-IDF关键词加权匹配"""
    if not query or not query.strip():
        return None

    # 计算每个类别的相似度
    scores = {}
    for category in _CATEGORY_KEYWORDS:
        sim = _compute_similarity(query, category)
        if sim > 0.1:  # 阈值
            scores[category] = sim

    if not scores:
        return None

    # 取最高分
    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]

    # 置信度阈值：>0.3 才走L2，否则留给L3
    if best_score < 0.3:
        return None

    # 类别→平台映射
    _CATEGORY_PLATFORMS = {
        "code": (["deepseek"], "fast"),
        "reasoning": (["deepseek"], "deep"),
        "academic": (["chatglm"], "fast"),
        "knowledge": (["chatglm"], "fast"),
        "daily": (["doubao"], "fast"),
    }

    platforms, mode = _CATEGORY_PLATFORMS.get(best_category, (["doubao"], "fast"))

    return RouteResult(
        level="L2",
        platforms=platforms,
        mode=mode,
        category=best_category,
        confidence=round(best_score, 2),
        reason=f"L2相似度匹配: {best_category}={best_score:.2f}",
    )


# ─── L3 LLM编排器 ──────────────────────────────────────────────

L3_ORCHESTRATOR_PROMPT = """你是一个AI平台编排器。根据用户任务，选择最合适的AI平台和模式。

## 平台能力
- deepseek: 代码生成、逻辑推理、数学（擅长技术问题）
- chatglm: 学术知识、知识图谱（擅长学术和知识问答）
- doubao: 日常对话、中文流畅（擅长日常和创意任务）

## 输出格式（纯JSON，无其他内容）
{"complexity":"simple|complex","category":"code|academic|daily","platforms":["平台名"],"mode":"fast|deep","reason":"选择原因"}

## 规则
- 简单任务：单平台 + fast模式
- 复杂任务：双平台 + deep模式
  - 代码→deepseek+chatglm
  - 学术→chatglm+doubao
  - 日常→doubao+deepseek
- 只输出JSON"""

# 配置路径（绝对路径，不依赖cwd）
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "model_config.json"

# 缓存ModelOrchestrator实例
_orch_instance = None
_orch_lock = threading.Lock()


def _get_orch():
    """获取缓存的ModelOrchestrator实例"""
    global _orch_instance
    if _orch_instance is not None:
        return _orch_instance
    with _orch_lock:
        if _orch_instance is not None:
            return _orch_instance
        try:
            from agent.model_orchestrator import ModelOrchestrator
            if _CONFIG_PATH.exists():
                _orch_instance = ModelOrchestrator(_CONFIG_PATH)
                return _orch_instance
        except Exception as e:
            logger.warning(f"ModelOrchestrator初始化失败: {e}")
    return None


def _extract_json(text: str) -> Optional[dict]:
    """从LLM响应中安全提取第一个JSON对象（支持嵌套）"""
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text) and text[idx] not in '{[':
        idx += 1
    if idx >= len(text):
        return None
    try:
        obj, _ = decoder.raw_decode(text, idx)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


async def l3_route(query: str) -> RouteResult:
    """L3 LLM编排：~300ms，深度理解，输出执行蓝图"""
    try:
        orch = _get_orch()
        if not orch:
            return _l3_fallback(query)

        client = orch.get_model_for_complexity(2)
        if not client:
            return _l3_fallback(query)

        response = await client.chat([
            {"role": "system", "content": L3_ORCHESTRATOR_PROMPT},
            {"role": "user", "content": query},
        ])

        content = response.get("content", "") if isinstance(response, dict) else str(response)
        plan = _extract_json(content)
        if not plan:
            return _l3_fallback(query)

        platforms = plan.get("platforms", ["doubao"])
        mode = plan.get("mode", "fast")
        category = plan.get("category", "general")
        reason = plan.get("reason", "L3编排器决策")

        valid_platforms = [p for p in platforms if p in PLATFORM_PROFILES]
        if not valid_platforms:
            valid_platforms = ["doubao"]

        return RouteResult(
            level="L3",
            platforms=valid_platforms,
            mode=mode,
            category=category,
            confidence=0.8,
            reason=reason,
        )

    except Exception as e:
        logger.warning(f"L3编排器异常: {e}")
        return _l3_fallback(query)


def _l3_fallback(query: str) -> RouteResult:
    """L3降级：基于关键词的简单分类"""
    code_kw = ["代码", "函数", "算法", "python", "javascript", "bug", "程序", "脚本"]
    academic_kw = ["论文", "学术", "研究", "文献", "引用"]

    q = query.lower()
    if any(kw in q for kw in code_kw):
        return RouteResult(level="L3", platforms=["deepseek"], mode="fast",
                          category="code", confidence=0.5, reason="L3降级:关键词匹配")
    if any(kw in q for kw in academic_kw):
        return RouteResult(level="L3", platforms=["chatglm"], mode="fast",
                          category="academic", confidence=0.5, reason="L3降级:关键词匹配")
    return RouteResult(level="L3", platforms=["doubao"], mode="fast",
                      category="general", confidence=0.3, reason="L3降级:默认通用")


# ─── 熔断降级 ──────────────────────────────────────────────────

class PlatformCircuitBreaker:
    """平台熔断降级器"""

    def __init__(self):
        self._failures: Dict[str, int] = defaultdict(int)
        self._successes: Dict[str, int] = defaultdict(int)
        self._last_failure: Dict[str, float] = {}
        self._circuit_open: Dict[str, bool] = {}
        self._lock = threading.Lock()
        # 配置
        self.failure_threshold = 3      # 连续失败N次 → 熔断
        self.recovery_timeout = 300.0   # 熔断后5分钟尝试恢复
        self.success_threshold = 2      # 恢复期成功N次 → 闭合

    def record_success(self, platform: str):
        """记录平台成功"""
        with self._lock:
            self._successes[platform] += 1
            self._failures[platform] = 0  # 重置连续失败
            # 恢复期成功 → 闭合电路
            if self._circuit_open.get(platform):
                if self._successes[platform] >= self.success_threshold:
                    self._circuit_open[platform] = False
                    logger.info(f"平台 {platform} 恢复正常，电路闭合")

    def record_failure(self, platform: str):
        """记录平台失败"""
        with self._lock:
            self._failures[platform] += 1
            self._successes[platform] = 0
            self._last_failure[platform] = time.time()
            # 连续失败 → 熔断
            if self._failures[platform] >= self.failure_threshold:
                self._circuit_open[platform] = True
                logger.warning(f"平台 {platform} 连续失败{self._failures[platform]}次，电路断开")

    def is_available(self, platform: str) -> bool:
        """检查平台是否可用"""
        with self._lock:
            return self._check_available_internal(platform)

    def _check_available_internal(self, platform: str) -> bool:
        """内部方法：检查平台是否可用（必须持有self._lock）"""
        if not self._circuit_open.get(platform):
            return True
        # 检查是否超过恢复期
        last_fail = self._last_failure.get(platform, 0)
        if time.time() - last_fail > self.recovery_timeout:
            # 进入半开状态，允许尝试
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """获取所有平台状态"""
        with self._lock:
            status = {}
            for platform in set(list(self._failures.keys()) + list(self._successes.keys())):
                status[platform] = {
                    "circuit_open": self._circuit_open.get(platform, False),
                    "consecutive_failures": self._failures.get(platform, 0),
                    "consecutive_successes": self._successes.get(platform, 0),
                    "available": self._check_available_internal(platform),
                }
            return status


# ─── 答案质量反馈闭环 ──────────────────────────────────────────

class FeedbackStore:
    """答案质量反馈存储"""

    # 绝对路径，不依赖cwd
    _DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / ".team" / "feedback.json"

    def __init__(self, json_path: Path = None):
        self._json_path = json_path or self._DEFAULT_PATH
        self._lock = threading.Lock()
        self._records: List[Dict] = []
        self._platform_scores: Dict[str, List[float]] = defaultdict(list)
        self._category_platform_scores: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._last_save_time: float = 0
        self._dirty_count: int = 0
        self._load()

    def record(self, query: str, platform: str, category: str, quality: float, latency_ms: int = 0):
        """记录答案质量"""
        with self._lock:
            entry = {
                "query": query[:200],  # 截断长查询
                "platform": platform,
                "category": category,
                "quality": quality,
                "latency_ms": latency_ms,
                "timestamp": time.time(),
            }
            self._records.append(entry)
            self._platform_scores[platform].append(quality)
            self._category_platform_scores[category][platform].append(quality)

            # 截断内存中的scores列表，防止无限增长
            if len(self._platform_scores[platform]) > 200:
                self._platform_scores[platform] = self._platform_scores[platform][-100:]
            if len(self._category_platform_scores[category][platform]) > 200:
                self._category_platform_scores[category][platform] = \
                    self._category_platform_scores[category][platform][-100:]

            # 保留最近1000条
            if len(self._records) > 1000:
                self._records = self._records[-1000:]

            # 节流写入：距上次写入>5s 或 累积>20条
            self._dirty_count += 1
            now = time.time()
            if self._dirty_count >= 20 or (now - self._last_save_time) > 5.0:
                self._save()
                self._dirty_count = 0
                self._last_save_time = now

    def get_platform_avg_quality(self, platform: str) -> float:
        """获取平台平均质量分（线程安全：锁内拷贝）"""
        with self._lock:
            scores = list(self._platform_scores.get(platform, []))
        if not scores:
            return 0.5  # 默认中等
        return sum(scores[-50:]) / len(scores[-50:])  # 最近50条均值

    def get_category_platform_quality(self, category: str) -> Dict[str, float]:
        """获取某类别下各平台的平均质量分（线程安全）"""
        with self._lock:
            cat_data = {p: list(s) for p, s in self._category_platform_scores.get(category, {}).items()}
        result = {}
        for platform, scores in cat_data.items():
            if scores:
                result[platform] = sum(scores[-30:]) / len(scores[-30:])
        return result

    def get_best_platform_for_category(self, category: str) -> Optional[str]:
        """获取某类别下表现最好的平台"""
        quality_map = self.get_category_platform_quality(category)
        if not quality_map:
            return None
        return max(quality_map, key=quality_map.get)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "total_records": len(self._records),
                "platforms": {
                    p: {
                        "count": len(s),
                        "avg_quality": round(sum(s[-50:]) / len(s[-50:]), 3) if s else 0,
                    }
                    for p, s in self._platform_scores.items()
                },
                "categories": {
                    c: {
                        platform: round(sum(scores[-30:]) / len(scores[-30:]), 3)
                        for platform, scores in platforms.items() if scores
                    }
                    for c, platforms in self._category_platform_scores.items()
                },
            }

    def _save(self):
        try:
            self._json_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "records": self._records[-500:],  # 保留最近500条
                "platform_scores": {p: s[-100:] for p, s in self._platform_scores.items()},
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            with open(self._json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"保存反馈数据失败（非致命）: {e}")

    def _load(self):
        try:
            if not self._json_path.exists():
                return
            with open(self._json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._records = data.get("records", [])
            for p, scores in data.get("platform_scores", {}).items():
                self._platform_scores[p] = scores
            # 重建分类数据
            for entry in self._records:
                cat = entry.get("category", "general")
                plat = entry.get("platform", "doubao")
                qual = entry.get("quality", 0.5)
                self._category_platform_scores[cat][plat].append(qual)
        except Exception as e:
            logger.debug(f"加载反馈数据失败（非致命）: {e}")


def score_answer_quality(answer: str, query: str, platform: str) -> float:
    """评估答案质量（0-1）"""
    if not answer:
        return 0.0

    score = 0.4  # 基础分

    # 长度合理性（100-3000字最佳）
    length = len(answer)
    if 100 < length < 3000:
        score += 0.15
    elif 50 < length < 5000:
        score += 0.05

    # 包含结构化内容
    if any(marker in answer for marker in ["```", "1.", "##", "- ", "* "]):
        score += 0.1

    # 包含代码（代码任务加分）
    if "```" in answer and platform == "deepseek":
        score += 0.1

    # 包含引用/来源（学术任务加分）
    if any(marker in answer for marker in ["[", "参考", "来源", "引用"]):
        score += 0.05

    # 语言流畅度（中文比例）
    chinese_chars = sum(1 for c in answer if '一' <= c <= '鿿')
    if chinese_chars > len(answer) * 0.3:
        score += 0.05

    # 明确拒绝模式：需要"抱歉/不好意思" + ("无法"/"不能"/"没有办法") 组合才扣分
    refusal_pattern = r'(抱歉|不好意思).{0,10}(无法|不能|没有办法|做不到)'
    if re.search(refusal_pattern, answer):
        score -= 0.1

    return max(0.0, min(score, 1.0))


# ─── 统一路由入口 ──────────────────────────────────────────────

class TaskRouter:
    """三级漏斗智能路由器（Phase 2: L2 + 熔断 + 反馈）"""

    def __init__(self):
        self.circuit_breaker = PlatformCircuitBreaker()
        self.feedback_store = FeedbackStore()

    def route(self, query: str) -> RouteResult:
        """路由：L1 → L2 → L3"""
        # L1: 正则拦截
        result = l1_route(query)
        if result:
            logger.debug(f"L1命中: {result.category} -> {result.platforms}")
            return result

        # L2: 轻量相似度
        result = l2_route(query)
        if result:
            logger.debug(f"L2命中: {result.category} -> {result.platforms} (sim={result.confidence})")
            return result

        # L3: 降级
        return _l3_fallback(query)

    async def route_async(self, query: str) -> RouteResult:
        """异步路由：L1 → L2 → L3（注意：不含熔断保护，由调用方自行 apply_circuit_breaker）"""
        # L1: 正则拦截
        result = l1_route(query)
        if result:
            logger.debug(f"L1命中: {result.category} -> {result.platforms}")
            return result

        # L2: 轻量相似度
        result = l2_route(query)
        if result:
            logger.debug(f"L2命中: {result.category} -> {result.platforms} (sim={result.confidence})")
            return result

        # L3: LLM编排
        return await l3_route(query)

    def apply_circuit_breaker(self, result: RouteResult) -> RouteResult:
        """应用熔断降级：过滤不可用平台"""
        available = [p for p in result.platforms if self.circuit_breaker.is_available(p)]
        if not available:
            # 全部熔断 → 检查doubao是否可用
            if self.circuit_breaker.is_available("doubao"):
                available = ["doubao"]
                logger.warning("所有平台熔断，降级到doubao")
            else:
                # 所有平台（含doubao）都不可用 → 返回空列表
                logger.error("所有平台均不可用（含doubao），无法降级")
                return RouteResult(
                    level=result.level,
                    platforms=[],
                    mode=result.mode,
                    category=result.category,
                    confidence=0.0,
                    reason=result.reason + " [所有平台不可用]",
                )
        if available != result.platforms:
            return RouteResult(
                level=result.level,
                platforms=available,
                mode=result.mode,
                category=result.category,
                confidence=result.confidence * 0.9,  # 降级略微降低置信度
                reason=result.reason + " [熔断降级]",
            )
        return result

    def record_platform_result(self, platform: str, success: bool, latency_ms: int = 0):
        """记录平台调用结果（更新熔断器）"""
        if success:
            self.circuit_breaker.record_success(platform)
        else:
            self.circuit_breaker.record_failure(platform)

    def record_feedback(self, query: str, platform: str, category: str, quality: float, latency_ms: int = 0):
        """记录答案质量反馈"""
        self.feedback_store.record(query, platform, category, quality, latency_ms)

    def create_blueprint(self, result: RouteResult, query: str) -> ExecutionBlueprint:
        """创建执行蓝图"""
        return ExecutionBlueprint(
            route_result=result,
            query=query,
            fallback_platforms=["doubao"],
        )


# ─── 全局实例（线程安全单例）────────────────────────────────────

_router: Optional[TaskRouter] = None
_router_lock = threading.Lock()


def get_router() -> TaskRouter:
    """获取全局路由器实例"""
    global _router
    if _router is not None:
        return _router
    with _router_lock:
        if _router is not None:
            return _router
        _router = TaskRouter()
        return _router



# ─── 重新导出拆分模块 ─────────────────────────────────────────

# AB测试框架（从 ab_test.py 导入）
from .ab_test import ABTestResult, ABTestFramework, get_ab_test  # noqa: F401

# 仪表盘（从 dashboard.py 导入）
from .dashboard import DashboardStats, RouterDashboard, get_dashboard  # noqa: F401

__all__ = [
    # 数据结构
    "RouteResult", "ExecutionBlueprint",
    # 路由函数
    "l1_route", "l2_route", "l3_route",
    # 核心类
    "PlatformCircuitBreaker", "FeedbackStore", "TaskRouter",
    # 全局实例
    "get_router",
    # AB测试
    "ABTestResult", "ABTestFramework", "get_ab_test",
    # 仪表盘
    "DashboardStats", "RouterDashboard", "get_dashboard",
    # 工具函数
    "score_answer_quality",
    # 平台画像
    "PLATFORM_PROFILES",
]
