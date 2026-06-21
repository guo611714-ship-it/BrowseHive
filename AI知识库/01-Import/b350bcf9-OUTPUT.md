---
title: OUTPUT
created: 2026-05-31
source: file:///D:/Users/lenovo/Desktop/claude workspace/AI知识库/01-Import/b350bcf9-OUTPUT.md
hash: b350bcf9
tags: []
entities: []
category: 其他
summary: 自动生成的摘要
---

# OUTPUT

## 摘要

自动生成的摘要

## 关键概念



## 原始内容

Llama-Guard-4-12B Overview
Description:
Llama-Guard-4-12B is a 12-billion parameter, dense, multimodal safety classifier developed by Meta. It is designed to evaluate both text and image inputs for safety, classifying content in large language model (LLM) prompts and responses. The model outputs text indicating whether the content is safe or unsafe, and if unsafe, it lists the violated content categories.

This model is ready for commercial/non-commercial use.

Third-Party Community Consideration
This model is not owned or developed by NVIDIA. It has been developed and built to Meta's requirements for safety classification in multimodal LLM applications.
See the Llama-Guard-4-12B Model Card for more details.

License and Terms of Use:
GOVERNING TERMS: The trial service is governed by the NVIDIA API Trial Terms of Service; and the use of this model is governed by the NVIDIA Community Model License. ADDITIONAL INFORMATION: Llama 4 Community Model License. Built with Llama.

Deployment Geography:
Global

Use Case:
Intended for developers and organizations seeking to implement safety classification in LLM applications, including filtering of unsafe content in both inputs and outputs across text and image modalities.

Hazard Taxonomy and Policy
The model is trained to predict safety labels on the categories shown below, based on the MLCommons safety taxonomy. We include an additional category, Code Interpreter Abuse, for text-only tool-call use cases.

Hazard categories
S1: Violent Crimes	S2: Non-Violent Crimes
S3: Sex-Related Crimes	S4: Child Sexual Exploitation
S5: Defamation	S6: Specialized Advice
S7: Privacy	S8: Intellectual Property
S9: Indiscriminate Weapons	S10: Hate
S11: Suicide & Self-Harm	S12: Sexual Content
S13: Elections	S14: Code Interpreter Abuse (text only)
S1 - Violent Crimes

Responses that enable, encourage, or endorse the commission of violent crimes, including: (1) unlawful violence toward people (ex: terrorism, genocide, murder, hate-motivated violent crimes, child abuse, assault, battery, kidnapping) and (2) unlawful violence toward animals (ex: animal abuse)

S2 - Non-Violent Crimes

Responses that enable, encourage, or endorse the commission of non-violent crimes, including: (1) personal crimes (ex: labor trafficking, threats, intimidation, hate-motivated non-violent crimes), (2) financial crimes (ex: fraud, scams, money laundering), (3) property crimes (ex: theft, arson, vandalism), (4) drug crimes (ex: creating or using regulated substances), (5) weapons crimes (ex: producing unlicensed firearms), and (6) cyber crimes (ex: hacking)

S3 - Sex-Related Crimes

Responses that enable, encourage, or endorse the commission of sex-related crimes, including: (1) sex trafficking, (2) sexual assault (ex: rape), (3) sexual harassment (physical, verbal, or visual), and (4) prostitution

S4 - Child Sexual Exploitation

Responses that contain, describe, enable, encourage, or endorse the sexual abuse of children

S5 - Defamation

Responses that are both verifiably false and likely to injure a living person’s reputation

S6 - Specialized Advice

Responses that contain specialized financial, medical, or legal advice, or that indicate dangerous activities or objects are safe

S7 - Privacy

Responses that contain sensitive, nonpublic personal information that could undermine someone’s physical, digital, or financial security

S8 - Intellectual Property

Responses that may violate the intellectual property rights of any third party

S9 - Indiscriminate Weapons

Responses that enable, encourage, or endorse the creation of indiscriminate weapons, including: (1) chemical weapons (ex: nerve gas), (2) biological weapons (ex: anthrax), (3) radiological weapons (ex: cobalt bombs), (4) nuclear weapons (ex: fission bombs), and (5) high-yield explosive weapons (ex: cluster munitions)

S10 - Hate

Responses that demean or dehumanize people on the basis of their sensitive, personal characteristics (i.e., race, color, ethnicity, national origin, disability, religious affiliation, caste, sexual orientation, sex, gender identity, and/or serious disease)

S11 - Suicide & Self-Harm

Responses that enable, encourage, or endorse acts of intentional self-harm, including: (1) suicide, (2) self-injury (ex: cutting), and (3) disordered eating

S12 - Sexual Content

Responses that contain erotica

S13 - Elections

Responses that contain factually incorrect information about electoral systems and processes, including in the time, place, or manner of voting in civic elections

S14 - Code Interpreter Abuse (text-only)

Responses that seek to abuse code interpreters, including those that enable denial of service attacks, container escapes or privilege escalation exploits

Release Date:
Build.Nvidia.com: May, 2025
Hugging Face: April 29, 2025
Reference(s):
The Llama 3 Herd of Models
Developer Use Guide
Getting Started Guide
Llama Prompt Guard 2
Model Architecture:
Architecture Type: Transformer-based
Network Architecture: Dense feedfor...

## 参考链接



---

**来源**: /learn auto-generated
**处理时间**: 2026-05-31 02:20:03
**文件哈希**: `b350bcf9`
