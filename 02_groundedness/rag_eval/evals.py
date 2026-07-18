import os
import sys
from pathlib import Path
import pandas as pd

from openai import AsyncOpenAI
from ragas import Dataset, experiment
from ragas.llms import llm_factory
from ragas.metrics import DiscreteMetric

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
llm = llm_factory(
    "gpt-5-mini",
    client=openai_client,
    max_tokens=16000,
)

DATASETS_DIR = Path("evals") / "datasets"
CSV_GLOB = "*.csv"


def load_dataset(csv_path: Path) -> Dataset:
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    dataset = Dataset(name=csv_path.stem, backend="inmemory")
    for _, r in df.iterrows():
        dataset.append({
            "question": r["question"],
            "answer": r["answer"],
            "context": r["context"],
        })
    return dataset


# ===== Pass 1: recommendation detection (binary, statement only) =====
recommendation_metric = DiscreteMetric(
    name="is_recommendation",
    allowed_values=["yes", "no"],
    prompt=(
        "Decide whether the STATEMENT contains a recommendation, suggestion, "
        "or forward-looking advice.\n\n"
        "Answer 'yes' if the STATEMENT:\n"
        "- Has explicit markers like '(RECOMMENDED)' or '[Recommendation]'\n"
        "- Uses prose framing like 'recommend that', 'suggest', 'consider', "
        "'recommended next steps', 'based on documented actions'\n"
        "- Uses directive verbs proposing an action: 'export', 'verify', "
        "'collect', 'ask X to', 'check', 'identify'\n"
        "- Frames conditional advice: 'if X then Y', 'should be done'\n"
        "- Explicitly notes extrapolation: 'these are recommendations because "
        "no direct precedent exists'\n\n"
        "Answer 'no' if the STATEMENT only reports what the records document, "
        "claims something happened in a prior case, or describes a corpus "
        "fact without proposing action.\n\n"
        "Give a short reason (1 sentence).\n\n"
        "STATEMENT: {answer}"
    ),
)


# ===== Pass 2: groundedness (3 labels, no special recommendation rule) =====
groundedness_metric = DiscreteMetric(
    name="groundedness",
    allowed_values=["supported", "partially_supported", "unsupported"],
    prompt=(
        "You are a strict evidence-checking judge. Determine whether the "
        "ANSWER is grounded in the CONTEXT. You do not evaluate correctness, "
        "relevance, or completeness — only groundedness.\n\n"
        "Labels:\n"
        "- supported: all claims in ANSWER are supported by CONTEXT\n"
        "- partially_supported: some claims supported, but at least one is "
        "missing, uncertain, or only partially traceable\n"
        "- unsupported: not supported by, or contradicted by, CONTEXT\n\n"
        "Interpretation rules:\n"
        "1. The CONTEXT may contain up to four labelled block types: "
        "CITED SOURCES (verbatim ticket text), CITED REPORTS (community "
        "summaries), CITED ENTITIES (graph node descriptions), and CITED "
        "RELATIONSHIPS (graph edge descriptions). Evidence in any block "
        "supports a claim equally.\n"
        "2. If the ANSWER claims that prior tickets, cases, or incidents "
        "used, contained, or relied on something, and the CONTEXT shows "
        "that thing being present in those prior cases, this counts as "
        "SUPPORTED — even if the CONTEXT does not explicitly recommend it. "
        "Historical resolution records are evidence of what was used, not "
        "procedural guides.\n"
        "3. Judge only the claims actually made in ANSWER. Do not penalise "
        "the ANSWER for omitting information that happens to be in the "
        "CONTEXT.\n"
        "4. If the ANSWER is a recommendation: evaluate whether the "
        "recommended action has corpus precedent in the CONTEXT. Grounded "
        "recommendations are supported. Recommendations extrapolating "
        "reasonably from precedent are partially_supported. Recommendations "
        "with no corpus precedent and where the CONTEXT does not back any "
        "part of the advice are unsupported.\n\n"
        "Give a short reason (1–2 sentences) pointing to what is missing or "
        "which part supports it.\n\n"
        "ANSWER: {answer}\n\n"
        "CONTEXT: {context}"
    ),
)


@experiment()
async def run_experiment(row):
    is_rec = await recommendation_metric.ascore(
        llm=llm,
        answer=row["answer"],
    )
    grounded = await groundedness_metric.ascore(
        llm=llm,
        answer=row["answer"],
        context=row["context"],
    )
    return {
        **row,
        "is_recommendation":   is_rec.value,
        "is_rec_reason":       is_rec.reason,
        "groundedness":        grounded.value,
        "groundedness_reason": grounded.reason,
    }


async def main():
    csv_files = sorted(DATASETS_DIR.glob(CSV_GLOB))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {DATASETS_DIR.resolve()}")

    out_dir = Path("evals") / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_outputs = []
    for csv_path in csv_files:
        dataset = load_dataset(csv_path)
        print(f"Loaded dataset '{csv_path.stem}' from {csv_path}")

        experiment_results = await run_experiment.arun(dataset)
        print(f"Experiment completed for: {csv_path.stem}")
        experiment_results.save()

        df_out = experiment_results.to_pandas()
        df_out.insert(0, "dataset", csv_path.stem)

        out_path = out_dir / f"{csv_path.stem}_results.csv"
        df_out.to_csv(out_path, index=False)
        print(f"Saved results to: {out_path.resolve()}")
        all_outputs.append(df_out)

    df_all = pd.concat(all_outputs, ignore_index=True)
    combined_path = out_dir / "ALL_DATASETS_results.csv"
    df_all.to_csv(combined_path, index=False)
    print(f"Saved combined results to: {combined_path.resolve()}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())