# 翰林（Hanlin）代码代理设计规格

**日期**: 2026-06-01
**状态**: 待审阅
**路径**: 路径A — 单一代码代理

---

## 1. 目标

在 Agent Team 现有7子代理架构上新增**翰林（hanlin）**代码代理，补齐"专业代码生成+自检"能力，与 ParallelFixEngine 形成飞轮闭环。

**核心价值**：
- 释放 ParallelFixEngine 的真正潜力（翰林出蓝图，引擎并行执行）
- 职责解耦（内官监退回纯工程执行，翰林专注逻辑内核）
- Shift-Left 质量保障（生成阶段消灭低级错误，而非 downstream 返工）

---

## 2. 代理身份

| 属性 | 值 |
|------|-----|
| 注册名 | `hanlin` |
| 中文名 | 翰林 |
| 定位 | 专司核心逻辑修撰、架构重构与代码拟稿 |
| 模型 | 动态切换（Level 1-5，复用 ModelOrchestrator） |
| 上级 | lead（主控调度） |
| 协作 | 内官监（工程执行）、典簿（质量验收）、ParallelFixEngine（并行修改） |

**与内官监的边界**：
- 内官监：环境构建者与脚本执行者（pip install、docker、shell）
- 翰林：代码创造者与重构者（函数实现、架构重构、蓝图生成）

---

## 3. 双模运行架构

### 3.1 复杂度评估器（CodeComplexityAnalyzer）

```python
class CodeComplexityAnalyzer:
    """基于任务特征的代码复杂度极简评估"""

    def assess(self, task_description: str, context_lines: int = 0) -> int:
        # Level 1: 极轻量 (Lint修复, 补全单行, 加import, 重命名)
        if any(kw in task_description for kw in ["lint", "import", "格式化", "重命名", "补全"]):
            return 1
        # Level 2: 轻量 (纯函数实现, 单文件内修改, getter/setter)
        if context_lines < 50 and "重构" not in task_description:
            return 2
        # Level 3: 中等 (类方法实现, 跨2-3个函数的联动修改, 适配)
        if context_lines < 200 or "适配" in task_description:
            return 3
        # Level 4-5: 重量 (架构重构, 设计模式应用, 核心算法实现, 跨文件重构)
        return 4
```

### 3.2 双模系统提示词

| 模式 | 触发条件 | 提示词策略 | 模型级别 |
|------|---------|-----------|---------|
| 快稿模式 🟢 | Level 1-2 | 不废话，直接写，写完 ast 过一下就交 | step-3.7-flash / minimax-m2.7 |
| 深度模式 🔴 | Level 3-5 | 先分析 git 上下文，出蓝图，调 fix_manifest | DeepSeek-Coder-33B / GLM-5.1 |

**快稿模式提示词要点**：
- 直接输出代码，不解释
- 写完后必须 `ast.parse()` 校验
- 如有 lint 问题，`ruff check --fix` 自动修复
- 输出格式：代码块 + 自检结果

**深度模式提示词要点**：
- 先读取 `git diff` 理解变更上下文
- 输出重构蓝图（要修改的文件列表 + 每个文件的具体改动）
- 禁止循环调用 `write_file`，必须调用 `fix_manifest`
- 输出格式：蓝图 + FixManifest JSON

---

## 4. 工具权限

| 工具 | 快稿模式 | 深度模式 | 说明 |
|------|---------|---------|------|
| `read_file` | ✅ | ✅ | 读取代码文件 |
| `write_file` | ✅ | ⚠️ | 快稿可自由写单文件；深度模式**仅允许单文件修改**，多文件必须走 fix_manifest |
| `exec_python` | ✅ | ✅ | 执行 Python 代码验证 |
| `ast_parse` | ✅ | ✅ | AST 语法校验（自检核心） |
| `ruff_check` | ✅ | ✅ | Lint 检查 + 自动修复 |
| `git_diff` | ❌ | ✅ | 深度模式查看变更历史 |
| `git_stash` | ❌ | ✅ | 深度模式暂存变更 |
| `fix_manifest` | ❌ | ✅ | 深度模式调用 ParallelFixEngine |

---

## 5. Lead 路由规则

```python
HANLIN_ROUTE_RULES = {
    # 翰林专属任务
    "hanlin": [
        "写代码", "实现函数", "代码生成", "重构代码", "修复逻辑",
        "代码优化", "提取基类", "设计模式", "算法实现",
        "生成函数", "编写模块", "代码拟稿",
    ],
    # 内官监专属任务（防止误派给翰林）
    "neiguan_yingzao": [
        "安装依赖", "运行脚本", "执行命令", "环境搭建",
        "启动服务", "Docker", "部署",
    ],
    # 模糊任务（需要 lead 判断）
    "ambiguous": [
        "修复bug",  # 可能是翰林（逻辑修复）也可能是内官监（环境问题）
        "优化性能",  # 可能是翰林（代码优化）也可能是内官监（配置优化）
    ],
}
```

**Lead 判断逻辑**：
1. 任务包含"代码/函数/重构/逻辑"关键词 → 派给翰林
2. 任务包含"安装/脚本/环境/部署"关键词 → 派给内官监
3. 任务模糊 → lead 先读取上下文判断，或拆解为多个子任务分别派遣

---

## 6. 标准作业流（SOP）

### 6.1 快稿模式 SOP（Level 1-2）

```
Lead 派遣 → 翰林接收
    ↓
CodeComplexityAnalyzer.assess(task) → Level 1-2
    ↓
选择快稿模式提示词 + 轻量模型
    ↓
生成代码（单文件/单函数）
    ↓
ast.parse() 校验 → 失败则重试（最多1次）
    ↓
ruff check --fix 自动修复 lint 问题
    ↓
输出代码 + 自检结果
    ↓
交付 Lead / 典簿验收
```

### 6.2 深度模式 SOP（Level 3-5）

```
Lead 派遣 → 翰林接收
    ↓
CodeComplexityAnalyzer.assess(task) → Level 3-5
    ↓
选择深度模式提示词 + 重量模型
    ↓
read_file + git_diff 理解当前代码
    ↓
生成重构蓝图（文件列表 + 改动描述）
    ↓
输出 FixManifest JSON → 调用 fix_manifest 工具
    ↓
ParallelFixEngine 并行执行修改
    ↓
每个子任务写完后 ruff check --fix
    ↓
所有 manifest 任务完成
    ↓
翰林退场，交由典簿验收
```

---

## 7. 集成点

### 7.1 注册表（agent/subagents/registry.py）

```python
# 新增翰林规格
SubagentSpec(
    name="hanlin",
    display_name="翰林",
    model="nvidia-step-3.7-flash",  # 默认模型，实际动态切换
    system_prompt="你是翰林，专司核心逻辑修撰、架构重构与代码拟稿...",
    allowed_tools=[
        "read_file", "write_file", "exec_python",
        "ast_parse", "ruff_check", "git_diff", "git_stash",
        "fix_manifest", "smart_ask",
    ],
    description="代码生成、重构、修复，配备AST+Lint自检，可调用ParallelFixEngine并行执行"
)
```

### 7.2 模型编排器（agent/model_orchestrator.py）

无需修改——翰林内部自行调用 `orchestrator.get_model_for_complexity(level)`。

### 7.3 平台路由器（agent/tools/browser/platform_router.py）

无需修改——翰林不涉及浏览器AI平台路由。

### 7.4 工具注册（agent/tools/tool_registry.py）

需新增工具：
- `ast_parse`: 调用 `ast.parse()` 校验代码语法
- `ruff_check`: 调用 `ruff check --fix` 自动修复 lint 问题

---

## 8. 测试策略

| 测试类型 | 覆盖范围 | 数量估算 |
|---------|---------|---------|
| 单元测试 | CodeComplexityAnalyzer 评估逻辑 | 8-10 |
| 单元测试 | 快稿模式完整流程 | 5-8 |
| 单元测试 | 深度模式完整流程 | 5-8 |
| 集成测试 | 翰林 + ParallelFixEngine 飞轮 | 3-5 |
| 集成测试 | Lead 路由规则准确性 | 5-8 |
| 边界测试 | AST 校验失败重试、lint 修复 | 3-5 |

**总计**: 约 30-44 个新测试

---

## 9. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `agent/subagents/hanlin.py` | 新增 | 翰林代理核心实现 |
| `agent/subagents/registry.py` | 修改 | 注册翰林规格 |
| `agent/tools/code_tools.py` | 新增 | ast_parse + ruff_check 工具 |
| `agent/tools/tool_registry.py` | 修改 | 注册新工具 |
| `tests/test_hanlin.py` | 新增 | 翰林单元+集成测试 |
| `tests/test_code_tools.py` | 新增 | 代码工具测试 |

---

## 10. 风险控制

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 翰林与内官监职责混淆 | 中 | 调度混乱 | 严格的路由规则 + Lead 判断逻辑 |
| 深度模式上下文溢出 | 低 | 重构失败 | FixManifest 强制拆分，不让翰林一次处理过多文件 |
| AST/Lint 自检耗时过长 | 低 | 延迟增加 | 自检超时5秒自动跳过，标记为"需人工复核" |
| 动态模型切换失败 | 低 | 回退到默认模型 | ModelOrchestrator 已有降级机制 |

---

## 11. 长期演进

- **Phase 1（本次）**: 实现翰林基础能力（双模 + 自检 + FixManifest）
- **Phase 2（未来）**: 如果代码任务分化严重，基于 CodeComplexityAnalyzer 拆分为 code_writer + code_refactor
- **Phase 3（远期）**: 翰林 + 典簿 形成"生成-验收"自动闭环，减少 Lead 干预
