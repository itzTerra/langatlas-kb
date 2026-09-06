# D22 verdict — source-corpus

- model: **qwen3-embedding-4b** (2560-dim)
- index type: hnsw-halfvec-cosine
- retrieval mode: hybrid
- reranker default-on: True
- chunking: target 400 / max 550 tokens
- incumbent was: qwen3-embedding-4b
- configuration moved: True
- pilot: rust-fls, rust-reference, scott-plp, sebesta-copl (37 queries scored)

## Why

- incumbent qwen3-embedding-4b stays at 67.6 pts Recall@5; best challenger nomic-embed-text-v1.5 reached 62.2, short of the 5-point bar, and no local model came within 2
- reranker adds +11.6 pts nDCG@10 on qwen3-embedding-4b — stays default-on
- hybrid adds +13.5 pts Recall@5 over vector-only on qwen3-embedding-4b — stays hybrid
- chunking at 400 tokens gained +2.7 pts Recall@5, clearing the 2-point bar

Recall figures come from a 4-source pilot: the distractor pool is a fraction of production's, so they are comparative between arms, not absolute predictions of production recall.

# D22 source-corpus benchmark

Pilot: rust-fls, rust-reference, scott-plp, sebesta-copl

| arm | R@5 | R@50 | nDCG@10 | MRR | p50 ms | chunks/s | MB | truncated | notes |
|---|---|---|---|---|---|---|---|---|---|
| local-baai-bge-small-en-v1-5__hybrid-rerank__c600 | 54.1 | 56.8 | 49.5 | 48.0 | 35 | 350054.7 | 10.5 | 0% | 15 queries out of corpus |
| local-baai-bge-small-en-v1-5__hybrid__c600 | 43.2 | 56.8 | 41.2 | 39.3 | 5 | 374057.2 | 10.5 | 0% | 15 queries out of corpus |
| local-baai-bge-small-en-v1-5__vector__c600 | 35.1 | 54.1 | 33.1 | 30.6 | 51 | 2.1 | 10.5 | 44% | 15 queries out of corpus |
| multilingual-e5-large-instruct__hybrid-rerank__c600 | 51.4 | 54.1 | 50.1 | 49.1 | 18372 | 470555.7 | 30.7 | 0% | 15 queries out of corpus |
| multilingual-e5-large-instruct__hybrid__c600 | 40.5 | 54.1 | 34.8 | 32.6 | 7 | 564870.1 | 30.7 | 0% | 15 queries out of corpus |
| multilingual-e5-large-instruct__vector__c600 | 27.0 | 43.2 | 27.0 | 26.0 | 148 | 46.8 | 30.7 | 51% | 15 queries out of corpus |
| mxbai-embed-large-latest__hybrid-rerank__c600 | 54.1 | 56.8 | 49.4 | 47.9 | 18554 | 652532.3 | 30.7 | 0% | 15 queries out of corpus |
| mxbai-embed-large-latest__hybrid__c600 | 43.2 | 56.8 | 41.2 | 38.3 | 5 | 561395.3 | 30.7 | 0% | 15 queries out of corpus |
| mxbai-embed-large-latest__vector__c600 | 32.4 | 54.1 | 31.5 | 28.5 | 109 | 71.3 | 30.7 | 51% | 15 queries out of corpus |
| nomic-embed-text-v1-5__hybrid-rerank__c600 | 62.2 | 67.6 | 56.1 | 54.2 | 17851 | 599169.1 | 23.1 | 0% | 15 queries out of corpus |
| nomic-embed-text-v1-5__hybrid__c600 | 51.4 | 67.6 | 47.0 | 44.5 | 6 | 463023.0 | 23.1 | 0% | 15 queries out of corpus |
| nomic-embed-text-v1-5__vector__c600 | 43.2 | 62.2 | 40.9 | 39.3 | 104 | 89.1 | 23.1 | 0% | 15 queries out of corpus |
| nomic-embed-text-v2-moe__hybrid-rerank__c600 | 59.5 | 67.6 | 56.8 | 55.4 | 19124 | 489505.9 | 23.1 | 0% | 15 queries out of corpus |
| nomic-embed-text-v2-moe__hybrid__c600 | 45.9 | 67.6 | 43.9 | 40.4 | 6 | 570845.7 | 23.1 | 0% | 15 queries out of corpus |
| nomic-embed-text-v2-moe__vector__c600 | 40.5 | 64.9 | 36.2 | 32.9 | 91 | 449365.7 | 23.1 | 0% | 15 queries out of corpus |
| qwen3-embedding-4b__hybrid-rerank__c400 | 70.3 | 86.5 | 71.7 | 57.4 | 16911 | 30.6 | 97.0 | 0% | cache-warm throughput; 15 queries out of corpus |
| qwen3-embedding-4b__hybrid-rerank__c600 | 67.6 | 78.4 | 59.0 | 54.7 | 21145 | 334969.0 | 75.8 | 0% | 15 queries out of corpus |
| qwen3-embedding-4b__hybrid-rerank__c800 | 64.9 | 81.1 | 64.0 | 56.3 | 17651 | 30.9 | 66.7 | 0% | cache-warm throughput; 15 queries out of corpus |
| qwen3-embedding-4b__hybrid__c600 | 54.1 | 78.4 | 47.4 | 43.4 | 96 | 669725.1 | 75.7 | 0% | 15 queries out of corpus |
| qwen3-embedding-4b__vector__c600 | 40.5 | 75.7 | 40.1 | 35.9 | 89 | 206.5 | 75.7 | 0% | cache-warm throughput; 15 queries out of corpus |
