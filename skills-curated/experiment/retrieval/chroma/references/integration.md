# Chroma Integration Guide

Integration with LlamaIndex.

## LlamaIndex

```python
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

db = chromadb.PersistentClient(path="./chroma_db")
collection = db.get_or_create_collection("docs")

vector_store = ChromaVectorStore(chroma_collection=collection)
```

## Resources

- **Docs**: https://docs.trychroma.com
