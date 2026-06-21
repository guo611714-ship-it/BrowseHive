---
name: "senior-ml-engineer"
description: ML engineering skill for productionizing models, building MLOps pipelines, and integrating LLMs. Covers model deployment, feature stores, drift monitoring, RAG systems, and cost optimization. Use when the user asks about deploying ML models to production, setting up MLOps infrastructure (MLflow, Kubeflow, Kubernetes, Docker), monitoring model performance or drift, building RAG pipelines, or integrating LLM APIs with retry logic and cost controls. Focused on production and operational concerns rather than model research or initial training.
triggers:
  - MLOps pipeline
  - model deployment
  - feature store
  - model monitoring
  - drift detection
  - RAG system
  - LLM integration
  - model serving
  - A/B testing ML
  - automated retraining
---

# Senior ML Engineer

Production ML engineering patterns for model deployment, MLOps infrastructure, and LLM integration.

## Model Deployment Workflow

Deploy a trained model to production with monitoring:

1. Export model to standardized format (ONNX, TorchScript, SavedModel)
2. Package model with dependencies in Docker container
3. Deploy to staging environment
4. Run integration tests against staging
5. Deploy canary (5% traffic) to production
6. Monitor latency and error rates for 1 hour
7. Promote to full production if metrics pass
8. **Validation:** p95 latency < 100ms, error rate < 0.1%

### Serving Options

| Option | Latency | Use Case |
|--------|---------|----------|
| FastAPI + Uvicorn | Low | REST APIs, small models |
| Triton Inference Server | Very Low | GPU inference, batching |
| Ray Serve | Medium | Complex pipelines, multi-model |

## MLOps Pipeline Setup

Establish automated training and deployment:

1. Configure feature store (Feast, Tecton) for training data
2. Set up experiment tracking (MLflow, Weights & Biases)
3. Create training pipeline with hyperparameter logging
4. Register model in model registry with version metadata
5. Configure staging deployment triggered by registry events
6. Set up A/B testing infrastructure for model comparison
7. Enable drift monitoring with alerting
8. **Validation:** New models automatically evaluated against baseline

### Retraining Triggers

| Trigger | Detection | Action |
|---------|-----------|--------|
| Scheduled | Cron (weekly/monthly) | Full retrain |
| Performance drop | Accuracy < threshold | Immediate retrain |
| Data drift | PSI > 0.2 | Evaluate, then retrain |
| New data volume | X new samples | Incremental update |

## LLM Integration Workflow

Integrate LLM APIs into production applications:

1. Provider abstraction layer + retry with exponential backoff (tenacity)
2. Fallback to secondary provider on failure
3. Token counting, context truncation, response caching
4. Cost tracking per request + structured output validation (Pydantic)
5. **Validation:** Response parses correctly, cost within budget

### Provider Abstraction

```python
from abc import ABC, abstractmethod
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, **kwargs) -> str:
        pass

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def call_llm_with_retry(provider: LLMProvider, prompt: str) -> str:
    return provider.complete(prompt)
```

### Cost Management

| Provider | Input Cost | Output Cost |
|----------|------------|-------------|
| GPT-4o | $0.0025/1K | $0.01/1K |
| GPT-4o-mini | $0.00015/1K | $0.0006/1K |
| Claude 3.5 Sonnet | $0.003/1K | $0.015/1K |
| Claude 3.5 Haiku | $0.00025/1K | $0.00125/1K |

## RAG System Implementation

Build retrieval-augmented generation pipeline:

1. Choose vector DB + embedding model (quality/cost tradeoff)
2. Document chunking strategy + ingestion pipeline with metadata
3. Retrieval with query embedding + reranking for relevance
4. Format context and send to LLM
5. **Validation:** Response references retrieved context, no hallucinations

### Vector Database Selection

| Database | Hosting | Scale | Latency | Best For |
|----------|---------|-------|---------|----------|
| Pinecone | Managed | High | Low | Production, managed |
| Qdrant | Both | High | Very Low | Performance-critical |
| Weaviate | Both | High | Low | Hybrid search |
| Chroma | Self-hosted | Medium | Low | Prototyping |
| pgvector | Self-hosted | Medium | Medium | Existing Postgres |

### Chunking Strategies

| Strategy | Chunk Size | Overlap | Best For |
|----------|------------|---------|----------|
| Fixed | 500-1000 tokens | 50-100 | General text |
| Sentence | 3-5 sentences | 1 sentence | Structured text |
| Semantic | Variable | Based on meaning | Research papers |
| Recursive | Hierarchical | Parent-child | Long documents |

## Model Monitoring

Monitor production models for drift and degradation:

1. Latency tracking (p50, p95, p99) + error rate alerting
2. Input data drift detection + prediction distribution shifts
3. Log ground truth, compare model versions with A/B metrics
4. Automated retraining triggers
5. **Validation:** Alerts fire before user-visible degradation

### Drift Detection

```python
from scipy.stats import ks_2samp

def detect_drift(reference, current, threshold=0.05):
    statistic, p_value = ks_2samp(reference, current)
    return {
        "drift_detected": p_value < threshold,
        "ks_statistic": statistic,
        "p_value": p_value
    }
```

---

## Reference Documentation

- `references/mlops_production_patterns.md` — deployment pipeline, feature store, drift detection, A/B testing, retraining
- `references/llm_integration_guide.md` — provider abstraction, retry/fallback, prompt templates, token optimization
- `references/rag_system_architecture.md` — RAG pipeline, vector DB comparison, chunking, embedding selection
