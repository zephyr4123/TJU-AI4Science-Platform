# nnsight Reference Documentation

This directory contains comprehensive reference materials for nnsight.

## Contents

- [api.md](api.md) - Complete API reference for LanguageModel, tracing, and proxy objects
- [tutorials.md](tutorials.md) - Step-by-step tutorials for local and remote interpretability

## Quick Links

- **Official Documentation**: https://nnsight.net/
- **GitHub Repository**: https://github.com/ndif-team/nnsight
- **NDIF (Remote Execution)**: https://ndif.us/
- **Community Forum**: https://discuss.ndif.us/
- **Paper**: https://arxiv.org/abs/2407.14561 (ICLR 2025)

## Installation

```bash
# Basic installation
pip install nnsight

# For vLLM support
pip install "nnsight[vllm]"
```

## Basic Usage

```python
from nnsight import LanguageModel

# Load model
model = LanguageModel("openai-community/gpt2", device_map="auto")

# Trace and access internals
with model.trace("The Eiffel Tower is in") as tracer:
    # Access layer output
    hidden = model.transformer.h[5].output[0].save()

    # Modify activations
    model.transformer.h[8].output[0][:] *= 0.5

    # Get final output
    logits = model.output.save()

# Access saved values outside context
print(hidden.shape)
```

## Key Concepts

### Tracing
The `trace()` context enables deferred execution - operations are recorded and executed together.

### Proxy Objects
Inside trace, module accesses return Proxies. Call `.save()` to retrieve values after execution.
