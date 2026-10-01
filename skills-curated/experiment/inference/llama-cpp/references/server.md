# Server Deployment Guide

Production deployment of llama.cpp server with OpenAI-compatible API.

## Server Modes

### llama-server

```bash
# Basic server
./llama-server \
    -m models/llama-2-7b-chat.Q4_K_M.gguf \
    --host 0.0.0.0 \
    --port 8080 \
    -c 4096  # Context size

# With GPU acceleration
./llama-server \
    -m models/llama-2-70b.Q4_K_M.gguf \
    -ngl 40  # Offload 40 layers to GPU
```

## OpenAI-Compatible API

### Chat completions
```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-2",
    "messages": [
      {"role": "system", "content": "You are helpful"},
      {"role": "user", "content": "Hello"}
    ],
    "temperature": 0.7,
    "max_tokens": 100
  }'
```

### Streaming
```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-2",
    "messages": [{"role": "user", "content": "Count to 10"}],
    "stream": true
  }'
```

## Monitoring

```bash
# Server metrics endpoint
curl http://localhost:8080/metrics

# Health check
curl http://localhost:8080/health
```

**Metrics**:
- requests_total
- tokens_generated
- prompt_tokens
- completion_tokens
- kv_cache_tokens

## Performance Tuning

**Parallel requests**:
```bash
./llama-server \
    -m model.gguf \
    -np 4  # 4 parallel slots
```

**Continuous batching**:
```bash
./llama-server \
    -m model.gguf \
    --cont-batching  # Enable continuous batching
```

**Context caching**:
```bash
./llama-server \
    -m model.gguf \
    --cache-prompt  # Cache processed prompts
```
