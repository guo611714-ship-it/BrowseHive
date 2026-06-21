# 三级漏斗智能平台路由器 — 完整设计文档

## 1. 问题背景

当前 `batch_ask` 并行向4个AI平台提问（doubao, deepseek, kimi, chatglm），存在以下问题：

| 问题 | 影响 |
|------|------|
| 冗余浪费 | 简单任务也问4个平台，响应时间翻倍 |
| 无智能路由 | 不区分任务类型，所有平台同权重 |
| 缺乏反馈 | 不知道哪个平台回答好，无法自学习 |
| 平台退化无感知 | 平台挂了或变差，用户无感知 |

**核心洞察**：`batch_ask` 不是搜索引擎（多源聚合），而是**AI协作系统**（按需调度）。不同任务应由最合适的平台处理。

---

## 2. 设计目标

1. **效率提升**：简单任务1平台10秒完成，复杂任务2平台20秒完成（vs 现在4平台30秒+）
2. **精度提升**：按平台优势匹配任务，回答质量提升
3. **成本控制**：减少不必要的API调用
4. **弹性降级**：平台故障时自动切换
5. **自学习**：通过答案质量反馈持续优化路由

---

## 3. 平台能力画像

### 3.1 三大平台定位

| 平台 | 核心优势 | 擅长领域 | 速度 | 适用场景 |
|------|----------|----------|------|----------|
| **deepseek** | 代码生成、逻辑推理、数学证明 | code, reasoning, math | 快 | 代码调试、算法设计、技术问题 |
| **chatglm** | 学术知识、知识图谱、中文理解 | academic, knowledge, chinese | 中 | 论文解读、知识问答、学术写作 |
| **doubao** | 日常对话、中文流畅、通用能力 | daily, chinese_fluent, general | 极快 | 日常问答、创意写作、快速响应 |

### 3.2 任务类型矩阵

| 任务类型 | 关键词特征 | 推荐平台 | 模式 |
|----------|-----------|----------|------|
| **代码类** | 写函数、调试、算法、API、代码 | deepseek | fast/deep |
| **推理类** | 分析、逻辑、证明、计算 | deepseek | deep |
| **学术类** | 论文、研究、文献、学术 | chatglm | deep |
| **知识类** | 什么是、原理、概念、解释 | chatglm | fast |
| **日常类** | 写作、创意、总结、翻译 | doubao | fast |
| **通用类** | 无明显特征 | doubao | fast |

---

## 4. 三级漏斗架构

### 4.1 整体流程

```
用户输入 (query)
    │
    ▼
┌─────────────────────────┐
│  L1: 正则拦截层 (0ms)   │  ← 关键词硬匹配，零成本
│  命中 → 直接路由         │
└───────────┬─────────────┘
            │ 未命中
            ▼
┌─────────────────────────┐
│  L2: 向量相似度层 (~50ms)│  ← 轻量embedding，低成本
│  相似度 > 0.85 → 路由    │
└───────────┬─────────────┘
            │ 未命中 / 相似度不足
            ▼
┌─────────────────────────┐
│  L3: LLM编排器 (~300ms) │  ← 深度理解，输出执行蓝图
│  输出: DAG + 平台 + 模式 │
└─────────────────────────┘
```

### 4.2 L1 正则拦截层

**目标**：0ms、0成本，拦截80%的简单任务

**规则设计**：

```python
L1_RULES = [
    # 代码类 → deepseek
    {
        "patterns": [r"写.*函数", r"实现.*算法", r"调试.*代码", r"python|javascript|java|c\+\+",
                     r"api.*接口", r"sql.*查询", r"正则表达式"],
        "platforms": ["deepseek"],
        "mode": "fast",
        "category": "code"
    },
    # 学术类 → chatglm
    {
        "patterns": [r"论文.*解读", r"文献.*综述", r"学术.*写作", r"研究.*方法",
                     r"引用.*格式", r"摘要.*写作"],
        "platforms": ["chatglm"],
        "mode": "fast",
        "category": "academic"
    },
    # 日常类 → doubao
    {
        "patterns": [r"写.*邮件", r"翻译.*成", r"总结.*一下", r"创意.*写作",
                     r"帮我.*写", r"润色.*文章"],
        "platforms": ["doubao"],
        "mode": "fast",
        "category": "daily"
    },
]
```

**命中逻辑**：

```python
def l1_route(query: str) -> Optional[RouteResult]:
    """L1正则拦截：0ms，命中即返回"""
    for rule in L1_RULES:
        for pattern in rule["patterns"]:
            if re.search(pattern, query, re.IGNORECASE):
                return RouteResult(
                    level="L1",
                    platforms=rule["platforms"],
                    mode=rule["mode"],
                    category=rule["category"],
                    confidence=1.0
                )
    return None  # 未命中，进入L2
```

### 4.3 L2 向量相似度层

**目标**：~50ms，低成本，处理L1未命中的模糊任务

**实现方式**：

1. 预计算每个平台历史成功案例的embedding
2. 对新query计算embedding
3. 计算余弦相似度，超过阈值则路由

**注意**：Phase 1可暂缓L2，用L1+L3覆盖。L2的价值在于：
- 减少L3的LLM调用成本
- 处理"L1正则未命中但其实很常见"的任务

**Phase 1降级策略**：L1未命中直接进入L3，跳过L2。

### 4.4 L3 LLM编排器

**目标**：~300ms，深度理解，输出执行蓝图

**核心职责**：
- 判断任务复杂度（simple/complex）
- 识别任务类别（code/academic/daily）
- 选择平台和模式
- 输出执行蓝图（DAG）

**Prompt设计**：

```python
L3_ORCHESTRATOR_PROMPT = """你是一个AI平台编排器。根据用户任务，选择最合适的AI平台和模式。

## 平台能力
- deepseek: 代码生成、逻辑推理、数学（擅长技术问题）
- chatglm: 学术知识、知识图谱（擅长学术和知识问答）
- doubao: 日常对话、中文流畅（擅长日常和创意任务）

## 输出格式（JSON）
{
  "complexity": "simple|complex",
  "category": "code|academic|daily",
  "platforms": ["平台名"],
  "mode": "fast|deep",
  "reason": "选择原因"
}

## 规则
- 简单任务：单平台 + fast模式
- 复杂任务：双平台 + deep模式（代码→deepseek+chatglm，学术→chatglm+doubao，日常→doubao+deepseek）
- 只输出JSON，不要其他内容
"""
```

**输出示例**：

```json
// 简单代码任务
{
  "complexity": "simple",
  "category": "code",
  "platforms": ["deepseek"],
  "mode": "fast",
  "reason": "单平台即可处理的代码任务"
}

// 复杂代码任务
{
  "complexity": "complex",
  "category": "code",
  "platforms": ["deepseek", "chatglm"],
  "mode": "deep",
  "reason": "需要深度推理和多角度分析"
}

// 学术任务
{
  "complexity": "complex",
  "category": "academic",
  "platforms": ["chatglm", "doubao"],
  "mode": "deep",
  "reason": "学术问题需要知识图谱和多角度分析"
}
```

---

## 5. 执行蓝图（DAG）

### 5.1 简单任务DAG

```
[用户输入] → [平台A, fast模式] → [LLM整合] → [输出]
```

- 单平台执行
- 快速模式
- 直接整合输出

### 5.2 复杂任务DAG

```
[用户输入] → ┌─[平台A, deep模式]─┐
              │                   ├─→ [LLM整合] → [输出]
              └─[平台B, deep模式]─┘
```

- 双平台并行执行
- 深度模式
- LLM整合多源结果

### 5.3 DAG执行逻辑

```python
async def execute_dag蓝prints(blueprint: dict, query: str) -> str:
    """根据执行蓝图执行"""
    platforms = blueprint["platforms"]
    mode = blueprint["mode"]

    if len(platforms) == 1:
        # 简单任务：单平台
        result = await ask_platform(platforms[0], query, mode)
        return await llm_synthesize([result], query)
    else:
        # 复杂任务：双平台并行
        tasks = [ask_platform(p, query, mode) for p in platforms]
        results = await asyncio.gather(*tasks)
        return await llm_synthesize(results, query)
```

---

## 6. 熔断降级机制

### 6.1 健康度熔断

基于 `HealthMonitor` 的趋势分析：

```python
def check_platform_health(platform: str) -> bool:
    """检查平台健康度，决定是否可用"""
    report = health_monitor.get_trend_report(platform)

    # 连续失败 ≥ 3次 → 熔断
    if report.get("consecutive_failures", 0) >= 3:
        return False

    # 失败率 > 50% → 熔断
    if report.get("failure_rate", 0) > 0.5:
        return False

    # 延迟上升趋势 + 高延迟 → 降级到fast模式
    if report.get("latency_trend") == "rising":
        return "degraded"  # 可用但降级

    return True
```

### 6.2 成本熔断

```python
COST_LIMITS = {
    "per_query": 0.1,      # 单次查询上限 $0.1
    "daily": 10.0,         # 日上限 $10
    "monthly": 200.0,      # 月上限 $200
}

def check_cost_budget(platform: str, estimated_cost: float) -> bool:
    """检查成本预算"""
    daily_cost = get_daily_cost(platform)
    if daily_cost + estimated_cost > COST_LIMITS["daily"]:
        return False
    return True
```

### 6.3 降级策略

```python
async def execute_with_fallback(blueprint: dict, query: str) -> str:
    """带降级的执行"""
    platforms = blueprint["platforms"]

    # 过滤不健康的平台
    healthy_platforms = [p for p in platforms if check_platform_health(p)]

    if not healthy_platforms:
        # 全部熔断 → 降级到doubao（最稳定的通用平台）
        healthy_platforms = ["doubao"]

    if len(healthy_platforms) == 1:
        # 降级为单平台
        result = await ask_platform(healthy_platforms[0], query, "fast")
        return await llm_synthesize([result], query)
    else:
        # 正常双平台
        tasks = [ask_platform(p, query, blueprint["mode"]) for p in healthy_platforms]
        results = await asyncio.gather(*tasks)
        return await llm_synthesize(results, query)
```

---

## 7. 答案质量反馈闭环

### 7.1 质量评分

```python
async def score_answer_quality(answer: str, query: str, platform: str) -> float:
    """评估答案质量（0-1）"""
    score = 0.5  # 基础分

    # 长度合理性
    if 50 < len(answer) < 2000:
        score += 0.1

    # 包含代码块（代码任务）
    if "```" in answer:
        score += 0.1

    # 包含引用/来源（学术任务）
    if any(marker in answer for marker in ["[", "参考", "来源"]):
        score += 0.1

    # 结构化程度
    if any(marker in answer for marker in ["1.", "##", "- "]):
        score += 0.1

    # LLM评估（可选，成本高）
    # evaluation = await llm_client.chat([...])

    return min(score, 1.0)
```

### 7.2 反馈记录

```python
def record_feedback(query: str, platform: str, quality: float, latency: float):
    """记录反馈，用于优化路由"""
    feedback_entry = {
        "query": query,
        "platform": platform,
        "quality": quality,
        "latency": latency,
        "timestamp": datetime.now().isoformat()
    }

    # 保存到反馈数据库
    save_feedback(feedback_entry)

    # 更新平台统计
    update_platform_stats(platform, quality, latency)
```

### 7.3 动态优化

```python
def optimize_routing():
    """基于反馈优化路由规则"""
    # 1. 统计各平台在不同任务类型上的表现
    stats = analyze_platform_performance()

    # 2. 调整平台权重
    for task_type, platform_stats in stats.items():
        best_platform = max(platform_stats.items(), key=lambda x: x[1]["avg_quality"])
        update_routing_weight(task_type, best_platform[0], weight=1.2)

    # 3. 发现新的路由模式
    new_patterns = discover_patterns()
    for pattern in new_patterns:
        add_l1_rule(pattern)
```

---

## 8. Phase 1 实现范围

### 8.1 必做

| 模块 | 内容 | 复杂度 |
|------|------|--------|
| PlatformProfile | 平台能力画像数据结构 | 低 |
| L1Router | 正则拦截层 | 低 |
| L3Orchestrator | LLM编排器 | 中 |
| TaskRouter | 统一路由入口 | 中 |
| batch_ask集成 | 替换现有并行逻辑 | 中 |

### 8.2 可暂缓

| 模块 | 原因 |
|------|------|
| L2向量层 | L1+L3已覆盖80%场景，L2是锦上添花 |
| 熔断降级 | 需要HealthMonitor数据积累 |
| 反馈闭环 | 需要线上数据验证 |
| DAG执行器 | Phase 1用简单if-else足够 |

### 8.3 文件结构

```
agent/tools/browser/
├── platform_router.py      # 新增：三级漏斗路由器
│   ├── PlatformProfile     # 平台画像
│   ├── L1Router           # 正则拦截
│   ├── L3Orchestrator     # LLM编排
│   └── TaskRouter         # 统一路由
├── ai_search.py            # 修改：batch_ask集成路由器
└── platform_selectors.json # 不变：平台选择器配置
```

---

## 9. 接口设计

### 9.1 核心接口

```python
@dataclass
class RouteResult:
    """路由结果"""
    level: str                    # "L1" | "L3"
    platforms: List[str]          # 选中的平台列表
    mode: str                     # "fast" | "deep"
    category: str                 # "code" | "academic" | "daily"
    confidence: float             # 路由置信度 0-1
    reason: str = ""              # 路由原因

@dataclass
class ExecutionBlueprint:
    """执行蓝图"""
    route_result: RouteResult
    query: str
    steps: List[dict]             # DAG步骤
    fallback_platforms: List[str] # 降级平台
```

### 9.2 使用示例

```python
# 初始化路由器
router = TaskRouter()

# 路由
result = router.route("帮我写一个Python快速排序函数")
# → RouteResult(level="L1", platforms=["deepseek"], mode="fast", category="code")

# 执行
blueprint = router.create_blueprint(result, "帮我写一个Python快速排序函数")
answer = await execute_blueprint(blueprint)

# 或一步到位
answer = await router.route_and_execute("帮我写一个Python快速排序函数")
```

---

## 10. 性能预期

| 指标 | 现在（4平台并行） | Phase 1（智能路由） | 提升 |
|------|-------------------|-------------------|------|
| 简单任务耗时 | ~30s | ~10s | 3x |
| 复杂任务耗时 | ~30s | ~20s | 1.5x |
| API调用次数 | 4次/查询 | 1-2次/查询 | 50-75% |
| 回答质量 | 平均 | 按平台优势匹配 | +20% |
| 平台故障影响 | 全部失败 | 自动降级 | 容错 |

---

## 11. 与现有系统集成

### 11.1 batch_ask改造

```python
# 现在
async def batch_ask(query, platforms="doubao,deepseek,kimi,chatglm", mode="auto"):
    # 并行问4个平台

# 改造后
async def batch_ask(query, platforms=None, mode=None):
    """智能路由版本"""
    router = TaskRouter()

    if platforms and mode:
        # 用户指定平台和模式（兼容旧接口）
        result = RouteResult(level="manual", platforms=platforms.split(","),
                           mode=mode, category="unknown", confidence=1.0)
    else:
        # 智能路由
        result = router.route(query)

    # 执行
    blueprint = router.create_blueprint(result, query)
    return await execute_blueprint(blueprint)
```

### 11.2 与ModelOrchestrator集成

```python
# 路由决策可参考模型健康度
class TaskRouter:
    def __init__(self):
        self.health_monitor = HealthMonitor()

    def route(self, query: str) -> RouteResult:
        # L1/L3路由
        result = self._route(query)

        # 检查平台健康度
        if not self.health_monitor.is_healthy(result.platforms[0]):
            # 替换为健康平台
            result.platforms = [self._get_healthy_fallback()]

        return result
```

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| L3 LLM编排器延迟高 | 路由耗时增加 | L1正则覆盖80%简单任务，减少L3调用 |
| L3编排结果不稳定 | 同query不同路由 | 输出结构化JSON + 重试机制 |
| 平台能力变化 | 路由不准 | 反馈闭环持续优化 |
| 新任务类型出现 | L1未覆盖 | L3兜底 + 定期更新L1规则 |

---

## 13. 总结

三级漏斗智能平台路由器的核心价值：

1. **效率**：简单任务秒级响应（L1直接路由）
2. **精度**：按平台优势匹配任务类型
3. **弹性**：熔断降级保证可用性
4. **进化**：反馈闭环持续优化

Phase 1聚焦L1+L3，用最小成本实现80%的价值。后续迭代加入L2向量层和反馈闭环，逐步逼近最优路由。
