# API Evaluation

Guide to evaluating models served behind a local OpenAI-compatible API (vLLM, llama.cpp server).

## Overview

The lm-evaluation-harness supports evaluating API-based models through a unified `TemplateAPI` interface. Many local inference servers expose OpenAI-compatible APIs, so a model you serve yourself can be benchmarked through the `local-completions` model type.

## Supported API Models

| Provider | Model Type | Request Types | Logprobs |
|----------|------------|---------------|----------|
| Local (OpenAI-compatible) | `local-completions` | Depends on server | Varies |

**Note**: Models without logprobs can only be evaluated on generation tasks, not perplexity or loglikelihood tasks.

### Configuration Options

```bash
lm_eval --model local-completions \
  --model_args \
    model=meta-llama/Llama-2-7b-hf,\
    base_url=http://localhost:8000/v1,\
    num_concurrent=5,\
    max_retries=3,\
    timeout=60
```

**Parameters**:
- `model`: Model identifier (required)
- `base_url`: API endpoint of the local server
- `num_concurrent`: Concurrent requests (default: 5)
- `max_retries`: Retry failed requests (default: 3)
- `timeout`: Request timeout in seconds (default: 60)
- `tokenizer`: Tokenizer to use (default: matches model)
- `tokenizer_backend`: `"tiktoken"` or `"huggingface"`

## Local OpenAI-Compatible APIs

Many local inference servers expose OpenAI-compatible APIs (vLLM, llama.cpp).

### vLLM Local Server

**Start server**:
```bash
vllm serve meta-llama/Llama-2-7b-hf \
  --host 0.0.0.0 \
  --port 8000
```

**Evaluate**:
```bash
lm_eval --model local-completions \
  --model_args \
    model=meta-llama/Llama-2-7b-hf,\
    base_url=http://localhost:8000/v1,\
    num_concurrent=1 \
  --tasks mmlu,gsm8k \
  --batch_size auto
```

### llama.cpp Server

**Start server**:
```bash
./server -m models/llama-2-7b.gguf --host 0.0.0.0 --port 8080
```

**Evaluate**:
```bash
lm_eval --model local-completions \
  --model_args \
    model=llama2,\
    base_url=http://localhost:8080/v1 \
  --tasks gsm8k
```

## Best Practices

### Reproducibility

Set temperature to 0 for deterministic results:
```bash
lm_eval --model local-completions \
  --model_args model=meta-llama/Llama-2-7b-hf,base_url=http://localhost:8000/v1 \
  --tasks mmlu \
  --gen_kwargs temperature=0.0
```

## Troubleshooting

### "Timeout error"

Increase timeout:
```bash
--model_args timeout=180
```

### "Model not found"

For local APIs, verify server is running:
```bash
curl http://localhost:8000/v1/models
```

## Advanced Features

### Disable SSL Verification (Development Only)

```bash
lm_eval --model local-completions \
  --model_args \
    base_url=https://localhost:8000/v1,\
    verify_certificate=false
```

### Custom Tokenizer

```bash
lm_eval --model local-completions \
  --model_args \
    model=meta-llama/Llama-2-7b-hf,\
    base_url=http://localhost:8000/v1,\
    tokenizer=gpt2,\
    tokenizer_backend=huggingface
```

## References

- TemplateAPI: `lm_eval/models/api_models.py`
- Local completions: `lm_eval/models/openai_completions.py`
