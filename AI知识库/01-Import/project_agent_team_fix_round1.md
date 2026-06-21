---
name: agent-team-fix-round1
description: Agent Team 4项核心问题修复完成 - 浏览器AI/LLM超时/挂起/稳定性
metadata: 
  node_type: memory
  type: project
  originSessionId: 17d73358-96b7-437e-818d-89a007140d6b
---

## 修复完成 (2026-05-31)

### 修复的4项核心问题

| 问题 | 根因 | 修复方案 | 文件 |
|------|------|----------|------|
| 浏览器AI响应提取100%失败 | CSS选择器不匹配doubao新DOM + _pendingRequests未初始化 | 三级fallback提取策略 | browser_agent.py |
| LLM复杂任务超时 | 固定60秒超时对慢速模型不够 | 动态超时（10模型速度等级） | llm_client.py + model_orchestrator.py |
| chat_engine挂起 | send/get_response串行无熔断 | 熔断器 + 解耦 + 心跳检测 | chat_engine.py |
| 简单任务不稳定~70% | 无自动降级+无结果校验 | 健康度评分 + 简单任务校验 | dispatch_tools.py + model_orchestrator.py |

### Code Review修复 (7项)

| 严重性 | 问题 | 修复 |
|--------|------|------|
| Critical | 心跳失败返回字符串绕过熔断器 | 改为raise HeartbeatError |
| High | chunk_timeout使用stale时间戳 | 心跳检查后刷新now |
| High | 心跳计数器被单次成功重置 | 改为滑动窗口(5次) |
| Medium | 注释与代码阈值不一致 | 统一为<50字 |
| Medium | 未测试模型排在100%成功率模型前 | 调整排序键 |
| Low | _circuit_is_open无锁文档 | 添加docstring |
| Low | record_model_result无并发保护 | 添加docstring |

### 关键设计决策

1. **熔断器**: 连续3次失败→跳过平台，60秒冷却，纯内存不持久化
2. **心跳检测**: 滑动窗口5次连续失败判定浏览器卡死
3. **健康度评分**: 连续2次失败标记不健康，连续3次成功恢复
4. **简单任务校验**: <50字任务自动校验结果有效性

### 后续优化项

- [ ] 浏览器AI实际测试验证（需手动触发doubao对话）
- [ ] 单元测试覆盖新增的熔断器/心跳/健康度逻辑
- [ ] 知识库同步更新修复经验

**Why:** Agent Team是核心调度系统，稳定性直接影响所有任务执行
**How to apply:** 后续修改这些文件时需理解新增的熔断器/心跳/健康度机制
