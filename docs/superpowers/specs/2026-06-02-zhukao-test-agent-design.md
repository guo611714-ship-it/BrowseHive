# 主考（TestAgent）设计规格

**日期**: 2026-06-02
**状态**: 待审阅
**关联**: 翰林代码代理设计规格 (2026-06-01)

---

## 1. 目标

新增**主考（zhukao）**测试代理，补齐"测试生成"能力，与翰林（写代码）、典簿（跑测试）形成三位一体的质量飞轮。

**核心价值**：
- 翰林写代码，主考出题，典簿阅卷——职责清晰，无越权
- 三层测试映射翰林双模：快稿配单测（毫秒级）、深度配契约（秒级）、关键交付配全栈（异步）
- FixItem 同组绑定，业务代码与测试代码同进同退

---

## 2. 代理身份

| 属性 | 值 |
|------|-----|
| 注册名 | `zhukao` |
| 中文名 | 主考 |
| 定位 | 提学御史，甩卷出题 |
| 模型 | 跟随翰林（编排层同频调度） |
| 上级 | lead（主控调度） |
| 协作 | 翰林（写代码）、典簿（跑测试）、ParallelFixEngine（并行写入） |

**与翰林的对仗**：
- 翰林：执笔修撰，下场答题（写代码）
- 主考：提学御史，甩卷出题（出测试）
- 典簿：掌管案卷，红笔阅卷（跑测试验收）

---

## 3. 权限矩阵

| 工具 | 权限 | 说明 |
|------|------|------|
| `read_file` | ✅ | 读取代码文件 |
| `read_codebase` | ✅ | 读取代码库上下文 |
| `glob` | ✅ | 文件查找 |
| `grep` | ✅ | 内容搜索 |
| `ast_parse` | ✅ | 提取函数签名和类结构 |
| `write_file` | ❌ | 由翰林/内官监执行写入 |
| `exec_python` | ❌ | 由典簿执行测试 |
| `fix_manifest` | ❌ | 由编排层包装 |

**输出格式**（结构化 JSON，不直接写文件）：
```json
{
  "test_file": "tests/test_new_feature.py",
  "content": "import pytest\n...",
  "target_file": "src/module.py",
  "coverage_strategy": "unit",
  "test_names": ["test_func_success", "test_func_boundary", "test_func_error"]
}
```

---

## 4. 三层测试策略

### 4.1 层级映射

| 层级 | 名称 | 触发条件 | 测试范围 | 输出标记 |
|------|------|---------|---------|---------|
| L1 | 同步单测 | 翰林快稿 (Level 1-2) | 函数入参/出参、边界值、异常路径 | `"coverage_strategy": "unit"` |
| L2 | 契约集成 | 翰林深度 (Level 3-5)，fix_manifest 涉及 ≥2 文件 | 跨模块调用链、接口签名一致性 | `"coverage_strategy": "contract"` |
| L3 | 异步全栈 | 特定 Skill 触发（pr-review / critical 标签） | API 端到端、DB 真实交互、性能压测 | `"coverage_strategy": "e2e"` |

### 4.2 快稿模式提示词（L1 单测）

```
你是主考，提学御史，专司出题考核。
任务：为以下代码生成单元测试。
规则：
1. 只读代码，不修改；输出严格 JSON 格式
2. 优先检查并复用项目中已有的 conftest.py 和公共 fixtures
3. 测试覆盖：正常路径 + 边界值 + 异常路径
4. 使用 pytest + unittest.mock，对数据库/网络/外部服务必须 Mock
5. 针对目标函数的复杂度合理分配用例数（核心逻辑不少于 3 个，简单 getter/setter 可仅 1 个）
6. 不运行测试，只生成
输出 JSON 格式：
{
  "test_file": "tests/test_<module>.py",
  "content": "<完整的 pytest 测试代码>",
  "coverage_strategy": "unit"
}
目标代码：
{code}
AST 解析签名：
{signatures_from_ast_parse}
相关 Conftest / 现有 Fixtures：
{conftest_context}
```

### 4.3 深度模式提示词（L2 契约集成）

```
你是主考，提学御史，专司出题考核。
任务：为以下跨模块重构生成集成测试。
规则：
1. 重点验证模块间接口契约（修改前后的签名一致性）
2. Mock 数据库/网络/外部服务，但必须验证跨模块调用链的参数传递正确性
3. 优先复用项目现有的 fixtures 和 mock 工具
4. 输出严格 JSON 格式
5. 标记 coverage_strategy 为 "contract"
输出 JSON 格式：
{
  "test_file": "tests/test_integration_<feature>.py",
  "content": "<完整的 pytest 集成测试代码>",
  "coverage_strategy": "contract"
}
重构蓝图（FixManifest）：
{blueprint}
涉及修改的文件列表：
{file_list}
相关模块的接口签名：
{signatures_from_ast_parse}
相关 Conftest / 现有 Fixtures：
{conftest_context}
```

### 4.4 L3 全栈模式（异步触发）

L3 不在主考的常规流程中，由内官监在后台发起：
- 触发条件：`gitnexus-pr-review` 合入前 / `performance` 标签 issue
- 执行者：内官监（有 exec_python 权限）
- 主考仅负责生成 L3 测试的 JSON 骨架

---

## 5. 飞轮调度流

### 5.1 快稿模式闭环（Level 1-2）

```
Lead 派遣任务
    ↓
翰林接收 → CodeComplexityAnalyzer → Level 1-2
    ↓
翰林(写代码) → ast_parse 自检通过
    ↓
翰林调用主考(出题)
    ↓
主考: read_file → 读 conftest → ast_parse 提取签名 → 生成测试 JSON
    ↓
翰林接收 JSON → write_file(test_file, content)
    ↓
典簿执行: pytest -k test_specific_func
    ↓
通过 → 交付 | 失败 → 打回翰林重写
```

### 5.2 深度模式闭环（Level 3-5）

```
Lead 派遣任务
    ↓
翰林接收 → CodeComplexityAnalyzer → Level 3-5
    ↓
翰林(读代码+git diff) → 生成重构蓝图
    ↓
翰林调用主考(出题)
    ↓
主考: read_file × N → 读 conftest → ast_parse → 生成契约测试 JSON
    ↓
编排层将 JSON 包装为 FixItem:
  FixItem(
    id="test-feature",
    file="tests/test_feature.py",
    description="Create contract tests",
    content=JSON.content,
    agent_type="neiguan_yingzao",
    group_id="feature-{task_id}",  // 关键：同组绑定
    metadata={"depends_on": [business_item_ids]}
  )
    ↓
submit_fix_manifest → ParallelFixEngine 并行写入:
  业务代码 FixItem + 测试代码 FixItem (同 group_id)
    ↓
典簿执行: pytest -k test_1,test_2,test_3
    ↓
通过 → 交付 | 失败 → 提取 error_evidence → 翰林定向修复
```

### 5.3 典簿升级：校验执行权限

典簿从"只读"升级为"校验执行"，新增工具：

| 新增工具 | 说明 |
|---------|------|
| `exec_python` | 执行 `pytest -k <test_names>` |
| `coverage` | 生成覆盖率报告（可选） |

典簿验证逻辑：
```python
async def verify(self, test_file: str, test_names: list) -> dict:
    """运行指定测试，返回结构化结果"""
    cmd = f"pytest {test_file} -k '{' or '.join(test_names)}' -v --tb=short -q"
    result = await exec_python(cmd)
    
    if result.returncode == 0:
        return {"pass": True, "output": "All tests passed"}
    else:
        # 提取精准报错证据
        import re
        failures = re.findall(r'(FAILED .*?AssertionError.*?)\n={5,}', result.stdout, re.DOTALL)
        clean_error = "\n".join(failures) if failures else result.stdout[-1000:]
        
        return {
            "pass": False,
            "failed_tests": [name for name in test_names if f"FAILED {test_file}::{name}" in result.stdout],
            "error_evidence": clean_error
        }
```

---

## 6. 异常处理与熔断

| 异常场景 | 处理方式 |
|---------|---------|
| 主考生成的测试 AST 校验失败 | 主考内部重试 1 次，仍失败则返回错误 JSON |
| 典簿执行测试失败 | 输出 error_evidence，交给翰林定向修复 |
| 翰林修复后依然失败（死循环熔断） | Lead 介入，降级为"带警告交付"，标记 `tests_passed: false` |
| 主考超时（>30s） | 降级为无测试交付，标记 `tests_generated: false` |
| conftest.py 不存在 | 主考跳过 fixture 复用，按标准 pytest 生成 |

---

## 7. 典簿升级：权限变更

典簿从"只读核验"升级为"校验执行"：

| 属性 | 变更前 | 变更后 |
|------|--------|--------|
| name | shangbao_dianbu | shangbao_dianbu |
| display_name | 尚宝监典簿 | 尚宝监典簿 |
| description | 只读核验 | 校验执行：跑测试+覆盖率分析 |
| allowed_tools | read_file, glob, grep | + exec_python, coverage |
| read_only | True | False |

---

## 8. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `agent/subagents/zhukao.py` | 新增 | 主考代理核心实现 |
| `agent/subagents/registry.py` | 修改 | 注册主考 + 升级典簿权限 |
| `tests/test_zhukao.py` | 新增 | 主考单元+集成测试 |

---

## 9. 测试策略

| 测试类型 | 覆盖范围 | 数量估算 |
|---------|---------|---------|
| 单元测试 | 主考提示词生成逻辑 | 8-10 |
| 单元测试 | JSON 输出格式校验 | 5-8 |
| 单元测试 | AST 自检 + test_names 提取 | 3-5 |
| 集成测试 | 主考 → 典簿执行闭环 | 3-5 |
| 边界测试 | 超时/AST失败/conftest缺失 | 3-5 |

**总计**: 约 22-33 个新测试

---

## 10. 风险控制

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 主考生成无意义测试 | 中 | 测试噪音 | AST 自检 + 用例数量按复杂度分配 |
| 深度模式 FixItem 冲突 | 低 | 测试丢失 | group_id 同组绑定，同进同退 |
| 死循环（修复→失败→修复） | 中 | 飞轮卡死 | 重试熔断：1次修复失败后降级交付 |
| conftest 变更导致测试失效 | 低 | 测试报错 | 主考每次重新读取 conftest_context |

---

## 11. 长期演进

- **Phase 1（本次）**: 实现 L1 单测生成 + 典簿升级
- **Phase 2（未来）**: 接入 FixManifest 深度模式
- **Phase 3（远期）**: L3 全栈测试（内官监异步触发）
