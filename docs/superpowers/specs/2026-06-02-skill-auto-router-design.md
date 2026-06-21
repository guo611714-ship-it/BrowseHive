# Skill Auto-Router for Agent Team

> 日期: 2026-06-02
> 状态: 设计完成，待实现
> 决策: Prompt 注入 + Dispatcher 预路由 + frontmatter 自动索引

## 1. 背景

当前 Agent Team 的 70 个 skill（SKILL.md）无法被子代理智能调用：
- 仅 2/8 子代理有 `load_skill` 工具
- 无自动路由机制
- dispatcher 不会根据任务匹配 skill

**目标**：dispatcher 在派遣子代理前，自动匹配最相关的 skill，将其内容注入子代理的 system_prompt，使子代理按 skill 指令行动。

## 2. 架构

```
任务进入 Dispatcher
  │
  ▼
SkillIndex.scan()  ← 启动时扫描所有 SKILL.md frontmatter
  │
  ▼
SkillRouter.match(task_text)  ← 两级匹配：精确 → 模糊
  │
  ├─ 匹配到 → 读取 SKILL.md 全文
  │            注入到子代理的 system_prompt 末尾
  │
  └─ 无匹配 → 正常派遣（不注入 skill）
```

### 核心组件

| 组件 | 文件 | 职责 |
|------|------|------|
| `SkillIndex` | `agent/skill_index.py` | 启动时扫描 `.claude/skills/*/SKILL.md`，解析 frontmatter，构建内存索引 |
| `SkillRouter` | `agent/skill_router.py` | 接收任务文本，匹配最相关的 skill，返回 SKILL.md 内容 |
| `Dispatcher 集成` | `agent/tools/dispatch/dispatcher.py` | 在 `dispatch()` 中调用 SkillRouter，将 skill 内容注入 system_prompt |

## 3. SkillIndex — 扫描与索引

### 数据结构

```python
@dataclass
class SkillEntry:
    name: str                    # skill 目录名
    description: str             # frontmatter description
    triggers: List[str]          # 触发关键词
    synonyms: List[str]          # 同义词
    prompt: str                  # SKILL.md 全文（去掉 frontmatter）
    path: str                    # 文件路径
    priority: int                # 匹配优先级（默认 0）

class SkillIndex:
    _entries: Dict[str, SkillEntry]      # name -> entry
    _trigger_map: Dict[str, List[str]]   # trigger -> [skill_names]（反向索引）
    _synonym_map: Dict[str, List[str]]   # synonym -> [skill_names]
```

### 扫描逻辑

启动时遍历 `.claude/skills/*/SKILL.md`，解析 YAML frontmatter：
- `name` 缺失 → fallback 为目录名（`os.path.basename`），`logger.warning`
- `triggers` + `synonyms` 均为空 → 跳过该 skill，`logger.warning`
- frontmatter 解析失败 → 跳过，`logger.warning`
- 扫描入口：`SkillIndex.scan(project_root)` — 传项目根目录，内部拼接 `.claude/skills/`

### 匹配算法

```python
MAX_SKILL_PROMPT_CHARS = 8000  # 可配置常量

def match(self, task_text: str) -> List[SkillEntry]:
    task_lower = task_text.lower()

    # 初始化：priority 作为基础分（priority * 10）
    scores = {name: entry.priority * 10
              for name, entry in self._entries.items()}

    # Level 1: 精确匹配 triggers（权重 3）
    for trigger, skill_names in self._trigger_map.items():
        if trigger in task_lower:
            for skill_name in skill_names:
                scores[skill_name] = scores.get(skill_name, 0) + 3

    # Level 1: 精确匹配 synonyms（权重 2）
    for synonym, skill_names in self._synonym_map.items():
        if synonym in task_lower:
            for skill_name in skill_names:
                scores[skill_name] = scores.get(skill_name, 0) + 2

    # Level 2: 模糊匹配 — 子串包含（权重 1，兼容中英文）
    for entry in self._entries.values():
        for trigger in entry.triggers + entry.synonyms:
            if trigger in task_lower:
                scores[entry.name] = scores.get(entry.name, 0) + 1

    # 按分数排序，返回 top-3（过滤 0 分）
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [self._entries[name]
            for name, score in ranked[:3] if score > 0]
```

**设计要点**：
- Level 2 使用纯子串包含（`if trigger in task_lower`），不使用 `\b`，兼容中文
- priority 作为基础分打破同分僵局
- 反向索引（`_trigger_map`/`_synonym_map`）预构建，匹配时 O(1)

### 性能

- 启动扫描：~50ms（70个文件，每个 <10KB）
- 匹配：<1ms（纯内存操作）
- 内容缓存：`_content_cache` 避免重复读文件

## 4. SkillRouter — 路由协调

```python
class SkillRouter:
    def __init__(self, skill_index: SkillIndex):
        self.index = skill_index
        self._content_cache = {}

    def route(self, task_text: str) -> Optional[Dict[str, Any]]:
        entries = self.index.match(task_text)
        if not entries:
            return None

        best = entries[0]
        return {
            "name": best.name,
            "description": best.description,
            "content": self._load_content(best),
            "all_matches": [e.name for e in entries],
        }

    def _load_content(self, entry: SkillEntry) -> str:
        if entry.name not in self._content_cache:
            content = entry.prompt
            if len(content) > MAX_SKILL_PROMPT_CHARS:
                content = content[:MAX_SKILL_PROMPT_CHARS] + "\n[truncated]"
            self._content_cache[entry.name] = content
        return self._content_cache[entry.name]
```

## 5. Dispatcher 集成

在 `dispatch()` 方法中注入：

```python
async def dispatch(self, agent_type, task, ...):
    spec = SubagentRegistry.get_spec(agent_type)

    # Skill 预路由
    skill_info = self.skill_router.route(task) if self.skill_router else None

    # 构造 system_prompt
    system_prompt = self._build_system_prompt(spec, task, context)

    if skill_info:
        skill_block = f"""
## 参考 Skill: {skill_info['name']}
{skill_info['description']}

以下是该 skill 的详细指令，请遵循执行：
---
{skill_info['content']}
---
"""
        system_prompt = system_prompt + "\n\n" + skill_block

    # 后续正常 LLM 工具调用循环...
```

### 关键决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 注入位置 | system_prompt 末尾 | LLM 对末尾内容注意力最强 |
| 注入数量 | 仅 top-1 | 多个 skill 分散注意力 |
| 无匹配时 | 不注入，正常派遣 | 不强制 skill |
| 截断长度 | `MAX_SKILL_PROMPT_CHARS = 8000` | 可配置常量 |

## 6. SKILL.md Frontmatter 标准

```yaml
---
name: autoreview                    # 必填（缺失 fallback 目录名）
description: 自动代码审查             # 必填
triggers: [审查, review, 代码质量]    # 必填（与 synonyms 均空则跳过）
synonyms: [审阅, 检查代码, PR review] # 可选
priority: 1                         # 可选（默认 0，越大越优先）
---
```

## 7. 错误处理

| 场景 | 处理 |
|------|------|
| SKILL.md frontmatter 解析失败 | 跳过，logger.warning |
| `name` 缺失 | fallback 为目录名 |
| triggers + synonyms 均空 | 跳过索引构建 |
| skill 内容读取失败 | route() 返回 None |
| SkillIndex 目录不存在 | 创建空索引 |
| skill 内容超长 | 截断到 `MAX_SKILL_PROMPT_CHARS` |

## 8. 测试策略（13 项）

| 测试 | 覆盖 |
|------|------|
| `test_scan_frontmatter` | 正常解析 triggers/synonyms |
| `test_scan_missing_name` | fallback 目录名 |
| `test_scan_empty_triggers` | triggers+synonyms 均空，跳过 |
| `test_match_exact_trigger` | 精确匹配 triggers |
| `test_match_exact_synonym` | 匹配 synonyms |
| `test_match_fuzzy_chinese` | 纯中文子串匹配 |
| `test_match_priority_breaks_tie` | 同分时 priority 胜出 |
| `test_match_no_match` | 无匹配返回空 |
| `test_match_duplicate_triggers` | 两个 skill 同 trigger，高分胜出 |
| `test_router_returns_top1` | 路由返回 top-1 |
| `test_router_no_match_none` | 无匹配返回 None |
| `test_dispatcher_injects_skill` | system_prompt 包含 skill |
| `test_dispatcher_no_injection` | 无匹配不注入 |

## 9. 文件清单

| 文件 | 操作 | 行数预估 |
|------|------|---------|
| `agent/skill_index.py` | 新建 | ~120 |
| `agent/skill_router.py` | 新建 | ~60 |
| `agent/tools/dispatch/dispatcher.py` | 修改 | +20 |
| `tests/test_skill_router.py` | 新建 | ~200 |

## 10. 不在范围内

- 子代理运行时自主发现 skill（方案 C，未来演进）
- LLM 语义路由（当前关键词匹配已足够）
- skill 执行追踪/审计
- skill 版本管理
