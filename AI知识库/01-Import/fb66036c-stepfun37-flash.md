---
title: Step 3.7 Flash 模型说明
created: 2026-05-31
source: file:///D:/Users/lenovo/Desktop/claude workspace/AI知识库/01-Import/fb66036c-stepfun37-flash.md
hash: fb66036c
tags: ["大语言模型", "多模态", "StepFun", "NVIDIA", "MoE架构", "代码生成", "智能体", "模型说明"]
entities: ["Step 3.7 Flash", "Step 3.5 Flash", "StepFun", "NVIDIA", "vLLM", "SGLang", "NVIDIA Blackwell（B200/B100/GB200）", "NVIDIA Hopper（H100/H200）", "SWE-bench Verified", "Terminal-Bench 2.0", "τ²-Bench", "Apache 2.0"]
category: AI
summary: Step 3.7 Flash是StepFun推出的基于Step 3.5 Flash的多模态大语言模型，支持文本、图像输入，面向多模态理解、智能体工作流、代码生成等场景，采用稀疏MoE架构具备高效推理能
---

# Step 3.7 Flash 模型说明

## 摘要

Step 3.7 Flash是StepFun推出的基于Step 3.5 Flash的多模态大语言模型，支持文本、图像输入，面向多模态理解、智能体工作流、代码生成等场景，采用稀疏MoE架构具备高效推理能力，可用于商业及非商业用途。

## 核心要点

- Step 3.7 Flash是StepFun基于Step 3.5 Flash升级的多模态视觉语言模型，原生支持文本、图像输入与文本输出
- 采用稀疏MoE架构，总参数量198B，单token仅激活约11B参数，兼顾精英模型性能与轻量级推理速度
- 支持256K长上下文，3路多令牌预测技术使推理吞吐量达100-350 tok/s，适配代码生成等高速场景
- 在智能体任务、代码生成等基准测试中表现优异，支持vLLM、SGLang等推理引擎，可部署于NVIDIA Blackwell、Hopper系列GPU

## 关键概念

- [[多模态大语言模型]]
- [[稀疏混合专家（MoE）]]
- [[多令牌预测（MTP）]]
- [[滑动窗口注意力]]
- [[智能体工作流]]
- [[代码生成]]
- [[vLLM推理引擎]]
- [[NVIDIA GPU加速]]
- [[Apache 2.0许可证]]

## 结构化拆解

### 核心观点
Step 3.7 Flash是面向多模态理解、智能体工作流与代码生成场景的高效稀疏MoE架构大语言模型，兼顾高性能与低成本推理。

### 详细解释
该模型基于Step 3.5 Flash升级新增原生视觉能力，总参数量198B，单token仅激活约11B参数，通过稀疏MoE架构实现精英模型性能与轻量级推理速度的平衡。采用3:1滑动窗口注意力机制支持256K长上下文，3路多令牌预测技术将推理吞吐量提升至100-350 tok/s，在SWE-bench Verified、Terminal-Bench 2.0等智能体基准测试中表现突出，支持vLLM、SGLang等推理引擎，可适配NVIDIA Blackwell、Hopper系列GPU部署。

### 代码示例
```
# vLLM启动Step 3.7 Flash示例
from vllm import LLM, SamplingParams
llm = LLM(model="stepfun/Step-3.7-Flash", tensor_parallel_size=2)
sampling_params = SamplingParams(temperature=0.7, top_p=0.95, max_tokens=2048)
outputs = llm.generate(["解释这张图片的内容：<image>"], sampling_params)
print(outputs[0].outputs[0].text)
```

### 适用场景
- 多模态内容理解（图文混合输入分析）
- 智能体工作流搭建（工具调用、自动化任务执行）
- 代码生成与前端开发辅助
- GUI相关任务处理（截图、界面元素分析）
- 长文本处理与推理

### 常见误区
- 误认为该模型为NVIDIA自研模型，实际为StepFun开发、NVIDIA提供适配部署支持
- 忽略稀疏MoE架构的激活参数特性，误判推理硬件需求
- 未注意输入图像尺寸要求（728x728像素），导致视觉输入处理异常

## 原始内容

Step 3.7 Flash
Description
Step-3.7-Flash is a StepFun vision-language model built on Step 3.5 Flash with additional vision capability for native multimodal, agentic, and coding-related use cases. The model is intended to process text and image inputs and produce text outputs, with emphasis on image understanding, fast throughput, and tool-use workflows.

This model is ready for commercial/non-commercial use.

Third-Party Community Consideration:
This model is not owned or developed by NVIDIA. This model has been developed and built to a third-party's requirements for this application and use case; see link to Non-NVIDIA Step-3.7-Flash Model Card.

License and Terms of Use:
GOVERNING TERMS: The trial service is governed by the NVIDIA API Trial Terms of Service; and use of this model is governed by the NVIDIA Open Model Agreement. Additional Information: Apache 2.0 License.

Deployment Geography:
Global

Use Case:
Use Case: Step-3.7-Flash is intended for multimodal understanding, agentic workflow support, coding and frontend-generation workflows, tool calling, and GUI-oriented tasks that use text, screenshots, or images as input.

Key Features:

Sparse MoE Efficiency: 196B parameters with only ~11B active per token, combining elite intelligence with 11B-class inference speed
MTP-3 Acceleration: 3-way Multi-Token Prediction enables 100-300 tok/s throughput, peaking at 350 tok/s for coding
Efficient Long Context: 256K context window using 3:1 Sliding Window Attention ratio for cost-efficient processing
Agentic Mastery: 74.4% on SWE-bench Verified, 51.0% on Terminal-Bench 2.0, 88.2 on τ²-Bench
Release Date:
Build.NVIDIA.com: 05/28/2026 via link
Huggingface: 05/28/2026 via link

Reference(s):
Step-3.7-Flash Model Card
Model Architecture:
Architecture Type: Transformer
Network Architecture: Mixture-of-Experts
Total Parameters: 198B
Active Parameters: Approximately 11B per token
Text backbone based on Step 3.5 Flash

Input:
Input Types: Text, Image
Input Formats: String, Red, Green, Blue (RGB)
Input Parameters: One-Dimensional (1D), Two-Dimensional (2D)
Other Input Properties: The vision module uses an image size of 728x728 pixels.
Input Context Length (ISL): 256k

Output:
Output Types: Text
Output Format: String
Output Parameters: One-Dimensional (1D)
Other Output Properties: None

Our AI models are designed and/or optimized to run on NVIDIA GPU-accelerated systems. By leveraging NVIDIA's hardware (e.g. GPU cores) and software frameworks (e.g., CUDA libraries), the model achieves faster training and inference times compared to CPU-only solutions.

Software Integration:
Runtime Engines:

vLLM
SGLang
Supported Hardware:

NVIDIA Blackwell: B200, B100, GB200
NVIDIA Hopper: H100, H200
Preferred Operating Systems: Linux

The integration of foundation and fine-tuned models into AI systems requires additional testing using use-case-specific data to ensure safe and effective deployment. Following the V-model methodology, iterative testing and validation at both unit and system levels are essential to mitigate risks, meet technical and functional requirements, and ensure compliance with safety and ethical standards before deployment.

Model Version(s)
Step-3.7-Flash v1.0

Training, Testing, and Evaluation Datasets:
Training Dataset
Data Modality: Text, Image
Image Training Data Size: Undisclosed
Text Training Data Size: Undisclosed
Training Data Collection: Undisclosed
Training Labeling: Undisclosed
Training Properties: Undisclosed

Testing Dataset
Testing Data Collection: Undisclosed
Testing Labeling: Undisclosed
Testing Properties: Undisclosed

Evaluation Dataset
Evaluation Benchmark Score: Undisclosed
Evaluation Data Collection: Undisclosed
Evaluation Labeling: Undisclosed
Evaluation Properties: Undisclosed

Inference
Acceleration Engine: vLLM
Test Hardware: NVIDIA 4xH100

Ethical Considerations
NVIDIA believes Trustworthy AI is a shared responsibility and we have established policies and practices to enable development for a wide array of AI applications. Developers should work with their internal developer team to ensure these software components meet requirements for the relevant industry and use case and address unforeseen product misuse.

Please make sure you have proper rights and permissions for all input image content; if image includes people, personal health information, or intellectual property, the image generated will not blur or maintain proportions of image subjects included.

Users are responsible for model inputs and outputs. Users are responsible for ensuring safe integration of this model, including implementing guardrails as well as other safety mechanisms, prior to deployment.

Please report model quality, risk, security vulnerabilities or NVIDIA AI Concerns here.

## 参考链接

- [[Step 3.5 Flash 模型说明]]
- [[vLLM环境下Mistral Large 3 675B Instruct 2512模型API配置与说明]]
- [[NVIDIA API 配置]]
- [[AI 工作流全景概述]]

## 相关概念（自动补全）

- [[稀疏混合专家（MoE）]] — 需要补充
- [[多令牌预测（MTP）]] — 需要补充
- [[滑动窗口注意力（Sliding Window Attention）]] — 需要补充
- [[SWE-bench Verified基准]] — 需要补充
- [[Terminal-Bench 2.0基准]] — 需要补充
- [[τ²-Bench基准]] — 需要补充

---

**来源**: /learn auto-generated
**处理时间**: 2026-05-31 02:22:52
**文件哈希**: `fb66036c`
