---
name: agent-team-code-review-2025-05-27
description: Agent Team 项目代码审查与修复记录 - 自启动hook失败问题
metadata:
  type: feedback
---

## 审查背景

- **时间**: 2025-05-27
- **触发**: agent team 项目自启动 hook 失败
- **范围**: agent/ 目录核心文件 (loop.py, model_orchestrator.py, llm_client.py)
- **审查方式**: 最大努力级别（5+4+1 角度，15+ 个发现）

## 发现的 15 个缺陷（按严重性）

### Critical（服务启动失败风险）

1. **agent/loop.py:42** - ModelOrchestrator 初始化缺少异常保护
   - 配置错误直接导致启动崩溃
   - 修复: 添加 try-except 包裹 ModelOrchestrator 创建

2. **agent/model_orchestrator.py:21** - _load_config 未捕获 JSONDecodeError 和 OSError
   - 配置格式错误时程序崩溃
   - 修复: 添加异常处理并返回空字典

### High（运行时崩溃风险）

3. **agent/llm_client.py:73,100,124** - API 响应解析未检查 choices/content 是否存在
   - IndexError/KeyError 导致调用失败
   - 修复: 添加 `.get()` 安全检查，空列表返回错误信息

4. **agent/llm_client.py:70** - HTTP 请求未处理网络异常
   - `resp.json()` 可能失败，httpx 异常未捕获
   - 修复: 添加 try-except 处理 `httpx.HTTPError` 和 `json.JSONDecodeError`

5. **agent/llm_client.py:81** - Anthropic 请求头 `Content-Type` 有前导空格
   - `" Content-Type"` 应为 `"Content-Type"`
   - 修复: 删除空格

### Medium（功能异常/降级）

6. **agent/model_orchestrator.py:28** - _get_or_create_client 未验证 model_name
   - None/空字符串导致后续问题
   - 修复: 增加 `if not model_name or not isinstance(model_name, str)` 检查

7. **agent/model_orchestrator.py:19** - 使用未验证的 _default_model 预加载
   - _default_model 可能为 None
   - 修复: 仅在 `_default_model` 为真值时预加载

8. **agent/model_orchestrator.py:44** - provider 缺失传递 None 给 LLMClient
   - 修复: 新增 `_default_provider` 从配置读取，`provider = model_cfg.get("provider") or self._default_provider`

9. **agent/loop.py:50** - dispatch_tools 注入异常处理过于宽泛
   - `except Exception` 和 `pass` 静默错误
   - 修复: 细化为 `ImportError`/`AttributeError`/`Exception`

10. **agent/loop.py:81** - 工具注册使用 `callable()` 可能误注册类
    - 修复: `isinstance(obj, type)` 排除类定义

11. **agent/model_orchestrator.py:48** - `temperature=0` 被 `or 0.1` 覆盖
    - 修复: 改为 `temperature = model_cfg.get("temperature"); if temperature is None: temperature = 0.1`

### Low（代码质量）

12. **agent/llm_client.py:151** - 配置类型可能不匹配
    - 修复: `load_llm_client_from_config` 对 `maxTokens`/`temperature` 添加 `int()`/`float()` 转换与异常处理

13. **agent/loop.py:88** - 状态方法对 `llm_client=None` 保护不完整
    - 已检查，但形式化记录

14. **agent/model_orchestrator.py:41** - 使用 `print` 而非 `logging`
    - 修复: 导入 `logging`，使用 `logger.warning()/logger.error()`

15. **agent/loop.py:46** - 重复的 llm_client 赋值逻辑混乱
    - 已重构为清晰的一次赋值

## 关键修复总结

### 稳定性改进
- 所有配置文件读取都添加异常处理
- LLM 客户端初始化有完整的降级路径
- 服务启动不会因配置问题直接崩溃

### API 调用健壮性
- HTTP 请求增加网络异常与 JSON 解析错误处理
- 响应数据添加边界检查（空列表、缺失字段）
- Anthropic API 内容提取支持 `text` 和 `tool_use` 类型

### 类型安全
- 配置值的 `int`/`float` 转换与默认值处理
- 避免 `0`/`""` 等 falsy 值被错误覆盖

### 日志与调试
- 从 `print` 切换到 `logging` 模块
- 更清晰的错误信息

## 与自启动 Hook 失败的关联

最可能导致 Windows NSSM 服务启动失败的根本原因：
1. `ModelOrchestrator` 初始化无异常保护 → 配置文件问题 → 进程直接退出
2. 配置格式错误未被处理 → 启动时抛出未捕获异常

修复后，服务应能：
- 优雅降级到模拟模式
- 记录错误日志到 `logs/` 目录
- 继续运行而非直接退出

## 验证建议

```bash
# 1. 测试配置错误处理
echo "{" > model_config.json  # 故意创建无效 JSON
python run_agent.py  # 应看到错误日志，服务继续（降级）

# 2. 测试正常启动
nssm start AgentTeam
# 检查日志:
# - logs/agent_2025-05-27.log
# - logs/agent_error_2025-05-27.log

# 3. 验证 API 调用
# 使用 /status 命令检查 LLM 状态
```

## 后续建议

- 添加配置文件模式验证（如使用 pydantic）
- 在 `TeamStore` 初始化也添加异常保护
- 考虑将 `logging` 配置读取 `model_config.json` 中的日志级别
- 增加启动时的配置健康检查（`/health` 端点）
