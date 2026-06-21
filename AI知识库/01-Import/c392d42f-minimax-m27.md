---
title: MiniMax M2.7 模型说明
created: 2026-05-31
source: file:///D:/Users/lenovo/Desktop/claude workspace/AI知识库/01-Import/c392d42f-minimax-m27.md
hash: c392d42f
tags: ["大语言模型", "MiniMax", "MoE架构", "智能体", "办公AI", "软件工程", "NVIDIA生态"]
entities: ["MiniMax M2.7", "NVIDIA", "SGLang", "Transformers", "vLLM", "NVIDIA Blackwell（B100/B200/GB200）", "NVIDIA Hopper（H100/H200）", "SWE-Pro", "VIBE-Pro", "Terminal Bench 2", "NL2Repo", "GDPval-AA", "Toolathon", "MM Claw", "MLE Bench Lite"]
category: AI
summary: MiniMax M2.7是面向复杂软件工程、智能体工作流及办公生产力场景研发的大语言模型，采用MoE架构，总参230B、激活参仅10B，支持20.48万长上下文，仅可用于研发用途，在多项基准测试中表现
---

# MiniMax M2.7 模型说明

## 摘要

MiniMax M2.7是面向复杂软件工程、智能体工作流及办公生产力场景研发的大语言模型，采用MoE架构，总参230B、激活参仅10B，支持20.48万长上下文，仅可用于研发用途，在多项基准测试中表现优异。

## 核心要点

- MiniMax M2.7是专为复杂软件工程、智能体工具调用、办公生产力等多步骤任务研发的大语言模型，仅可用于研发用途，非NVIDIA开发
- 模型采用MoE架构，总参数量230B，单token仅激活8个专家，激活参数量仅10B，支持20.48万超长上下文输入
- 模型适配NVIDIA GPU硬件及SGLang、vLLM等推理框架，支持Linux系统部署，需针对具体用例做额外测试验证
- 模型在SWE-Pro、GDPval-AA等软件工程、办公、智能体工具调用类基准测试中表现优异，GDPval-AA得分居开源模型首位

## 关键概念

- [[大语言模型（LLM）]]
- [[Mixture-of-Experts（混合专家架构）]]
- [[Transformer]]
- [[智能体（Agent）工作流]]
- [[长上下文处理]]
- [[软件工程辅助]]
- [[办公生产力]]
- [[模型评估基准]]

## 结构化拆解

### 核心观点
MiniMax M2.7是一款面向复杂软件工程、智能体工作流与办公生产力场景的高性能MoE架构大语言模型，仅可用于研发用途。

### 详细解释
该模型总参数量达230B，采用混合专家（MoE）架构，每token仅激活8个专家，激活参数量仅10B，兼顾性能与推理效率。支持20.48万超长上下文输入，适配NVIDIA Blackwell、Hopper系列GPU，可基于SGLang、Transformers、vLLM等框架在Linux系统部署。在软件工程、办公、智能体工具调用等多类基准测试中表现优异，其中GDPval-AA得分居开源模型首位。

### 代码示例
暂无

### 适用场景
- 复杂软件工程开发与调试
- 多步骤智能体工作流编排
- 办公文档生成与编辑
- 生产环境问题实时排查
- 机器学习竞赛任务辅助

### 常见误区
- 误以为该模型可商用，实际仅可用于研发用途
- 误认为该模型由NVIDIA开发，实际为第三方开发
- 忽略部署需适配NVIDIA GPU硬件及对应软件框架
- 未针对具体用例做额外测试验证就直接部署

## 原始内容

MiniMax M2.7
Description
MiniMax M2.7 is a large language model for complex software engineering, agentic tool use, and office productivity workflows. It is presented as a model deeply participating in its own evolution, with support for complex agent harnesses, dynamic tool search, Agent Teams, and high-fidelity coding and document-editing tasks.

This model is for research and development only.

Third-Party Community Consideration:
This model is not owned or developed by NVIDIA. This model has been developed and built to a third-party's requirements for this application and use case; see link to Non-NVIDIA MiniMax M2.7 Model Card

License and Terms of Use:
GOVERNING TERMS: The trial service is governed by the NVIDIA API Trial Terms of Service; use of this model is governed by the NVIDIA Software and Model Evaluation license. ADDITIONAL INFORMATION: Non-Commercial MiniMax License. Copyright (c) 2026 MiniMax.

Deployment Geography:
Global

Use Case:
Use Case: Designed for advanced coding assistance, agentic workflows, long-horizon software engineering, live production troubleshooting, office document generation and editing, and other complex multi-step productivity tasks.

Release Date:
Build.NVIDIA.com: 04/11/2026 via link
Huggingface: 04/11/2026 via link

Reference(s):
References:

MiniMax M2.7 model page
MiniMax M2.7 launch report
MiniMax M2.7 Hugging Face repository
MiniMax M2.7 GitHub repository
MiniMax text generation docs
MiniMax model release notes
MiniMax API platform
OpenRoom
Model Architecture:
Architecture Type: Transformer
Network Architecture: Mixture-of-Experts
Total Parameters: 230B
Active Parameters: 10B
Layers: 62
Hidden Size: 3072
Experts: 256 local experts, with 8 experts activated per token

Input:
Input Types: Text
Input Formats: String
Input Parameters: One-Dimensional (1D)
Other Input Properties: Supports long system prompts.
Input Context Length (ISL): 204,800

Output:
Output Types: Text
Output Format: String
Output Parameters: One-Dimensional (1D)
Other Output Properties: Not applicable.

Our AI models are designed and/or optimized to run on NVIDIA GPU-accelerated systems. By leveraging NVIDIA's hardware (e.g. GPU cores) and software frameworks (e.g., CUDA libraries), the model achieves faster training and inference times compared to CPU-only solutions.

Software Integration:
Runtime Engines:

SGLang
Transformers
vLLM
Supported Hardware:

NVIDIA Blackwell: B100, B200, GB200
NVIDIA Hopper: H100, H200
Operating Systems: Linux

The integration of foundation and fine-tuned models into AI systems requires additional testing using use-case-specific data to ensure safe and effective deployment. Following the V-model methodology, iterative testing and validation at both unit and system levels are essential to mitigate risks, meet technical and functional requirements, and ensure compliance with safety and ethical standards before deployment.

Model Version(s)
MiniMax M2.7 v2.7

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
Evaluation Benchmark Score: Publicly reported results include 56.22% on SWE-Pro, 55.6% on VIBE-Pro, 57.0% on Terminal Bench 2, 39.8% on NL2Repo, 1495 ELO on GDPval-AA, 46.3% on Toolathon, 62.7% on MM Claw, and a 66.6% medal rate on MLE Bench Lite. The GDPval-AA result is presented as the highest among open-source models.
Evaluation Data Collection: Undisclosed
Evaluation Labeling: Undisclosed
Evaluation Properties: Evaluation results span software engineering, office productivity, agentic tool-use, and machine learning competition benchmarks, including SWE-Pro, SWE Multilingual, Multi SWE Bench, VIBE-Pro, Terminal Bench 2, NL2Repo, GDPval-AA, Toolathon, MM Claw, and MLE Bench Lite (22 ML competitions). MM Claw testing also cites 97% skill compliance across 40+ complex skills.

View Selected Publicly Reported Benchmarks
Inference
Acceleration Engine: vLLM
Test Hardware: NVIDIA H100x4

Additional Details
Production Troubleshooting
M2.7 is described as supporting live production debugging workflows involving monitoring metrics, trace analysis, database verification, and SRE-style decision-making. Its use is also described as reducing recovery time for live production incidents to under three minutes on multiple occasions.

Model Self-Evolution
M2.7 is positioned as MiniMax's first model deeply participating in its own evolution. During development, the model updated memory, built complex skills for reinforcement learning experiments, improved its learning process based on experiment results, and autonomously optimized a programming scaffold over 100+ rounds for a reported 30% performance improvement.

Recommended Deployment Settings
Recommended deployment settings include temperature=1.0, top_p=0.95, and t...

## 参考链接

- [[Agent Team 浏览器AI 整合方案]]
- [[NVIDIA API 配置]]
- [[AI 工作流全景概述]]
- [[Office Add-in 工作流程]]

## 相关概念（自动补全）

- [[Mixture-of-Experts（混合专家架构）]] — 需要补充
- [[SWE-Pro基准]] — 需要补充
- [[VIBE-Pro基准]] — 需要补充
- [[Terminal Bench 2基准]] — 需要补充
- [[NL2Repo基准]] — 需要补充
- [[GDPval-AA基准]] — 需要补充
- [[Toolathon基准]] — 需要补充
- [[MM Claw基准]] — 需要补充
- [[MLE Bench Lite基准]] — 需要补充
- [[SGLang推理框架]] — 需要补充
- [[vLLM推理框架]] — 需要补充
- [[NVIDIA Blackwell架构]] — 需要补充
- [[NVIDIA Hopper架构]] — 需要补充

---

**来源**: /learn auto-generated
**处理时间**: 2026-05-31 02:20:26
**文件哈希**: `c392d42f`
