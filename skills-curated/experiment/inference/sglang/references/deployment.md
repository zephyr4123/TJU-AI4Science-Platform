# Production Deployment Guide

Complete guide to deploying SGLang in production environments.

## Server Deployment

### Basic server

```bash
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-8B-Instruct \
    --host 0.0.0.0 \
    --port 30000 \
    --mem-fraction-static 0.9
```

### Multi-GPU (Tensor Parallelism)

```bash
# Llama 3-70B on 4 GPUs
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-70B-Instruct \
    --tp 4 \
    --port 30000
```

### Quantization

```bash
# FP8 quantization (H100)
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-70B-Instruct \
    --quantization fp8 \
    --tp 4

# INT4 AWQ quantization
python -m sglang.launch_server \
    --model-path TheBloke/Llama-2-70B-AWQ \
    --quantization awq \
    --tp 2

# INT4 GPTQ quantization
python -m sglang.launch_server \
    --model-path TheBloke/Llama-2-70B-GPTQ \
    --quantization gptq \
    --tp 2
```

## Monitoring

### Health checks

```bash
# Health endpoint
curl http://localhost:30000/health

# Model info
curl http://localhost:30000/v1/models

# Server stats
curl http://localhost:30000/stats
```

### Prometheus metrics

```bash
# Start server with metrics
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-8B-Instruct \
    --enable-metrics

# Metrics endpoint
curl http://localhost:30000/metrics

# Key metrics:
# - sglang_request_total
# - sglang_request_duration_seconds
# - sglang_tokens_generated_total
# - sglang_active_requests
# - sglang_queue_size
# - sglang_radix_cache_hit_rate
# - sglang_gpu_memory_used_bytes
```

### Logging

```bash
# Enable debug logging
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-8B-Instruct \
    --log-level debug

# Log to file
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-8B-Instruct \
    --log-file /var/log/sglang.log
```

## Performance Tuning

### Memory optimization

```bash
# Reduce memory usage
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-70B-Instruct \
    --tp 4 \
    --mem-fraction-static 0.85 \  # Use 85% of GPU memory
    --max-radix-cache-len 8192    # Limit cache to 8K tokens
```

### Throughput optimization

```bash
# Maximize throughput
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-8B-Instruct \
    --mem-fraction-static 0.95 \  # More memory for batching
    --max-radix-cache-len 16384 \ # Larger cache
    --max-running-requests 256    # More concurrent requests
```

### Latency optimization

```bash
# Minimize latency
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-8B-Instruct \
    --max-running-requests 32 \   # Fewer concurrent (less queueing)
    --schedule-policy fcfs         # First-come first-served
```

## Multi-Node Deployment

### Ray cluster setup

```bash
# Head node
ray start --head --port=6379

# Worker nodes
ray start --address='head-node:6379'

# Launch server across cluster
python -m sglang.launch_server \
    --model-path meta-llama/Meta-Llama-3-405B-Instruct \
    --tp 8 \
    --num-nodes 2  # Use 2 nodes (8 GPUs each)
```

## Troubleshooting

### High memory usage

**Check**:
```bash
nvidia-smi
curl http://localhost:30000/stats | grep cache
```

**Solutions**:
```bash
# Reduce cache size
--max-radix-cache-len 4096

# Reduce memory fraction
--mem-fraction-static 0.75

# Enable quantization
--quantization fp8
```

### Low throughput

**Check**:
```bash
curl http://localhost:30000/stats | grep queue_size
```

**Solutions**:
```bash
# Increase batch size
--max-running-requests 256

# Add more GPUs
--tp 4  # Increase tensor parallelism

# Check cache hit rate (should be >70%)
curl http://localhost:30000/stats | grep cache_hit_rate
```

### High latency

**Check**:
```bash
curl http://localhost:30000/metrics | grep duration
```

**Solutions**:
```bash
# Reduce concurrent requests
--max-running-requests 32

# Use FCFS scheduling (no batching delay)
--schedule-policy fcfs

# Add more replicas (horizontal scaling)
```

### OOM errors

**Solutions**:
```bash
# Reduce batch size
--max-running-requests 128

# Reduce cache
--max-radix-cache-len 2048

# Enable quantization
--quantization awq

# Increase tensor parallelism
--tp 8
```

## Best Practices

1. **Use RadixAttention** - Enabled by default, 5-10× speedup for agents
2. **Monitor cache hit rate** - Target >70% for agent/few-shot workloads
3. **Set health checks** - Use `/health` endpoint for k8s probes
4. **Enable metrics** - Monitor with Prometheus + Grafana
5. **Use load balancing** - Distribute load across replicas
6. **Tune memory** - Start with `--mem-fraction-static 0.9`, adjust based on OOM
7. **Use quantization** - FP8 on H100, AWQ/GPTQ on A100
8. **Set up autoscaling** - Scale based on GPU utilization or active requests
9. **Log to persistent storage** - Use `--log-file` for debugging
10. **Test before production** - Run load tests with expected traffic patterns

## Cost Optimization

### GPU selection

**A100 80GB** ($3-4/hour):
- Llama 3-70B with FP8 (TP=4)
- Throughput: 10,000-15,000 tok/s
- Cost per 1M tokens: $0.20-0.30

**H100 80GB** ($6-8/hour):
- Llama 3-70B with FP8 (TP=4)
- Throughput: 20,000-30,000 tok/s
- Cost per 1M tokens: $0.15-0.25 (2× faster)

**L4** ($0.50-1/hour):
- Llama 3-8B
- Throughput: 1,500-2,500 tok/s
- Cost per 1M tokens: $0.20-0.40

### Batching for cost efficiency

**Low batch (batch=1)**:
- Throughput: 1,000 tok/s
- Cost: $3/hour ÷ 1M tok/hour = $3/M tokens

**High batch (batch=128)**:
- Throughput: 8,000 tok/s
- Cost: $3/hour ÷ 8M tok/hour = $0.375/M tokens
- **8× cost reduction**

**Recommendation**: Target batch size 64-256 for optimal cost/latency.
