---
title: Step 3.5 Flash 模型说明
created: 2026-05-31
source: file:///D:/Users/lenovo/Desktop/claude workspace/AI知识库/01-Import/2b417604-stepfun35-flash.md
hash: 2b417604
tags: ["大语言模型", "MoE架构", "开源模型", "NVIDIA API", "编码辅助", "智能体应用", "长上下文模型", "高性能推理"]
entities: ["StepFun", "NVIDIA", "DGX Spark", "NVIDIA A100", "NVIDIA A10", "NVIDIA B100", "NVIDIA B200", "NVIDIA H100", "NVIDIA H200", "SWE-bench", "Terminal-Bench 2.0", "τ²-Bench", "OpenRouter", "HuggingFace"]
category: AI
summary: Step 3.5 Flash是阶跃星辰（StepFun）开发的稀疏混合专家（MoE）大语言模型，总参196.81B、单token仅激活约11B参数，支持256K长上下文，最高推理速度达350tok/s
---

# Step 3.5 Flash 模型说明

## 摘要

Step 3.5 Flash是阶跃星辰（StepFun）开发的稀疏混合专家（MoE）大语言模型，总参196.81B、单token仅激活约11B参数，支持256K长上下文，最高推理速度达350tok/s，适用于编码、复杂推理、智能体等场景，支持商用。

## 核心要点

- Step 3.5 Flash为StepFun开发的稀疏MoE大模型，总参196.81B，单token仅激活约11B参数，实现性能与推理效率的平衡
- 模型支持256K超长上下文，最高推理吞吐达350tok/s，在编码、复杂推理、智能体任务上表现优异
- 模型支持商用，可适配vLLM、SGLang等主流推理框架，优化运行于NVIDIA Ampere、Blackwell、Hopper系列GPU

## 关键概念

- [[稀疏混合专家（MoE）]]
- [[多令牌预测（MTP）]]
- [[滑动窗口注意力（SWA）]]
- [[智能体（Agentic）]]
- [[RAG]]
- [[向量搜索]]
- [[Embedding模型]]
- [[vLLM]]
- [[SGLang]]
- [[llama.cpp]]
- [[Hugging Face Transformers]]
- [[NVIDIA GPU加速]]
- [[Apache 2.0许可证]]

## 结构化拆解

### 核心观点
Step 3.5 Flash是高效率稀疏MoE架构的开源大语言模型，专为编码、智能体及复杂推理场景优化，具备高吞吐与长上下文能力。

### 详细解释
该模型采用稀疏混合专家架构，总参数量达196.81B，单token推理仅激活约11B参数，大幅降低推理成本；通过3路多令牌预测（MTP-3）与3:1滑动窗口注意力机制，实现100-350tok/s的推理吞吐，支持256K超长上下文；在SWE-bench、Terminal-Bench等基准测试中表现突出，适配vLLM、SGLang等主流推理框架，可运行于NVIDIA多系列GPU，适用于编码助手、深度研究智能体、GUI自动化等场景。

### 代码示例
```
completion = client.chat.completions.create(
    model="stepfun-ai/step-3.5-flash",
    messages=[{"role":"user","content":""}],
    temperature=1,
    top_p=0.9,
    max_tokens=16384,
    stream=False
)
```

### 适用场景
- 编码辅助开发
- 复杂多步推理任务
- 智能体与GUI自动化
- 深度研究信息处理
- 企业级AI应用部署

### 常见误区
- 误认为该模型为NVIDIA自研模型，实际为StepFun开发、NVIDIA提供部署支持
- 忽略稀疏MoE架构的总参数与激活参数差异，错误预估硬件资源需求
- 未关注商用场景需遵守NVIDIA Open Model License Agreement与Apache 2.0许可证的相关条款

## 原始内容

completion = client.chat.completions.create(
  model="stepfun-ai/step-3.5-flash",
  messages=[{"role":"user","content":""}],
  temperature=1,
  top_p=0.9,
  max_tokens=16384,
  stream=False
)
Step 3.5 Flash
Description
Step 3.5 Flash is a sparse Mixture-of-Experts (MoE) large language model developed by StepFun, engineered to deliver frontier reasoning and agentic capabilities with exceptional efficiency. Built on 196.81B total parameters with only ~11B active per token, it achieves the reasoning depth of top-tier models while maintaining real-time responsiveness with 100-300 tok/s throughput (peaking at 350 tok/s for coding tasks).

This model is ready for commercial/non-commercial use.

Third-Party Community Consideration:
This model is not owned or developed by NVIDIA. This model has been developed and built to a third-party's requirements for this application and use case; see link to Non-NVIDIA Step 3.5 Flash Model Card

License and Terms of Use:
GOVERNING TERMS: This trial service is governed by the NVIDIA API Trial Terms of Service. Use of this model is governed by the NVIDIA Open Model License Agreement. Additional Information: Apache License, Version 2.0.

Deployment Geography:
Global

Use Case:
Use Case: Developers and enterprises seeking a high-performance open-weight LLM for coding assistants, deep research agents, GUI automation, and complex multi-step reasoning tasks. The model is optimized for DGX Spark deployment with fast inference speeds and is particularly strong at tool-calling and agentic applications.

Key Features:

Sparse MoE Efficiency: 196B parameters with only ~11B active per token, combining elite intelligence with 11B-class inference speed
MTP-3 Acceleration: 3-way Multi-Token Prediction enables 100-300 tok/s throughput, peaking at 350 tok/s for coding
Efficient Long Context: 256K context window using 3:1 Sliding Window Attention ratio for cost-efficient processing
Agentic Mastery: 74.4% on SWE-bench Verified, 51.0% on Terminal-Bench 2.0, 88.2 on τ²-Bench
Release Date:
Build.NVIDIA.com: 02/2026 via link
Huggingface: 02/2026 via link

Reference(s):
References:

StepFun HuggingFace
StepFun Platform
OpenRouter
Model Architecture:
Architecture Type: Transformer
Network Architecture: Mixture-of-Experts
Total Parameters: 196.81B (196B Backbone + 0.81B MTP Head)
Active Parameters: ~11B per token
Vocabulary Size: 128,896
Layers: 45
Hidden Size: 4,096
Experts: 288 routed experts + 1 shared expert (always active), Top-8 selection per token
Attention: 3:1 SWA ratio (three sliding-window layers per full-attention layer), window size 512

Input:
Input Types: Text
Input Formats: String
Input Parameters: One-Dimensional (1D)
Other Input Properties: Supports multi-turn conversations and tool-calling formats.
Input Context Length (ISL): 256,000

Output:
Output Types: Text
Output Format: String
Output Parameters: One-Dimensional (1D)
Other Output Properties: Generates coherent responses for coding, reasoning, and general text generation tasks.

Our AI models are designed and/or optimized to run on NVIDIA GPU-accelerated systems. By leveraging NVIDIA's hardware (e.g. GPU cores) and software frameworks (e.g., CUDA libraries), the model achieves faster training and inference times compared to CPU-only solutions.

Software Integration:
Integrations
Supported inference frameworks include vLLM, SGLang, llama.cpp, and Hugging Face Transformers.

Runtime Engines:

vLLM:
SGLang:
Transformers:
Supported Hardware:

NVIDIA Ampere: A100, A10
NVIDIA Blackwell: B100, B200
NVIDIA Hopper: H100, H200
Preferred Operating Systems: Linux

The integration of foundation and fine-tuned models into AI systems requires additional testing using use-case-specific data to ensure safe and effective deployment. Following the V-model methodology, iterative testing and validation at both unit and system levels are essential to mitigate risks, meet technical and functional requirements, and ensure compliance with safety and ethical standards before deployment.

Model Version(s)
Step 3.5 Flash v1.0

Training, Testing, and Evaluation Datasets:
Training Dataset
Data Modality: Text
Training Data Collection: Undisclosed
Training Labeling: Undisclosed
Training Properties: Undisclosed

Testing Dataset
Testing Data Collection: Undisclosed
Testing Labeling: Undisclosed
Testing Properties: Undisclosed

Evaluation Dataset
Evaluation Benchmark Score: Step 3.5 Flash achieves frontier-level performance across Agency, Reasoning, and Coding benchmarks. For more information see Detailed Benchmark Comparison Table below.
Evaluation Data Collection: Automated
Evaluation Labeling: Hybrid: Automated, Human
Evaluation Properties: Evaluated on industry-standard benchmarks for coding (SWE-bench Verified, LiveCodeBench-V6, Terminal-Bench 2.0), agentic capabilities (τ²-Bench, BrowseComp, GAIA, xbench-DeepSearch), and mathematical reasoning (AIME 2025, HMMT 2025, IMOAnswerBench).

Detailed Benchmark Comparison Table
Inference
Acceleration Engine: vLLM
Test...

## 参考链接

- [[Step 3.5 Flash]]
- [[NVIDIA API 配置]]
- [[vLLM环境下Mistral Large 3 675B Instruct 2512模型API配置与说明]]
- [[AI 工作流全景概述]]
- [[feedback_default_model]]

## 相关概念（自动补全）

- [[稀疏混合专家（MoE）架构]] — 需要补充
- [[多令牌预测（MTP）技术]] — 需要补充
- [[3:1滑动窗口注意力（SWA）机制]] — 需要补充
- [[SWE-bench编码能力基准]] — 需要补充
- [[Terminal-Bench终端任务基准]] — 需要补充
- [[τ²-Bench推理能力基准]] — 需要补充
- [[DGX Spark部署方案]] — 需要补充

---

**来源**: /learn auto-generated
**处理时间**: 2026-05-31 02:22:35
**文件哈希**: `2b417604`
