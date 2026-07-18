# 02 — Correctness (BenchmarkQED assertion tests)

> **Step 2 of 3** (independent of `02_groundedness/`; both consume the answers
> from `00_index_query/`). See the [root README](../README.md) for the full
> run order.

This harness scores **correctness** with
[BenchmarkQED / AutoE](https://github.com/microsoft/benchmark-qed) assertion
tests: each generated answer is re-analysed against the assertion set for its
question, per category and per mode.

There are two stages — first convert the answers into `activity_*.json`, then run
the assertion harness over them. All paths below are relative to this folder's
own root.

---

## Inputs

This step consumes the answers produced by the two workflow notebooks in
`00_index_query/`.

Throughout this folder, the two modes are named:

- **`graphrag`** = DRIFT Search = the **artifact**
- **`vector_rag`** / **`rag`** = Basic Search = the **baseline**

---

## Stage 1 — Convert answers to `activity_*.json`

### 1. Collect the answers

Copy the answer `.txt` files into the matching category and mode folder under:

```
ASSERTIONS_converter/<Classification|Resolution>/converter_cat<1|2>_<rag|graphrag>/
```

### 2. Run the converter launcher

```bash
# from ASSERTIONS_converter/Classification/  (or Resolution/)
python run_all_converters.py
```

It scans every sibling subfolder, and for each one containing
`add_answers_to_activity.py` it runs that script with the subfolder as the
working directory, so each script finds its own local `activity_cat*.json` and
`classification_answer*.txt` via relative paths. Each answer is folded into an
`activity_cat<1|2>.json` file that stores the answers under a per-question
identifier (e.g. `TI-EVAL-cat1-01`) — the shape the assertion harness expects.

> Useful flags:
> `--only cat1_rag` runs a single folder;
> `--stop-on-error` halts at the first failure.

---

## Stage 2 — Run the assertion tests (BenchmarkQED / AutoE)

The assertion harness lives in a separate per-stage folder:

```
local_classification/assertion_test/     (and local_resolution/assertion_test/)
├── input/
│   ├── graphrag/      activity_cat1.json, activity_cat2.json   (DRIFT/artifact answers)
│   ├── vector_rag/    activity_cat1.json, activity_cat2.json   (Basic/baseline answers)
│   ├── activity_cat1_assertions.json    (the CAT1 assertion set)
│   └── activity_cat2_assertions.json    (the CAT2 assertion set)
├── output/            results land here
├── prompts/           assertion_user_prompt.txt, assertion_system_prompt.txt
├── .env
├── settings_graphrag_cat1.yaml
├── settings_graphrag_cat2.yaml
├── settings_rag_cat1.yaml
└── settings_rag_cat2.yaml
```

### 1. Place the converted answers

Take the `activity_cat1.json` / `activity_cat2.json` produced in Stage 1 and drop
each into the matching mode subfolder of the correct stage:

- classification answers → `local_classification/assertion_test/input/<graphrag|vector_rag>/`
- resolution answers → `local_resolution/assertion_test/input/<graphrag|vector_rag>/`

`graphrag/` holds the DRIFT/artifact answers; `vector_rag/` holds the
Basic/baseline answers. The assertion sets
(`activity_cat<1|2>_assertions.json`) already sit in `input/` and are shared
across both modes.

### 2. Run one settings file per (mode, category)

Each `settings_*.yaml` points at its answer file
(`generated.answer_base_path`) and its assertion set
(`assertions.assertions_path`), and runs the answers back against the assertions
with the BenchmarkQED assertion scorer. There are four runs per stage:

| Settings file | Mode | Category | Reads |
|---|---|---|---|
| `settings_graphrag_cat1.yaml` | DRIFT/artifact | CAT1 | `input/graphrag/activity_cat1.json` |
| `settings_graphrag_cat2.yaml` | DRIFT/artifact | CAT2 | `input/graphrag/activity_cat2.json` |
| `settings_rag_cat1.yaml` | Basic/baseline | CAT1 | `input/vector_rag/activity_cat1.json` |
| `settings_rag_cat2.yaml` | Basic/baseline | CAT2 | `input/vector_rag/activity_cat2.json` |

Do the same four in `local_resolution/assertion_test/`. Results are written to
`output/`.

Each run uses `gpt-5-mini` at `temperature: 1`, `trials: 4`, and a
`pass_threshold` of `0.5` (an assertion counts as passed when its score exceeds
the threshold). Provide the model key via the `.env` in that folder
(`OPENAI_API_KEY`, referenced by the settings as `${OPENAI_API_KEY}`).
