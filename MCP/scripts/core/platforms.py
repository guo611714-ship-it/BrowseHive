"""平台定义和管理."""

from .config import config, PLATFORM_CAPABILITIES, TASK_KEYWORDS

# 平台定义
PLATFORMS = {
    "doubao": {
        "name": "豆包",
        "url": "https://www.doubao.com/chat/",
        "mode": "超能模式",
        "purpose": "中文内容生成（润色/写作/翻译/文案/创意/一键生成/联网搜索/文件上传）",
        "login_keywords": ["sign_in", "login", "passport"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "url": "https://chat.deepseek.com/",
        "mode": "专家模式+深度思考+R1推理+智能搜索",
        "purpose": "专业技术文档（代码/推理/数学/分析/研究/报告/DeepSeek-V3&R1）",
        "login_keywords": ["sign_in", "login"],
    },
    "volcengine": {
        "name": "火山引擎",
        "url": "https://ai.volcengine.com/experience/ark?mode=chat&modelId=ep-20260512152006-fxsc9",
        "mode": "Doubao-Seed-2.0-pro",
        "purpose": "企业级AI平台（代码/技术分析/联网/视觉/多AI Agents/文件上传）",
        "login_keywords": ["login", "signin", "passport"],
    },
    "ouyi": {
        "name": "欧亿AI",
        "url": "https://ai.rcouyi.com/home",
        "mode": "高级VIP",
        "purpose": "多功能AI平台（对话、写作、思维导图、绘图、API管理）",
        "login_keywords": ["login", "signin"],
    },
}

# 任务类型检测
def detect_task_type(task: str) -> str:
    """检测任务类型：browser/api/mixed"""
    if not task:
        return "mixed"
    task_lower = task.lower()
    has_browser = any(kw in task_lower for kw in TASK_KEYWORDS["browser"])
    has_api = any(kw in task_lower for kw in TASK_KEYWORDS["api"])
    if has_browser and not has_api:
        return "browser"
    elif has_api and not has_browser:
        return "api"
    return "mixed"

def assess_complexity(message: str) -> dict:
    """评估任务复杂度，返回等级和推荐平台。

    新逻辑：
    - 所有任务都通过能力匹配（移除代码任务的L3特殊处理）
    - 如果best_score>0（有匹配平台）：
      - L1 (<5字符): 短文本，直接发送，不树状
      - L2/L3 (>=5字符): 树状调用，主平台=best_platform，辅助平台=其他平台top 2
    - 如果best_score==0: 按健康评分选择，不树状
    """
    char_count = len(message)
    msg_lower = message.lower()

    # 检测平台能力匹配
    platform_scores = {}
    for pk, caps in PLATFORM_CAPABILITIES.items():
        score = sum(1 for cap in caps if cap in msg_lower)
        platform_scores[pk] = score

    best_platform = max(platform_scores, key=platform_scores.get) if platform_scores else ""
    best_score = platform_scores.get(best_platform, 0) if best_platform else 0

    # 有平台能力匹配
    if best_score > 0:
        # L1: 极短文本 (<5字符) → 直接发送
        if char_count < 5:
            return {
                "level": 1,
                "platform": best_platform,
                "reason": "极短文本",
                "tree": False
            }

        # L2/L3: >=5字符 → 树状调用
        # 辅助平台：按能力匹配分数降序选择其他平台，取top 2
        other_platforms = sorted(
            [(pk, score) for pk, score in platform_scores.items() if pk != best_platform],
            key=lambda x: x[1],
            reverse=True
        )
        secondary = [pk for pk, _ in other_platforms[:2]]

        return {
            "level": 2 if char_count < 100 else 3,
            "platform": best_platform,
            "reason": "能力匹配" if char_count < 100 else "复杂任务",
            "tree": True,
            "tree_config": {
                "layer1": best_platform,
                "layer2": secondary,
            }
        }

    # 无能力匹配：按健康评分选择单一平台
    if not message:
        return {"level": 1, "platform": "doubao", "reason": "空消息", "tree": False}

    platform = recommend_platform(message)
    if not platform:
        platform = "doubao"

    return {
        "level": 2,
        "platform": platform,
        "reason": "健康评分优选",
        "tree": False
    }

def recommend_platform(message: str, error_stats: dict = None,
                       response_times: dict = None, fetch_stats: dict = None,
                       response_quality_log: list = None) -> str:
    """智能平台推荐：结合任务匹配度+健康评分+历史表现，返回最优平台key。

    参数说明:
    - message: 用户消息
    - error_stats: 错误统计 {platform: {type: count}}
    - response_times: 响应时间 {platform: [times]}
    - fetch_stats: 获取统计 {platform: {success, fail, total_time}}
    - response_quality_log: 响应质量日志 [{"platform": str, "score": int, "ts": float}]
    """
    if not message:
        return ""

    msg_lower = message.lower()

    # 1. 关键词匹配分 (0-10)
    keyword_scores = {}
    for platform, keywords in PLATFORM_CAPABILITIES.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        keyword_scores[platform] = min(score * 2, 10)

    # 2. 健康评分 (0-10)
    health_scores = {}
    for pk in PLATFORMS.keys():
        health = 10

        # 错误扣分
        stats = error_stats.get(pk, {}) if error_stats else {}
        total_err = sum(stats.values())
        if total_err > 5:
            health -= min(total_err * 0.5, 5)

        # 响应时间扣分
        times = response_times.get(pk, []) if response_times else []
        if times:
            avg_time = sum(times) / len(times)
            if avg_time > 10:
                health -= min((avg_time - 10) * 0.3, 3)

        # 成功率加分
        fs = fetch_stats.get(pk, {}) if fetch_stats else {}
        total_fetch = fs.get("success", 0) + fs.get("fail", 0)
        if total_fetch > 0:
            success_rate = fs["success"] / total_fetch
            health += (success_rate - 0.5) * 4

        # 响应质量加分
        if response_quality_log:
            quality_scores = [q["score"] for q in response_quality_log if q["platform"] == pk]
            if quality_scores:
                avg_quality = sum(quality_scores[-5:]) / min(len(quality_scores), 5)
                health += (avg_quality - 5) * 0.5  # 质量5分基础

        # 并发负载惩罚 (active_requests 需要外部传入)
        # 这里简化，不检查并发

        health_scores[pk] = max(0, min(health, 10))

    # 3. 综合评分 (关键词60% + 健康40%)
    final_scores = {}
    for pk in PLATFORMS.keys():
        kw = keyword_scores.get(pk, 0)
        hp = health_scores.get(pk, 5)
        if kw == 0:
            final_scores[pk] = hp * 0.3
        else:
            final_scores[pk] = kw * 0.6 + hp * 0.4

    if not final_scores:
        return ""

    best = max(final_scores, key=final_scores.get)
    # 如果最高分太低，返回空
    if final_scores[best] < 1:
        return ""
    return best

def route_by_capability(message: str) -> str:
    """根据消息内容智能路由到最佳平台."""
    assessment = assess_complexity(message)
    return assessment["platform"]

def is_login_page(url: str, platform_key: str) -> bool:
    """检查是否为登录页面."""
    url_lower = url.lower()
    return any(kw in url_lower for kw in PLATFORMS[platform_key]["login_keywords"])
