---
title: vLLM环境下Mistral Large 3 675B Instruct 2512模型API配置与说明
created: 2026-05-31
source: file:///D:/Users/lenovo/Desktop/claude workspace/AI知识库/01-Import/e8157d48-Modify OpenAIs API key and API base to use vLLMs A.md
hash: e8157d48
tags: ["大语言模型", "模型参考", "API配置", "vLLM", "NVIDIA API", "多模态模型", "MoE模型", "企业级应用"]
entities: ["Mistral Large 3 675B Instruct 2512", "vLLM框架", "NVIDIA API", "Mistral Common Library", "Eagle Draft Model", "Hugging Face", "Apache License 2.0", "NVIDIA Community Model License"]
category: 参考
summary: 本文档包含适配vLLM/NVIDIA API的Mistral Large 3 675B Instruct 2512模型调用payload示例，以及该模型的架构参数、能力边界、部署要求等核心说明，适用于
---

# vLLM环境下Mistral Large 3 675B Instruct 2512模型API配置与说明

## 摘要

本文档包含适配vLLM/NVIDIA API的Mistral Large 3 675B Instruct 2512模型调用payload示例，以及该模型的架构参数、能力边界、部署要求等核心说明，适用于企业级AI应用、Agent开发等场景。

## 核心要点

- Mistral Large 3 675B Instruct 2512为总参数675B、激活参数41B的多模态MoE模型，支持图文输入、函数调用及262144 token长上下文
- 官方推荐通过vLLM最新nightly版本部署，支持FP8/NVFP4量化与Eagle推测解码以提升推理效率
- 适用于企业级AI助手、Agent系统、长文档处理、代码辅助等生产场景，需遵守NVIDIA服务条款与模型开源协议

## 关键概念

- [[混合专家模型（MoE）]]
- [[FP8量化]]
- [[vLLM推理框架]]
- [[多模态输入]]
- [[函数调用]]
- [[长上下文处理]]
- [[推测解码]]
- [[NVIDIA API服务]]

## 结构化拆解

### 核心观点
本文档提供了Mistral Large 3 675B Instruct 2512模型的API调用配置示例及核心能力说明，指导用户基于vLLM/NVIDIA API完成该模型的合规部署与调用。

### 详细解释
该模型是Mistral推出的多模态MoE大模型，总参数675B，激活参数仅41B，支持最长262144 token的输入上下文，具备多模态理解、原生函数调用、长文本处理能力，官方推荐通过vLLM框架部署，支持FP8量化以提升推理效率，适用于企业级生产环境下的AI助手、Agent系统、知识工作等场景，使用时需遵守NVIDIA API试用条款及Apache 2.0开源协议。

### 代码示例
```
payload = {
    "model": "mistralai/mistral-large-3-675b-instruct-2512",
    "messages": [{"role":"user","content": ""}],
    "max_tokens": 2048,
    "temperature": 0.15,
    "top_p": 1.00,
    "frequency_penalty": 0.00,
    "presence_penalty": 0.00,
    "stream": stream
}
```

### 适用场景
- 企业级AI助手开发
- Agent工具调用与自动化任务
- 长文档理解与RAG知识检索
- 科学计算与复杂企业工作流
- 多模态图文分析任务

### 常见误区
- 未使用vLLM最新nightly版本导致模型兼容性问题
- 输入图像未保持近1:1宽高比影响多模态识别效果
- 生产环境温度设置过高导致输出稳定性下降
- 忽略模型服务条款与开源协议引发合规风险

## 原始内容

payload = {
  "model": "mistralai/mistral-large-3-675b-instruct-2512",
  "messages": [{"role":"user","content":""}],
  "max_tokens": 2048,
  "temperature": 0.15,
  "top_p": 1.00,
  "frequency_penalty": 0.00,
  "presence_penalty": 0.00,
  "stream": stream
}
Mistral Large 3 675B Instruct 2512
Description
Mistral Large 3 675B Instruct 2512 is a state-of-the-art general-purpose multimodal granular Mixture-of-Experts model with 41B active parameters and 675B total parameters, trained from the ground up with 3000 H200s. This instruct post-trained version in FP8 precision is fine-tuned for instruction tasks, making it ideal for chat, agentic, and instruction-based use cases. Designed for reliability and long-context comprehension, it is engineered for production-grade assistants, retrieval-augmented systems, scientific workloads, and complex enterprise workflows.

This model is ready for commercial/non-commercial use.

Third-Party Community Consideration:
This model is not owned or developed by NVIDIA. This model has been developed and built to a third-party's requirements for this application and use case; see link to Non-NVIDIA Mistral Large 3 675B Instruct 2512 Model Card

License and Terms of Use:
GOVERNING TERMS: This trial service is governed by the NVIDIA API Trial Terms of Service. Use of this model is governed by the NVIDIA Community Model License. Additional Information: Apache License Version 2.0.

Deployment Geography:
Global

Use Case:
Use Case: Designed for enterprise-grade applications including long document understanding, powerful daily-driver AI assistants, state-of-the-art agentic and tool-use capabilities, enterprise knowledge work, and general coding assistance. Engineered for production-grade assistants, retrieval-augmented systems, scientific workloads, and complex enterprise workflows with powerful long-context performance and stable cross-domain behavior.

Release Date:
Build.NVIDIA.com: 12/2025 via link
Huggingface: 12/2025 via link

Reference(s):
References:

vLLM Framework
Mistral Common Library
System Prompt Configuration
FP8 Quantized Version
NVFP4 Quantized Version
Eagle Draft Model for Speculative Decoding
Model Architecture:
Architecture Type: Transformer
Network Architecture: Granular Mixture-of-Experts (MoE) with Vision Encoder (673B Language Model + 2.5B Vision Encoder)
Total Parameters: 675B
Active Parameters: 41B (39B language model active parameters + 2.5B vision encoder)
Base Model: mistralai/Mistral-Large-3-675B-Base-2512

Input:
Input Types: Image, Text
Input Formats: Red, Green, Blue (RGB), String
Input Parameters: Two Dimensional (2D), One Dimensional (1D)
Other Input Properties: Supports multimodal input with vision capabilities for image analysis. Images should maintain aspect ratio close to 1:1 (width-to-height) for optimal performance. Text inputs support multilingual content (English, French, Spanish, German, Italian, Portuguese, Dutch, Chinese, Japanese, Korean, Arabic). Recommended system prompt configuration available in repository. Supports tools/function calling with recommendation to keep tool set well-defined and limited.
Input Context Length (ISL): 262,144 (256k)

Output:
Output Types: Text
Output Format: String
Output Parameters: One Dimensional (1D)
Other Output Properties: Supports native function calling and JSON output formatting. Best results achieved with temperature below 0.1 for daily-driver and production environments. Strong system prompt adherence. Best-in-class agentic capabilities with tool use.
Output Context Length (OSL): Undisclosed

Our AI models are designed and/or optimized to run on NVIDIA GPU-accelerated systems. By leveraging NVIDIA's hardware (e.g. GPU cores) and software frameworks (e.g., CUDA libraries), the model achieves faster training and inference times compared to CPU-only solutions.

Software Integration:
Runtime Engines:

vLLM: Latest version (recommended, install from nightly wheels)
Transformers: Not yet available (community contribution welcome)
Supported Hardware:

NVIDIA Ampere: A100 (single node, NVFP4)
NVIDIA Blackwell: B200 (single node, FP8)
NVIDIA Hopper: H100 (single node, NVFP4), H200 (single node, FP8)
Operating Systems: Linux

Additional Testing Statement: The integration of foundation and fine-tuned models into AI systems requires additional testing using use-case-specific data to ensure safe and effective deployment. Following the V-model methodology, iterative testing and validation at both unit and system levels are essential to mitigate risks, meet technical and functional requirements, and ensure compliance with safety and ethical standards before deployment.

Model Version(s)
v1.0 (December 2025)

Training, Testing, and Evaluation Datasets:
Training Dataset
Data Modality: Undisclosed
Training Data Collection: Undisclosed
Training Labeling: Undisclosed
Training Properties: Undisclosed

Testing Dataset
Testing Data Collection: Undisclosed
Testing Labeling: Undisclosed
Testing Properties: Undisclosed

Evalu...

## 参考链接

- [[NVIDIA API 配置]]
- [[AI 工作流全景概述]]
- [[Agent Team 浏览器AI 整合方案]]
- [[feedback_default_model]]

## 相关概念（自动补全）

- [[混合专家模型（MoE）]] — 需要补充
- [[推测解码（Speculative Decoding）]] — 需要补充
- [[NVFP4量化]] — 需要补充
- [[NVIDIA API试用条款]] — 需要补充

---

**来源**: /learn auto-generated
**处理时间**: 2026-05-31 02:20:54
**文件哈希**: `e8157d48`
