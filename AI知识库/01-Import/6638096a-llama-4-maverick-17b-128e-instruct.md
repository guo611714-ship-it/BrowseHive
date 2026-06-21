---
title: llama-4-maverick-17b-128e-instruct
created: 2026-05-31
source: file:///D:/Users/lenovo/Desktop/claude workspace/AI知识库/01-Import/6638096a-llama-4-maverick-17b-128e-instruct.md
hash: 6638096a
tags: []
entities: []
category: AI
summary: payload = {
  "model": "meta/llama-4-maverick-17b-128e-instruct",
  "messages": [{"role":"user","con
---

# llama-4-maverick-17b-128e-instruct

## 摘要

payload = {
  "model": "meta/llama-4-maverick-17b-128e-instruct",
  "messages": [{"role":"user","content":""}],
  "max_tokens": 512,
  "temperature": 1.00,
  "top_p": 1.00,
  "frequency_penalty": 0.00

## 关键概念



## 原始内容

payload = {
  "model": "meta/llama-4-maverick-17b-128e-instruct",
  "messages": [{"role":"user","content":""}],
  "max_tokens": 512,
  "temperature": 1.00,
  "top_p": 1.00,
  "frequency_penalty": 0.00,
  "presence_penalty": 0.00,
  "stream": stream
}

Model Information
The Llama 4 collection of models are natively multimodal AI models that enable text and multimodal experiences. These models leverage a mixture-of-experts architecture to offer industry-leading performance in text and image understanding.

These Llama 4 models mark the beginning of a new era for the Llama ecosystem. We are launching two efficient models in the Llama 4 series, Llama 4 Scout, a 17 billion parameter model with 16 experts, and Llama 4 Maverick, a 17 billion parameter model with 128 experts.

Third-Party Community Consideration
This model is not owned or developed by NVIDIA. This model has been developed and built to Meta's requirements for this application and use case; see link to Non-NVIDIA Llama 4 Maverick.

License/Terms of Use:
GOVERNING TERMS: The trial service is governed by the NVIDIA API Trial Terms of Service; and the use of this model is governed by the NVIDIA Community Model License. ADDITIONAL INFORMATION: Llama 4 Community Model License. Built with Llama.

Model developer: Meta

Model Architecture: The Llama 4 models are auto-regressive language models that use a mixture-of-experts (MoE) architecture and incorporate early fusion for native multimodality.

Model Name	Training Data	Params	Input modalities	Output modalities	Context length	Token count	Knowledge cutoff
Llama 4 Scout (17Bx16E)	A mix of publicly available, licensed data and information from Meta’s products and services. This includes publicly shared posts from Instagram and Facebook and people’s interactions with Meta AI. Learn more in our Privacy Center.	17B (Activated) 109B (Total)	Multilingual text and image	Multilingual text and code	10M	~40T	August 2024
Llama 4 Maverick (17Bx128E)		17B (Activated) 400B (Total)	Multilingual text and image	Multilingual text and code	1M	~22T	August 2024
Supported languages: Arabic, English, French, German, Hindi, Indonesian, Italian, Portuguese, Spanish, Tagalog, Thai, and Vietnamese.

Model Release Date: April 5, 2025

Status: This is a static model trained on an offline dataset. Future versions of the tuned models may be released as we improve model behavior with community feedback.

Where to send questions or comments about the model: Instructions on how to provide feedback or comments on the model can be found in the Llama README. For more technical information about generation parameters and recipes for how to use Llama 4 in applications, please go here.

Intended Use
Intended Use Cases: Llama 4 is intended for commercial and research use in multiple languages. Instruction tuned models are intended for assistant-like chat and visual reasoning tasks, whereas pretrained models can be adapted for natural language generation. For vision, Llama 4 models are also optimized for visual recognition, image reasoning, captioning, and answering general questions about an image. The Llama 4 model collection also supports the ability to leverage the outputs of its models to improve other models including synthetic data generation and distillation. The Llama 4 Community License allows for these use cases.

Out-of-scope: Use in any manner that violates applicable laws or regulations (including trade compliance laws). Use in any other way that is prohibited by the Acceptable Use Policy and Llama 4 Community License. Use in languages or capabilities beyond those explicitly referenced as supported in this model card**.

**Note:

1. Llama 4 has been trained on a broader collection of languages than the 12 supported languages (pre-training includes 200 total languages). Developers may fine-tune Llama 4 models for languages beyond the 12 supported languages provided they comply with the Llama 4 Community License and the Acceptable Use Policy. Developers are responsible for ensuring that their use of Llama 4 in additional languages is done in a safe and responsible manner.

2. Llama 4 has been tested for image understanding up to 5 input images. If leveraging additional image understanding capabilities beyond this, Developers are responsible for ensuring that their deployments are mitigated for risks and should perform additional testing and tuning tailored to their specific applications.

Hardware and Software
Training Factors: We used custom training libraries, Meta's custom built GPU clusters, and production infrastructure for pretraining. Fine-tuning, quantization, annotation, and evaluation were also performed on production infrastructure.

Training Energy Use: Model pre-training utilized a cumulative of 7.38M GPU hours of computation on H100-80GB (TDP of 700W) type hardware, per the table below. Training time is the total GPU time required for training each model and power consumption is the peak power capacity per GPU device used, ...

## 参考链接



---

**来源**: /learn auto-generated
**处理时间**: 2026-05-31 02:19:18
**文件哈希**: `6638096a`
