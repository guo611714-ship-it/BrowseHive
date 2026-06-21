# FixManifest 集成架构 — 三 Skill 统一接入

## 设计目标

让 `skill-stocktake`、`autoreview`、`gh-issues` 共享同一个 manifest_builder 接口，
各自只需实现自己的「数据源适配器」，无需关心引擎细节。

## 统一接口

```python
# agent/manifest_builder.py

from abc import ABC, abstractmethod
from typing import List
from fix_engine.manifest import FixItem

class ManifestAdapter(ABC):
    """数据源适配器基类"""

    @abstractmethod
    def source_name(self) -> str:
        """返回数据源名称（用于日志和追踪）"""

    @abstractmethod
    def to_fix_items(self, raw_data: any) -> List[FixItem]:
        """将原始数据转换为 FixItem 列表"""

    def filter_actionable(self, items: List[FixItem]) -> List[FixItem]:
        """过滤出可执行的任务（默认：全部保留）"""
        return items
```

## 三个适配器

### 1. StocktakeAdapter

```python
class StocktakeAdapter(ManifestAdapter):
    def source_name(self) -> str:
        return "skill-stocktake"

    def to_fix_items(self, results: dict) -> List[FixItem]:
        """results.json 中的 verdicts → FixItem[]"""
        items = []
        for skill_name, info in results.get("skills", {}).items():
            verdict = info.get("verdict", "Keep")
            reason = info.get("reason", "")
            path = info.get("path", "")

            if verdict == "Retire":
                items.append(FixItem(
                    id=f"stocktake-retire-{skill_name}",
                    file=path,
                    description=f"Retire skill '{skill_name}': {reason}",
                    agent_type="neiguan_yingzao",
                    priority=1,
                    metadata={"verdict": verdict, "skill": skill_name},
                ))
            elif verdict == "Improve":
                items.append(FixItem(
                    id=f"stocktake-improve-{skill_name}",
                    file=path,
                    description=f"Improve skill '{skill_name}': {reason}",
                    agent_type="neiguan_yingzao",
                    context=reason,
                    metadata={"verdict": verdict, "skill": skill_name},
                ))
            elif verdict.startswith("Merge into"):
                target = verdict.replace("Merge into ", "")
                items.append(FixItem(
                    id=f"stocktake-merge-{skill_name}",
                    file=path,
                    description=f"Merge '{skill_name}' into '{target}': {reason}",
                    agent_type="neiguan_yingzao",
                    context=reason,
                    metadata={"verdict": verdict, "skill": skill_name, "target": target},
                ))
        return items
```

### 2. AutoreviewAdapter

```python
class AutoreviewAdapter(ManifestAdapter):
    def source_name(self) -> str:
        return "autoreview"

    def to_fix_items(self, findings: List[dict]) -> List[FixItem]:
        """review findings → FixItem[]"""
        items = []
        for f in findings:
            if f.get("status") != "accepted":
                continue  # 只处理 accepted 的 findings

            severity_map = {"critical": 2, "important": 1, "minor": 0}
            items.append(FixItem(
                id=f"review-{f['id']}",
                file=f["file_path"],
                description=f"[{f['severity']}] {f['message']}",
                agent_type="neiguan_yingzao",
                line_start=f.get("line_start"),
                line_end=f.get("line_end"),
                context=f.get("suggestion", ""),
                priority=severity_map.get(f.get("severity", "minor"), 0),
                metadata={"finding_id": f["id"], "severity": f["severity"]},
            ))
        return items

    def filter_actionable(self, items: List[FixItem]) -> List[FixItem]:
        """排除 minor 级别（可选）"""
        return [i for i in items if i.priority >= 1]
```

### 3. GhIssuesAdapter

```python
class GhIssuesAdapter(ManifestAdapter):
    def source_name(self) -> str:
        return "gh-issues"

    def to_fix_items(self, issues: List[dict]) -> List[FixItem]:
        """GitHub issues → FixItem[]"""
        items = []
        for issue in issues:
            # 从 issue body 推断受影响文件
            files = self._infer_files(issue)

            items.append(FixItem(
                id=f"issue-{issue['number']}",
                file=files[0] if files else "unknown",
                description=f"Fix #{issue['number']}: {issue['title']}\n\n{issue.get('body', '')[:500]}",
                agent_type="neiguan_yingzao",
                context=issue.get("url", ""),
                priority=2 if "critical" in issue.get("labels", []) else 1,
                metadata={
                    "issue_number": issue["number"],
                    "repo": issue.get("repo"),
                    "all_files": files,
                },
            ))
        return items

    def _infer_files(self, issue: dict) -> List[str]:
        """从 issue body 推断受影响文件"""
        # 简单实现：查找 code blocks 中的文件路径
        import re
        body = issue.get("body", "")
        # 匹配 ```python\npath/to/file.py 或 file.py:line 格式
        patterns = [
            r'`([a-zA-Z0-9_/.-]+\.(py|js|ts|tsx|jsx|java|go|rs))`',
            r'([a-zA-Z0-9_/.-]+\.(py|js|ts|tsx|jsx|java|go|rs)):\d+',
        ]
        files = set()
        for pattern in patterns:
            files.update(re.findall(pattern, body))
        return list(files) if files else []
```

## 统一入口

```python
# agent/tools/fix_tools.py 新增

@tool(
    name="submit_fix_manifest",
    description="提交修复任务清单。支持从不同数据源（stocktake/autoreview/issues）自动转换。",
)
async def submit_fix_manifest(
    source: str,           # "stocktake" | "autoreview" | "issues"
    data: dict | list,     # 原始数据
    strategy: str = "auto",
    filter_actionable: bool = True,
) -> dict:
    adapter = get_adapter(source)  # 工厂函数
    items = adapter.to_fix_items(data)
    if filter_actionable:
        items = adapter.filter_actionable(items)

    if not items:
        return {"success": True, "summary": "No actionable items", "tasks": []}

    manifest = FixManifest(tasks=items, strategy=strategy)
    engine = engine_ctx.get()
    result = await engine.submit_fix_manifest(manifest)

    return {
        "success": result.success,
        "summary": result.summary,
        "source": source,
        "task_count": len(items),
        "patch": result.patch,
        "conflicts": result.conflicts,
        "details": result.details,
    }
```

## 数据流图

```
┌─────────────────────────────────────────────────────────────┐
│                    Skill 层（数据源）                         │
├─────────────────┬─────────────────┬─────────────────────────┤
│ skill-stocktake │   autoreview    │       gh-issues         │
│ (results.json)  │ (findings list) │ (issues from gh api)    │
└────────┬────────┴────────┬────────┴───────────┬─────────────┘
         │                 │                    │
         ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│              ManifestAdapter（统一接口）                      │
│  StocktakeAdapter │ AutoreviewAdapter │ GhIssuesAdapter      │
└────────┬─────────┴────────┬──────────┴──────────┬──────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│              submit_fix_manifest（统一入口）                  │
│         filter_actionable → FixManifest → engine             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              ParallelFixEngine（并行执行）                    │
│    冲突预测 → 智能分片 → 并行调度 → 结果合并                   │
└─────────────────────────────────────────────────────────────┘
```

## 实现顺序

### ✅ Phase 1：基础层（已完成）
- `agent/manifest_builder.py` — ManifestAdapter 基类 + 工厂函数
- `agent/tools/fix_tools.py` — 新增 `submit_fix_manifest` 工具
- `tests/test_manifest_builder.py` — 21 个单元测试全绿

### ✅ Phase 2：三个适配器（已完成）
- `StocktakeAdapter` — verdicts → FixItems
- `AutoreviewAdapter` — findings → FixItems
- `GhIssuesAdapter` — issues → FixItems + 文件推断

### ✅ Phase 3：Skill 集成（已完成）
- `skill-stocktake` — Phase 4 改为调用 `submit_fix_manifest`
- `autoreview` — 新增 Parallel Fix 阶段
- `gh-issues` — Phase 5 新增并行预修复选项

### ✅ Phase 4：测试（已完成）
- 单元测试：21 passed
- 集成测试：6 passed
- 回归测试：26 passed（现有 engine 测试）

---

## 完成总结

| 组件 | 文件 | 状态 |
|------|------|------|
| ManifestAdapter 基类 | `agent/manifest_builder.py` | ✅ |
| StocktakeAdapter | `agent/manifest_builder.py` | ✅ |
| AutoreviewAdapter | `agent/manifest_builder.py` | ✅ |
| GhIssuesAdapter | `agent/manifest_builder.py` | ✅ |
| submit_fix_manifest 工具 | `agent/tools/fix_tools.py` | ✅ |
| skill-stocktake 集成 | `.claude/skills/skill-stocktake/SKILL.md` | ✅ |
| autoreview 集成 | `.claude/skills/autoreview/SKILL.md` | ✅ |
| gh-issues 集成 | `.claude/skills/gh-issues/SKILL.md` | ✅ |
| 单元测试 | `tests/test_manifest_builder.py` | 21 ✅ |
| 集成测试 | `tests/test_integration_fix_manifest.py` | 6 ✅ |
