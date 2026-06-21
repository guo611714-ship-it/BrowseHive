---
name: nvidia-api-reference
description: NVIDIA API endpoint and model configuration for Office add-in AI backend
metadata: 
  node_type: memory
  type: reference
  originSessionId: 746c168e-f9fa-4697-a929-fdae2e4c1a89
---

# NVIDIA API 配置

## 端点
- Base URL: `https://integrate.api.nvidia.com/v1/chat/completions`
- 认证: Bearer token
- 格式: OpenAI兼容

## 模型
- 当前使用: `google/gemma-3n-e2b-it`（多模态模型）
- 备选: `stepfun-ai/step-3.5-flash`

## 请求格式
```json
{
  "model": "google/gemma-3n-e2b-it",
  "messages": [{"role": "user", "content": "..."}],
  "max_tokens": 512,
  "temperature": 0.20,
  "top_p": 0.70,
  "stream": false
}
```

## 响应格式
```json
{
  "choices": [{"message": {"content": "AI回复内容"}}]
}
```

## 配置来源
- 从CC Switch (localhost:15721) 的env配置中提取
- CC Switch配置路径: `C:\Users\lenovo\.cc-switch\settings.json`

**Why:** Office Add-in需要可靠的AI后端
**How to apply:** 修改模型或参数时参考此配置
