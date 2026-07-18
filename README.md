# ITSM Issue-to-Resolution — GraphRAG Artifact

This repository accompanies the master's thesis *Connecting Organisational
Knowledge Across Ticket Classification and Resolution: Design and Evaluation of a
GraphRAG-Based Artifact for the ITSM Issue-to-Resolution Process*.

It contains a fully indexed [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
corpus, two [LangGraph](https://github.com/langchain-ai/langgraph) query pipelines
that operate over it, and the two evaluation harnesses used in the thesis.

- **Baseline** — Basic Search RAG.
- **Artifact** — DRIFT Search over the connected semantic representation.

Both pipelines run across the two stages of the issue-to-resolution process
(classification and resolution) and the two ticket categories (CAT1, CAT2).

---

## Repository map

```
.
├── 00_index_query/     The GraphRAG index + the two LangGraph query notebooks
├── 01_correctness/        Correctness evaluation (BenchmarkQED assertion tests)
└── 02_groundedness/       Groundedness evaluation (RAGAS)
```

Each folder is a self-contained tree with its own environment, its own `.env`,
and its own README. **Start with the README in the folder you need:**

- [`00_index_query/README.md`](00_index_query/README.md) — build/query the index, run the pipelines.
- [`01_correctness/README.md`](01_correctness/README.md) — score answers against assertion sets.
- [`02_groundedness/README.md`](02_groundedness/README.md) — score answers with RAGAS.

---

## End-to-end run order

The three folders form a chain — later steps consume the answers produced by the
first.

1. **`00_index_query/`** — run the two workflow notebooks
   (`workflow_basic_coordination.ipynb`, `workflow_drift_coordination.ipynb`).
   These produce the answers for both modes, both stages, both categories.
   The index is already built and ships with the repo, so you only need an API
   key to reproduce the queries.
2. **`01_correctness/`** — feed those answers through the assertion tests.
3. **`02_groundedness/`** — feed those answers through the RAGAS pipeline.

Steps 2 and 3 are independent of each other and can run in either order; both
depend on step 1.

---

## Reproducing the thesis results

The index in `00_index_query/output/` is pre-computed, so the whole thesis is
reproducible without re-indexing. The minimum path is: add an API key in
`00_index_query/.env`, run the two notebooks, then run the two evaluation
harnesses over the resulting answers. See each folder's README for the details.
