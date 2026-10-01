# Production Serving Guide

Comprehensive guide to deploying TensorRT-LLM in production environments.

## Server Modes

### trtllm-serve (Recommended)

**Features**:
- OpenAI-compatible API
- Automatic model download and compilation
- Built-in load balancing
- Prometheus metrics
- Health checks

**Basic usage**:
```bash
trtllm-serve meta-llama/Meta-Llama-3-8B \
    --tp_size 1 \
    --max_batch_size 256 \
    --port 8000
```

**Advanced configuration**:
```bash
trtllm-serve meta-llama/Meta-Llama-3-70B \
    --tp_size 4 \
    --dtype fp8 \
    --max_batch_size 256 \
    --max_num_tokens 4096 \
    --enable_chunked_context \
    --scheduler_policy max_utilization \
    --port 8000
```

### Python LLM API (For embedding)

```python
from tensorrt_llm import LLM

class LLMService:
    def __init__(self):
        self.llm = LLM(
            model="meta-llama/Meta-Llama-3-8B",
            dtype="fp8"
        )

    def generate(self, prompt, max_tokens=100):
        from tensorrt_llm import SamplingParams

        params = SamplingParams(
            max_tokens=max_tokens,
            temperature=0.7
        )
        outputs = self.llm.generate([prompt], params)
        return outputs[0].text

# Use in FastAPI, Flask, etc
from fastapi import FastAPI
app = FastAPI()
service = LLMService()

@app.post("/generate")
def generate(prompt: str):
    return {"response": service.generate(prompt)}
```

## OpenAI-Compatible API

### Chat Completions

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Meta-Llama-3-8B",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain quantum computing"}
    ],
    "temperature": 0.7,
    "max_tokens": 500,
    "stream": false
  }'
```

**Response**:
```json
{
  "id": "chat-abc123",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "meta-llama/Meta-Llama-3-8B",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Quantum computing is..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 150,
    "total_tokens": 175
  }
}
```

### Streaming

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Meta-Llama-3-8B",
    "messages": [{"role": "user", "content": "Count to 10"}],
    "stream": true
  }'
```

**Response** (SSE stream):
```
data: {"choices":[{"delta":{"content":"1"}}]}

data: {"choices":[{"delta":{"content":", 2"}}]}

data: {"choices":[{"delta":{"content":", 3"}}]}

data: [DONE]
```

### Completions

```bash
curl -X POST http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Meta-Llama-3-8B",
    "prompt": "The capital of France is",
    "max_tokens": 10,
    "temperature": 0.0
  }'
```

## Monitoring

### Prometheus Metrics

**Enable metrics**:
```bash
trtllm-serve meta-llama/Meta-Llama-3-8B \
    --enable_metrics \
    --metrics_port 9090
```

**Key metrics**:
```bash
# Scrape metrics
curl http://localhost:9090/metrics

# Important metrics:
# - trtllm_request_success_total - Total successful requests
# - trtllm_request_latency_seconds - Request latency histogram
# - trtllm_tokens_generated_total - Total tokens generated
# - trtllm_active_requests - Current active requests
# - trtllm_queue_size - Requests waiting in queue
# - trtllm_gpu_memory_usage_bytes - GPU memory usage
# - trtllm_kv_cache_usage_ratio - KV cache utilization
```

### Health Checks

```bash
# Readiness probe
curl http://localhost:8000/health/ready

# Liveness probe
curl http://localhost:8000/health/live

# Model info
curl http://localhost:8000/v1/models
```

## Cost Optimization

### GPU Selection

**A100 80GB** ($3-4/hour):
- Use for: 70B models with FP8
- Throughput: 10,000-15,000 tok/s (TP=4)
- Cost per 1M tokens: $0.20-0.30

**H100 80GB** ($6-8/hour):
- Use for: 70B models with FP8, 405B models
- Throughput: 20,000-30,000 tok/s (TP=4)
- Cost per 1M tokens: $0.15-0.25 (2× faster = lower cost)

**L4** ($0.50-1/hour):
- Use for: 7-8B models
- Throughput: 1,000-2,000 tok/s
- Cost per 1M tokens: $0.25-0.50

### Batch Size Tuning

**Impact on cost**:
- Batch size 1: 1,000 tok/s → $3/hour per 1M = $3/M tokens
- Batch size 64: 5,000 tok/s → $3/hour per 5M = $0.60/M tokens
- **5× cost reduction** with batching

**Recommendation**: Target batch size 32-128 for cost efficiency.

## Troubleshooting

### High latency

**Diagnosis**:
```bash
# Check queue size
curl http://localhost:9090/metrics | grep queue_size

# Check active requests
curl http://localhost:9090/metrics | grep active_requests
```

**Solutions**:
- Scale horizontally (more replicas)
- Increase batch size (if GPU underutilized)
- Enable chunked context (if long prompts)
- Use FP8 quantization

### OOM crashes

**Solutions**:
- Reduce `max_batch_size`
- Reduce `max_num_tokens`
- Enable FP8 or INT4 quantization
- Increase `tensor_parallel_size`

## Best Practices

1. **Use FP8 on H100** for 2× speedup and 50% cost reduction
2. **Monitor metrics** - Set up Prometheus + Grafana
3. **Set readiness probes** - Prevent routing to unhealthy pods
4. **Use load balancing** - Distribute load across replicas
5. **Tune batch size** - Balance latency and throughput
6. **Enable streaming** - Better UX for chat applications
7. **Set up autoscaling** - Handle traffic spikes
8. **Use persistent volumes** - Cache compiled models
9. **Implement retries** - Handle transient failures
10. **Monitor costs** - Track cost per token
