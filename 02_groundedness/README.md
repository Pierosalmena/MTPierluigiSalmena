# 03 — Groundedness (RAGAS)

> **Step 3 of 3** (independent of `01_correctness/`; both consume the answers
> from `00_index_query/`). See the [root README](../README.md) for the full
> run order.

This harness scores **groundedness** with RAGAS: each generated answer is split
into statements, each statement is paired with the citations it makes back to
the GraphRAG index, and RAGAS judges whether the cited evidence supports the
statement.

All paths below are relative to this folder's own root.

---

## Inputs

This step consumes the answers produced by the two workflow notebooks in
`00_index_query/`. The statement/citation extraction relies on the
`RAGAS_Converter/` tool, which reads citations back against the parquet
artefacts in `00_index_query/output/`.

---

## Steps

The steps below are described exactly as they were run for the thesis. They
involve some manual copying between folders; this is intentional (see
[Notes on automation](#notes-on-automation)).

### 1. Collect the answers

After running `workflow_basic` / `workflow_drift`, copy each generated answer
into the `answer.txt` files for the matching category **and** mode under
`RAGAS_Converter/`:

```
RAGAS_Converter/<classification|resolution>/<BASIC|DRIFT>/<CAT1|CAT2>/answers/
```

All `.txt` answers for that cell go into this `answers/` folder.

### 2. Convert answers → statement/citation CSVs

You do not have to run each folder by hand — the launcher runs them all:

```bash
# from RAGAS_Converter/
python launcher.py
```

`launcher.py` walks `<classification|resolution>/<BASIC|DRIFT>/<CAT1|CAT2>/` and
runs `trace_ragas_allv3.py` inside each, with that folder as the working
directory so the relative paths (`./answers`, `./trace_exports`) resolve. Each
answer `.txt` is split **line by line into statements**, and each statement is
paired with the citations extracted from the GraphRAG parquet files. Results are
written to that folder's `trace_exports/` as both `.csv` and `.json`.

> Run a single folder instead: within it, `python trace_ragas_allv3.py`.

### 3. Move the CSVs into the groundedness datasets

Copy the generated `trace_exports/*.csv` into the corresponding dataset folder:

```
classification_dataset/     (or resolution_dataset/)
  dataset_CAT1_BASIC_Classification/
  dataset_CAT1_DRIFT_Classification/
  dataset_CAT2_BASIC_Classification/
  dataset_CAT2_DRIFT_Classification/
```

Each dataset is the **six** files for that (category, mode) cell.

### 4. Run the evaluation, one dataset at a time

In `rag_eval/`, place the current dataset into `evals/datasets/`, then run:

```bash
# from rag_eval/
python evals.py
```

Repeat dataset by dataset.

---

## Notes on automation

This pipeline deliberately keeps a few **manual copy steps** (moving
`trace_exports/` CSVs into the `dataset_*` folders, staging one dataset at a time
into `evals/datasets/`). These are the exact steps used to produce the thesis
results, so the pipeline is documented as it was actually run.

Some of this could be automated (e.g. a script that copies `trace_exports/`
outputs straight into the right `dataset_*` folder, or a runner that stages and
evaluates each dataset in turn). That is an **optional future improvement**, not
a requirement: the current process is reproducible as-is, and the manual
boundaries make it easy to inspect intermediate artefacts and stop if something
looks wrong. If you automate later, do it one hop at a time and diff the outputs
against a known-good run before trusting it.


I SHOULD ADD HERE THAT DATASETS NEED TO BE PLACED SINGULARLY MEANING THE 6 FILES WITHIN THE DATASET FOLDER
ALSO THE RESULT OF ARE IN THE EXPERIMENTS