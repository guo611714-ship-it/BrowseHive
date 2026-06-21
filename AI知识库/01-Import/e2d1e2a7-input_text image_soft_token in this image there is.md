---
title: [{'input_text': '<image_soft_token> in this image, there is',
created: 2026-05-31
source: file:///D:/Users/lenovo/Desktop/claude workspace/AI知识库/01-Import/e2d1e2a7-input_text image_soft_token in this image there is.md
hash: e2d1e2a7
tags: []
entities: []
category: AI
summary: payload = {
  "model": "google/gemma-3n-e2b-it",
  "messages": [{"role":"user","content":""}],
  "ma
---

# [{'input_text': '<image_soft_token> in this image, there is',

## 摘要

payload = {
  "model": "google/gemma-3n-e2b-it",
  "messages": [{"role":"user","content":""}],
  "max_tokens": 512,
  "temperature": 0.20,
  "top_p": 0.70,
  "frequency_penalty": 0.00,
  "presence_pen

## 关键概念



## 原始内容

payload = {
  "model": "google/gemma-3n-e2b-it",
  "messages": [{"role":"user","content":""}],
  "max_tokens": 512,
  "temperature": 0.20,
  "top_p": 0.70,
  "frequency_penalty": 0.00,
  "presence_penalty": 0.00,
  "stream": stream
}

Gemma 3n e2b-it Overview
Description
Gemma is a family of lightweight, state-of-the-art open models from Google, built from the same research and technology used to create the Gemini models. Gemma 3n models are designed for efficient execution on low-resource devices. They are capable of multimodal input, handling text, image, video, and audio input, and generating text outputs, with open weights for pre-trained and instruction-tuned variants. These models were trained with data in over 140 spoken languages.

This model is ready for commercial/non-commercial use.

Third-Party Community Consideration
This model is not owned or developed by NVIDIA. It has been produced to a third-party's requirements for this application and use-case. See the external card: Gemma 3n e2b-it Model Card.

License and Terms of Use:
GOVERNING TERMS: This trial service is governed by the NVIDIA API Trial Terms of Service. Use of this model is governed by the NVIDIA Community Model License. Additional Information: Gemma Terms of Use

Deployment Geography:
Global

Use Case:
Content Creation and Communication (Text Generation, Chatbots, Summarization, Image/Audio Data Extraction), Research and Education (NLP Research, Language Learning, Knowledge Exploration)

Intended Usage
Open generative models have a wide range of applications across various industries and domains. The following list of potential uses is not comprehensive. The purpose of this list is to provide contextual information about the possible use-cases that the model creators considered as part of model training and development.

Content Creation and Communication
Text Generation: Generate creative text formats such as poems, scripts, code, marketing copy, and email drafts.
Chatbots and Conversational AI: Power conversational interfaces for customer service, virtual assistants, or interactive applications.
Text Summarization: Generate concise summaries of a text corpus, research papers, or reports.
Image Data Extraction: Extract, interpret, and summarize visual data for text communications.
Audio Data Extraction: Transcribe spoken language, translate speech to text in other languages, and analyze sound-based data.
Research and Education
Natural Language Processing (NLP) and generative model Research: These models can serve as a foundation for researchers to experiment with generative models and NLP techniques, develop algorithms, and contribute to the advancement of the field.
Language Learning Tools: Support interactive language learning experiences, aiding in grammar correction or providing writing practice.
Knowledge Exploration: Assist researchers in exploring large bodies of data by generating summaries or answering questions about specific topics.
Release Date:
Build.NVIDIA.com: 06/26/2025 via (link)
Hugging Face: 06/26/2025 via (link)

References:
Gemma 3n Model Overview
Gemma 3n's Efficient Parameter Management Technology
Responsible Generative AI Toolkit
Gemma on Kaggle
Gemma on HuggingFace
Gemma on Vertex Model Garden
Model Architecture:
Architecture Type: Matryoshka Transformer
Network Architecture: Matryoshka Transformer (MatFormer)
Parameter Count: 2B (base model), ~4.4B (with Per-Layer Embeddings)
Number of Layers: 30
Notable Architectural Features: Selective parameter activation technology
Base Model: google/gemma-3n-e2b
Additional Notes: The model's full parameter count is higher than its base model size due to Per-Layer Embeddings (PLE). Standard implementations will load all parameters, including PLE, into VRAM.
Input
Input Type(s): Text, Image, Audio
Input Formats: Text string, Images (normalized to 256x256, 512x512, or 768x768), Audio data (single channel)
Input Parameters: One Dimensional (1D), Two Dimensional (2D), Three Dimensional (3D)
Other Properties Related to Input: Total input context of 32K tokens. Images are encoded to 256 tokens each. Audio data is encoded to 6.25 tokens per second from a single channel.
Output
Output Type(s): Text
Output Formats: Text
Output Parameters: 1D
Other Properties Related to Output: Total output length up to 32K tokens, subtracting the request input tokens.

Our Al models are designed and/or optimized to run on NVIDIA GPU-accelerated systems. By leveraging NVIDIA's hardware (e.g. GPU cores) and software frameworks (e.g., CUDA libraries), the model achieves faster training and inference times compared to CPU-only solutions.
Software Integration
Supported Hardware Microarchitecture Compatibility:

NVIDIA GPU Micro-architectures Suitable for Serving Gemma 3n in Production
(≥ 16 GB VRAM + Tensor-core /mixed-precision support)

µArch	First Public Release	Example SKUs (≥ 16 GB)	Tensor-core Gen / Precision	Production Suitability
Blackwell	2024	B100 (192 GB HBM3e) · B200 (192 GB HBM3e) · RT...

## 参考链接



---

**来源**: /learn auto-generated
**处理时间**: 2026-05-31 02:16:32
**文件哈希**: `e2d1e2a7`
