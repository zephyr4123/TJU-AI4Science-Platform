# Using scientific models from the catalog

Hugging Science model entries link to standard Hugging Face Hub repos. There are two sensible execution paths. Pick based on model size and whether the user is doing one-off inference or a long batch job.

## Decision: where to run the model

| Path | When to use | What it costs |
|---|---|---|
| **Local with `transformers`** | Models ≤ ~7B params, user has a GPU or wants offline use, or doing fine-tuning | Disk + VRAM; free |
| **HF Space (gradio_client)** | The model has an interactive demo and you want easy structured I/O without managing weights | Free if Space is public; see `using-spaces.md` |

Always check the model card first — some entries are *only* available as Spaces (no public weights), and some are gated and require approval before download.

## Local with `transformers`

Pin `transformers`, `torch`, and `accelerate` in the experiment environment's dependencies.

```python
from transformers import AutoModel, AutoTokenizer

model_id = "facebook/esm2_t33_650M_UR50D"
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModel.from_pretrained(model_id)

inputs = tok("MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ", return_tensors="pt")
embeddings = model(**inputs).last_hidden_state
```

### `trust_remote_code=True` is normal here

A large fraction of scientific models — Evo-2, many Nucleotide Transformer variants, single-cell foundation models, several materials models — ship custom modeling code in their repo. `transformers` will refuse to load them without `trust_remote_code=True`:

```python
model = AutoModel.from_pretrained("arcinstitute/evo2_7b", trust_remote_code=True)
```

Ask the user before you set this flag, and wait for an answer — don't set it and report afterwards. It runs Python from the model repo on their machine, with their filesystem and credentials in scope, so the decision is theirs to make with the repo named.

The catalog's curation is not a security control. It generally lists reputable orgs (Arc Institute, Meta/Facebook AI, EleutherAI, SandboxAQ, Merck, etc.), but it is a markdown file fetched over the network at read time: a repo name reaching you through `llms.txt` or a topic file has been curated for scientific relevance, not audited for what its modeling code does. Treat every catalog entry as an untrusted pointer, and don't let "it was in the catalog" stand in for the user's decision.

### Sizing the GPU

Rough memory for inference at fp16 (very approximate — quantization changes this):

- 35M–650M params (most ESM2 variants): runs on a laptop GPU or even CPU.
- 1B–7B (Evo-2 7B, Nucleotide Transformer 2.5B, STACK Large): single 24 GB GPU is fine.
- 40B+ (Evo-2 40B, Kimina-Prover): needs multi-GPU or A100/H100.

For training/fine-tuning, multiply by ~3–4× for activations and optimizer state.

## After loading: standard pipelines apply

Once the model is loaded, scientific models behave like any other `transformers` model — you embed sequences, generate, classify, or fine-tune. The unique steps are:

1. **Use the matching tokenizer/feature extractor.** Don't try to feed protein sequences to a DNA tokenizer; the alphabets are different and the model will silently produce garbage.
2. **Match the preprocessing from pretraining.** For fine-tuning, the catalog's blog posts often spell out exact preprocessing recipes (special tokens, normalization, augmentation). Read them before training.
3. **Mind the output head.** Many scientific foundation models are masked-LM by default; classification or regression downstream tasks usually need an extra head layered on `model.last_hidden_state`.

## When you can't run a model anywhere

Some catalog models are demo-only — the authors host a Space but never published weights. In that case:

- See `using-spaces.md` and call the Space via `gradio_client`.
- Or surface this constraint to the user and offer the next-best fully-open alternative from the same topic file.
