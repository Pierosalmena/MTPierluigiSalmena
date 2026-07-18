# 01 — Query pipeline (GraphRAG + LangGraph)

> **Step 1 of 3.** This folder builds/holds the index and runs the two query
> pipelines. Its answers are consumed by `01_correctness/` and
> `02_groundedness/`. See the [root README](../README.md) for the full run order.

This folder contains a fully indexed [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
corpus together with two [LangGraph](https://github.com/langchain-ai/langgraph)
pipelines that operate over it:

- **`workflow_basic_coordination.ipynb`** — Basic Search RAG (the **baseline**).
- **`workflow_drift_coordination.ipynb`** — DRIFT Search over the connected
  semantic representation (the **artifact**).

Both run across the two stages of the issue-to-resolution process
(classification and resolution) and the two ticket categories (CAT1, CAT2).

> **The index is already built.** The `output/` directory ships with the
> pre-computed parquet artefacts, so you do **not** need to re-run indexing to
> reproduce the queries. The only thing you must supply is an API key (see
> [Quick start](#quick-start)).

---

## Table of contents

1. [Folder layout](#folder-layout)
2. [Quick start (querying only)](#quick-start)
3. [Initialising GraphRAG from scratch](#initialising-graphrag-from-scratch)
4. [When a GraphRAG version bump forces a re-init](#version-bump)

---

## Folder layout

```
00_index_query/
├── .venv/                         Python virtual environment
├── .env                           API key (you create this — see Quick start)
├── settings.yaml                  GraphRAG configuration (already adapted, see below)
├── workflow_basic_coordination.ipynb   LangGraph pipeline — Basic mode (baseline)
├── workflow_drift_coordination.ipynb   LangGraph pipeline — DRIFT mode (artifact)
│
├── input/                         Ticket records + organisational material (TI-*.txt, blueprint_*.txt)
├── output/                        Pre-computed GraphRAG parquet artefacts (the built index)
├── cache/                         Cached LLM responses from the indexing runs
├── csv_parquet_form/              Parquet artefacts exported to CSV for inspection / downstream use
├── logs/                          Indexing and query logs
├── prompts/                       All indexing + query prompts, unchanged, as used for evaluation
│
├── QUERY_CAT1/                    Query set for category 1 (query1.txt … query6.txt)
├── QUERY_CAT2/                    Query set for category 2
│
├── RAGAS_Converter/               Statement/citation extraction for the groundedness metric
└── RESULTS/                       Saved run outputs (basic + drift, per category, per query)
```

### What each folder holds

| Folder | Contents |
|--------|----------|
| `cache/` | Cache files from the indexing runs (LLM call cache per workflow stage). |
| `csv_parquet_form/` | The parquet artefacts transformed into CSV — inspectable, and reused downstream in the groundedness and correctness evaluations. |
| `input/` | The ticket records and supporting organisational material fed into indexing. |
| `logs/` | Logs produced by the indexing and query runs. |
| `output/` | The parquet artefacts described in the Development phase (entities, relationships, communities, community_reports, text_units, documents, plus `lancedb/`). |
| `prompts/` | Every prompt used for querying and indexing — unchanged, exactly as used for the evaluation. |
| `QUERY_CAT1/`, `QUERY_CAT2/` | The query sets for each ticket category. |
| `RAGAS_Converter/` | Converts each `answer.txt` into per-statement CSV rows with their extracted citations. It lives here because it needs to read the citations back against the `output/` parquet files. Its own use is documented in [`02_groundedness/README.md`](../02_groundedness/README.md). |
| `RESULTS/` | All saved results from the basic and drift runs. |
| `settings.yaml` | The complete GraphRAG configuration. |

---

## Quick start

You only need this section to **reproduce the queries** — the index is already built.

### 1. Create the `.env` file

In this folder (`00_index_query/`), create a file named `.env` containing a
single key/value pair:

```dotenv
GRAPHRAG_API_KEY=your-key-here
```

### 2. Activate the environment

```bash
# from 00_index_query/
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

If the shipped `.venv` does not work on your machine, recreate it:

```bash
python -m venv .venv
source .venv/bin/activate
pip install graphrag langgraph pandas   # + any imports the notebooks report as missing
```

### 3. Run the pipelines

Open and run, top to bottom:

- `workflow_basic_coordination.ipynb` — baseline (Basic Search)
- `workflow_drift_coordination.ipynb` — artifact (DRIFT Search)

Each notebook reads the built index from `output/`, the queries from
`QUERY_CAT1/` and `QUERY_CAT2/`, and the prompts from `prompts/`. Nothing else
needs configuring for querying.

The answers these notebooks produce are the input to the two evaluation
harnesses (`01_correctness/`, `02_groundedness/`).

---

## Initialising GraphRAG from scratch

You do **not** need to do this to reproduce the thesis — it is only relevant if
you want to rebuild the index on new data, or if a GraphRAG version change
regenerates the configuration (see the [next section](#version-bump)).

1. **Install GraphRAG** into the environment:

   ```bash
   pip install graphrag
   ```

2. **Initialise a workspace.** From this folder, run:

   ```bash
   graphrag init --root .
   ```

   This generates a fresh `settings.yaml`, a `.env` stub, and the default
   `prompts/` folder.

3. **Provide the API key** in `.env`:

   ```dotenv
   GRAPHRAG_API_KEY=your-key-here
   ```

4. **Place the corpus** in `input/` (ticket records + organisational material).

5. **Apply the thesis configuration.** The `settings.yaml` in this folder already
   contains every change made during the Development phase (model choices,
   chunking, search modes including DRIFT, community settings, etc.). After a
   fresh `graphrag init`, do **not** keep the default file — reconcile it against
   the shipped `settings.yaml` so the same settings are in force.

6. **Build the index:**

   ```bash
   graphrag index --root .
   ```

   This regenerates everything in `output/` (and `cache/`, `logs/`).

---

## <a id="version-bump"></a>When a GraphRAG version bump forces a re-init

The shipped `settings.yaml` already encodes all the changes required by the
Development phase, so under the **same** GraphRAG version you can use it as-is.

However, a new Microsoft GraphRAG release can rename, add, or restructure
settings keys. When that happens, GraphRAG may refuse to run against the old
file, and you will have to regenerate the configuration:

```bash
graphrag init --root .        # writes a fresh settings.yaml for the new version
```

The freshly generated file will use the **new version's defaults**. You then have
to re-apply the Development-phase settings on top of it — matching what the
thesis describes — rather than blindly copying the old `settings.yaml` over
(some keys may no longer exist or may have moved). Treat the shipped
`settings.yaml` as the **specification of intended settings**, and port those
choices into the new file key by key.

> Practical tip: keep the shipped `settings.yaml` under version control and diff
> it against the newly generated one so you can see exactly which keys changed.
